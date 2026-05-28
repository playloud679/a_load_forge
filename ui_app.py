"""
Dashboard monotab — Generatore Acustico professionale.
Flusso: Parametri tromba → Parametri flangia → Anteprima 2D → Generazione 3D.
"""

import io
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st
import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "src"))

# ── Unified lazy-import helper ────────────────────────────────────────
def _lazy(mod_name: str, file_name: str):
    import importlib.machinery, importlib.util
    p = Path(__file__).parent / "src" / file_name
    loader = importlib.machinery.SourceFileLoader(mod_name, str(p))
    spec = importlib.util.spec_from_loader(mod_name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m

_core = lambda: _lazy("_c", "01_profile_generator.py")
_rf   = lambda: _lazy("_r", "04_rectangular_flange.py")
_fg   = lambda: _lazy("_f", "02_flange_generator.py")
_rh   = lambda: _lazy("_rh", "03_rectangular_horn.py")
_rd   = lambda: _lazy("_rd", "03_omni_radial_horn.py")

st.set_page_config(page_title="Generatore Acustico", layout="centered")
st.title("📯 Generatore Acustico")
st.caption("Tromba assialsimmetrica / rettangolare + flangia di montaggio · assembly unico")

# ═══════════════════════════════════════════════════════════════════════
#  1 — PARAMETRI TROMBA
# ═══════════════════════════════════════════════════════════════════════

st.subheader("1. Parametri tromba")

col_a, col_b, col_c = st.columns(3)

with col_a:
    profilo = st.selectbox("Profilo", ["tractrix", "lecleach", "iwata", "rectangular", "radial"],
                           index=0)
with col_b:
    spessore = st.number_input("Spessore parete (mm)", 1.0, 20.0, 4.0, 0.5)
with col_c:
    segmenti = st.number_input("Segmenti profilo", 100, 50000, 300, 50)

st.markdown("#### Geometria")

is_rect = profilo == "rectangular"
is_radial = profilo == "radial"
has_fc  = profilo in ("lecleach", "iwata", "rectangular", "radial")
has_mouth = profilo in ("tractrix", "radial")

col1, col2, col3, col4 = st.columns(4)

with col1:
    if is_rect:
        tw = st.number_input("Larghezza gola (mm)", 4.0, 200.0, 20.0, 1.0)
    elif is_radial:
        td = st.number_input("Diametro gola (mm)", 5.0, 100.0, 25.0, 1.0)
    else:
        td = st.number_input("Diametro gola (mm)", 2.0, 200.0, 20.0, 1.0)

with col2:
    if is_rect:
        th = st.number_input("Altezza gola (mm)", 2.0, 200.0, 10.0, 1.0)
    elif is_radial:
        md = st.number_input("Diametro bocca (mm)", 20.0, 500.0, 200.0, 5.0)
    elif profilo == "tractrix":
        md = st.number_input("Diametro bocca (mm)", 4.0, 500.0, 100.0, 5.0)
    else:
        st.caption("Bocca calcolata da Fc")

with col3:
    if has_fc:
        fc = st.number_input("Frequenza taglio Fc (Hz)", 50, 20000, 600, 50)
    else:
        fc = None
        st.caption("—")

with col4:
    if is_rect:
        mw = st.number_input("Larghezza bocca (mm)", 10.0, 500.0, 160.0, 5.0)
        _hint = ""
        _fw = _fh = None
    elif profilo == "iwata":
        ln = st.number_input("Lunghezza (mm)", 10.0, 500.0, 80.0, 5.0)
    else:
        st.caption("—")

# ═══════════════════════════════════════════════════════════════════════
#  2 — FLANGE DI MONTAGGIO  (gola + bocca)
# ═══════════════════════════════════════════════════════════════════════

st.subheader("2. Flange di montaggio")

f_tipo = "rectangular" if is_rect else "circular"
if is_rect:
    st.info("🔒 Flangia rettangolare bloccata (profilo rettangolare)")

# ── Calcolo automatico diametri ──────────────────────────────────────

def _calc_flange_defaults():
    """Compute flange outer diameters & bolt-circle diameters from horn geometry."""
    if is_rect:
        inner_r_g = max(tw, th) / 2
        inner_r_m = mw / 2
        mid_pct = 50
        z_p, w_p, h_p = _rh().get_rectangular_exponential(tw, th, mw, fc, segmenti)
        z_mid = z_p[-1] * mid_pct / 100.0
        mid_idx = int(np.searchsorted(z_p, z_mid))
        inner_r_mid = max(w_p[mid_idx], h_p[mid_idx]) / 2
    elif is_radial:
        inner_r_g = td / 2
        inner_r_m = md / 2
        mid_pct = 50
        inner_r_mid = None  # no mid flange for radial
    elif profilo == "tractrix":
        inner_r_g = td / 2
        inner_r_m = md / 2
        mid_pct = 50
        z_p, r_p = _core().get_tractrix(td, md, segmenti)
        z_mid = z_p[-1] * mid_pct / 100.0
        mid_idx = int(np.searchsorted(z_p, z_mid))
        inner_r_mid = r_p[mid_idx]
    else:
        C = _core()
        mid_pct = 50
        if profilo == "lecleach":
            z_p, r_p = C.get_lecleach(td, fc, segmenti)
            inner_r_m = r_p.max()
            z_max = z_p.max()
            z_mid = z_max * mid_pct / 100.0
            mid_idx = int(np.searchsorted(z_p, z_mid))
            inner_r_mid = r_p[mid_idx]
        else:
            z_p, r_p = C.get_iwata(td, fc, ln, segmenti)
            inner_r_m = r_p.max()
            z_mid = z_p[-1] * mid_pct / 100.0
            mid_idx = int(np.searchsorted(z_p, z_mid))
            inner_r_mid = r_p[mid_idx]
        inner_r_g = td / 2

    # Throat & mouth flange
    fg_od = inner_r_g * 2 + 20
    if profilo == "lecleach":
        fm_od = inner_r_m * 2
        fm_hole = fm_od - 20
    else:
        fm_od = inner_r_m * 2 + 20
        fm_hole = inner_r_m * 2

    outer_r_g = inner_r_g + spessore
    outer_r_m = inner_r_m + spessore
    fg_bc = outer_r_g + fg_od / 2
    if profilo == "lecleach":
        fm_bc = (fm_hole / 2 + fm_od / 2)
    else:
        fm_bc = outer_r_m + fm_od / 2

    # Mid flange
    if inner_r_mid is not None:
        mid_od = inner_r_mid * 2 + 20
        mid_hole = inner_r_mid * 2
        outer_r_mid = inner_r_mid + spessore
        mid_bc = outer_r_mid + mid_od / 2
    else:
        mid_od = mid_hole = mid_bc = outer_r_mid = 0.0

    return fg_od, fm_od, fg_bc, fm_bc, outer_r_g, outer_r_m, fm_hole, \
           mid_pct, mid_od, mid_hole, mid_bc, outer_r_mid

# ── Initialize / recalculate ──────────────────────────────────────────
if "fg_od" not in st.session_state:
    fg_od_d, fm_od_d, fg_bc_d, fm_bc_d, fg_br, fm_br, fm_hole_d, \
        mid_pos, mid_od_d, mid_hole_d, mid_bc_d, mid_br = _calc_flange_defaults()
    st.session_state.fg_od = fg_od_d
    st.session_state.fm_od = fm_od_d
    st.session_state.fg_bc = fg_bc_d
    st.session_state.fm_bc = fm_bc_d
    st.session_state.fg_outer_r = fg_br
    st.session_state.fm_outer_r = fm_br
    st.session_state.fm_hole = fm_hole_d
    st.session_state.mid_pos = mid_pos
    st.session_state.mid_od = mid_od_d
    st.session_state.mid_hole = mid_hole_d
    st.session_state.mid_bc = mid_bc_d
    st.session_state.mid_outer_r = mid_br

if st.button("🔧 Calcola flange", use_container_width=True,
             help="Ricalcola tutti i diametri a partire dalle dimensioni attuali della tromba"):
    fg_od_d, fm_od_d, fg_bc_d, fm_bc_d, fg_br, fm_br, fm_hole_d, \
        mid_pos, mid_od_d, mid_hole_d, mid_bc_d, mid_br = _calc_flange_defaults()
    st.session_state.fg_od = fg_od_d
    st.session_state.fm_od = fm_od_d
    st.session_state.fg_bc = fg_bc_d
    st.session_state.fm_bc = fm_bc_d
    st.session_state.fg_outer_r = fg_br
    st.session_state.fm_outer_r = fm_br
    st.session_state.fm_hole = fm_hole_d
    st.session_state.mid_pos = mid_pos
    st.session_state.mid_od = mid_od_d
    st.session_state.mid_hole = mid_hole_d
    st.session_state.mid_bc = mid_bc_d
    st.session_state.mid_outer_r = mid_br

# ── Derived values (Fc, length, mouth) ───────────────────────────────
if "horn_fc" not in st.session_state:
    st.session_state.horn_fc = None
    st.session_state.horn_len = None
    st.session_state.horn_mouth = None

# Compute derived values whenever inputs change
try:
    if is_rect:
        z_p, w_p, h_p = _rh().get_rectangular_exponential(tw, th, mw, fc, segmenti)
        st.session_state.horn_len = z_p[-1]
        st.session_state.horn_mouth = f"{w_p[-1]:.0f}×{h_p[-1]:.0f}"
        st.session_state.horn_fc = None
    elif is_radial:
        st.session_state.horn_len = None
        st.session_state.horn_mouth = None
        st.session_state.horn_fc = None
    elif profilo == "tractrix":
        z_p, r_p = _core().get_tractrix(td, md, segmenti)
        st.session_state.horn_len = z_p[-1]
        st.session_state.horn_mouth = f"Ø{r_p[-1]*2:.0f}"
        st.session_state.horn_fc = 343_000 / (np.pi * md)
    elif profilo == "lecleach":
        z_p, r_p = _core().get_lecleach(td, fc, segmenti)
        mouth_idx = int(np.argmax(z_p))
        st.session_state.horn_len = z_p.max()
        st.session_state.horn_mouth = f"Ø{r_p[mouth_idx]*2:.0f}"
        st.session_state.horn_fc = None
    elif profilo == "iwata":
        z_p, r_p = _core().get_iwata(td, fc, ln, segmenti)
        st.session_state.horn_len = None
        st.session_state.horn_mouth = f"Ø{r_p.max()*2:.0f}"
        st.session_state.horn_fc = None
except Exception:
    pass

# Show derived metrics
_metrics = []
if st.session_state.horn_len is not None:
    _metrics.append(f"L={st.session_state.horn_len:.0f} mm")
if st.session_state.horn_mouth is not None:
    _metrics.append(f"Bocca {st.session_state.horn_mouth} mm")
if st.session_state.horn_fc is not None:
    _metrics.append(f"Fc={st.session_state.horn_fc:.0f} Hz")

if _metrics:
    st.caption(" · ".join(_metrics))

col_g1, col_g2 = st.columns(2)

with col_g1:
    st.markdown("##### Gola (attacco driver)")
    gen_gola = st.checkbox("Genera flangia gola", value=True, key="gen_gola")
    fg_esterno = st.number_input("Ø esterno gola (mm)", 10.0, 300.0,
                    key="fg_od", step=1.0,
                    help=f"Apertura tromba + 20 mm (10 mm per lato)")
    fg_spess   = st.number_input("Spessore gola (mm)", 2.0, 20.0, 6.0, 0.5)
    fg_offset  = st.number_input("Offset gola (mm)", -50.0, 50.0, 0.0, 0.5,
                    help="0 = filo con la base, positivo = verso l'alto")
    fg_cfori   = st.number_input("Ø cerchio fori gola (mm)", 10.0, 280.0,
                    key="fg_bc", step=1.0,
                    help=f"Metà tra corpo esterno (Ø{st.session_state.fg_outer_r*2:.0f}) e bordo flangia")
    fg_nbull   = st.number_input("N° bulloni gola", 2, 24, 4, 1)
    fg_dboll   = st.number_input("Ø bulloni gola (mm)", 1.0, 12.0, 3.5, 0.1)

with col_g2:
    st.markdown("##### Bocca (uscita tromba)")
    gen_bocca = st.checkbox("Genera flangia bocca", value=True, key="gen_bocca")
    fm_esterno = st.number_input("Ø esterno bocca (mm)", 10.0, 1000.0,
                    key="fm_od", step=1.0,
                    help="Apertura tromba + 20 mm (10 mm per lato)")
    fm_spess   = st.number_input("Spessore bocca (mm)", 2.0, 20.0, 6.0, 0.5)
    fm_offset  = st.number_input("Offset bocca (mm)", -50.0, 50.0, 0.0, 0.5,
                    help="0 = filo con la bocca, positivo = verso l'esterno")
    fm_cfori   = st.number_input("Ø cerchio fori bocca (mm)", 10.0, 980.0,
                    key="fm_bc", step=1.0,
                    help=f"Metà tra corpo esterno (Ø{st.session_state.fm_outer_r*2:.0f}) e bordo flangia")
    fm_nbull   = st.number_input("N° bulloni bocca", 2, 24, 4, 1)
    fm_dboll   = st.number_input("Ø bulloni bocca (mm)", 1.0, 12.0, 3.5, 0.1)

# ── Flangia intermedia ────────────────────────────────────────────────
if not is_radial:
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.markdown("##### Intermedia")
        gen_mid = st.checkbox("Genera flangia intermedia", value=False, key="gen_mid")
        mid_pos = st.number_input("Posizione (% lunghezza)", 5, 95,
                    key="mid_pos", step=5,
                    help="0% = gola, 100% = bocca")
    with col_m2:
        mid_esterno = st.number_input("Ø esterno intermedia (mm)", 10.0, 1000.0,
                    key="mid_od", step=1.0,
                    help="Apertura tromba in quel punto + 20 mm")
    with col_m3:
        mid_spess = st.number_input("Spessore intermedia (mm)", 2.0, 20.0, 4.0, 0.5)
    
    col_n1, col_n2, col_n3 = st.columns(3)
    with col_n1:
        mid_cfori = st.number_input("Ø cerchio fori intermedia (mm)", 10.0, 980.0,
                    key="mid_bc", step=1.0,
                    help="Metà tra corpo e bordo flangia")
    with col_n2:
        mid_nbull = st.number_input("N° bulloni intermedia", 2, 24, 4, 1)
    with col_n3:
        mid_dboll = st.number_input("Ø bulloni intermedia (mm)", 1.0, 12.0, 3.5, 0.1)

with st.expander("Anteprima 2D profilo"):
        if st.button("✏️ Calcola anteprima", use_container_width=True):
            import matplotlib.pyplot as plt
            C = _core()
            try:
                if is_rect:
                    z_p, w_p, h_p = _rh().get_rectangular_exponential(
                        tw, th, mw, fc, segmenti)
                    f, ax = plt.subplots()
                    ax.plot(z_p, w_p/2, label="Mezza larghezza", c="#2196F3")
                    ax.plot(z_p, h_p/2, label="Mezza altezza", c="#FF5722")
                    ax.plot(z_p, w_p/2+spessore, "--", c="#2196F3", alpha=0.4)
                    ax.plot(z_p, h_p/2+spessore, "--", c="#FF5722", alpha=0.4)
                    ax.set_xlabel("Z (mm)"); ax.set_ylabel("R (mm)")
                    ax.legend(); ax.grid(True, alpha=0.3)
                    st.pyplot(f)
                    st.caption(f"Bocca: {w_p[-1]:.0f}×{h_p[-1]:.0f} mm · L={z_p[-1]:.0f} mm")
                elif is_radial:
                    Rr, Zb, Zt = _rd().get_radial_profiles(td, md, fc, segmenti)
                    f, ax = plt.subplots()
                    ax.plot(Rr, Zb, label="Deflettore inf.", c="#FF5722")
                    ax.plot(Rr, Zt, label="Riflettore sup.", c="#2196F3")
                    ax.fill_between(Rr, Zb, Zt, alpha=0.15, color="#4CAF50")
                    ax.set_xlabel("R (mm)"); ax.set_ylabel("Z (mm)")
                    ax.legend(); ax.grid(True, alpha=0.3)
                    st.pyplot(f)
                    st.caption(f"Mouth gap: H(Rt)={Zt[0]-Zb[0]:.1f} → H(Rm)={Zt[-1]-Zb[-1]:.1f} mm")
                else:
                    z_p, r_p = C.get_tractrix(td, md, segmenti) if profilo == "tractrix" else \
                               (C.get_lecleach(td, fc, segmenti) if profilo == "lecleach" else
                                C.get_iwata(td, fc, ln, segmenti))
                    f, ax = plt.subplots()
                    ax.plot(z_p, r_p, label="Profilo interno", c="#2196F3")
                    ax.plot(z_p, r_p+spessore, "--", label="+ parete", c="#FF5722", alpha=0.5)
                    ax.set_xlabel("Z (mm)"); ax.set_ylabel("R (mm)")
                    ax.legend(); ax.grid(True, alpha=0.3)
                    st.pyplot(f)
                    st.caption(f"Bocca: Ø{r_p[-1]*2:.0f} mm · L={z_p[-1]:.0f} mm")
            except Exception as exc:
                st.error(f"Anteprima fallita: {exc}")
        else:
            st.info("Clicca **Calcola anteprima** per visualizzare il profilo 2D")

# ═══════════════════════════════════════════════════════════════════════
#  3 — GENERAZIONE ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════

st.subheader("3. Genera assembly completo")

col_sel, _ = st.columns([1, 3])
with col_sel:
    gen_horn = st.checkbox("Genera tromba", value=True, key="gen_horn")

gen_btn = st.button("🔧 Genera assembly STL", type="primary", use_container_width=True)

if gen_btn:
    with st.spinner("Generazione tromba + flangia …"):
        try:
            C = _core()
            import trimesh as _tm
            import matplotlib.pyplot as plt

            # ── 3a. Genera tromba (sempre per dimensioni flange) ──────────
            if is_rect:
                z, w, h = _rh().get_rectangular_exponential(tw, th, mw, fc, segmenti)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
                    tp = t.name
                _rh().generate_rectangular_3d_mesh(z, w, h, spessore, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                bocca_w = float(horn.bounds[1,0] - horn.bounds[0,0])
                bocca_h = float(horn.bounds[1,1] - horn.bounds[0,1])
            elif is_radial:
                with tempfile.TemporaryDirectory() as _tmp:
                    _rd().generate_radial_horn(td, md, fc, 48, _tmp)
                    horn = _tm.load(os.path.join(_tmp, "radial_bottom.stl"), file_type="stl")
                bocca_w = bocca_h = md
            else:
                z_p, r_p = (C.get_tractrix(td, md, segmenti) if profilo == "tractrix" else
                            C.get_lecleach(td, fc, segmenti) if profilo == "lecleach" else
                            C.get_iwata(td, fc, ln, segmenti))
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
                    tp = t.name
                C.generate_3d_mesh_from_profile(z_p, r_p, spessore, 64, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                bocca_w = bocca_h = float(np.sqrt(horn.vertices[:,0]**2+horn.vertices[:,1]**2).max()) * 2

            # ── 3b. Dimensioni fori flangia ────────────────────────────
            def _dim1(v):
                if is_rect:
                    hw = float(np.abs(v[:,0]).max())
                    hh = float(np.abs(v[:,1]).max())
                    return hw*2, hh*2
                ho = float(np.sqrt(v[:,0]**2+v[:,1]**2).max())
                return ho*2, ho*2

            # Throat: trova vertici vicini a Z=0 (minimo assoluto)
            z_min = horn.vertices[:,2].min()
            v_gola = horn.vertices[np.abs(horn.vertices[:,2] - z_min) < 1.0]
            if len(v_gola) < 4:
                v_gola = horn.vertices[np.abs(horn.vertices[:,2] - z_min) < 5.0]
            fiw_g, fih_g = _dim1(v_gola)

            # Mouth: LeCleach → massimo raggio (roll-back), altri → max Z
            rr_mouth = np.sqrt(horn.vertices[:,0]**2 + horn.vertices[:,1]**2)
            idx_max_r = int(rr_mouth.argmax())
            if profilo == "lecleach":
                z_mouth = float(horn.vertices[idx_max_r, 2])
                v_bocca = horn.vertices[rr_mouth > (rr_mouth[idx_max_r] - 2.0)]
                if len(v_bocca) < 4:
                    v_bocca = horn.vertices[rr_mouth > (rr_mouth[idx_max_r] - 10.0)]
            else:
                z_mouth = horn.vertices[:,2].max()
                v_bocca = horn.vertices[np.abs(horn.vertices[:,2] - z_mouth) < 1.0]
                if len(v_bocca) < 4:
                    v_bocca = horn.vertices[np.abs(horn.vertices[:,2] - z_mouth) < 5.0]
            fiw_m, fih_m = _dim1(v_bocca)
            if profilo == "lecleach":
                fiw_m = fiw_m - 20  # inward: 10mm per side verso il centro

            # ── 3c. Genera flangia gola ─────────────────────────────────
            f_gola = None
            f_bocca = None
            if gen_gola:
                if f_tipo == "rectangular":
                    f_gola = _rf().generate_rectangular_flange(
                        outer_diam=fg_esterno, inner_w=fiw_g, inner_h=fih_g,
                        thickness=fg_spess, bolt_radius=fg_cfori/2,
                        bolt_count=int(fg_nbull), bolt_diam=fg_dboll, output_path=None)
                else:
                    f_gola = _fg().generate_flange(
                        throat_R=fiw_g / 2, flange_R=fg_esterno / 2,
                        thickness=fg_spess, bolt_R=fg_cfori / 2,
                        bolt_n=int(fg_nbull), bolt_d=fg_dboll,
                        offset=fg_offset + fg_spess)
            if gen_bocca:
                if f_tipo == "rectangular":
                    f_bocca = _rf().generate_rectangular_flange(
                        outer_diam=fm_esterno, inner_w=fiw_m, inner_h=fih_m,
                        thickness=fm_spess, bolt_radius=fm_cfori/2,
                        bolt_count=int(fm_nbull), bolt_diam=fm_dboll, output_path=None)
                else:
                    f_bocca = _fg().generate_flange(
                        throat_R=fiw_m / 2, flange_R=fm_esterno / 2,
                        thickness=fm_spess, bolt_R=fm_cfori / 2,
                        bolt_n=int(fm_nbull), bolt_d=fm_dboll,
                        offset=z_mouth + fm_offset)

            # ── 3c2. Flangia intermedia ─────────────────────────────────
            f_mid = None
            if not is_radial and gen_mid:
                z_len = horn.vertices[:,2].max() - z_min
                z_mid_pos = z_min + z_len * mid_pos / 100.0
                v_mid = horn.vertices[np.abs(horn.vertices[:,2] - z_mid_pos) < 1.0]
                if len(v_mid) < 4:
                    v_mid = horn.vertices[np.abs(horn.vertices[:,2] - z_mid_pos) < 5.0]
                fiw_mid, fih_mid = _dim1(v_mid)
                if f_tipo == "rectangular":
                    f_mid = _rf().generate_rectangular_flange(
                        outer_diam=mid_esterno, inner_w=fiw_mid, inner_h=fih_mid,
                        thickness=mid_spess, bolt_radius=mid_cfori/2,
                        bolt_count=int(mid_nbull), bolt_diam=mid_dboll, output_path=None)
                else:
                    f_mid = _fg().generate_flange(
                        throat_R=fiw_mid / 2, flange_R=mid_esterno / 2,
                        thickness=mid_spess, bolt_R=mid_cfori / 2,
                        bolt_n=int(mid_nbull), bolt_d=mid_dboll,
                        offset=z_mid_pos + 0.0)

            # ── 3d. Unisci ──────────────────────────────────────────────

            bodies = []
            if gen_horn: bodies.append(horn)
            if f_gola is not None: bodies.append(f_gola)
            if f_bocca is not None: bodies.append(f_bocca)
            if f_mid is not None: bodies.append(f_mid)

            if not bodies:
                st.error("❌ Seleziona almeno un elemento da generare")
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

            with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
                tp = t.name
            combined.export(tp)
            with open(tp, "rb") as f:
                stl_bytes = f.read()
            os.unlink(tp)

            # ── 3e. Risultati ───────────────────────────────────────────
            st.success("✅ Assembly generato con successo")

            _wt = combined.is_watertight if hasattr(combined, 'is_watertight') else "—"
            _vol = combined.volume if hasattr(combined, 'volume') else 0
            _tris = len(combined.faces) if hasattr(combined, 'faces') else 0

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                if gen_horn:
                    st.metric("Lunghezza", f"{horn.bounds[1,2]-horn.bounds[0,2]:.0f} mm")
                else:
                    st.metric("Lunghezza", "—")
            with col_m2:
                if gen_horn:
                    st.metric("Bocca", f"Ø{bocca_w:.0f} mm" if abs(bocca_w-bocca_h)<1 else
                              f"{bocca_w:.0f}×{bocca_h:.0f} mm")
                else:
                    st.metric("Bocca", "—")
            with col_m3:
                st.metric("Triangoli", f"{_tris:,}")
            with col_m4:
                st.metric("Volume", f"{_vol:.0f} mm³")

            if _wt is True:
                st.success("✅ Mesh watertight — pronta per la stampa")
            elif isinstance(_wt, str):
                st.info("ℹ️ Mesh multi-corpo (flange separate)")

            st.download_button("📥 Download STL", stl_bytes,
                "tromba_con_flangia.stl", "model/stl", use_container_width=True)
            st.caption(
                "💡 Per editare il modello: importa lo STL in FreeCAD (gratuito) o Fusion 360, "
                "converti in solido, ed esporta come STEP. "
                "Usa l'anteprima 2D sopra come riferimento del profilo."
            )

        except Exception as exc:
            import traceback
            st.error(f"❌ Generazione fallita: {exc}")
            st.code(traceback.format_exc())

else:
    st.info("Configura i parametri sopra e clicca **Genera assembly STL**")
