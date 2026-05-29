"""
Horn Generator — Dashboard monotab professionale.
Layout: Profilo (sx) + Anteprima 2D (dx) | Flange | Generazione Assembly.
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

st.set_page_config(page_title="Generatore di Trombe", layout="wide",
    initial_sidebar_state="collapsed", menu_items={})

# ── Flange recalculation callback ────────────────────────────────────

def _on_horn_change():
    """Recalculate geometry-dependent flange defaults when horn changes."""
    for _k in ("fg_od", "fg_bc", "fg_ow", "fg_oh",
               "fm_od", "fm_bc", "fm_ow", "fm_oh",
               "mid_od", "mid_bc", "mid_ow", "mid_oh"):
        st.session_state.pop(_k, None)

st.title("Generatore di Trombe Acustiche")
st.caption("Profilo acustico + flange di montaggio · assembly watertight per stampa 3D")

# ═══════════════════════════════════════════════════════════════════════
#  ROW 1 — Horn Profile (Left) + Live 2D Preview (Right)
# ═══════════════════════════════════════════════════════════════════════

col_prof, col_prev = st.columns([2, 3])

with col_prof:
    st.subheader("Profilo Acustico")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        espansione = st.selectbox("Espansione",
            ["Tractrix", "Le Cléac'h", "Iwata", "Esponenziale", "Radiale 360°"], index=0,
            on_change=_on_horn_change, key="espansione")
    with c2:
        sezione = st.radio("Sezione", ["Circolare", "Rettangolare"],
                          index=0, horizontal=True, key="sezione",
                          disabled=espansione.startswith("Rad"),
                          on_change=_on_horn_change)
    with c3:
        spessore = st.number_input("Spessore parete (mm)", 1.0, 20.0, 4.0, 0.5,
            help="Spessore uniforme applicato lungo la normale del profilo",
            on_change=_on_horn_change, key="spessore")
    with c4:
        segmenti = st.number_input("Punti profilo", 100, 50000, 300, 50)

    is_radial = espansione.startswith("Rad")
    is_rect  = sezione == "Rettangolare" and not is_radial
    is_tractrix = espansione.startswith("Tract")
    is_lecleach = espansione.startswith("Le Clé")
    is_iwata    = espansione.startswith("Iwata")
    is_exp      = espansione.startswith("Espon")
    has_fc = is_lecleach or is_iwata or is_exp or is_radial

    st.markdown("##### Dimensioni")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        if is_rect:
            tw = st.number_input("Larghezza gola (mm)", 4.0, 200.0, 20.0, 1.0)
            th = st.number_input("Altezza gola (mm)", 2.0, 200.0, 10.0, 1.0)
        elif is_radial:
            td = st.number_input("Ø gola (mm)", 5.0, 100.0, 25.0, 1.0)
        else:
            td = st.number_input("Ø gola (mm)", 2.0, 200.0, 20.0, 1.0)
    with d2:
        if is_rect:
            if is_tractrix or is_exp:
                mw = st.number_input("Larghezza bocca (mm)", 10.0, 500.0, 160.0, 5.0)
            else:
                st.caption("Bocca — calcolata")
        elif is_radial or is_tractrix:
            md = st.number_input("Ø bocca (mm)", 4.0, 500.0, 100.0 if is_tractrix else 200.0, 5.0)
        else:
            st.caption("Bocca — calcolata da Fc")
    with d3:
        if has_fc:
            fc = st.number_input("Frequenza di taglio Fc (Hz)", 50, 20000, 600, 50,
                help="Determina il tasso di espansione (m = 4π·fc / c₀)")
        else:
            fc = None; st.caption("—")
    with d4:
        if is_rect and is_exp:
            pass  # exponential: mouth_w determines length
        elif is_iwata:
            ln = st.number_input("Lunghezza assiale (mm)", 10.0, 500.0, 80.0, 5.0)
        else:
            st.caption("—")

    # Derived metrics
    try:
        if is_radial:
            _len = _mouth = _fc = None
        elif is_rect:
            if is_exp:
                zp, wp, hp = _get_rect_profile(segmenti)
            elif is_tractrix:
                zp, wp, hp = _rh.get_rectangular_tractrix(tw, th, mw, segmenti)
            elif is_lecleach:
                zp, wp, hp = _rh.get_rectangular_lecleach(tw, th, fc, segmenti)
            else:
                zp, wp, hp = _rh.get_rectangular_iwata(tw, th, fc, ln, segmenti)
            _len = zp[-1]; _mouth = f"{wp[-1]:.0f}×{hp[-1]:.0f}"; _fc = None
        elif is_tractrix:
            zp, rp = _core.get_tractrix(td, md, segmenti)
            _len = zp[-1]; _mouth = f"Ø{rp[-1]*2:.0f}"; _fc = 343_000 / (np.pi * md)
        elif is_lecleach:
            zp, rp = _core.get_lecleach(td, fc, segmenti)
            mi = int(np.argmax(zp)); _len = zp.max(); _mouth = f"Ø{rp[mi]*2:.0f}"; _fc = None
        elif is_iwata:
            zp, rp = _core.get_iwata(td, fc, ln, segmenti)
            _len = ln; _mouth = f"Ø{rp.max()*2:.0f}"; _fc = None
        _m = []
        if _len: _m.append(f"Lunghezza = {_len:.0f} mm")
        if _mouth: _m.append(f"Bocca {_mouth}")
        if _fc: _m.append(f"Fc = {_fc:.0f} Hz")
        if _m: st.caption(" · ".join(_m))
    except Exception:
        _len = _mouth = _fc = None

with col_prev:
    st.subheader("Anteprima 2D — Sezione trasversale")

    try:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        if is_rect:
            zp, wp, hp = _get_rect_profile(segmenti)
            ax.plot(zp, wp/2, label="Mezza larghezza", c="#2196F3")
            ax.plot(zp, hp/2, label="Mezza altezza", c="#FF5722")
            ax.plot(zp, wp/2+spessore, "--", c="#2196F3", alpha=.4)
            ax.plot(zp, hp/2+spessore, "--", c="#FF5722", alpha=.4)
        elif is_radial:
            Rr, Zb, Zt = _rd.get_radial_profiles(td, md, fc, segmenti)
            ax.plot(Rr, Zb, label="Deflettore inf.", c="#FF5722")
            ax.plot(Rr, Zt, label="Riflettore sup.", c="#2196F3")
            ax.fill_between(Rr, Zb, Zt, alpha=.15, color="#4CAF50")
            ax.set_xlabel("R (mm)")
        elif is_rect:
            if is_exp:
                zp, wp, hp = _get_rect_profile(segmenti)
            elif is_tractrix:
                zp, wp, hp = _rh.get_rectangular_tractrix(tw, th, mw, segmenti)
            elif is_lecleach:
                zp, wp, hp = _rh.get_rectangular_lecleach(tw, th, fc, segmenti)
            else:
                zp, wp, hp = _rh.get_rectangular_iwata(tw, th, fc, ln, segmenti)
            ax.plot(zp, wp/2, label="Mezza larghezza", c="#2196F3")
            ax.plot(zp, hp/2, label="Mezza altezza", c="#FF5722")
            ax.plot(zp, wp/2+spessore, "--", c="#2196F3", alpha=.4)
            ax.plot(zp, hp/2+spessore, "--", c="#FF5722", alpha=.4)
        else:
            if is_tractrix:
                zp, rp = _core.get_tractrix(td, md, segmenti)
            elif is_lecleach:
                zp, rp = _core.get_lecleach(td, fc, segmenti)
            else:
                zp, rp = _core.get_iwata(td, fc, ln, segmenti)
            ax.plot(zp, rp, label="Profilo interno", c="#2196F3")
            ax.plot(zp, rp+spessore, "--", label="+ parete", c="#FF5722", alpha=.5)
            ax.set_xlabel("Z (mm)")
        ax.set_ylabel("R (mm)"); ax.legend(fontsize=8); ax.grid(True, alpha=.3)
        fig.tight_layout(); st.pyplot(fig)
        plt.close(fig)
    except Exception:
        st.info("Imposta i parametri del profilo per visualizzare l'anteprima")

# ═══════════════════════════════════════════════════════════════════════
#  ROW 2 — Flange di montaggio
# ═══════════════════════════════════════════════════════════════════════

st.divider()
st.subheader("Flange di Montaggio")

# Helper: get rectangular profile for current expansion
def _get_rect_profile(n=300):
    if is_exp:
        return _rh.get_rectangular_exponential(tw, th, mw, fc, n)
    elif is_tractrix:
        return _rh.get_rectangular_tractrix(tw, th, mw, n)
    elif is_lecleach:
        return _rh.get_rectangular_lecleach(tw, th, fc, n)
    else:
        return _rh.get_rectangular_iwata(tw, th, fc, ln, n)

# --- Auto-calculate flange dimensions from profile ---

def _calc_flange_dims():
    """Return suggested flange dimensions based on current horn profile."""
    if is_rect:
        ir_g = max(tw, th) / 2
        if is_exp:
            zp, wp, hp = _get_rect_profile(segmenti)
        elif is_tractrix:
            zp, wp, hp = _rh.get_rectangular_tractrix(tw, th, mw, segmenti)
        elif is_lecleach:
            zp, wp, hp = _rh.get_rectangular_lecleach(tw, th, fc, segmenti)
        else:
            zp, wp, hp = _rh.get_rectangular_iwata(tw, th, fc, ln, segmenti)
        ir_m = max(wp[-1], hp[-1]) / 2
        _get_mid_r = lambda pct: max(
            wp[int(np.searchsorted(zp, zp[-1]*pct/100))],
            hp[int(np.searchsorted(zp, zp[-1]*pct/100))]
        ) / 2
    elif is_radial:
        ir_g = td / 2; ir_m = md / 2
        _get_mid_r = lambda pct: None
    elif is_tractrix:
        ir_g = td / 2; ir_m = md / 2
        zp, rp = _core.get_tractrix(td, md, segmenti)
        _get_mid_r = lambda pct: rp[int(np.searchsorted(zp, zp[-1]*pct/100))]
    elif is_lecleach:
        zp, rp = _core.get_lecleach(td, fc, segmenti)
        ir_g = td / 2; ir_m = rp.max()
        _zmax = zp.max(); _zmax_idx = int(np.argmax(zp))
        _zmono, _rmono = zp[:_zmax_idx+1], rp[:_zmax_idx+1]
        _get_mid_r = lambda pct: np.interp(_zmax * pct / 100.0, _zmono, _rmono)
    else:  # iwata
        zp, rp = _core.get_iwata(td, fc, ln, segmenti)
        ir_g = td / 2; ir_m = rp.max()
        _get_mid_r = lambda pct: rp[int(np.searchsorted(zp, zp[-1]*pct/100))]

    return ir_g, ir_m, _get_mid_r


ir_g, ir_m, _get_mid_r = _calc_flange_dims()

if st.button("🔧 Ricalcola flange", use_container_width=True,
             help="Aggiorna tutti i diametri flange in base ai parametri attuali del corno"):
    _on_horn_change()

# Common bolt defaults
_bolt_n = 4
_bolt_d = 3.5
_flange_sp = 6.0

# --- Flange inputs (3 columns) ---
fg1, fg2, fg3 = st.columns(3)

with fg1:
    st.markdown("##### Flangia Gola")
    gen_gola = st.checkbox("Includi", True, key="gen_gola")
    _fg_sp = st.number_input("Spessore (mm)", 2.0, 20.0, _flange_sp, 0.5, key="fg_spess")
    _fg_off = st.number_input("Offset Z (mm)", -50.0, 50.0, 0.0, 0.5, key="fg_off")
    _fg_nb = st.number_input("N° bulloni", 2, 24, _bolt_n, 1, key="fg_nb")
    _fg_db = st.number_input("Ø foro bullone (mm)", 1.0, 12.0, _bolt_d, 0.1, key="fg_db")
    if is_rect:
        r_corner_g = np.sqrt((max(tw, th)/2)**2 + (min(tw, th)/2)**2)
        r_horn_outer_g = r_corner_g + spessore
        _fg_od = (r_horn_outer_g + 15.0) * 2.0
        _fg_bc = r_horn_outer_g + _fg_od / 2.0
        st.caption(f"Foro: {max(tw,th):.0f}×{min(tw,th):.0f} mm (rettangolare)")
    else:
        _fg_od = (td/2 + spessore) * 2 + 20
        _fg_bc = td/2 + spessore + _fg_od / 2
        st.caption(f"Foro: Ø{td + spessore*2:.0f} mm (circolare)")
    gola_out = st.radio("Esterno", ["Circolare", "Rettangolare"],
                         index=1 if is_rect else 0, horizontal=True, key="gola_out")
    if gola_out == "Rettangolare":
        if '_fg_ow' not in dir(): _fg_ow = _fg_od
        if '_fg_oh' not in dir(): _fg_oh = _fg_od
        _fg_ow = st.number_input("Larghezza (mm)", 10.0, 300.0, _fg_ow, 1.0, key="fg_ow")
        _fg_oh = st.number_input("Altezza (mm)", 10.0, 300.0, _fg_oh, 1.0, key="fg_oh")
    else:
        _fg_od = st.number_input("Ø esterno (mm)", 10.0, 300.0, _fg_od, 1.0, key="fg_od")
        _fg_bc = st.number_input("Ø cerchio fori (mm)", 10.0, 280.0, _fg_bc, 1.0, key="fg_bc")

with fg2:
    st.markdown("##### Flangia Bocca")
    gen_bocca = st.checkbox("Includi", True, key="gen_bocca")
    _fm_sp = st.number_input("Spessore (mm)", 2.0, 20.0, _flange_sp, 0.5, key="fm_spess")
    _fm_off = st.number_input("Offset Z (mm)", -50.0, 50.0, 0.0, 0.5, key="fm_off")
    _fm_nb = st.number_input("N° bulloni", 2, 24, _bolt_n, 1, key="fm_nb")
    _fm_db = st.number_input("Ø foro bullone (mm)", 1.0, 12.0, _bolt_d, 0.1, key="fm_db")
    if is_rect:
        zp, wp, hp = _get_rect_profile(segmenti)
        fm_hole_w = wp[-1] + spessore * 2
        fm_hole_h = hp[-1] + spessore * 2
        if is_lecleach:
            # INWARD: entire flange sits inside mouth (outer = mouth - 20, hole = mouth - 40)
            _fm_od = fm_hole_w - 20
            _fm_ow = fm_hole_w - 20
            _fm_oh = fm_hole_h - 20
            _fm_bc = fm_hole_w - 30  # midpoint of 20mm inward ring
        else:
            r_corner_m = np.sqrt((fm_hole_w/2)**2 + (fm_hole_h/2)**2)
            _fm_od = (r_corner_m + 15.0) * 2.0
            _fm_ow = _fm_od
            _fm_oh = _fm_od * fm_hole_h / fm_hole_w
            _fm_bc = r_corner_m + _fm_od / 2.0
        st.caption(f"Foro: {fm_hole_w:.0f}×{fm_hole_h:.0f} mm (rettangolare)")
    elif is_lecleach:
        _fm_od = ir_m * 2
        _fm_bc = _fm_od - 20  # inward: midpoint between hole and mouth edge
        st.caption(f"Foro: Ø{ir_m*2 + spessore*2:.0f} mm (circolare)")
    else:
        _fm_od = (ir_m + spessore) * 2 + 20
        _fm_bc = ir_m + spessore + _fm_od / 2
        st.caption(f"Foro: Ø{ir_m*2 + spessore*2:.0f} mm (circolare)")
    bocca_out = st.radio("Esterno", ["Circolare", "Rettangolare"],
                          index=1 if is_rect else 0, horizontal=True, key="bocca_out")
    if bocca_out == "Rettangolare":
        if '_fm_ow' not in dir(): _fm_ow = _fm_od
        if '_fm_oh' not in dir(): _fm_oh = _fm_od
        _fm_ow = st.number_input("Larghezza (mm)", 10.0, 1000.0, _fm_ow, 1.0, key="fm_ow")
        _fm_oh = st.number_input("Altezza (mm)", 10.0, 1000.0, _fm_oh, 1.0, key="fm_oh")
    else:
        _fm_od = st.number_input("Ø esterno (mm)", 10.0, 1000.0, _fm_od, 1.0, key="fm_od")
        _fm_bc = st.number_input("Ø cerchio fori (mm)", 10.0, 980.0, _fm_bc, 1.0, key="fm_bc")

with fg3:
    st.markdown("##### Flangia Intermedia")
    if is_radial:
        gen_mid = False; _mid_pos = 50
        st.caption("Non disponibile per profilo radiale")
    else:
        gen_mid = st.checkbox("Includi", False, key="gen_mid")
        _mid_pos = st.number_input("Distanza dalla gola (mm)", 5.0, 2000.0,
            max(5.0, (_len or 200) * 0.5), 5.0, key="mid_z")
        _mid_sp = st.number_input("Spessore (mm)", 2.0, 20.0, 4.0, 0.5, key="mid_spess")
        _mid_nb = st.number_input("N° bulloni", 2, 24, _bolt_n, 1, key="mid_nb")
        _mid_db = st.number_input("Ø foro bullone (mm)", 1.0, 12.0, _bolt_d, 0.1, key="mid_db")
        if is_rect:
            zp, wp, hp = _get_rect_profile(segmenti)
            _idx = min(int(np.searchsorted(zp, _mid_pos)), len(zp)-1)
            _w_mid = wp[_idx] + spessore * 2
            _h_mid = hp[_idx] + spessore * 2
            r_corner_mid = np.sqrt((_w_mid / 2.0)**2 + (_h_mid / 2.0)**2)
            _mid_od = (r_corner_mid + 15.0) * 2.0
            _mid_ow = _mid_od
            _mid_oh = _mid_od * _h_mid / _w_mid
            _mid_bc = r_corner_mid + _mid_od / 2.0
            st.caption(f"Foro: {_w_mid:.0f}×{_h_mid:.0f} mm (rettangolare)")
        else:
            mid_r = _get_mid_r(_mid_pos / max(_len or 1, 1) * 100) if _len else 10
            mid_outer = mid_r + spessore
            mid_hole = mid_outer * 2
            _mid_od = mid_hole + 20
            _mid_bc = mid_outer + _mid_od / 2
            st.caption(f"Foro: Ø{mid_hole:.0f} mm (circolare)")
        mid_out = st.radio("Esterno", ["Circolare", "Rettangolare"],
                            index=1 if is_rect else 0, horizontal=True, key="mid_out")
        if mid_out == "Rettangolare":
            if '_mid_ow' not in dir(): _mid_ow = _mid_od
            if '_mid_oh' not in dir(): _mid_oh = _mid_od
            _mid_ow = st.number_input("Larghezza (mm)", 10.0, 1000.0, _mid_ow, 1.0, key="mid_ow")
            _mid_oh = st.number_input("Altezza (mm)", 10.0, 1000.0, _mid_oh, 1.0, key="mid_oh")
        else:
            _mid_od = st.number_input("Ø esterno (mm)", 10.0, 1000.0, _mid_od, 1.0, key="mid_od")
            _mid_bc = st.number_input("Ø cerchio fori (mm)", 10.0, 980.0, _mid_bc, 1.0, key="mid_bc")

# ═══════════════════════════════════════════════════════════════════════
#  ROW 3 — Generate Assembly
# ═══════════════════════════════════════════════════════════════════════

st.divider()
st.subheader("Generazione Assembly")

chk, _ = st.columns([1, 3])
with chk:
    gen_horn = st.checkbox("Includi tromba", True, key="gen_horn")

gen_btn = st.button("Genera Assembly STL", type="primary", use_container_width=True)

if gen_btn:
    with st.spinner("Generazione in corso…"):
        try:
            import trimesh as _tm
            C = _core

            # --- 3a. Generate horn ---
            if is_rect:
                if is_exp:
                    z, w, h = _get_rect_profile(segmenti)
                elif is_tractrix:
                    z, w, h = _rh.get_rectangular_tractrix(tw, th, mw, segmenti)
                elif is_lecleach:
                    z, w, h = _rh.get_rectangular_lecleach(tw, th, fc, segmenti)
                else:
                    z, w, h = _rh.get_rectangular_iwata(tw, th, fc, ln, segmenti)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                _rh.generate_rectangular_3d_mesh(z, w, h, spessore, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                bocca_w = w[-1] + spessore * 2
                bocca_h = h[-1] + spessore * 2
            elif is_radial:
                with tempfile.TemporaryDirectory() as _tmp:
                    _rd.generate_radial_horn(td, md, fc, 48, _tmp)
                    horn = _tm.load(os.path.join(_tmp, "radial_bottom.stl"), file_type="stl")
                    # Rebuild top reflector as a proper solid (no hole, no flip)
                    R, Zb, Zt = _rd.get_radial_profiles(td, md, fc, segmenti)
                    Rm, Rt_rad = R[-1], R[0]
                    Z_top_flat = Zt[-1] + 4.0
                    # Polygon: curve → outer wall → flat top → center (fills hole) → back to start
                    r_poly = np.concatenate([R, [Rm], [0.0], [Rt_rad]])
                    z_poly = np.concatenate([Zt, [Z_top_flat], [Z_top_flat], [Zt[0]]])
                    top_mesh = _rd._revolve_polygon(r_poly, z_poly, 48)
                    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as _tf: _tfn = _tf.name
                    top_mesh.save(_tfn)
                    horn_top = _tm.load(_tfn, file_type="stl"); os.unlink(_tfn)
                    gap = Zt[-1] - Zb[-1]
                    horn_top.apply_translation([0, 0, horn.bounds[1, 2] + gap])
                bocca_w = bocca_h = md
            else:
                if is_tractrix:
                    zp, rp = C.get_tractrix(td, md, segmenti)
                elif is_lecleach:
                    zp, rp = C.get_lecleach(td, fc, segmenti)
                else:
                    zp, rp = C.get_iwata(td, fc, ln, segmenti)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                C.generate_3d_mesh_from_profile(zp, rp, spessore, 64, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                bocca_w = bocca_h = (rp[-1] + spessore) * 2 if not is_lecleach else ir_m * 2

            z_min = horn.vertices[:,2].min()

            # --- 3b. Throat hole — analytical ---
            if is_rect:
                fiw_g = tw + spessore * 2
                fih_g = th + spessore * 2
            else:
                fiw_g = fih_g = td + spessore * 2

            # --- 3c. Exact mouth dimensions ---
            if is_rect:
                zp, wp, hp = _get_rect_profile(segmenti)
                fiw_m = wp[-1] + spessore * 2
                fih_m = hp[-1] + spessore * 2
                z_mouth = zp[-1]
            elif is_radial:
                fiw_m = fih_m = md
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
                    fiw_m -= 30.0  # 15mm overlap per side for watertight union

            # --- 3d. Generate flanges ---
            f_gola = f_bocca = f_mid = None

            if gen_gola:
                if is_rect:
                    f_gola = _rf.generate_rectangular_flange(
                        outer_diam=_fg_od, inner_w=fiw_g, inner_h=fih_g,
                        thickness=_fg_sp, bolt_radius=_fg_bc/2,
                        bolt_count=int(_fg_nb), bolt_diam=_fg_db,
                        outer_type="circular" if gola_out == "Circolare" else "rectangular",
                        outer_w=_fg_ow if gola_out == "Rettangolare" else None,
                        outer_h=_fg_oh if gola_out == "Rettangolare" else None,
                        offset=z_min + _fg_off, output_path=None)
                else:
                    _tr = np.sqrt(fiw_g**2 + fih_g**2)/2 if is_rect else fiw_g/2
                    f_gola = _fg.generate_flange(
                        throat_R=_tr, flange_R=_fg_od/2,
                        thickness=_fg_sp, bolt_R=_fg_bc/2,
                        bolt_n=int(_fg_nb), bolt_d=_fg_db,
                        offset=z_min + _fg_off + _fg_sp)

            if gen_bocca:
                if is_rect:
                    f_bocca = _rf.generate_rectangular_flange(
                        outer_diam=_fm_od, inner_w=fiw_m, inner_h=fih_m,
                        thickness=_fm_sp, bolt_radius=_fm_bc/2,
                        bolt_count=int(_fm_nb), bolt_diam=_fm_db,
                        outer_type="circular" if bocca_out == "Circolare" else "rectangular",
                        outer_w=_fm_ow if bocca_out == "Rettangolare" else None,
                        outer_h=_fm_oh if bocca_out == "Rettangolare" else None,
                        offset=z_mouth + _fm_off - _fm_sp, output_path=None)
                else:
                    _R = _fm_od / 2.0
                    _tr_m = fiw_m / 2.0
                    if is_lecleach:
                        _R = min(_R, rp.max())
                        _tr_m = min(_tr_m, _R - 5.0)
                    f_bocca = _fg.generate_flange(
                        throat_R=_tr_m, flange_R=_R,
                        thickness=_fm_sp, bolt_R=_fm_bc/2,
                        bolt_n=int(_fm_nb), bolt_d=_fm_db,
                        offset=z_mouth + _fm_off)

            if gen_mid and not is_radial:
                z_mid = z_min + _mid_pos
                if is_rect:
                    zp, wp, hp = _get_rect_profile(segmenti)
                    _idx = min(int(np.searchsorted(zp, _mid_pos)), len(zp)-1)
                    fiw_mid = wp[_idx] + spessore * 2
                    fih_mid = hp[_idx] + spessore * 2
                    f_mid = _rf.generate_rectangular_flange(
                        outer_diam=_mid_od, inner_w=fiw_mid, inner_h=fih_mid,
                        thickness=_mid_sp, bolt_radius=_mid_bc/2,
                        bolt_count=int(_mid_nb), bolt_diam=_mid_db,
                        outer_type="circular" if mid_out == "Circolare" else "rectangular",
                        outer_w=_mid_ow if mid_out == "Rettangolare" else None,
                        outer_h=_mid_oh if mid_out == "Rettangolare" else None,
                        offset=z_mid - _mid_sp, output_path=None)
                else:
                    mid_r = _get_mid_r(_mid_pos / max(_len or 1, 1) * 100) if _len else 10
                    fiw_mid = (mid_r + spessore) * 2
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
            if f_gola is not None: bodies.append(f_gola)
            if f_bocca is not None: bodies.append(f_bocca)
            if f_mid is not None: bodies.append(f_mid)

            if not bodies:
                st.error("Seleziona almeno un elemento da generare")
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
            st.success("✅ Assembly generato con successo")

            _wt = combined.is_watertight if hasattr(combined, 'is_watertight') else None
            _vol = combined.volume if hasattr(combined, 'volume') else 0
            _tris = len(combined.faces) if hasattr(combined, 'faces') else 0

            r1, r2, r3, r4 = st.columns(4)
            with r1:
                st.metric("Lunghezza", f"{horn.bounds[1,2]-horn.bounds[0,2]:.0f} mm" if gen_horn else "—")
            with r2:
                if gen_horn:
                    st.metric("Bocca", f"Ø{bocca_w:.0f}" if abs(bocca_w-bocca_h)<1 else f"{bocca_w:.0f}×{bocca_h:.0f}")
                else:
                    st.metric("Bocca", "—")
            with r3:
                st.metric("Triangoli", f"{_tris:,}")
            with r4:
                st.metric("Volume", f"{_vol:.0f} mm³")

            if _wt is True:
                st.success("Mesh watertight — pronta per la stampa 3D")
            elif _wt is False:
                st.warning("Mesh non watertight — verifica i parametri")
            else:
                st.info("Output multi-corpo (flange separate)")

            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button("📥 Scarica STL", stl_bytes, "tromba_assembly.stl",
                    "model/stl", use_container_width=True)
            with col_dl2:
                if step_bytes is not None:
                    st.download_button("📥 Scarica STEP", step_bytes, "tromba_assembly.step",
                        "model/step", use_container_width=True)
                else:
                    st.caption("STEP non disponibile")

        except Exception as exc:
            st.error(f"❌ Generazione fallita: {exc}")
            st.code(traceback.format_exc())
else:
    st.info("Configura i parametri e clicca **Genera Assembly STL**")
