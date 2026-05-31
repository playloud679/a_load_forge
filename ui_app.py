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
from _step_export import export_step

import importlib
importlib.reload(_core)
importlib.reload(_fg)
importlib.reload(_rf)
importlib.reload(_rh)
importlib.reload(_rd)

st.set_page_config(page_title="flare_forge", layout="wide",
    initial_sidebar_state="collapsed", menu_items={})

# ── Flange recalculation callback ────────────────────────────────────

def _on_horn_change():
    """Recalculate geometry-dependent flange defaults when horn changes."""
    for _k in ("ft_od", "ft_bc", "ft_ow", "ft_oh",
               "fm_od", "fm_bc", "fm_ow", "fm_oh",
               "mid_od", "mid_bc", "mid_ow", "mid_oh"):
        st.session_state.pop(_k, None)

st.title("flare_forge")
st.caption("Acoustic profile + mounting flanges · watertight assembly for 3D printing")

# ═══════════════════════════════════════════════════════════════════════
#  ROW 1 — Horn Profile (Left) + Live 2D Preview (Right)
# ═══════════════════════════════════════════════════════════════════════

def _get_rect_profile(n=300):
    if is_exp:
        return _rh.get_rectangular_exponential(throat_w, throat_h, mouth_w, fc, n)
    elif is_tractrix:
        return _rh.get_rectangular_tractrix(throat_w, throat_h, mouth_w, n)
    elif is_lecleach:
        return _rh.get_rectangular_lecleach(throat_w, throat_h, fc, n)
    else:
        return _rh.get_rectangular_iwata(throat_w, throat_h, fc, axial_len, n)


col_prof, col_prev = st.columns([2, 3])

with col_prof:
    st.subheader("Acoustic Profile")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        profile_type = st.selectbox("Profile",
            ["Tractrix", "Le Cléac'h", "Iwata", "Exponential", "Radial 360°"], index=0,
            on_change=_on_horn_change, key="profile_type")
    with c2:
        section_type = st.radio("Section", ["Circular", "Rectangular"],
                          index=0, horizontal=True, key="section_type",
                          disabled=profile_type.startswith("Rad"),
                          on_change=_on_horn_change)
    with c3:
        thickness = st.number_input("Wall thickness (mm)", 1.0, 20.0, 4.0, 0.5,
            help="Uniform thickness applied along the profile normal",
            on_change=_on_horn_change, key="thickness")
    with c4:
        segments = st.number_input("Profile points", 100, 50000, 300, 50)

    is_radial   = profile_type.startswith("Rad")
    is_rect     = section_type == "Rectangular" and not is_radial
    is_tractrix = profile_type.startswith("Tract")
    is_lecleach = profile_type.startswith("Le Clé")
    is_iwata    = profile_type.startswith("Iwata")
    is_exp      = profile_type.startswith("Exp")
    has_fc      = is_lecleach or is_iwata or is_exp or is_radial

    st.markdown("##### Dimensions")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        if is_rect:
            throat_w = st.number_input("Throat width (mm)", 4.0, 200.0, 20.0, 1.0)
            throat_h = st.number_input("Throat height (mm)", 2.0, 200.0, 10.0, 1.0)
        elif is_radial:
            throat_d = st.number_input("Throat Ø (mm)", 5.0, 100.0, 25.0, 1.0)
        else:
            throat_d = st.number_input("Throat Ø (mm)", 2.0, 200.0, 20.0, 1.0)
    with d2:
        if is_rect:
            if is_tractrix or is_exp:
                mouth_w = st.number_input("Mouth width (mm)", 10.0, 500.0, 160.0, 5.0)
            else:
                st.caption("Mouth — computed")
        elif is_radial or is_tractrix:
            mouth_d = st.number_input("Mouth Ø (mm)", 4.0, 500.0,
                                      100.0 if is_tractrix else 200.0, 5.0)
        else:
            st.caption("Mouth — computed from Fc")
    with d3:
        if has_fc:
            fc = st.number_input("Cutoff frequency Fc (Hz)", 50, 20000, 600, 50,
                help="Sets the flare rate (m = 4π·fc / c₀)")
        else:
            fc = None; st.caption("—")
    with d4:
        if is_rect and is_exp:
            pass  # exponential: mouth_w determines length
        elif is_iwata:
            axial_len = st.number_input("Axial length (mm)", 10.0, 500.0, 80.0, 5.0)
        else:
            st.caption("—")

    # Derived metrics
    try:
        if is_radial:
            _len = _mouth = _fc = None
        elif is_rect:
            zp, wp, hp = _get_rect_profile(segments)
            _len = zp[-1]; _mouth = f"{wp[-1]:.0f}×{hp[-1]:.0f}"; _fc = None
        elif is_tractrix:
            zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
            _len = zp[-1]; _mouth = f"Ø{rp[-1]*2:.0f}"; _fc = 343_000 / (np.pi * mouth_d)
        elif is_lecleach:
            zp, rp = _core.get_lecleach(throat_d, fc, segments)
            mi = int(np.argmax(zp)); _len = zp.max(); _mouth = f"Ø{rp[mi]*2:.0f}"; _fc = None
        elif is_iwata:
            zp, rp = _core.get_iwata(throat_d, fc, axial_len, segments)
            _len = axial_len; _mouth = f"Ø{rp.max()*2:.0f}"; _fc = None
        _m = []
        if _len:  _m.append(f"Length = {_len:.0f} mm")
        if _mouth: _m.append(f"Mouth {_mouth}")
        if _fc:   _m.append(f"Fc = {_fc:.0f} Hz")
        if _m: st.caption(" · ".join(_m))
    except Exception:
        _len = _mouth = _fc = None

with col_prev:
    st.subheader("2D Preview — Cross-section")

    try:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        if is_rect:
            zp, wp, hp = _get_rect_profile(segments)
            ax.plot(zp, wp/2, label="Half width", c="#2196F3")
            ax.plot(zp, hp/2, label="Half height", c="#FF5722")
            ax.plot(zp, wp/2+thickness, "--", c="#2196F3", alpha=.4)
            ax.plot(zp, hp/2+thickness, "--", c="#FF5722", alpha=.4)
        elif is_radial:
            Rr, Zb, Zt = _rd.get_radial_profiles(throat_d, mouth_d, fc, segments)
            ax.plot(Rr, Zb, label="Bottom deflector", c="#FF5722")
            ax.plot(Rr, Zt, label="Top reflector", c="#2196F3")
            ax.fill_between(Rr, Zb, Zt, alpha=.15, color="#4CAF50")
            ax.set_xlabel("R (mm)")
        else:
            if is_tractrix:
                zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
            elif is_lecleach:
                zp, rp = _core.get_lecleach(throat_d, fc, segments)
            else:
                zp, rp = _core.get_iwata(throat_d, fc, axial_len, segments)
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
    if is_rect:
        ir_throat = max(throat_w, throat_h) / 2
        zp, wp, hp = _get_rect_profile(segments)
        ir_mouth = max(wp[-1], hp[-1]) / 2
        _get_mid_r = lambda pct: max(
            wp[int(np.searchsorted(zp, zp[-1]*pct/100))],
            hp[int(np.searchsorted(zp, zp[-1]*pct/100))]
        ) / 2
    elif is_radial:
        ir_throat = throat_d / 2; ir_mouth = mouth_d / 2
        _get_mid_r = lambda pct: None
    elif is_tractrix:
        ir_throat = throat_d / 2; ir_mouth = mouth_d / 2
        zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
        _get_mid_r = lambda pct: rp[int(np.searchsorted(zp, zp[-1]*pct/100))]
    elif is_lecleach:
        zp, rp = _core.get_lecleach(throat_d, fc, segments)
        ir_throat = throat_d / 2; ir_mouth = rp.max()
        _zmax = zp.max(); _zmax_idx = int(np.argmax(zp))
        _zmono, _rmono = zp[:_zmax_idx+1], rp[:_zmax_idx+1]
        _get_mid_r = lambda pct: np.interp(_zmax * pct / 100.0, _zmono, _rmono)
    else:  # iwata
        zp, rp = _core.get_iwata(throat_d, fc, axial_len, segments)
        ir_throat = throat_d / 2; ir_mouth = rp.max()
        _get_mid_r = lambda pct: rp[int(np.searchsorted(zp, zp[-1]*pct/100))]

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

# --- Flange inputs (3 columns) ---
fg1, fg2, fg3 = st.columns(3)

with fg1:
    st.markdown("##### Throat Flange")
    gen_throat = st.checkbox("Include", True, key="gen_throat")
    _ft_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, _flange_sp, 0.5, key="ft_spess")
    _ft_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="ft_off")
    _ft_nb  = st.number_input("Bolt count", 2, 24, _bolt_n, 1, key="ft_nb")
    _ft_db  = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="ft_db")
    if is_rect:
        r_corner_g    = np.sqrt((max(throat_w, throat_h)/2)**2 + (min(throat_w, throat_h)/2)**2)
        r_horn_outer_g = r_corner_g + thickness
        _ft_od = (r_horn_outer_g + 15.0) * 2.0
        _ft_bc = r_horn_outer_g + _ft_od / 2.0
        st.caption(f"Hole: {max(throat_w,throat_h):.0f}×{min(throat_w,throat_h):.0f} mm (rectangular)")
    else:
        _ft_od = (throat_d/2 + thickness) * 2 + 20
        _ft_bc = throat_d/2 + thickness + _ft_od / 2
        st.caption(f"Hole: Ø{throat_d + thickness*2:.0f} mm (circular)")
    _ft_ow = _ft_od
    _ft_oh = _ft_od
    throat_outer = st.radio("Outer shape", ["Circular", "Rectangular"],
                         index=1 if is_rect else 0, horizontal=True, key="throat_outer")
    if throat_outer == "Rectangular":
        _ft_ow = st.number_input("Width (mm)",  10.0, 300.0, _ft_ow, 1.0, key="ft_ow")
        _ft_oh = st.number_input("Height (mm)", 10.0, 300.0, _ft_oh, 1.0, key="ft_oh")
    else:
        _ft_od = st.number_input("Outer Ø (mm)",       10.0, 300.0, _ft_od, 1.0, key="ft_od")
        _ft_bc = st.number_input("Bolt circle Ø (mm)", 10.0, 280.0, _ft_bc, 1.0, key="ft_bc")

with fg2:
    st.markdown("##### Mouth Flange")
    gen_mouth = st.checkbox("Include", True, key="gen_mouth")
    _fm_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, _flange_sp, 0.5, key="fm_spess")
    _fm_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="fm_off")
    _fm_nb  = st.number_input("Bolt count", 2, 24, _bolt_n, 1, key="fm_nb")
    _fm_db  = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="fm_db")
    if is_rect:
        zp, wp, hp = _get_rect_profile(segments)
        fm_hole_w = wp[-1] + thickness * 2
        fm_hole_h = hp[-1] + thickness * 2
        if is_lecleach:
            _fm_od = fm_hole_w - 20
            _fm_ow = fm_hole_w - 20
            _fm_oh = fm_hole_h - 20
            _fm_bc = fm_hole_w - 30
        else:
            r_corner_m = np.sqrt((fm_hole_w/2)**2 + (fm_hole_h/2)**2)
            _fm_od = (r_corner_m + 15.0) * 2.0
            _fm_ow = _fm_od
            _fm_oh = _fm_od * fm_hole_h / fm_hole_w
            _fm_bc = r_corner_m + _fm_od / 2.0
        st.caption(f"Hole: {fm_hole_w:.0f}×{fm_hole_h:.0f} mm (rectangular)")
    elif is_lecleach:
        _fm_od = ir_mouth * 2
        _fm_bc = _fm_od - 20
        _fm_ow = _fm_od
        _fm_oh = _fm_od
        st.caption(f"Hole: Ø{ir_mouth*2 + thickness*2:.0f} mm (circular)")
    else:
        _fm_od = (ir_mouth + thickness) * 2 + 20
        _fm_bc = ir_mouth + thickness + _fm_od / 2
        _fm_ow = _fm_od
        _fm_oh = _fm_od
        st.caption(f"Hole: Ø{ir_mouth*2 + thickness*2:.0f} mm (circular)")
    mouth_outer = st.radio("Outer shape", ["Circular", "Rectangular"],
                          index=1 if is_rect else 0, horizontal=True, key="mouth_outer")
    if mouth_outer == "Rectangular":
        _fm_ow = st.number_input("Width (mm)",  10.0, 1000.0, _fm_ow, 1.0, key="fm_ow")
        _fm_oh = st.number_input("Height (mm)", 10.0, 1000.0, _fm_oh, 1.0, key="fm_oh")
    else:
        _fm_od = st.number_input("Outer Ø (mm)",       10.0, 1000.0, _fm_od, 1.0, key="fm_od")
        _fm_bc = st.number_input("Bolt circle Ø (mm)", 10.0,  980.0, _fm_bc, 1.0, key="fm_bc")

with fg3:
    st.markdown("##### Mid Flange")
    if is_radial:
        gen_mid = False; _mid_pos = 50
        st.caption("Not available for radial profile")
    else:
        gen_mid = st.checkbox("Include", False, key="gen_mid")
        _mid_pos = st.number_input("Distance from throat (mm)", 5.0, 2000.0,
            max(5.0, (_len or 200) * 0.5), 5.0, key="mid_z")
        _mid_sp = st.number_input("Thickness (mm)", 2.0, 20.0, 4.0, 0.5, key="mid_spess")
        _mid_nb = st.number_input("Bolt count", 2, 24, _bolt_n, 1, key="mid_nb")
        _mid_db = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="mid_db")
        if is_rect:
            zp, wp, hp = _get_rect_profile(segments)
            _idx   = min(int(np.searchsorted(zp, _mid_pos)), len(zp)-1)
            _w_mid = wp[_idx] + thickness * 2
            _h_mid = hp[_idx] + thickness * 2
            r_corner_mid = np.sqrt((_w_mid / 2.0)**2 + (_h_mid / 2.0)**2)
            _mid_od = (r_corner_mid + 15.0) * 2.0
            _mid_ow = _mid_od
            _mid_oh = _mid_od * _h_mid / _w_mid
            _mid_bc = r_corner_mid + _mid_od / 2.0
            st.caption(f"Hole: {_w_mid:.0f}×{_h_mid:.0f} mm (rectangular)")
        else:
            mid_r    = _get_mid_r(_mid_pos / max(_len or 1, 1) * 100) if _len else 10
            mid_wall = mid_r + thickness
            mid_hole = mid_wall * 2
            _mid_od  = mid_hole + 20
            _mid_bc  = mid_wall + _mid_od / 2
            _mid_ow  = _mid_od
            _mid_oh  = _mid_od
            st.caption(f"Hole: Ø{mid_hole:.0f} mm (circular)")
        mid_out = st.radio("Outer shape", ["Circular", "Rectangular"],
                            index=1 if is_rect else 0, horizontal=True, key="mid_out")
        if mid_out == "Rectangular":
            _mid_ow = st.number_input("Width (mm)",  10.0, 1000.0, _mid_ow, 1.0, key="mid_ow")
            _mid_oh = st.number_input("Height (mm)", 10.0, 1000.0, _mid_oh, 1.0, key="mid_oh")
        else:
            _mid_od = st.number_input("Outer Ø (mm)",       10.0, 1000.0, _mid_od, 1.0, key="mid_od")
            _mid_bc = st.number_input("Bolt circle Ø (mm)", 10.0,  980.0, _mid_bc, 1.0, key="mid_bc")

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
            if is_rect:
                z, w, h = _get_rect_profile(segments)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                _rh.generate_rectangular_3d_mesh(z, w, h, thickness, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                mouth_bx = w[-1] + thickness * 2
                mouth_by = h[-1] + thickness * 2
            elif is_radial:
                with tempfile.TemporaryDirectory() as _tmp:
                    _rd.generate_radial_horn(throat_d, mouth_d, fc, 48, _tmp)
                    horn = _tm.load(os.path.join(_tmp, "radial_bottom.stl"), file_type="stl")
                    R, Zb, Zt = _rd.get_radial_profiles(throat_d, mouth_d, fc, segments)
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
                elif is_lecleach:
                    zp, rp = C.get_lecleach(throat_d, fc, segments)
                else:
                    zp, rp = C.get_iwata(throat_d, fc, axial_len, segments)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                C.generate_3d_mesh_from_profile(zp, rp, thickness, 64, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                mouth_bx = mouth_by = (rp[-1] + thickness) * 2 if not is_lecleach else ir_mouth * 2

            z_min = horn.vertices[:,2].min()

            # --- 3b. Throat hole — analytical ---
            if is_rect:
                fiw_g = throat_w + thickness * 2
                fih_g = throat_h + thickness * 2
            else:
                fiw_g = fih_g = throat_d + thickness * 2

            # --- 3c. Exact mouth dimensions ---
            if is_rect:
                zp, wp, hp = _get_rect_profile(segments)
                fiw_m = wp[-1] + thickness * 2
                fih_m = hp[-1] + thickness * 2
                z_mouth = zp[-1]
            elif is_radial:
                fiw_m = fih_m = mouth_d
                z_mouth = 0.0
            else:
                fiw_m = fih_m = rp[-1] * 2
                z_mouth = zp[-1]

            if is_lecleach:
                if is_rect:
                    _shrink = 40
                    ratio = fih_m / fiw_m if fiw_m > 0 else 1
                    fiw_m -= _shrink
                    fih_m = fiw_m * ratio
                else:
                    fiw_m -= 30.0

            # --- 3d. Generate flanges ---
            f_throat = f_mouth = f_mid = None

            if gen_throat and not is_radial:
                if is_rect:
                    f_throat = _rf.generate_rectangular_flange(
                        outer_diam=_ft_od, inner_w=fiw_g, inner_h=fih_g,
                        thickness=_ft_sp, bolt_radius=_ft_bc/2,
                        bolt_count=int(_ft_nb), bolt_diam=_ft_db,
                        outer_type="circular" if throat_outer == "Circular" else "rectangular",
                        outer_w=_ft_ow if throat_outer == "Rectangular" else None,
                        outer_h=_ft_oh if throat_outer == "Rectangular" else None,
                        offset=z_min + _ft_off, output_path=None)
                else:
                    _tr = fiw_g / 2
                    f_throat = _fg.generate_flange(
                        throat_R=_tr, flange_R=_ft_od/2,
                        thickness=_ft_sp, bolt_R=_ft_bc/2,
                        bolt_n=int(_ft_nb), bolt_d=_ft_db,
                        offset=z_min + _ft_off + _ft_sp)

            if gen_mouth and not is_radial:
                if is_rect:
                    f_mouth = _rf.generate_rectangular_flange(
                        outer_diam=_fm_od, inner_w=fiw_m, inner_h=fih_m,
                        thickness=_fm_sp, bolt_radius=_fm_bc/2,
                        bolt_count=int(_fm_nb), bolt_diam=_fm_db,
                        outer_type="circular" if mouth_outer == "Circular" else "rectangular",
                        outer_w=_fm_ow if mouth_outer == "Rectangular" else None,
                        outer_h=_fm_oh if mouth_outer == "Rectangular" else None,
                        offset=z_mouth + _fm_off - _fm_sp, output_path=None)
                else:
                    _R    = _fm_od / 2.0
                    _tr_m = fiw_m / 2.0
                    if is_lecleach:
                        _R    = min(_R, rp.max())
                        _tr_m = min(_tr_m, _R - 5.0)
                    f_mouth = _fg.generate_flange(
                        throat_R=_tr_m, flange_R=_R,
                        thickness=_fm_sp, bolt_R=_fm_bc/2,
                        bolt_n=int(_fm_nb), bolt_d=_fm_db,
                        offset=z_mouth + _fm_off)

            if gen_mid and not is_radial:
                z_mid = z_min + _mid_pos
                if is_rect:
                    zp, wp, hp = _get_rect_profile(segments)
                    _idx    = min(int(np.searchsorted(zp, _mid_pos)), len(zp)-1)
                    fiw_mid = wp[_idx] + thickness * 2
                    fih_mid = hp[_idx] + thickness * 2
                    f_mid = _rf.generate_rectangular_flange(
                        outer_diam=_mid_od, inner_w=fiw_mid, inner_h=fih_mid,
                        thickness=_mid_sp, bolt_radius=_mid_bc/2,
                        bolt_count=int(_mid_nb), bolt_diam=_mid_db,
                        outer_type="circular" if mid_out == "Circular" else "rectangular",
                        outer_w=_mid_ow if mid_out == "Rectangular" else None,
                        outer_h=_mid_oh if mid_out == "Rectangular" else None,
                        offset=z_mid - _mid_sp, output_path=None)
                else:
                    mid_r   = _get_mid_r(_mid_pos / max(_len or 1, 1) * 100) if _len else 10
                    fiw_mid = (mid_r + thickness) * 2
                    f_mid = _fg.generate_flange(
                        throat_R=fiw_mid/2, flange_R=_mid_od/2,
                        thickness=_mid_sp, bolt_R=_mid_bc/2,
                        bolt_n=int(_mid_nb), bolt_d=_mid_db,
                        offset=z_mid)

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

            if is_rect:
                combined = _tm.util.concatenate(bodies)
            elif len(bodies) == 1:
                combined = bodies[0]
            else:
                try:
                    combined = _tm.boolean.union(bodies, engine="manifold")
                except Exception:
                    combined = _tm.util.concatenate(bodies)

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
