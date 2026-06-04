"""
flare_forge — Professional single-tab dashboard.
Layout: Profile (left) + 2D Preview (right) | Flanges | Assembly Generation.
"""

import io, os, sys, tempfile, traceback
from pathlib import Path

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent / "src"))
import profile_generator as _core
import flange_generator as _fg
import rectangular_flange as _rf
import rectangular_horn as _rh
import radial_horn as _rd
import polygonal_horn as _ph
import _slicer as _slc
import throat_adapter as _ta
from _step_export import export_step

import importlib
importlib.reload(_core)
importlib.reload(_fg)
importlib.reload(_rf)
importlib.reload(_rh)
importlib.reload(_rd)
importlib.reload(_ph)
importlib.reload(_slc)
importlib.reload(_ta)

st.set_page_config(page_title="flare_forge", layout="wide",
    initial_sidebar_state="collapsed", menu_items={})

# ── Support link ─────────────────────────────────────────────────────
# Replace with your Buy Me a Coffee username; the button hides if left blank.
BMC_USERNAME = "steo_lab"
BMC_URL = f"https://buymeacoffee.com/{BMC_USERNAME}"

# ── Flange recalculation callback ────────────────────────────────────

def _on_horn_change():
    """Recalculate geometry-dependent flange defaults when horn changes."""
    for _k in ("ft_ring", "ft_bc", "ft_bc_rad", "ft_ow", "ft_oh",
               "fm_spess", "fm_ring", "fm_bc", "fm_ow", "fm_oh",
               "mid_ring", "mid_bc", "mid_ow", "mid_oh"):
        st.session_state.pop(_k, None)
    st.session_state.pop("_combined", None)

_hdr_l, _hdr_r = st.columns([5, 1])
with _hdr_l:
    st.title("flare_forge")
    st.caption("Acoustic profile + mounting flanges · watertight assembly for 3D printing")
with _hdr_r:
    if BMC_USERNAME and BMC_USERNAME != "your_username":
        st.link_button("☕ Buy me a coffee", BMC_URL, use_container_width=True)
    else:
        st.caption("☕ set BMC_USERNAME")

# ═══════════════════════════════════════════════════════════════════════
#  ROW 1 — Horn Profile (Left) + Live 2D Preview (Right)
# ═══════════════════════════════════════════════════════════════════════

col_prof, col_prev = st.columns([2, 3])

with col_prof:
    st.subheader("Acoustic Profile")

    # ── Shape — the two primary design choices ───────────────────────────
    sh1, sh2 = st.columns([2, 3])
    with sh1:
        profile_type = st.selectbox("Profile",
            ["Tractrix", "Salmon", "Iwata", "Le Cléac'h (isophase)", "Exponential"], index=0,
            on_change=_on_horn_change, key="profile_type")
    with sh2:
        section_type = st.radio("Section", ["Circular", "Polygonal", "Rectangular", "Radial 360°"],
                          index=0, horizontal=True, key="section_type",
                          on_change=_on_horn_change)

    is_radial   = section_type.startswith("Rad")
    is_poly     = section_type == "Polygonal"
    is_rect     = section_type == "Rectangular"
    is_tractrix = profile_type.startswith("Tract")
    is_salmon    = profile_type.startswith("Salmon")
    is_iwata    = profile_type.startswith("Iwata")
    is_lecleach = profile_type.startswith("Le Cl")
    is_exp      = profile_type.startswith("Exp")
    has_fc      = is_salmon or is_lecleach or is_exp
    is_T_variable = is_salmon or is_lecleach

    # Iwata is the real l'Audiophile horn: a fixed *rectangular* dual-flare
    # geometry digitized from the plan, driven only by throat size + length.
    # It always renders as a rectangular section, whatever the Section selector.
    if is_iwata:
        is_rect = True
        is_poly = is_radial = False
        st.caption("ℹ️ Iwata = fixed rectangular dual-flare horn (l'Audiophile plan) — "
                   "the Section selector is ignored.")

    # ── Section / flare modifiers — only those relevant to the current shape
    rect_ar, n_sides, salmon_T = 1.5, 4, 0.707
    _mods = (["ar"] if (is_rect and not is_iwata) else []) + (["sides"] if is_poly else []) \
            + (["T"] if is_T_variable else [])
    if _mods:
        _mcols = st.columns(len(_mods))
        for _mcol, _mk in zip(_mcols, _mods):
            with _mcol:
                if _mk == "ar":
                    rect_ar = st.number_input("Aspect ratio (W:H)", 1.0, 10.0, 1.5, 0.1,
                        key="rect_ar", help="Throat width / throat height")
                elif _mk == "sides":
                    n_sides = st.select_slider("Sides", options=list(range(3, 13)),
                        value=4, key="n_sides")
                elif _mk == "T":
                    salmon_T = st.number_input("Flare parameter T", 0.0, 10.0, 0.707, 0.01,
                        key="salmon_T", on_change=_on_horn_change,
                        help="Hornresp T: 0 = catenoidal · <1 = cosh · 1 = exponential · >1 = sinh")

    # ── Advanced settings — print params + the global speed of sound
    with st.expander("⚙️ Advanced settings"):
        _ps1, _ps2, _ps3 = st.columns(3)
        with _ps1:
            thickness = st.number_input("Wall thickness (mm)", 1.0, 20.0, 4.0, 0.5,
                help="Uniform thickness applied along the profile normal",
                on_change=_on_horn_change, key="thickness")
        with _ps2:
            segments = st.number_input("Profile points", 100, 50000, 300, 50,
                help="Resolution of the generated profile / mesh")
        with _ps3:
            _c_ms = st.number_input("Speed of sound (m/s)", 320.0, 360.0, 344.0, 1.0,
                on_change=_on_horn_change, key="c_sound",
                help="Temperature-dependent (≈343 at 20°C, ≈349 at 30°C). "
                     "Hornresp default is 344.")

    # All flare math reads SOUND_SPEED from its module global at call time, so
    # overriding it here (after the importlib.reload above) makes the chosen
    # speed of sound flow through every profile, cutoff and mouth calculation.
    c_val = _c_ms * 1000.0  # mm/s
    _core.SOUND_SPEED = c_val
    _rh.SOUND_SPEED = c_val
    _rd.SOUND_SPEED = c_val

    # ── Exponential profile delegate ─────────────────────────────────────
    def _get_exp_profile(throat_d, mouth_d, fc, n):
        return _core.get_exponential(throat_d, mouth_d, fc, n)

    st.markdown("##### Dimensions")

    # Each profile is driven by a different set of inputs; the rest are solved
    # from the math and shown as results in the "Computed" panel on the right.
    _hint = ("Set **throat + mouth**. Acoustic gap follows."         if is_radial   else
             "Set **throat + mouth**. Length and Fc follow."          if is_tractrix else
             "Real **Iwata** (l'Audiophile): set **throat + length**; mouth W×H & Fc follow." if is_iwata else
             "Set **throat W×H + mouth W**. Mouth H follows."         if is_rect     else
             "Set **throat + Fc + length** (T=0.707 Hypex)."          if is_salmon    else
             "Set **throat + Fc + length**. Roll-back at mouth."      if is_lecleach else
             "Set **throat + mouth + Fc** (Fc = flare rate). Length follows.")
    st.caption(_hint)

    col_in, col_out = st.columns(2)

    # ---- Inputs: only the parameters that drive the chosen profile --------
    with col_in:
        st.markdown("**You set**")
        if is_iwata:
            throat_d = st.number_input("Throat Ø (mm)", 10.0, 200.0, 50.0, 1.0,
                help="Square rectangular throat, downstream of the round driver adaptor "
                     "(native plan = 50 mm, for a 1.5\" driver)")
            throat_w = throat_h = throat_d
            iwata_length = st.number_input("Axial length (mm)", 100.0, 1500.0, 572.0, 10.0,
                help="Stretches the l'Audiophile plan along the axis (native = 572 mm)")
            mouth_d = mouth_w = None
            _mouth_is_input = False
        elif is_rect:
            throat_w = st.number_input("Throat W (mm)", 2.0, 200.0, 30.0, 1.0,
                help="Driver-side opening — width")
            throat_h = st.number_input("Throat H (mm)", 2.0, 200.0,
                max(2.0, 30.0 / rect_ar), 1.0,
                help="Driver-side opening — height (set by aspect ratio)")
            throat_d = np.sqrt(throat_w * throat_h * 4 / np.pi)
            _mouth_is_input = True
        else:
            throat_d = st.number_input("Throat Ø (mm)", 2.0, 200.0,
                25.0 if is_radial else 20.0, 1.0,
                help="Driver-side opening — the small end")
            throat_w = throat_h = throat_d
            _mouth_is_input = is_radial or is_tractrix or is_exp

        if _mouth_is_input:
            if is_rect:
                mouth_w = st.number_input("Mouth W (mm)", 4.0, 500.0, 160.0, 5.0,
                    help="Large end — width. Height follows from area preservation.")
                mouth_d = None
            else:
                mouth_d = st.number_input("Mouth Ø (mm)", 4.0, 500.0,
                    200.0 if is_radial else 100.0, 5.0,
                    help="Large end — where the horn stops expanding")
                mouth_w = mouth_d
        elif not is_iwata:
            mouth_d = None
            mouth_w = None

        if has_fc:
            _fc_help = ("Flare rate — how fast the horn opens. The mouth sets where it ends."
                        if is_exp else
                        "Cutoff frequency — sets the flare rate, and with it the mouth size.")
            fc = st.number_input("Cutoff Fc (Hz)", 50, 20000, 600, 50, help=_fc_help)
        else:
            fc = None

        if is_iwata:
            axial_len = iwata_length
        elif (is_salmon or is_lecleach) and not is_radial and not is_rect:
            axial_len = st.number_input("Axial length (mm)", 10.0, 500.0, 80.0, 5.0,
                help="Horn depth along the axis")
        else:
            axial_len = 80.0

    # Compute the profile once; derive the remaining scalars.
    _len = None
    _mouth_d_eff = mouth_d or mouth_w  # circular-equivalent mouth diameter
    _fc_eff = fc
    _gap_t = _gap_m = None
    _err = False
    _zw = _zh = None  # rectangular profile arrays
    _iwata_mw = _iwata_mh = None  # iwata mouth W, H (mm)
    _rect_w_o_0 = _rect_h_o_0 = 0.0  # actual outer at throat (rect)
    _rect_w_o_n = _rect_h_o_n = 0.0  # actual outer at mouth  (rect)
    # Rect-flange holes are sized to the horn's OUTER wall. Making the hole
    # exactly equal to the outer wall makes the flange's hole face *coincide*
    # with the horn's faceted outer wall → the manifold union of the two is
    # degenerate (coincident coplanar walls) and leaves a non-manifold edge
    # plus a visible ledge. Shrinking the hole by this much (per side) makes
    # the flange bite *into* the wall so the union is a clean volumetric weld.
    _FLANGE_WALL_BITE = 0.5  # mm per side
    try:
        if is_radial:
            _Rr, _Zb, _Zt = _rd.get_radial_profiles(throat_d, mouth_d, fc, 50, profile_type)
            _gap_t = _Zt[0] - _Zb[0]; _gap_m = _Zt[-1] - _Zb[-1]
        elif is_rect:
            if is_tractrix:
                zr, wr, hr = _rh.get_rectangular_tractrix(throat_w, throat_h, mouth_w, segments)
                _len = zr[-1]; _fc_eff = c_val / (np.pi * mouth_w)
                zp, rp = zr, np.sqrt(wr * hr / np.pi)
                _mouth_d_eff = max(wr.max(), hr.max())
            elif is_exp:
                zr, wr, hr = _rh.get_rectangular_exponential(throat_w, throat_h, mouth_w, fc, segments)
                _len = zr[-1]
                zp, rp = zr, np.sqrt(wr * hr / np.pi)
                _mouth_d_eff = max(wr.max(), hr.max())
            elif is_salmon:
                zr, wr, hr = _rh.get_rectangular_salmon(throat_w, throat_h, fc, axial_len, segments)
                _len = axial_len
                zp, rp = zr, np.sqrt(wr * hr / np.pi)
                _mouth_d_eff = max(wr.max(), hr.max())
            elif is_iwata:   # real l'Audiophile plan — rectangular dual-flare
                zr, wr, hr = _rh.get_iwata_horn(throat_d, axial_len, segments)
                _len = zr[-1]
                _iwata_mw, _iwata_mh = float(wr[-1]), float(hr[-1])
                _mouth_d_eff = max(wr.max(), hr.max())
                _fc_eff = _core.SOUND_SPEED * np.log(
                    (wr[-1] * hr[-1]) / (wr[0] * hr[0])) / (4.0 * np.pi * zr[-1])
                zp, rp = zr, np.sqrt(wr * hr / np.pi)
            else:  # lecleach — area-preserving from circular
                throat_d_eq = np.sqrt(throat_w * throat_h * 4 / np.pi)
                zp, rp = _core.get_lecleach(throat_d_eq, fc, axial_len, segments, T=salmon_T)
                zr, wr, hr = _rh._area_to_rect(zp, rp, throat_w, throat_h)
                _mouth_d_eff = max(wr.max(), hr.max())
                _len = zp.max()
            # Actual outer dimensions at throat and mouth (normal offset)
            import _utils as _uts
            _nw_rect = _uts.compute_profile_normals(zr, wr, flip_if_negative=True)
            _nh_rect = _uts.compute_profile_normals(zr, hr, flip_if_negative=True)
            _z_o_rect = zr + thickness * (_nw_rect[:, 0] + _nh_rect[:, 0]) / 2.0
            _z_o_rect = np.clip(_z_o_rect, zr[0], zr[-1])
            _z_o_rect[0] = zr[0]
            _z_o_rect[-1] = zr[-1]
            _w_o_rect = wr + 2.0 * thickness * _nw_rect[:, 1]
            _h_o_rect = hr + 2.0 * thickness * _nh_rect[:, 1]
            # At the throat: take the max width among all slices whose outer Z == zr[0]
            # (the clip flattens several slices onto the base plane)
            _throat_mask = np.abs(_z_o_rect - zr[0]) < 1e-6
            _rect_w_o_0 = float(_w_o_rect[_throat_mask].max()) if _throat_mask.any() else _w_o_rect[0]
            _rect_h_o_0 = float(_h_o_rect[_throat_mask].max()) if _throat_mask.any() else _h_o_rect[0]
            _rect_w_o_n = _w_o_rect[-1]
            _rect_h_o_n = _h_o_rect[-1]
        elif is_tractrix:
            zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
            _len = zp[-1]; _fc_eff = c_val / (np.pi * mouth_d)
        elif is_salmon:
            zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
            _len = axial_len; _mouth_d_eff = rp.max() * 2
        elif is_lecleach:
            zp, rp = _core.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
            _len = zp.max(); _mouth_d_eff = rp.max() * 2
        elif is_exp:
            zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
            _len = zp[-1]
    except Exception:
        _err = True

    # ---- Computed: derived scalars, shown as results (not editable) -------
    _S_t_cm2 = (throat_w * throat_h if is_rect else np.pi * (throat_d / 2) ** 2) / 100.0
    if _err or _mouth_d_eff is None:
        _S_m_cm2 = None
    elif is_iwata and _iwata_mw is not None:
        _S_m_cm2 = _iwata_mw * _iwata_mh / 100.0   # true rectangular mouth area
    elif is_rect:
        _S_m_cm2 = _S_t_cm2 * (_mouth_d_eff / max(throat_w, throat_h)) ** 2
    else:
        _S_m_cm2 = np.pi * (_mouth_d_eff / 2) ** 2 / 100.0

    with col_out:
        st.markdown("**Computed**")
        if _err:
            st.caption("Adjust parameters — profile could not be computed")
        else:
            _mets = []
            if is_radial:
                if not has_fc and _gap_t is not None:
                    _mets.append(("Throat gap", f"{_gap_t:.1f} mm"))
                if _gap_m is not None:
                    _mets.append(("Mouth gap", f"{_gap_m:.1f} mm"))
            elif _len:
                _mets.append(("Length", f"{_len:.0f} mm"))
            if not has_fc and _fc_eff:                       # Fc derived (tractrix)
                _mets.append(("Cutoff Fc", f"{_fc_eff:.0f} Hz"))
            if is_iwata and _iwata_mw is not None:           # real Iwata: rectangular mouth
                _mets.append(("Mouth W×H", f"{_iwata_mw:.0f}×{_iwata_mh:.0f} mm"))
            elif not _mouth_is_input and _mouth_d_eff:       # mouth derived (salmon/lecleach)
                _mets.append(("Mouth Ø", f"{_mouth_d_eff:.0f} mm"))
            elif is_rect and _mouth_d_eff:
                _mets.append(("Mouth Ø eq", f"{_mouth_d_eff:.0f} mm"))
            _mets.append(("S_t", f"{_S_t_cm2:.2f} cm²"))
            if _S_m_cm2:
                _mets.append(("S_m", f"{_S_m_cm2:.2f} cm²"))
            for _ri in range(0, len(_mets), 2):
                _rcols = st.columns(2)
                for _rc, (_lbl, _val) in zip(_rcols, _mets[_ri:_ri + 2]):
                    _rc.metric(_lbl, _val)
            if is_poly and _mouth_d_eff:
                from polygonal_horn import _r_to_circumradius
                _Rp = _r_to_circumradius(_mouth_d_eff / 2.0, n_sides)
                st.caption(f"Polygonal mouth: Ø{2*_Rp:.0f} across corners ({n_sides}-gon)")

            # ── Mouth-size adequacy check ─────────────────────────────────
            # A horn only loads down to its cutoff if the mouth circumference is
            # at least one wavelength there: π·D ≥ λ = c/fc  →  D ≥ c/(π·fc).
            # Below that the real cutoff rises above the stated Fc.
            _fc_used = fc if has_fc else _fc_eff
            if _fc_used and _S_m_cm2:
                _D_eq = np.sqrt(400.0 * _S_m_cm2 / np.pi)      # area-equivalent mouth Ø (mm)
                _D_min = c_val / (np.pi * _fc_used)
                if _D_eq < 0.9 * _D_min:
                    st.warning(
                        f"⚠️ Mouth ≈Ø{_D_eq:.0f} mm (area-equivalent) is below the "
                        f"~{_D_min:.0f} mm needed to load down to {_fc_used:.0f} Hz "
                        f"(mouth circumference < wavelength). The real cutoff will be "
                        f"higher — enlarge the mouth or raise Fc.")

with col_prev:
    st.subheader("2D Preview — Cross-section")

    try:
        import _utils as _uts
        fig, ax = plt.subplots(figsize=(6, 3.5))
        if is_poly:
            if is_tractrix:
                zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
            elif is_salmon:
                zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
            elif is_lecleach:
                zp, rp = _core.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
            elif is_exp:
                zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
            from polygonal_horn import _r_to_circumradius
            R_poly_arr = _r_to_circumradius(rp, n_sides)
            # Parallel offset along the meridian normal — matches the poly engine
            # (R_o = R_i + t/cos·n_r, z_o = z + t·n_z, ends pinned), so the outer
            # wall stays parallel instead of a constant-z radial offset.
            _nml = _uts.compute_profile_normals(zp, R_poly_arr, flip_if_negative=True)
            R_poly_o = R_poly_arr + thickness / np.cos(np.pi / n_sides) * _nml[:, 1]
            z_poly_o = zp + thickness * _nml[:, 0]
            z_poly_o = np.clip(z_poly_o, zp[0], zp[-1])
            z_poly_o[0] = zp[0]; z_poly_o[-1] = zp[-1]
            ax.plot(zp, R_poly_arr, label=f"Inner ({n_sides}-gon)", c="#2196F3")
            ax.plot(z_poly_o, R_poly_o, label="+ wall", c="#FF5722", alpha=.5, linestyle="--")
            ax.set_xlabel("Z (mm)")
        elif is_rect:
            if is_tractrix:
                zr, wr, hr = _rh.get_rectangular_tractrix(throat_w, throat_h, mouth_w, segments)
            elif is_exp:
                zr, wr, hr = _rh.get_rectangular_exponential(throat_w, throat_h, mouth_w, fc, segments)
            elif is_salmon:
                zr, wr, hr = _rh.get_rectangular_salmon(throat_w, throat_h, fc, axial_len, segments)
            elif is_iwata:
                zr, wr, hr = _rh.get_iwata_horn(throat_d, axial_len, segments)
            else:
                # lecleach — area-preserving from circular
                zr, wr, hr = _rh._area_to_rect(zp, rp, throat_w, throat_h)
            ax.plot(zr, wr, label="Width W(z)", c="#2196F3")
            ax.plot(zr, hr, label="Height H(z)", c="#FF5722")
            ax.set_xlabel("Z (mm)")
        elif is_radial:
            Rr, Zb, Zt = _rd.get_radial_profiles(throat_d, mouth_d, fc, segments, profile_type)
            ax.plot(Rr, Zb, label="Bottom deflector", c="#FF5722")
            ax.plot(Rr, Zt, label="Top reflector", c="#2196F3")
            ax.fill_between(Rr, Zb, Zt, alpha=.15, color="#4CAF50")
            ax.set_xlabel("R (mm)")
        else:
            if is_tractrix:
                zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
            elif is_salmon:
                zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
            elif is_lecleach:
                zp, rp = _core.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
            elif is_exp:
                zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
            # Parallel offset along the meridian normal — matches the mesh engine
            # (constant-thickness wall), so the outer line stays parallel instead
            # of a constant-z radial offset.
            _nml = _uts.compute_profile_normals(zp, rp)
            z_wall = zp + thickness * _nml[:, 0]
            r_wall = rp + thickness * _nml[:, 1]
            ax.plot(zp, rp, label="Inner profile", c="#2196F3")
            ax.plot(z_wall, r_wall, "--", label="+ wall", c="#FF5722", alpha=.5)
            ax.set_xlabel("Z (mm)")
        ax.set_ylabel("R (mm)"); ax.legend(fontsize=8); ax.grid(True, alpha=.3)
        fig.tight_layout(); st.pyplot(fig)
        plt.close(fig)
        if is_iwata:
            st.caption("Plan-view mouth is a circular arc (r≈692 mm scaled, apex R below "
                       "the throat); the height-plane mouth stays flat. The arc is applied "
                       "to the 3D mesh, not shown in this W/H section.")
    except Exception:
        st.info("Set profile parameters to display the preview")

# ═══════════════════════════════════════════════════════════════════════
#  ROW 2 — Mounting Flanges
# ═══════════════════════════════════════════════════════════════════════

st.divider()
st.subheader("Mounting Flanges")

# --- Auto-calculate flange dimensions from profile ---

def _calc_flange_dims():
    """Return suggested flange dimensions based on current horn profile."""
    import _utils as _uts

    def _mouth_wall_dz(zp, rp):
        """Axial (Z) extent of the wall at the mouth — matches the mesh engine's
        parallel normal offset, so a flange of this thickness sits flush with the
        flare (no protruding rim) instead of using the along-normal thickness."""
        nml = _uts.compute_profile_normals(zp, rp)
        z_o = zp + nml[:, 0] * thickness
        return float(max(0.1, zp[-1] - z_o[-1]))

    mouth_dz = float(thickness)
    if is_rect:
        ir_throat = throat_w / 2 + thickness
        if is_tractrix:
            zr, wr, hr = _rh.get_rectangular_tractrix(throat_w, throat_h, mouth_w, segments)
        elif is_exp:
            zr, wr, hr = _rh.get_rectangular_exponential(throat_w, throat_h, mouth_w, fc, segments)
        elif is_salmon:
            zr, wr, hr = _rh.get_rectangular_salmon(throat_w, throat_h, fc, axial_len, segments)
        elif is_iwata:
            zr, wr, hr = _rh.get_iwata_horn(throat_d, axial_len, segments)
        else:
            throat_d_eq = np.sqrt(throat_w * throat_h * 4 / np.pi)
            zr, wr, hr = _rh._area_to_rect(*_core.get_lecleach(throat_d_eq, fc, axial_len, segments, T=salmon_T), throat_w, throat_h)
        ir_mouth = max(wr[-1], hr[-1]) / 2 + thickness
        _get_mid_r = lambda pct, _z=zr, _w=wr, _h=hr: max(
            _w[min(int(len(_w)*pct/100), len(_w)-1)],
            _h[min(int(len(_h)*pct/100), len(_h)-1)]) / 2 + thickness
    elif is_poly:
        from polygonal_horn import _r_to_circumradius
        ir_throat = _r_to_circumradius(np.array([throat_d/2]), n_sides)[0]
        if is_tractrix:
            zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
        elif is_salmon:
            zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
        elif is_lecleach:
            zp, rp = _core.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
        elif is_exp:
            zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
        ir_mouth = _r_to_circumradius(np.array([rp.max()]), n_sides)[0]
        mouth_dz = _mouth_wall_dz(zp, rp)
        _get_mid_r = lambda pct: _r_to_circumradius(np.array([rp[int(len(rp)*pct/100)]]), n_sides)[0]
    elif is_radial:
        ir_throat = throat_d / 2; ir_mouth = mouth_d / 2
        _get_mid_r = lambda pct: None
    elif is_tractrix:
        ir_throat = throat_d / 2; ir_mouth = mouth_d / 2
        zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
        mouth_dz = _mouth_wall_dz(zp, rp)
        _get_mid_r = lambda pct: rp[int(np.searchsorted(zp, zp[-1]*pct/100))]
    elif is_exp:
        zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
        ir_throat = throat_d / 2; ir_mouth = rp.max()
        mouth_dz = _mouth_wall_dz(zp, rp)
        _get_mid_r = lambda pct: rp[min(int(np.searchsorted(zp, zp[-1]*pct/100)), len(rp)-1)]
    else:  # salmon / lecleach
        if is_salmon:
            zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
        else:
            zp, rp = _core.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
        ir_throat = throat_d / 2; ir_mouth = rp.max()
        mouth_dz = _mouth_wall_dz(zp, rp)
        _z_len = zp.max()  # for roll-back profiles, use max z (axial extent)
        _get_mid_r = lambda pct, _zp=zp, _rp=rp, _zl=_z_len: _rp[np.argmin(np.abs(_zp - _zl*pct/100))]

    return ir_throat, ir_mouth, _get_mid_r, mouth_dz


ir_throat, ir_mouth, _get_mid_r, _mouth_wall_dz = _calc_flange_dims()

if st.button("🔧 Recalculate flanges", use_container_width=True,
             help="Update all flange diameters based on current horn parameters"):
    _on_horn_change()
    st.toast("Flanges recalculated", icon="✅")

# Common bolt defaults
_bolt_n = n_sides if (is_poly or is_rect) else 4
_bolt_d = 3.5
_flange_sp = 6.0

def _bolt_phase(sides, pos):
    if pos == "faces":
        return np.pi / 2.0 + np.pi / max(sides, 3)
    return np.pi / 2.0

def _def_bc(lo, hi):
    """Default bolt-circle Ø: bias strongly outward (toward vertices) for poly/rect."""
    return float(hi - 2.0) if (is_poly or is_rect) else float((lo + hi) / 2.0)


def _clamp_state(key, lo, hi):
    """Keep a persisted widget value within [lo, hi] before the widget is created.

    Streamlit reads session_state[key] as the widget value; if a previously stored
    value falls outside a newly computed min/max it raises at creation time. Clamp
    it here so changing the horn (and thus the flange bounds) never crashes the run.
    """
    if key in st.session_state:
        try:
            st.session_state[key] = float(min(max(st.session_state[key], lo), hi))
        except (TypeError, ValueError):
            st.session_state.pop(key, None)


def _flange_R_from_ring(inner_R, ring, outer_n):
    """
    Outer circumradius such that the wall thickness at the FLAT faces equals `ring`.

    Circular (outer_n < 3): flange_R = inner_R + ring (uniform radial wall).
    Polygonal: inradius = flange_R·cos(π/N) must equal inner_R + ring, so
        flange_R = (inner_R + ring) / cos(π/N).
    The corners extend further out, but the minimum wall (at the flats) stays = ring,
    so the default 15 mm is always coherent for any side count — the hole never
    breaks through the polygon edges.
    """
    if outer_n >= 3:
        return (inner_R + ring) / np.cos(np.pi / outer_n)
    return inner_R + ring


def _bolt_circle_band(inner_R, flange_R, bolt_d, outer_n):
    """Valid bolt-circle Ø range so the holes stay inside the ring.

    The flange size is fixed by the ring width; the bolts must sit between the
    inner hole and the outer edge, clear of both by the bolt radius + 1 mm.
    Returns (lo, hi) diameters. Moving the bolt circle within this band slides the
    holes through the ring without ever pushing them off the edge or into the hole,
    and without resizing the flange. (Polygons: uses circumradius when bolts are
    vertex-aligned, inradius for face-aligned.)
    """
    if outer_n >= 3 and (is_poly or is_rect):
        outer_lim = flange_R  # bolts at vertices → bind on circumradius
    elif outer_n >= 3:
        outer_lim = flange_R * np.cos(np.pi / outer_n)  # inradius
    else:
        outer_lim = flange_R
    lo = max(10.0, 2.0 * (inner_R + bolt_d / 2.0 + 1.0))
    hi = 2.0 * (outer_lim - bolt_d / 2.0 - 1.0)
    if hi <= lo:
        hi = lo + 2.0
    return lo, hi


# --- Flange inputs (3 columns) ---
fg1, fg2, fg3 = st.columns(3)

with fg1:
    st.markdown("##### Throat Flange / Adapter")
    if is_radial:
        st.caption("Mounting holes on bottom plate")
        gen_throat = st.checkbox("Include", True, key="gen_throat")
        _ft_nb    = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="ft_nb")
        _ft_db    = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="ft_db")
        _ft_bc_lo, _ft_bc_hi = float(throat_d), float(mouth_d * 0.95)
        if "ft_bc_rad" not in st.session_state:
            st.session_state["ft_bc_rad"] = float(mouth_d * 0.7)
        _clamp_state("ft_bc_rad", _ft_bc_lo, _ft_bc_hi)
        _ft_bc    = st.number_input("Bolt circle Ø (mm)", _ft_bc_lo, _ft_bc_hi,
                                    step=1.0, key="ft_bc_rad")
        _ft_depth = st.number_input("Hole depth (mm)", 2.0, 30.0, 8.0, 0.5, key="ft_depth")
        _ft_sp = _ft_off = _ft_od = _ft_ow = _ft_oh = 0.0; _ft_ring = 0.0
        throat_outer = "Circular"; _ta_driver_type = "flanged"; _ta_include_adapter = False
        _ta_adapter_len = 0.0; _ta_socket_depth = 0.0
    elif is_rect or is_poly:
        gen_throat = st.checkbox("Include", True, key="gen_throat")

        # ── Adapter section ───────────────────────────────────────────────
        _ta_include_adapter = st.checkbox("Include shape adapter", True,
            key="ta_incl_adapter",
            help="Transitions from round driver to the rectangular/polygonal "
                 "horn throat, maintaining the expansion profile. "
                 "Uncheck for a simple rectangular/polygonal throat flange.")

        if _ta_include_adapter:
            # ── Adapter mode: round driver → rect/poly transition ─────────
            _ta_driver_type = st.radio("Driver interface",
                ["Flanged", 'Threaded 1"', 'Threaded 1\u00bc"', 'Threaded 2"'],
                index=0, horizontal=True, key="ta_driver_type")
            _driver_is_flanged = _ta_driver_type == "Flanged"
            _driver_is_threaded = not _driver_is_flanged

            _ta_thread_key = None
            if _driver_is_threaded:
                _ta_thread_key = {"Threaded 1\"": "1in",
                                  "Threaded 1\u00bc\"": "1_25in",
                                  "Threaded 2\"": "2in"}[_ta_driver_type]

            _ta_adapter_len = st.number_input("Adapter length (mm)", 5.0, 200.0, 30.0, 5.0,
                key="ta_adapter_len",
                help="Length of the round-to-shape transition section")

            if _driver_is_threaded:
                _ft_driver_d = _ta.THREAD_SPECS[_ta_thread_key].major_diam
                st.caption(f"Driver throat: \u00d8{_ft_driver_d:.1f} mm ({_ta_driver_type})")
                _ta_socket_depth = st.number_input("Socket depth (mm)", 5.0, 30.0, 15.0, 1.0,
                    key="ta_socket_depth",
                    help="Depth of the threaded bore for the driver")
                _ft_sp = _ft_off = _ft_nb = _ft_db = _ft_od = _ft_bc = 0.0
                _ft_ring = _ft_outer_n = 0; _ft_inner_R = _ft_driver_d / 2.0
                throat_outer = "Circular"; _ft_bphase = 0.0; _ft_ow = _ft_oh = 0.0
            else:
                _default_driver_d = float(throat_d if is_rect else throat_d)
                _ft_driver_d = st.number_input("Driver throat \u00d8 (mm)", 5.0, 200.0,
                    _default_driver_d, 1.0, key="ft_driver_d",
                    help="Circular throat diameter at the driver end. "
                         "The adapter transitions from this to the horn throat shape.")
                _ft_inner_R = _ft_driver_d / 2.0
                _ft_sp  = st.number_input("Flange thickness (mm)", 2.0, 20.0, _flange_sp, 0.5,
                    key="ft_spess")
                _ft_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="ft_off")
                _ft_nb  = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="ft_nb")
                _ft_db  = st.number_input("Bolt hole \u00d8 (mm)", 1.0, 12.0, _bolt_d, 0.1, key="ft_db")
                st.caption(f"Hole: \u00d8{_ft_driver_d:.0f} mm (circular — driver end)")
                _ft_bpos = st.radio("Bolt position", ["At vertices", "At mid-faces"],
                    index=0, horizontal=True, key="ft_bpos",
                    help="Align bolts with polygon vertices or face centers"
                    ) if is_poly else "At vertices"
                _ft_bphase = _bolt_phase(n_sides if is_poly else 4, _ft_bpos)
                throat_outer = st.radio("Outer shape",
                    ["Circular", "Polygonal"], index=0, horizontal=True, key="throat_outer")
                _ft_outer_n = (st.select_slider("Outer sides", options=list(range(3, 13)),
                                                value=n_sides, key="ft_outer_n")
                               if throat_outer == "Polygonal" else 0)
                _ft_ring = st.number_input("Ring width (mm)", 5.0, 200.0, 15.0, 1.0, key="ft_ring",
                    help="Wall around the hole — this sets the flange size. "
                         "Widen it to fit bolts further out.")
                _ft_flange_R = _flange_R_from_ring(_ft_inner_R, _ft_ring, _ft_outer_n)
                _ft_od = _ft_flange_R * 2
                if _ft_outer_n >= 3:
                    st.caption(f"Across corners \u00d8: {_ft_od:.1f} mm \u00b7 flats wall {_ft_ring:.0f} mm")
                else:
                    st.caption(f"Outer \u00d8: {_ft_od:.1f} mm")
                _ft_bc_lo, _ft_bc_hi = _bolt_circle_band(_ft_inner_R, _ft_flange_R, _ft_db, _ft_outer_n)
                if "ft_bc" not in st.session_state:
                    st.session_state["ft_bc"] = _def_bc(_ft_bc_lo, _ft_bc_hi)
                _clamp_state("ft_bc", _ft_bc_lo, _ft_bc_hi)
                _ft_bc = st.number_input("Bolt circle \u00d8 (mm)", _ft_bc_lo, _ft_bc_hi,
                    step=1.0, key="ft_bc")
                _ta_socket_depth = 0.0; _ft_ow = _ft_oh = 0.0

            _ft_depth = 0.0
            # Dummy old-style rect/poly vars (not used in adapter mode)
            _ft_inner_w = _ft_inner_h = 0.0
        else:
            # ── No adapter: traditional rect/poly flange at horn throat ──
            _ta_driver_type = "flanged"
            _ta_include_adapter = False
            _ta_adapter_len = 0.0
            _ta_socket_depth = 0.0
            _driver_is_threaded = False
            _driver_is_flanged = True

            if is_rect:
                _ft_inner_w = max(_rect_w_o_0 - 2 * _FLANGE_WALL_BITE, 1.0)
                _ft_inner_h = max(_rect_h_o_0 - 2 * _FLANGE_WALL_BITE, 1.0)
                _ft_inner_R = max(_ft_inner_w, _ft_inner_h) / 2
                st.caption(f"Hole: {_ft_inner_w:.1f}\u00d7{_ft_inner_h:.1f} mm (rectangular)")
            else:
                from polygonal_horn import _r_to_circumradius
                _R_poly_g     = _r_to_circumradius(np.array([throat_d/2]), n_sides)[0]
                _R_o_g_approx = _R_poly_g + thickness / np.cos(np.pi / n_sides)
                _ft_inner_R   = _R_o_g_approx
                _ft_inner_w = _ft_inner_h = 0.0
                st.caption(f"Hole: {n_sides}-gon, R={_ft_inner_R:.1f} mm")

            _ft_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, _flange_sp, 0.5, key="ft_spess")
            _ft_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="ft_off")
            _ft_nb  = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="ft_nb")
            _ft_db  = st.number_input("Bolt hole \u00d8 (mm)", 1.0, 12.0, _bolt_d, 0.1, key="ft_db")
            _ft_bpos = st.radio("Bolt position", ["At vertices", "At mid-faces"],
                index=0, horizontal=True, key="ft_bpos",
                help="Align bolts with polygon vertices or face centers"
                ) if (is_poly or is_rect) else "At vertices"
            _ft_bphase = _bolt_phase(n_sides if is_poly else 4, _ft_bpos)
            throat_outer = st.radio("Outer shape",
                ["Circular", "Rectangular"] if is_rect else ["Circular", "Polygonal"],
                index=0, horizontal=True, key="throat_outer")
            _ft_outer_n = (st.select_slider("Outer sides", options=list(range(3, 13)),
                                            value=n_sides, key="ft_outer_n")
                           if throat_outer == "Polygonal" else 0)
            _ft_ring = st.number_input("Ring width (mm)", 5.0, 200.0, 15.0, 1.0, key="ft_ring",
                help="Wall around the hole — this sets the flange size. Widen it to fit bolts further out.")
            _ft_flange_R = _flange_R_from_ring(_ft_inner_R, _ft_ring, _ft_outer_n)
            _ft_od = _ft_flange_R * 2
            if is_rect:
                _ft_outer_w = _ft_inner_w + 2 * _ft_ring
                _ft_outer_h = _ft_inner_h + 2 * _ft_ring
                if throat_outer == "Circular":
                    _ft_diag = np.sqrt(_ft_inner_w**2 + _ft_inner_h**2)
                    _ft_od = _ft_diag + 2 * _ft_ring
                    st.caption(f"Outer \u00d8: {_ft_od:.0f} mm (diag + 2\u00d7ring)")
                else:
                    st.caption(f"Outer: {_ft_outer_w:.0f}\u00d7{_ft_outer_h:.0f} mm (ring {_ft_ring:.0f} mm)")
            elif _ft_outer_n >= 3:
                st.caption(f"Across corners \u00d8: {_ft_od:.1f} mm \u00b7 flats wall {_ft_ring:.0f} mm")
            else:
                st.caption(f"Outer \u00d8: {_ft_od:.1f} mm")
            _ft_bc_lo, _ft_bc_hi = _bolt_circle_band(_ft_inner_R, _ft_flange_R, _ft_db, _ft_outer_n)
            if "ft_bc" not in st.session_state:
                st.session_state["ft_bc"] = _def_bc(_ft_bc_lo, _ft_bc_hi)
            _clamp_state("ft_bc", _ft_bc_lo, _ft_bc_hi)
            _ft_bc = st.number_input("Bolt circle \u00d8 (mm)", _ft_bc_lo, _ft_bc_hi,
                step=1.0, key="ft_bc")
            _ft_depth = 0.0; _ft_ow = _ft_oh = 0.0
    else:
        gen_throat = st.checkbox("Include", True, key="gen_throat")
        _ft_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, _flange_sp, 0.5, key="ft_spess")
        _ft_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="ft_off")
        _ft_nb  = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="ft_nb")
        _ft_db  = st.number_input("Bolt hole \u00d8 (mm)", 1.0, 12.0, _bolt_d, 0.1, key="ft_db")
        _ft_inner_R = throat_d / 2 + thickness
        st.caption(f"Hole: \u00d8{_ft_inner_R*2:.0f} mm (circular)")
        _ft_bpos = "At vertices"
        _ft_bphase = _bolt_phase(4, "At vertices")
        throat_outer = st.radio("Outer shape",
            ["Circular", "Polygonal"], index=0, horizontal=True, key="throat_outer")
        _ft_outer_n = (st.select_slider("Outer sides", options=list(range(3, 13)),
                                        value=4, key="ft_outer_n")
                       if throat_outer == "Polygonal" else 0)
        _ft_ring = st.number_input("Ring width (mm)", 5.0, 200.0, 15.0, 1.0, key="ft_ring",
            help="Wall around the hole — this sets the flange size. Widen it to fit bolts further out.")
        _ft_flange_R = _flange_R_from_ring(_ft_inner_R, _ft_ring, _ft_outer_n)
        _ft_od = _ft_flange_R * 2
        if _ft_outer_n >= 3:
            st.caption(f"Across corners \u00d8: {_ft_od:.1f} mm \u00b7 flats wall {_ft_ring:.0f} mm")
        else:
            st.caption(f"Outer \u00d8: {_ft_od:.1f} mm")
        _ft_bc_lo, _ft_bc_hi = _bolt_circle_band(_ft_inner_R, _ft_flange_R, _ft_db, _ft_outer_n)
        if "ft_bc" not in st.session_state:
            st.session_state["ft_bc"] = _def_bc(_ft_bc_lo, _ft_bc_hi)
        _clamp_state("ft_bc", _ft_bc_lo, _ft_bc_hi)
        _ft_bc = st.number_input("Bolt circle \u00d8 (mm)", _ft_bc_lo, _ft_bc_hi,
            step=1.0, key="ft_bc")
        _ft_depth = 0.0
        _ta_driver_type = "flanged"; _ta_include_adapter = False
        _ta_adapter_len = 0.0; _ta_socket_depth = 0.0; _ft_driver_R = _ft_inner_R

with fg2:
    st.markdown("##### Mouth Flange")
    if is_radial or is_lecleach or is_iwata:
        gen_mouth = False
        _fm_sp = _fm_off = _fm_nb = _fm_db = _fm_od = _fm_bc = _fm_ow = _fm_oh = 0.0
        mouth_outer = "Circular"
        if is_radial:
            st.caption("Not available for radial profile")
        elif is_iwata:
            st.caption("Not available — Iwata mouth is a curved arc (no flat flange)")
        else:
            st.caption("Not available — use Mid Flange instead")
    else:
        gen_mouth = st.checkbox("Include", True, key="gen_mouth")
        # Default to the wall's axial extent at the mouth so the flange sits flush
        # with the flare (no protruding rim). This is thickness·|n_z|, not the raw
        # along-normal wall thickness.
        _fm_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, max(2.0, float(_mouth_wall_dz)), 0.5,
            key="fm_spess",
            help="Defaults to the flare's axial thickness at the mouth, so the "
                 "flange ends flush with the wall (no rim)")
        _fm_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="fm_off")
        _fm_nb  = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="fm_nb")
        _fm_db  = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="fm_db")
        if is_rect:
            _fm_inner_w = max(_rect_w_o_n - 2 * _FLANGE_WALL_BITE, 1.0)
            _fm_inner_h = max(_rect_h_o_n - 2 * _FLANGE_WALL_BITE, 1.0)
            _fm_inner_R = max(_fm_inner_w, _fm_inner_h) / 2
            st.caption(f"Hole: {_fm_inner_w:.1f}×{_fm_inner_h:.1f} mm (rectangular)")
        elif is_poly:
            _fm_inner_R = ir_mouth
            st.caption(f"Hole: {n_sides}-gon, R≈{_fm_inner_R:.0f} mm")
        else:
            _fm_inner_R = ir_mouth + thickness
            _fm_prof_R  = ir_mouth  # inner profile radius (without wall)
            st.caption(f"Hole: Ø{_fm_prof_R*2:.0f} mm (circular)")
        _fm_bpos = st.radio("Bolt position", ["At vertices", "At mid-faces"],
            index=0, horizontal=True, key="fm_bpos",
            help="Align bolts with polygon vertices or face centers"
            ) if (is_poly or is_rect) else "At vertices"
        _fm_bphase = _bolt_phase(n_sides if is_poly else 4, _fm_bpos)
        _mouth_outer_default = 0
        mouth_outer = st.radio("Outer shape",
            ["Circular", "Rectangular"] if is_rect else ["Circular", "Polygonal"],
            index=_mouth_outer_default, horizontal=True, key="mouth_outer")
        _fm_outer_n = (st.select_slider("Outer sides", options=list(range(3, 13)),
                                        value=n_sides, key="fm_outer_n")
                       if mouth_outer == "Polygonal" else 0)
        _fm_ring = st.number_input("Ring width (mm)", 5.0, 200.0, 15.0, 1.0, key="fm_ring",
            help="Wall around the hole — this sets the flange size.")
        _fm_flange_R = _flange_R_from_ring(ir_mouth, _fm_ring, _fm_outer_n)
        _fm_hole_R   = ir_mouth
        _fm_od = _fm_flange_R * 2
        if is_rect:
            _fm_outer_w = _fm_inner_w + 2 * _fm_ring
            _fm_outer_h = _fm_inner_h + 2 * _fm_ring
            if mouth_outer == "Circular":
                _fm_diag = np.sqrt(_fm_inner_w**2 + _fm_inner_h**2)
                _fm_od = _fm_diag + 2 * _fm_ring
                st.caption(f"Outer Ø: {_fm_od:.0f} mm (diag + 2×ring)")
            else:
                st.caption(f"Outer: {_fm_outer_w:.0f}×{_fm_outer_h:.0f} mm (ring {_fm_ring:.0f} mm)")
        elif _fm_outer_n >= 3:
            st.caption(f"Across corners Ø: {_fm_od:.1f} mm · flats wall {_fm_ring:.0f} mm")
        else:
            st.caption(f"Outer Ø: {_fm_od:.1f} mm")
        _fm_ow = _fm_od; _fm_oh = _fm_od
        _fm_bc_lo, _fm_bc_hi = _bolt_circle_band(_fm_hole_R, _fm_flange_R, _fm_db, _fm_outer_n)
        if "fm_bc" not in st.session_state:
            st.session_state["fm_bc"] = _def_bc(_fm_bc_lo, _fm_bc_hi)
        _clamp_state("fm_bc", _fm_bc_lo, _fm_bc_hi)
        _fm_bc = st.number_input("Bolt circle Ø (mm)", _fm_bc_lo, _fm_bc_hi,
            step=1.0, key="fm_bc")

with fg3:
    st.markdown("##### Mid Flange")
    if is_radial:
        gen_mid = False; _mid_pos = 50
        st.caption("Not available for radial profile")
    else:
        gen_mid = st.checkbox("Include", is_lecleach, key="gen_mid")
        _mid_max = max(5.0, _len or 200.0)
        _mid_pos = st.number_input("Distance from throat (mm)", 5.0, _mid_max,
            max(5.0, _mid_max * 0.5), 5.0, key="mid_z")
        _mid_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, 4.0, 0.5, key="mid_spess")
        _mid_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="mid_off")
        _mid_nb = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="mid_nb")
        _mid_db = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="mid_db")
        _mid_pct = min(100.0, _mid_pos / max(_len or 1, 1) * 100)
        mid_r = _get_mid_r(_mid_pct) if _len else 10
        if is_rect:
            _mid_idx = min(int(_mid_pct / 100 * len(zr)), len(zr) - 1)
            import _utils as _uts
            _nw_mid = _uts.compute_profile_normals(zr, wr, flip_if_negative=True)
            _nh_mid = _uts.compute_profile_normals(zr, hr, flip_if_negative=True)
            _mid_inner_w = max(wr[_mid_idx] + 2.0 * thickness * _nw_mid[_mid_idx, 1]
                               - 2 * _FLANGE_WALL_BITE, 1.0)
            _mid_inner_h = max(hr[_mid_idx] + 2.0 * thickness * _nh_mid[_mid_idx, 1]
                               - 2 * _FLANGE_WALL_BITE, 1.0)
            _mid_inner_R = max(_mid_inner_w, _mid_inner_h) / 2
            st.caption(f"Hole: {_mid_inner_w:.0f}×{_mid_inner_h:.0f} mm (rectangular)")
        elif is_poly:
            _mid_inner_R = mid_r
            st.caption(f"Hole: {n_sides}-gon, R≈{_mid_inner_R:.0f} mm")
        else:
            _mid_inner_R = mid_r + thickness
            st.caption(f"Hole: Ø{_mid_inner_R*2:.0f} mm (circular)")
        _mid_bpos = st.radio("Bolt position", ["At vertices", "At mid-faces"],
            index=0, horizontal=True, key="mid_bpos",
            help="Align bolts with polygon vertices or face centers"
            ) if (is_poly or is_rect) else "At vertices"
        _mid_bphase = _bolt_phase(n_sides if is_poly else 4, _mid_bpos)
        _mid_outer_default = 0
        mid_out = st.radio("Outer shape",
            ["Circular", "Rectangular"] if is_rect else ["Circular", "Polygonal"],
            index=_mid_outer_default, horizontal=True, key="mid_out")
        _mid_outer_n = (st.select_slider("Outer sides", options=list(range(3, 13)),
                                         value=n_sides, key="mid_outer_n")
                        if mid_out == "Polygonal" else 0)
        _mid_ring = st.number_input("Ring width (mm)", 5.0, 200.0, 15.0, 1.0, key="mid_ring",
            help="Wall around the hole — this sets the flange size. Widen it to fit bolts further out.")
        _mid_flange_R = _flange_R_from_ring(_mid_inner_R, _mid_ring, _mid_outer_n)
        _mid_od = _mid_flange_R * 2
        if is_rect:
            _mid_outer_w = _mid_inner_w + 2 * _mid_ring
            _mid_outer_h = _mid_inner_h + 2 * _mid_ring
            if mid_out == "Circular":
                _mid_diag = np.sqrt(_mid_inner_w**2 + _mid_inner_h**2)
                _mid_od = _mid_diag + 2 * _mid_ring
                st.caption(f"Outer Ø: {_mid_od:.0f} mm (diag + 2×ring)")
            else:
                st.caption(f"Outer: {_mid_outer_w:.0f}×{_mid_outer_h:.0f} mm (ring {_mid_ring:.0f} mm)")
        elif _mid_outer_n >= 3:
            st.caption(f"Across corners Ø: {_mid_od:.1f} mm · flats wall {_mid_ring:.0f} mm")
        else:
            st.caption(f"Outer Ø: {_mid_od:.1f} mm")
        _mid_bc_lo, _mid_bc_hi = _bolt_circle_band(_mid_inner_R, _mid_flange_R, _mid_db, _mid_outer_n)
        if "mid_bc" not in st.session_state:
            st.session_state["mid_bc"] = _def_bc(_mid_bc_lo, _mid_bc_hi)
        _clamp_state("mid_bc", _mid_bc_lo, _mid_bc_hi)
        _mid_bc = st.number_input("Bolt circle Ø (mm)", _mid_bc_lo, _mid_bc_hi,
            step=1.0, key="mid_bc")

# ═══════════════════════════════════════════════════════════════════════
#  ROW 3 — Generate Assembly
# ═══════════════════════════════════════════════════════════════════════

st.divider()
st.subheader("Generate Assembly")

chk, _ = st.columns([1, 3])
with chk:
    gen_horn = st.checkbox("Include horn", True, key="gen_horn")

gen_btn = st.button("Generate Assembly STL", type="primary", use_container_width=True)

if gen_btn:
    with st.spinner("Generating…"):
        try:
            import trimesh as _tm
            C = _core

            # --- 3a. Generate horn ---
            if is_poly:
                if is_tractrix:
                    zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
                elif is_salmon:
                    zp, rp = C.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
                elif is_lecleach:
                    zp, rp = C.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
                elif is_exp:
                    zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                _ph.generate_polygonal_3d_mesh(zp, rp, n_sides, thickness, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                horn.fix_normals()
                from polygonal_horn import _r_to_circumradius
                import _utils as _uts
                _R_i_arr   = _r_to_circumradius(rp, n_sides)
                _nml_poly  = _uts.compute_profile_normals(zp, _R_i_arr, flip_if_negative=True)
                _cos_pn    = np.cos(np.pi / n_sides)
                _R_o_arr   = _R_i_arr + thickness / _cos_pn * _nml_poly[:, 1]
                _R_o_throat_poly = _R_o_arr[0]
                _R_o_mouth_poly  = _R_o_arr[-1]
                mouth_bx = mouth_by = _R_o_arr[-1] * 2
                _rp_mouth = rp[-1]
                _zp_mouth = zp[-1]
            elif is_radial:
                with tempfile.TemporaryDirectory() as _tmp:
                    _rd.generate_radial_horn(throat_d, mouth_d, fc, 48, _tmp, profile_type)
                    horn = _tm.load(os.path.join(_tmp, "radial_bottom.stl"), file_type="stl")
                    R, Zb, Zt = _rd.get_radial_profiles(throat_d, mouth_d, fc, segments, profile_type)
                    Rm, Rt_rad = R[-1], R[0]
                    Z_top_flat = Zt[-1] + 4.0
                    eps = 0.01
                    r_poly = np.concatenate([[eps], R, [Rm, eps, eps]])
                    z_poly = np.concatenate([[Zt[0]], Zt, [Z_top_flat, Z_top_flat, Zt[0]]])
                    top_mesh = _rd._revolve_polygon(r_poly, z_poly, 48)
                    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as _tf: _tfn = _tf.name
                    top_mesh.save(_tfn)
                    horn_top = _tm.load(_tfn, file_type="stl"); os.unlink(_tfn)
                    horn_top.apply_translation([0, 0, Zt[0]])
                mouth_bx = mouth_by = mouth_d
            elif is_rect:
                if is_tractrix:
                    zr, wr, hr = _rh.get_rectangular_tractrix(throat_w, throat_h, mouth_w, segments)
                elif is_exp:
                    zr, wr, hr = _rh.get_rectangular_exponential(throat_w, throat_h, mouth_w, fc, segments)
                elif is_salmon:
                    zr, wr, hr = _rh.get_rectangular_salmon(throat_w, throat_h, fc, axial_len, segments)
                elif is_iwata:
                    zr, wr, hr = _rh.get_iwata_horn(throat_d, axial_len, segments)
                else:
                    throat_d_eq = np.sqrt(throat_w * throat_h * 4 / np.pi)
                    zp_c, rp_c = _core.get_lecleach(throat_d_eq, fc, axial_len, segments, T=salmon_T)
                    zr, wr, hr = _rh._area_to_rect(zp_c, rp_c, throat_w, throat_h)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                _rh.generate_rectangular_3d_mesh(zr, wr, hr, thickness, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                horn.fix_normals()
                if is_iwata:
                    # Roll the wide-plane mouth back onto the plan arc (r=692 native):
                    # intersect with a solid cylinder whose axis runs along the height (Y).
                    _R_arc, _cz = _rh.iwata_arc_mouth(throat_d, axial_len)
                    _cyl = _tm.creation.cylinder(radius=_R_arc, sections=256,
                                                 height=(hr[-1] + 2 * thickness) * 2.0)
                    _cyl.apply_transform(
                        _tm.transformations.rotation_matrix(np.pi / 2.0, [1, 0, 0]))
                    _cyl.apply_translation([0.0, 0.0, _cz])
                    _trimmed = _tm.boolean.intersection([horn, _cyl], engine="manifold")
                    if _trimmed is not None and not _trimmed.is_empty:
                        horn = _trimmed
                        horn.fix_normals()
                _rp_mouth = max(wr[-1], hr[-1]) / 2 + thickness
                _zp_mouth = zr[-1]
                if is_iwata:
                    # The arc trim narrows the wide-plane mouth — report the real extent.
                    mouth_bx = float(horn.bounds[1, 0] - horn.bounds[0, 0])
                    mouth_by = float(horn.bounds[1, 1] - horn.bounds[0, 1])
                else:
                    mouth_bx, mouth_by = wr[-1] + 2 * thickness, hr[-1] + 2 * thickness
            else:
                if is_tractrix:
                    zp, rp = C.get_tractrix(throat_d, mouth_d, segments)
                elif is_salmon:
                    zp, rp = C.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
                elif is_lecleach:
                    zp, rp = C.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
                elif is_exp:
                    zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                C.generate_3d_mesh_from_profile(zp, rp, thickness, 64, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                if is_lecleach:
                    _rmax = rp.max(); _imax = rp.argmax()
                    _rp_mouth = _rmax; _zp_mouth = zp[_imax]
                else:
                    _rp_mouth = rp[-1]; _zp_mouth = zp[-1]
                mouth_bx = mouth_by = (_rp_mouth + thickness) * 2

            z_min = horn.vertices[:,2].min()

            # --- 3b. Throat hole — analytical ---
            fiw_g = fih_g = throat_d + thickness * 2

            # --- 3c. Exact mouth dimensions ---
            if is_radial:
                fiw_m = fih_m = mouth_d; z_mouth = 0.0
            else:
                fiw_m = fih_m = _rp_mouth * 2; z_mouth = _zp_mouth

            # --- 3d. Generate flanges ---
            f_throat = f_mouth = f_mid = None

            if gen_throat and is_radial:
                bolt_angles = np.linspace(0, 2 * np.pi, int(_ft_nb), endpoint=False)
                for angle in bolt_angles:
                    x = (_ft_bc / 2.0) * np.cos(angle)
                    y = (_ft_bc / 2.0) * np.sin(angle)
                    cyl = _tm.creation.cylinder(radius=_ft_db / 2.0, height=_ft_depth + 2.0)
                    cyl.apply_translation([x, y, _ft_depth / 2.0])
                    horn = _tm.boolean.difference([horn, cyl], engine="manifold", check_volume=False)

            if gen_throat and not is_radial:
                if (is_rect or is_poly) and _ta_include_adapter:
                    # ── Adapter path: round driver → rect/poly transition ──
                    _outer_target_R = None; _outer_rw = None; _outer_rh = None
                    if is_rect:
                        horn_shape = "rectangular"
                        rect_w = throat_w
                        rect_h = throat_h
                        poly_n_sides = 0
                        poly_circumR = 0.0
                        horn_R_eq = np.sqrt(throat_w * throat_h / np.pi)
                        if _driver_is_threaded:
                            _outer_rw = _rect_w_o_0
                            _outer_rh = _rect_h_o_0
                            _outer_target_R = np.sqrt(_rect_w_o_0 * _rect_h_o_0 / np.pi)
                    else:
                        horn_shape = "polygonal"
                        rect_w = rect_h = 0.0
                        poly_n_sides = n_sides
                        from polygonal_horn import _r_to_circumradius
                        poly_circumR = _r_to_circumradius(
                            np.array([throat_d / 2.0]), n_sides)[0]
                        horn_R_eq = throat_d / 2.0
                        if _driver_is_threaded:
                            _ocr = poly_circumR + thickness / np.cos(np.pi / n_sides)
                            _outer_A = 0.5 * n_sides * _ocr**2 * np.sin(2*np.pi/n_sides)
                            _outer_target_R = np.sqrt(_outer_A / np.pi)

                    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                    f_throat = _ta.make_adapter_assembly(
                        driver_type=_ta_thread_key if _driver_is_threaded else "flanged",
                        driver_diam=_ft_driver_d if _driver_is_flanged else None,
                        thread_key=_ta_thread_key,
                        horn_shape=horn_shape,
                        rect_w=rect_w, rect_h=rect_h,
                        poly_n_sides=poly_n_sides,
                        poly_circumR=poly_circumR,
                        horn_R_eq=horn_R_eq,
                        adapter_length=_ta_adapter_len,
                        wall_thickness=thickness,
                        flange_R=_ft_od / 2.0 if _driver_is_flanged else 0.0,
                        flange_thickness=_ft_sp if _driver_is_flanged else 0.0,
                        flange_bolt_R=_ft_bc / 2.0 if _driver_is_flanged else 0.0,
                        flange_bolt_n=int(_ft_nb) if _driver_is_flanged else 0,
                        flange_bolt_d=_ft_db if _driver_is_flanged else 0.0,
                        flange_bolt_phase=_ft_bphase if _driver_is_flanged else 0.0,
                        flange_outer_n=_ft_outer_n if _driver_is_flanged else 0,
                        socket_length=_ta_socket_depth if _driver_is_threaded else 0.0,
                        outer_target_R=_outer_target_R,
                        outer_rect_w=_outer_rw,
                        outer_rect_h=_outer_rh,
                        z_offset=z_min,
                        output_path=tp,
                    )
                elif is_rect:
                    _ft_ot = "circular" if throat_outer == "Circular" else "rectangular"
                    f_throat = _rf.generate_rectangular_flange(
                        outer_diam=_ft_od if _ft_ot == "circular" else None,
                        inner_w=_ft_inner_w, inner_h=_ft_inner_h,
                        thickness=_ft_sp,
                        bolt_radius=_ft_bc/2, bolt_count=int(_ft_nb), bolt_diam=_ft_db,
                        bolt_phase=_ft_bphase,
                        outer_type=_ft_ot,
                        outer_w=_ft_outer_w if _ft_ot == "rectangular" else None,
                        outer_h=_ft_outer_h if _ft_ot == "rectangular" else None,
                        offset=z_min + _ft_off,
                        output_path=None)
                elif is_poly:
                    f_throat = _fg.generate_polygonal_flange(
                        inner_circumR=_R_o_throat_poly, n_sides=n_sides,
                        flange_R=_ft_od/2,
                        thickness=_ft_sp, bolt_R=_ft_bc/2,
                        bolt_n=int(_ft_nb), bolt_d=_ft_db,
                        bolt_phase=_ft_bphase,
                        offset=z_min + _ft_off + _ft_sp,
                        outer_n_sides=_ft_outer_n)
                else:
                    f_throat = _fg.generate_flange(
                        throat_R=fiw_g/2, flange_R=_ft_od/2,
                        thickness=_ft_sp, bolt_R=_ft_bc/2,
                        bolt_n=int(_ft_nb), bolt_d=_ft_db,
                        bolt_phase=_ft_bphase,
                        offset=z_min + _ft_off + _ft_sp,
                        outer_n_sides=_ft_outer_n,
                        output_path=None)

            if gen_mouth and not is_radial:
                if is_rect:
                    _fm_ot = "circular" if mouth_outer == "Circular" else "rectangular"
                    f_mouth = _rf.generate_rectangular_flange(
                        outer_diam=_fm_od if _fm_ot == "circular" else None,
                        inner_w=_fm_inner_w, inner_h=_fm_inner_h,
                        thickness=_fm_sp,
                        bolt_radius=_fm_bc/2, bolt_count=int(_fm_nb), bolt_diam=_fm_db,
                        bolt_phase=_fm_bphase,
                        outer_type=_fm_ot,
                        outer_w=_fm_outer_w if _fm_ot == "rectangular" else None,
                        outer_h=_fm_outer_h if _fm_ot == "rectangular" else None,
                        offset=z_mouth + _fm_off - _fm_sp,
                        output_path=None)
                elif is_poly:
                    f_mouth = _fg.generate_polygonal_flange(
                        inner_circumR=_R_o_mouth_poly, n_sides=n_sides,
                        flange_R=_fm_od/2,
                        thickness=_fm_sp, bolt_R=_fm_bc/2,
                        bolt_n=int(_fm_nb), bolt_d=_fm_db,
                        bolt_phase=_fm_bphase,
                        offset=z_mouth + _fm_off,
                        outer_n_sides=_fm_outer_n)
                else:
                    _R    = _fm_od / 2.0
                    _tr_m = _fm_hole_R
                    # guard: outer radius must exceed inner by at least 1 mm
                    if _R <= _tr_m + 1.0:
                        _R = _tr_m + 5.0
                    f_mouth = _fg.generate_flange(
                        throat_R=_tr_m, flange_R=_R,
                        thickness=_fm_sp, bolt_R=_fm_bc/2,
                        bolt_n=int(_fm_nb), bolt_d=_fm_db,
                        bolt_phase=_fm_bphase,
                        offset=z_mouth + _fm_off,
                        outer_n_sides=_fm_outer_n,
                        output_path=None)

            if gen_mid and not is_radial:
                z_mid = z_min + _mid_pos + _mid_off
                if is_rect:
                    _mid_ot = "circular" if mid_out == "Circular" else "rectangular"
                    f_mid = _rf.generate_rectangular_flange(
                        outer_diam=_mid_od if _mid_ot == "circular" else None,
                        inner_w=_mid_inner_w, inner_h=_mid_inner_h,
                        thickness=_mid_sp,
                        bolt_radius=_mid_bc/2, bolt_count=int(_mid_nb), bolt_diam=_mid_db,
                        bolt_phase=_mid_bphase,
                        outer_type=_mid_ot,
                        outer_w=_mid_outer_w if _mid_ot == "rectangular" else None,
                        outer_h=_mid_outer_h if _mid_ot == "rectangular" else None,
                        offset=z_mid - _mid_sp,
                        output_path=None)
                elif is_poly:
                    _R_o_mid_poly = float(np.interp(_mid_pos, zp, _R_o_arr))
                    f_mid = _fg.generate_polygonal_flange(
                        inner_circumR=_R_o_mid_poly, n_sides=n_sides,
                        flange_R=_mid_od/2,
                        thickness=_mid_sp, bolt_R=_mid_bc/2,
                        bolt_n=int(_mid_nb), bolt_d=_mid_db,
                        bolt_phase=_mid_bphase,
                        offset=z_mid,
                        outer_n_sides=_mid_outer_n)
                else:
                    _mid_pct_gen = min(100.0, _mid_pos / max(_len or 1, 1) * 100)
                    mid_r   = _get_mid_r(_mid_pct_gen) if _len else 10
                    fiw_mid = (mid_r + thickness) * 2
                    f_mid = _fg.generate_flange(
                        throat_R=fiw_mid/2, flange_R=_mid_od/2,
                        thickness=_mid_sp, bolt_R=_mid_bc/2,
                        bolt_n=int(_mid_nb), bolt_d=_mid_db,
                        bolt_phase=_mid_bphase,
                        offset=z_mid,
                        outer_n_sides=_mid_outer_n,
                        output_path=None)

            # --- 3e. Merge ---
            bodies = []
            if gen_horn:
                bodies.append(horn)
                if is_radial:
                    bodies.append(horn_top)
            if f_throat is not None: bodies.append(f_throat)
            if f_mouth  is not None: bodies.append(f_mouth)
            if f_mid    is not None: bodies.append(f_mid)

            if not bodies:
                st.error("Select at least one element to generate")
                st.stop()

            if len(bodies) == 1:
                combined = bodies[0]
            else:
                try:
                    combined = _tm.boolean.union(bodies, engine="manifold")
                except Exception:
                    combined = _tm.util.concatenate(bodies)
            st.session_state["_combined"] = combined

            with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
            combined.export(tp)
            with open(tp, "rb") as f: stl_bytes = f.read()

            # STEP export
            tp_step = tp.replace(".stl", ".step")
            try:
                export_step(tp, tp_step)
                with open(tp_step, "rb") as f: step_bytes = f.read()
                os.unlink(tp_step)
            except Exception:
                step_bytes = None
            os.unlink(tp)

            # --- 3f. Results ---
            st.success("✅ Assembly generated successfully")

            _wt   = combined.is_watertight if hasattr(combined, 'is_watertight') else None
            _vol  = combined.volume if hasattr(combined, 'volume') else 0
            _tris = len(combined.faces) if hasattr(combined, 'faces') else 0

            r1, r2, r3, r4 = st.columns(4)
            with r1:
                st.metric("Length", f"{horn.bounds[1,2]-horn.bounds[0,2]:.0f} mm" if gen_horn else "—")
            with r2:
                if gen_horn:
                    st.metric("Mouth", f"Ø{mouth_bx:.0f}" if abs(mouth_bx-mouth_by)<1
                              else f"{mouth_bx:.0f}×{mouth_by:.0f}")
                else:
                    st.metric("Mouth", "—")
            with r3:
                st.metric("Triangles", f"{_tris:,}")
            with r4:
                st.metric("Volume", f"{_vol:.0f} mm³")

            if _wt is True:
                st.success("Watertight mesh — ready for 3D printing")
            elif _wt is False:
                st.warning("Non-watertight mesh — check parameters")
            else:
                st.info("Multi-body output (separate flanges)")

            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button("📥 Download STL", stl_bytes, "flare_forge_assembly.stl",
                    "model/stl", use_container_width=True)
            with col_dl2:
                if step_bytes is not None:
                    st.download_button("📥 Download STEP", step_bytes, "flare_forge_assembly.step",
                        "model/step", use_container_width=True)
                else:
                    st.caption("STEP not available")

        except Exception as exc:
            st.error(f"❌ Generation failed: {exc}")
            st.code(traceback.format_exc())
else:
    st.info("Configure the parameters and click **Generate Assembly STL**")

# ══════════════════════════════════════════════════════════════
#  ROW 4 — STL Slicing (always visible, works on generated or uploaded STL)
# ══════════════════════════════════════════════════════════════

st.divider()
st.subheader("Slice STL")

load_choice = st.radio("Source", ["Generated assembly", "Upload STL file"],
                       index=0, horizontal=True, key="slice_src")
mesh_to_slice = None
if load_choice == "Generated assembly":
    if "_combined" in st.session_state:
        mesh_to_slice = st.session_state["_combined"]
    else:
        st.caption("⚠️ Generate an assembly first, or switch to Upload")
else:
    uploaded = st.file_uploader("Upload STL", type=["stl"], key="slice_upload")
    if uploaded:
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as _t:
            _t.write(uploaded.read())
            _tp = _t.name
        mesh_to_slice = _tm.load(_tp, file_type="stl")
        os.unlink(_tp)

if mesh_to_slice is None:
    st.stop()

# ── Slicing workflow ────────────────────────────────────────────────
import io, zipfile

# Shift mesh so Z_min = 0 for clean segmentation
_z_off = mesh_to_slice.bounds[0, 2]
if abs(_z_off) > 0.5:
    mesh_to_slice = mesh_to_slice.copy()
    mesh_to_slice.apply_translation([0, 0, -_z_off])
    st.caption(f"Mesh shifted by {-_z_off:.0f} mm so Z starts at 0")

_joint = st.checkbox("Axial joint lip", True, key="joint_en",
                     help="Add a joint lip on each axial cut so stacked segments "
                          "register and glue together.")
_joint_w = st.number_input("Lip wall (mm)", 0.5, 10.0, 4.0, 0.5, key="joint_w",
                            help="Wall thickness of the axial joint lip") if _joint else 0.0

_radial_joint = st.checkbox("Radial joint (tongue & groove)", False, key="radial_joint_en",
                            help="Add a vertical tongue & groove on each radial "
                                 "seam so petals interlock and self-align.")
_radial_joint_d = st.number_input("Joint depth (mm)", 0.5, 5.0, 2.0, 0.5,
                                   key="radial_joint_d",
                                   help="How far the tongue sticks out / groove "
                                        "goes in") if _radial_joint else 0.0
_radial_clearance = st.number_input("Clearance (mm)", 0.0, 0.5, 0.1, 0.05,
                                     key="radial_clearance",
                                     help="Total gap between tongue and groove "
                                          "(split evenly: 0.05 mm per side at default)"
                                     ) if _radial_joint else 0.0

ax_mode = st.radio("Define segments by", ["Count", "Height (mm)"],
                   horizontal=True, key="ax_mode")
if ax_mode == "Count":
    n_ax = st.number_input("Number of axial segments", 1, 50, 4, step=1, key="n_ax")
    seg_ref = ("count", n_ax)
else:
    seg_h = st.number_input("Cut every (mm)", 5, 500, 50, step=5, key="seg_h")
    total_z = mesh_to_slice.bounds[1, 2] - mesh_to_slice.bounds[0, 2]
    cuts = [seg_h * k for k in range(1, int(total_z / seg_h) + 1)]
    n_seg = len(cuts) + 1
    st.caption(f"Total Z={total_z:.0f} mm → {n_seg} segment{'s' if n_seg>1 else ''} (cut at {', '.join(f'{c:.0f}' for c in cuts)})")
    seg_ref = ("height", seg_h)

if st.button("❶ Slice axially", use_container_width=True):
    with st.spinner("Cutting axially…"):
        if seg_ref[0] == "count":
            n = seg_ref[1]
            if n <= 1:
                st.session_state["_ax_segs"] = [mesh_to_slice]
            else:
                st.session_state["_ax_segs"] = _slc.slice_into_segments(mesh_to_slice, n, joint_wall=_joint_w)
        else:
            dz = seg_ref[1]
            z0, z1 = mesh_to_slice.bounds[0, 2], mesh_to_slice.bounds[1, 2]
            cuts = [dz * k for k in range(1, int((z1 - z0) / dz) + 1)]
            if not cuts:
                st.session_state["_ax_segs"] = [mesh_to_slice]
            else:
                st.session_state["_ax_segs"] = _slc.slice_at_heights(mesh_to_slice, cuts, joint_wall=_joint_w)
    st.session_state.pop("_pieces", None)
    # cleanup old per-segment petal keys
    for k in list(st.session_state.keys()):
        if k.startswith("_pet_ax") or k.startswith("_sel_ax"):
            del st.session_state[k]

ax_segs = st.session_state.get("_ax_segs", None)
if ax_segs:
    st.markdown(f"**{len(ax_segs)} axial segment{'s' if len(ax_segs)>1 else ''}** — set petals per segment (1 = no petal)")

    n_cols = min(4, len(ax_segs))
    cols = st.columns(n_cols)
    petals_per = []
    for ai, seg in enumerate(ax_segs):
        with cols[ai % n_cols]:
            z_lo, z_hi = seg.bounds[0, 2], seg.bounds[1, 2]
            st.caption(f"S{ai+1}  Z={z_lo:.0f}–{z_hi:.0f}")
            pet_key = f"_pet_ax{ai}"
            default_pet = int(st.session_state.get(pet_key, 1))
            np_ = st.number_input("Petals", 1, 36, default_pet, step=1,
                                  key=pet_key, label_visibility="collapsed")
            petals_per.append(np_)

    # Bolt-hole angles from the enabled mounting flanges (holes start at 0°).
    # Petal seams are rotated into the widest gap so they never cut a hole.
    _hole_angles = []
    for _en, _nb, _bp in ((globals().get("gen_throat", False), globals().get("_ft_nb", 0), globals().get("_ft_bphase", 0.0)),
                           (globals().get("gen_mouth", False),  globals().get("_fm_nb", 0), globals().get("_fm_bphase", 0.0)),
                           (globals().get("gen_mid", False),    globals().get("_mid_nb", 0), globals().get("_mid_bphase", 0.0))):
        try:
            _nb = int(_nb)
        except (TypeError, ValueError):
            _nb = 0
        if _en and _nb >= 2:
            _hole_angles += list(_bp + np.linspace(0, 2 * np.pi, _nb, endpoint=False))
    if _hole_angles:
        st.caption(f"🔩 {len(_hole_angles)} bolt hole(s) detected — seams will be "
                   "rotated to fall between them.")

    if _radial_joint:
        st.caption(f"✔ Tongue & groove — depth {_radial_joint_d} mm, clearance {_radial_clearance} mm")

    if st.button("❷ Apply petals", use_container_width=True):
        with st.spinner("Cutting petals…"):
            pieces = []
            for ai, (seg, np_) in enumerate(zip(ax_segs, petals_per)):
                if np_ > 1:
                    phase = _slc.seam_phase_avoiding_holes(np_, _hole_angles)
                    pets = _slc.slice_into_petals(seg, np_, phase=phase,
                                                   joint_depth=_radial_joint_d,
                                                   clearance=_radial_clearance)
                    for pi, pet in enumerate(pets):
                        pieces.append((f"ax{ai+1:02d}_pet{pi+1:02d}", pet))
                else:
                    pieces.append((f"ax{ai+1:02d}", seg))
            st.session_state["_pieces"] = pieces
        st.rerun()

# Show results
pieces = st.session_state.get("_pieces", None)
if pieces:
    st.success(f"{len(pieces)} piece{'s' if len(pieces)>1 else ''} generated")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, mesh in pieces:
            with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as _t:
                _tp = _t.name
                mesh.export(_tp)
            with open(_tp, "rb") as f:
                zf.writestr(f"{name}.stl", f.read())
            os.unlink(_tp)

    _, col_zip, _ = st.columns([1, 2, 1])
    with col_zip:
        st.download_button("📦 Download all as ZIP", zip_buf.getvalue(),
                           "flare_forge_slices.zip", "application/zip",
                           use_container_width=True)

    for name, mesh in pieces:
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as _t:
            _tp = _t.name
            mesh.export(_tp)
        with open(_tp, "rb") as f:
            b = f.read()
        os.unlink(_tp)
        label = f"📥 {name}"
        if "_pet" not in name:
            z_lo, z_hi = mesh.bounds[0, 2], mesh.bounds[1, 2]
            label += f"  (Z={z_lo:.0f}–{z_hi:.0f} mm)"
        st.download_button(label, b, f"{name}.stl", "model/stl")
