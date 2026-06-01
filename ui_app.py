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
from _step_export import export_step

import importlib
importlib.reload(_core)
importlib.reload(_fg)
importlib.reload(_rf)
importlib.reload(_rh)
importlib.reload(_rd)
importlib.reload(_ph)
importlib.reload(_slc)

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
               "fm_ring", "fm_bc", "fm_ow", "fm_oh",
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

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        profile_type = st.selectbox("Profile",
            ["Tractrix", "Salmon", "Iwata", "Le Cléac'h (isophase)", "Exponential"], index=0,
            on_change=_on_horn_change, key="profile_type")
    with c2:
        section_type = st.radio("Section", ["Circular", "Polygonal", "Radial 360°"],
                          index=0, horizontal=True, key="section_type",
                          on_change=_on_horn_change)
    with c3:
        thickness = st.number_input("Wall thickness (mm)", 1.0, 20.0, 4.0, 0.5,
            help="Uniform thickness applied along the profile normal",
            on_change=_on_horn_change, key="thickness")
    with c4:
        segments = st.number_input("Profile points", 100, 50000, 300, 50)

    is_radial   = section_type.startswith("Rad")
    is_poly     = section_type == "Polygonal"
    is_rect     = False  # removed
    is_tractrix = profile_type.startswith("Tract")
    is_salmon    = profile_type.startswith("Salmon")
    is_iwata    = profile_type.startswith("Iwata")
    is_lecleach = profile_type.startswith("Le Cl")
    is_exp      = profile_type.startswith("Exp")
    has_fc      = is_salmon or is_iwata or is_lecleach or is_exp
    is_T_variable = is_salmon or is_lecleach

    st.markdown("##### Dimensions")

    # Each profile is driven by a different set of inputs; the rest are solved
    # from the math and shown live (greyed) in their own fields.
    _hint = ("Set **throat + mouth**. Acoustic gap follows."         if is_radial   else
             "Set **throat + mouth**. Length and Fc follow."          if is_tractrix else
             "Set **throat + Fc + length** (T=0.707 Hypex)."          if is_salmon    else
             "Set **throat + Fc + length** (T=0.707, preset Iwata)."  if is_iwata    else
             "Set **throat + Fc + length**. Roll-back at mouth."      if is_lecleach else
             "Set **throat + mouth + Fc** (Fc = flare rate). Length follows.")
    st.caption(_hint)

    if is_poly:
        n_sides = st.select_slider("Sides", options=list(range(3, 13)), value=4,
                                   key="n_sides")
    else:
        n_sides = 4

    # ── Exponential profile delegate ─────────────────────────────────────
    def _get_exp_profile(throat_d, mouth_d, fc, n):
        return _core.get_exponential(throat_d, mouth_d, fc, n)

    d1, d2, d3, d4 = st.columns(4)

    # Editable inputs first, so the derived fields can use their live values.
    with d1:
        throat_d = st.number_input("Throat Ø (mm)", 2.0, 200.0,
            25.0 if is_radial else 20.0, 1.0,
            help="Driver-side opening — the small end")
        _S_t_cm2 = np.pi * (throat_d / 2) ** 2 / 100
        st.caption(f"S_t = {_S_t_cm2:.2f} cm²")

    _mouth_is_input = is_radial or is_tractrix or is_exp
    if _mouth_is_input:
        with d2:
            mouth_d = st.number_input("Mouth Ø (mm)", 4.0, 500.0,
                200.0 if is_radial else 100.0, 5.0,
                help="Large end — where the horn stops expanding")
            _S_m_cm2 = np.pi * (mouth_d / 2) ** 2 / 100
            st.caption(f"S_m = {_S_m_cm2:.2f} cm²")
    else:
        mouth_d = None

    if has_fc:
        with d3:
            _fc_help = ("Flare rate — how fast the horn opens. The mouth sets where it ends."
                        if is_exp else
                        "Cutoff frequency — sets the flare rate, and with it the mouth size.")
            fc = st.number_input("Cutoff Fc (Hz)", 50, 20000, 600, 50, help=_fc_help)
    else:
        fc = None

    if (is_salmon or is_iwata or is_lecleach) and not is_radial:
        with d4:
            axial_len = st.number_input("Axial length (mm)", 10.0, 500.0, 80.0, 5.0,
                help="Horn depth along the axis")
    else:
        axial_len = 80.0

    if is_T_variable:
        salmon_T = st.number_input(
            "Flare parameter T", 0.0, 10.0, 0.707, 0.01, key="salmon_T",
            on_change=_on_horn_change,
            help="Hornresp T: 0 = catenoidal · <1 = cosh · 1 = exponential · >1 = sinh"
        )
    else:
        salmon_T = 0.707

    # Compute the profile once; derive the remaining scalars.
    _len = None
    _mouth_d_eff = mouth_d          # circular-equivalent mouth diameter
    _fc_eff = fc
    _gap_t = _gap_m = None
    _err = False
    try:
        if is_radial:
            _Rr, _Zb, _Zt = _rd.get_radial_profiles(throat_d, mouth_d, fc, 50, profile_type)
            _gap_t = _Zt[0] - _Zb[0]; _gap_m = _Zt[-1] - _Zb[-1]
        elif is_tractrix:
            zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
            _len = zp[-1]; _fc_eff = 343_000 / (np.pi * mouth_d)
        elif is_salmon:
            zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
            _len = axial_len; _mouth_d_eff = rp.max() * 2
        elif is_iwata:
            zp, rp = _core.get_iwata(throat_d, fc, axial_len, segments)
            _len = axial_len; _mouth_d_eff = rp.max() * 2
        elif is_lecleach:
            zp, rp = _core.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
            _len = zp.max(); _mouth_d_eff = rp.max() * 2
        elif is_exp:
            zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
            _len = zp[-1]
    except Exception:
        _err = True

    # Read-only display: shows the actual computed number, greyed out.
    def _ro(col, label, value, fmt="%.0f"):
        with col:
            try:
                st.number_input(label, value=float(value), disabled=True, format=fmt)
            except Exception:
                st.text_input(label, value="—", disabled=True)

    if _err:
        st.caption("Adjust parameters — profile could not be computed")
    elif is_radial:
        if not has_fc:
            _ro(d3, "Throat gap (mm)", _gap_t, fmt="%.1f")
        _ro(d4, "Mouth gap (mm)", _gap_m, fmt="%.1f")
    else:
        if not _mouth_is_input:                 # mouth derived (Salmon)
            _ro(d2, "Mouth Ø (mm)", _mouth_d_eff)
        if not has_fc:                          # Fc derived (Tractrix)
            _ro(d3, "Cutoff Fc (Hz)", _fc_eff)
        if not ((is_salmon or is_iwata) and not is_radial):  # length derived (all but Salmon/Iwata)
            _ro(d4, "Axial length (mm)", _len)
        if is_poly:
            from polygonal_horn import _r_to_circumradius
            _Rp = _r_to_circumradius(_mouth_d_eff / 2.0, n_sides)
            st.caption(f"Polygonal mouth: Ø{2*_Rp:.0f} across corners ({n_sides}-gon)")

with col_prev:
    st.subheader("2D Preview — Cross-section")

    try:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        if is_poly:
            if is_tractrix:
                zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
            elif is_salmon:
                zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
            elif is_iwata:
                zp, rp = _core.get_iwata(throat_d, fc, axial_len, segments)
            elif is_lecleach:
                zp, rp = _core.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
            elif is_exp:
                zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
            from polygonal_horn import _r_to_circumradius
            R_poly_arr = _r_to_circumradius(rp, n_sides)
            R_poly_o   = R_poly_arr + thickness / np.cos(np.pi / n_sides)
            ax.plot(zp, R_poly_arr, label=f"Inner ({n_sides}-gon)", c="#2196F3")
            ax.plot(zp, R_poly_o,   label="+ wall", c="#FF5722", alpha=.5, linestyle="--")
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
            elif is_iwata:
                zp, rp = _core.get_iwata(throat_d, fc, axial_len, segments)
            elif is_lecleach:
                zp, rp = _core.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
            elif is_exp:
                zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
            ax.plot(zp, rp, label="Inner profile", c="#2196F3")
            ax.plot(zp, rp+thickness, "--", label="+ wall", c="#FF5722", alpha=.5)
            ax.set_xlabel("Z (mm)")
        ax.set_ylabel("R (mm)"); ax.legend(fontsize=8); ax.grid(True, alpha=.3)
        fig.tight_layout(); st.pyplot(fig)
        plt.close(fig)
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
    if is_poly:
        from polygonal_horn import _r_to_circumradius
        ir_throat = _r_to_circumradius(np.array([throat_d/2]), n_sides)[0]
        if is_tractrix:
            zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
        elif is_salmon:
            zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
        elif is_iwata:
            zp, rp = _core.get_iwata(throat_d, fc, axial_len, segments)
        elif is_lecleach:
            zp, rp = _core.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
        elif is_exp:
            zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
        ir_mouth = _r_to_circumradius(np.array([rp.max()]), n_sides)[0]
        _get_mid_r = lambda pct: _r_to_circumradius(np.array([rp[int(len(rp)*pct/100)]]), n_sides)[0]
    elif is_radial:
        ir_throat = throat_d / 2; ir_mouth = mouth_d / 2
        _get_mid_r = lambda pct: None
    elif is_tractrix:
        ir_throat = throat_d / 2; ir_mouth = mouth_d / 2
        zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
        _get_mid_r = lambda pct: rp[int(np.searchsorted(zp, zp[-1]*pct/100))]
    elif is_exp:
        zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
        ir_throat = throat_d / 2; ir_mouth = rp.max()
        _get_mid_r = lambda pct: rp[min(int(np.searchsorted(zp, zp[-1]*pct/100)), len(rp)-1)]
    else:  # salmon / iwata / lecleach
        if is_salmon:
            zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
        elif is_iwata:
            zp, rp = _core.get_iwata(throat_d, fc, axial_len, segments)
        else:
            zp, rp = _core.get_lecleach(throat_d, fc, axial_len, segments, T=salmon_T)
        ir_throat = throat_d / 2; ir_mouth = rp.max()
        _z_len = zp.max()  # for roll-back profiles, use max z (axial extent)
        _get_mid_r = lambda pct, _zp=zp, _rp=rp, _zl=_z_len: _rp[np.argmin(np.abs(_zp - _zl*pct/100))]

    return ir_throat, ir_mouth, _get_mid_r


ir_throat, ir_mouth, _get_mid_r = _calc_flange_dims()

if st.button("🔧 Recalculate flanges", use_container_width=True,
             help="Update all flange diameters based on current horn parameters"):
    _on_horn_change()
    st.toast("Flanges recalculated", icon="✅")

# Common bolt defaults
_bolt_n = 4
_bolt_d = 3.5
_flange_sp = 6.0


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
    and without resizing the flange. (Polygons: the binding edge is the inradius.)
    """
    outer_lim = flange_R * np.cos(np.pi / outer_n) if outer_n >= 3 else flange_R
    lo = max(10.0, 2.0 * (inner_R + bolt_d / 2.0 + 1.0))
    hi = 2.0 * (outer_lim - bolt_d / 2.0 - 1.0)
    if hi <= lo:                 # ring too thin to seat a bolt clear of both edges
        hi = lo + 2.0
    return lo, hi


# --- Flange inputs (3 columns) ---
fg1, fg2, fg3 = st.columns(3)

with fg1:
    st.markdown("##### Throat Flange")
    if is_radial:
        st.caption("Mounting holes on bottom plate")
        gen_throat = st.checkbox("Include", True, key="gen_throat")
        _ft_nb    = st.number_input("Bolt count", 2, 24, _bolt_n, 1, key="ft_nb")
        _ft_db    = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="ft_db")
        _ft_bc_lo, _ft_bc_hi = float(throat_d), float(mouth_d * 0.95)
        if "ft_bc_rad" not in st.session_state:
            st.session_state["ft_bc_rad"] = float(mouth_d * 0.7)
        _clamp_state("ft_bc_rad", _ft_bc_lo, _ft_bc_hi)
        _ft_bc    = st.number_input("Bolt circle Ø (mm)", _ft_bc_lo, _ft_bc_hi,
                                    step=1.0, key="ft_bc_rad")
        _ft_depth = st.number_input("Hole depth (mm)", 2.0, 30.0, 8.0, 0.5, key="ft_depth")
        _ft_sp = _ft_off = _ft_od = _ft_ow = _ft_oh = 0.0
        throat_outer = "Circular"
    else:
        gen_throat = st.checkbox("Include", True, key="gen_throat")
        _ft_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, _flange_sp, 0.5, key="ft_spess")
        _ft_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="ft_off")
        _ft_nb  = st.number_input("Bolt count", 2, 24, _bolt_n, 1, key="ft_nb")
        _ft_db  = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="ft_db")
        if is_poly:
            from polygonal_horn import _r_to_circumradius
            _R_poly_g     = _r_to_circumradius(np.array([throat_d/2]), n_sides)[0]
            _R_o_g_approx = _R_poly_g + thickness / np.cos(np.pi / n_sides)
            _ft_inner_R   = _R_o_g_approx
            st.caption(f"Hole: {n_sides}-gon, R={_ft_inner_R:.1f} mm")
        else:
            _ft_inner_R = throat_d / 2 + thickness
            st.caption(f"Hole: Ø{_ft_inner_R*2:.0f} mm (circular)")
        throat_outer = st.radio("Outer shape", ["Circular", "Polygonal"],
                             index=0, horizontal=True, key="throat_outer")
        _ft_outer_n = (st.select_slider("Outer sides", options=list(range(3, 13)),
                                        value=n_sides, key="ft_outer_n")
                       if throat_outer == "Polygonal" else 0)
        _ft_ring = st.number_input("Ring width (mm)", 5.0, 200.0, 15.0, 1.0, key="ft_ring",
            help="Wall around the hole — this sets the flange size. Widen it to fit bolts further out.")
        _ft_flange_R = _flange_R_from_ring(_ft_inner_R, _ft_ring, _ft_outer_n)
        _ft_od = _ft_flange_R * 2
        if _ft_outer_n >= 3:
            st.caption(f"Across corners Ø: {_ft_od:.1f} mm · flats wall {_ft_ring:.0f} mm")
        else:
            st.caption(f"Outer Ø: {_ft_od:.1f} mm")
        # Bolt circle constrained to the ring band — holes stay inside, flange fixed.
        _ft_bc_lo, _ft_bc_hi = _bolt_circle_band(_ft_inner_R, _ft_flange_R, _ft_db, _ft_outer_n)
        if "ft_bc" not in st.session_state:
            st.session_state["ft_bc"] = float((_ft_bc_lo + _ft_bc_hi) / 2.0)
        _clamp_state("ft_bc", _ft_bc_lo, _ft_bc_hi)
        _ft_bc = st.number_input("Bolt circle Ø (mm)", _ft_bc_lo, _ft_bc_hi,
            step=1.0, key="ft_bc")
        _ft_depth = 0.0

with fg2:
    st.markdown("##### Mouth Flange")
    if is_radial or is_lecleach:
        gen_mouth = False
        _fm_sp = _fm_off = _fm_nb = _fm_db = _fm_od = _fm_bc = _fm_ow = _fm_oh = 0.0
        mouth_outer = "Circular"
        if is_radial:
            st.caption("Not available for radial profile")
        else:
            st.caption("Not available — use Mid Flange instead")
    else:
        gen_mouth = st.checkbox("Include", True, key="gen_mouth")
        _fm_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, _flange_sp, 0.5, key="fm_spess")
        _fm_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="fm_off")
        _fm_nb  = st.number_input("Bolt count", 2, 24, _bolt_n, 1, key="fm_nb")
        _fm_db  = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="fm_db")
        if is_poly:
            _fm_inner_R = ir_mouth
            st.caption(f"Hole: {n_sides}-gon, R≈{_fm_inner_R:.0f} mm")
        else:
            _fm_inner_R = ir_mouth + thickness
            _fm_prof_R  = ir_mouth  # inner profile radius (without wall)
            st.caption(f"Hole: Ø{_fm_prof_R*2:.0f} mm (circular)")
        _mouth_outer_default = 1 if is_poly else 0
        mouth_outer = st.radio("Outer shape", ["Circular", "Polygonal"],
                              index=_mouth_outer_default, horizontal=True, key="mouth_outer")
        _fm_outer_n = (st.select_slider("Outer sides", options=list(range(3, 13)),
                                        value=n_sides, key="fm_outer_n")
                       if mouth_outer == "Polygonal" else 0)
        _fm_ring = st.number_input("Ring width (mm)", 5.0, 200.0, 15.0, 1.0, key="fm_ring",
            help="Wall around the hole — this sets the flange size.")
        _fm_flange_R = _flange_R_from_ring(ir_mouth, _fm_ring, _fm_outer_n)
        _fm_hole_R   = ir_mouth
        _fm_od = _fm_flange_R * 2
        if _fm_outer_n >= 3:
            st.caption(f"Across corners Ø: {_fm_od:.1f} mm · flats wall {_fm_ring:.0f} mm")
        else:
            st.caption(f"Outer Ø: {_fm_od:.1f} mm")
        _fm_ow = _fm_od; _fm_oh = _fm_od
        _fm_bc_lo, _fm_bc_hi = _bolt_circle_band(_fm_hole_R, _fm_flange_R, _fm_db, _fm_outer_n)
        if "fm_bc" not in st.session_state:
            st.session_state["fm_bc"] = float((_fm_bc_lo + _fm_bc_hi) / 2.0)
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
        _mid_nb = st.number_input("Bolt count", 2, 24, _bolt_n, 1, key="mid_nb")
        _mid_db = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="mid_db")
        _mid_pct = min(100.0, _mid_pos / max(_len or 1, 1) * 100)
        mid_r = _get_mid_r(_mid_pct) if _len else 10
        if is_poly:
            _mid_inner_R = mid_r
            st.caption(f"Hole: {n_sides}-gon, R≈{_mid_inner_R:.0f} mm")
        else:
            _mid_inner_R = mid_r + thickness
            st.caption(f"Hole: Ø{_mid_inner_R*2:.0f} mm (circular)")
        _mid_outer_default = 1 if is_poly else 0
        mid_out = st.radio("Outer shape", ["Circular", "Polygonal"],
                            index=_mid_outer_default, horizontal=True, key="mid_out")
        _mid_outer_n = (st.select_slider("Outer sides", options=list(range(3, 13)),
                                         value=n_sides, key="mid_outer_n")
                        if mid_out == "Polygonal" else 0)
        _mid_ring = st.number_input("Ring width (mm)", 5.0, 200.0, 15.0, 1.0, key="mid_ring",
            help="Wall around the hole — this sets the flange size. Widen it to fit bolts further out.")
        _mid_flange_R = _flange_R_from_ring(_mid_inner_R, _mid_ring, _mid_outer_n)
        _mid_od = _mid_flange_R * 2
        if _mid_outer_n >= 3:
            st.caption(f"Across corners Ø: {_mid_od:.1f} mm · flats wall {_mid_ring:.0f} mm")
        else:
            st.caption(f"Outer Ø: {_mid_od:.1f} mm")
        _mid_bc_lo, _mid_bc_hi = _bolt_circle_band(_mid_inner_R, _mid_flange_R, _mid_db, _mid_outer_n)
        if "mid_bc" not in st.session_state:
            st.session_state["mid_bc"] = float((_mid_bc_lo + _mid_bc_hi) / 2.0)
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
                elif is_iwata:
                    zp, rp = C.get_iwata(throat_d, fc, axial_len, segments)
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
            else:
                if is_tractrix:
                    zp, rp = C.get_tractrix(throat_d, mouth_d, segments)
                elif is_salmon:
                    zp, rp = C.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
                elif is_iwata:
                    zp, rp = C.get_iwata(throat_d, fc, axial_len, segments)
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
                if is_poly:
                    f_throat = _fg.generate_polygonal_flange(
                        inner_circumR=_R_o_throat_poly, n_sides=n_sides,
                        flange_R=_ft_od/2,
                        thickness=_ft_sp, bolt_R=_ft_bc/2,
                        bolt_n=int(_ft_nb), bolt_d=_ft_db,
                        offset=z_min + _ft_off + _ft_sp,
                        outer_n_sides=_ft_outer_n)
                else:
                    f_throat = _fg.generate_flange(
                        throat_R=fiw_g/2, flange_R=_ft_od/2,
                        thickness=_ft_sp, bolt_R=_ft_bc/2,
                        bolt_n=int(_ft_nb), bolt_d=_ft_db,
                        offset=z_min + _ft_off + _ft_sp,
                        outer_n_sides=_ft_outer_n,
                        output_path=None)

            if gen_mouth and not is_radial:
                if is_poly:
                    f_mouth = _fg.generate_polygonal_flange(
                        inner_circumR=_R_o_mouth_poly, n_sides=n_sides,
                        flange_R=_fm_od/2,
                        thickness=_fm_sp, bolt_R=_fm_bc/2,
                        bolt_n=int(_fm_nb), bolt_d=_fm_db,
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
                        offset=z_mouth + _fm_off,
                        outer_n_sides=_fm_outer_n,
                        output_path=None)

            if gen_mid and not is_radial:
                z_mid = z_min + _mid_pos + _mid_off
                if is_poly:
                    _R_o_mid_poly = float(np.interp(_mid_pos, zp, _R_o_arr))
                    f_mid = _fg.generate_polygonal_flange(
                        inner_circumR=_R_o_mid_poly, n_sides=n_sides,
                        flange_R=_mid_od/2,
                        thickness=_mid_sp, bolt_R=_mid_bc/2,
                        bolt_n=int(_mid_nb), bolt_d=_mid_db,
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

ax_mode = st.radio("Define segments by", ["Count", "Height (mm)"],
                   horizontal=True, key="ax_mode")
if ax_mode == "Count":
    n_ax = st.number_input("Number of axial segments", 1, 50, 4, step=1, key="n_ax")
    seg_ref = ("count", n_ax)
else:
    seg_h = st.number_input("Segment height (mm)", 5, 500, 50, step=5, key="seg_h")
    total_z = mesh_to_slice.bounds[1, 2] - mesh_to_slice.bounds[0, 2]
    n_ax_auto = max(1, int(round(total_z / seg_h)))
    st.caption(f"Total Z={total_z:.0f} mm → ~{n_ax_auto} segments")
    seg_ref = ("height", seg_h)

if st.button("❶ Slice axially", use_container_width=True):
    with st.spinner("Cutting axially…"):
        if seg_ref[0] == "count":
            n = seg_ref[1]
            if n <= 1:
                st.session_state["_ax_segs"] = [mesh_to_slice]
            else:
                st.session_state["_ax_segs"] = _slc.slice_into_segments(mesh_to_slice, n)
        else:
            dz = seg_ref[1]
            z0, z1 = mesh_to_slice.bounds[0, 2], mesh_to_slice.bounds[1, 2]
            n = max(1, int(round((z1 - z0) / dz)))
            if n <= 1:
                st.session_state["_ax_segs"] = [mesh_to_slice]
            else:
                st.session_state["_ax_segs"] = _slc.slice_into_segments(mesh_to_slice, n)
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

    if st.button("❷ Apply petals", use_container_width=True):
        with st.spinner("Cutting petals…"):
            pieces = []
            for ai, (seg, np_) in enumerate(zip(ax_segs, petals_per)):
                if np_ > 1:
                    pets = _slc.slice_into_petals(seg, np_)
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
