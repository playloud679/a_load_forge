"""
Horn Generator + Flange — Web UI (Streamlit).

Usage:
    streamlit run ui_app.py
"""

import io
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st
import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "src"))

# ── Lazy-import the core engine ───────────────────────────────────────
def _get_core():
    import importlib.machinery, importlib.util
    p = Path(__file__).parent / "src" / "01_profile_generator.py"
    l = importlib.machinery.SourceFileLoader("_hc", str(p))
    s = importlib.util.spec_from_loader("_hc", l)
    m = importlib.util.module_from_spec(s)
    l.exec_module(m)
    return m

def _get_flange():
    import importlib.machinery, importlib.util
    p = Path(__file__).parent / "src" / "02_flange_generator.py"
    l = importlib.machinery.SourceFileLoader("_fg", str(p))
    s = importlib.util.spec_from_loader("_fg", l)
    m = importlib.util.module_from_spec(s)
    l.exec_module(m)
    return m


st.set_page_config(page_title="Horn Generator", layout="centered")
st.title("📯 Horn + Flange Generator")

tab1, tab2, tab3 = st.tabs(["🔧 Horn", "🔩 Flange", "🧩 Merge"])

# ═══════════════════════════════════════════════════════════════════════
#  TAB 1 — Horn
# ═══════════════════════════════════════════════════════════════════════

with tab1:
    col1, col2 = st.columns([1, 2])

    with col1:
        profile = st.selectbox("Profile",
            ["tractrix", "lecleach", "iwata", "rectangular"], index=0,
            help="tractrix / lecleach / iwata = axisymmetric · rectangular = area-preserving rectangular horn")

        thickness = st.number_input("Wall (mm)", 1.0, 20.0, 4.0, 0.5)

        mouth_diam = fc = length = tw = th = mw = None
        if profile == "rectangular":
            tw = st.number_input("Throat width (mm)", 4.0, 200.0, 20.0, 1.0)
            th = st.number_input("Throat height (mm)", 2.0, 200.0, 10.0, 1.0)
            mw = st.number_input("Mouth width (mm)", 10.0, 500.0, 160.0, 5.0)
            fc = st.number_input("Cutoff Fc (Hz)", 50, 20000, 600, 50)
        elif profile == "tractrix":
            throat_diam = st.number_input("Throat ø (mm)", 2.0, 200.0, 20.0, 1.0)
            mouth_diam = st.number_input("Mouth ø (mm)", 4.0, 500.0, 100.0, 5.0)
        elif profile == "lecleach":
            throat_diam = st.number_input("Throat ø (mm)", 2.0, 200.0, 20.0, 1.0)
            fc = st.number_input("Cutoff Fc (Hz)", 50, 20000, 600, 50,
                help="m = 4π·fc/c — Euler integration with 160° roll-back")
        else:  # iwata
            throat_diam = st.number_input("Throat ø (mm)", 2.0, 200.0, 20.0, 1.0)
            fc = st.number_input("Cutoff Fc (Hz)", 50, 20000, 600, 50)
            length = st.number_input("Length (mm)", 10.0, 500.0, 80.0, 5.0)

        segments = st.slider("Segments", 100, 500, 300, 50)
        rings = st.slider("Rings", 32, 128, 64, 16) if profile != "rectangular" else st.slider("Rings (inutilizzato)", 32, 128, 64, 16, disabled=True)

        gen_btn = st.button("🔧 Generate STL", type="primary", use_container_width=True)

    with col2:
        if gen_btn:
            with st.spinner("Generating …"):
                core = _get_core()
                try:
                    if profile == "rectangular":
                        import importlib.machinery, importlib.util as _iu
                        _rl = _iu.SourceFileLoader("_rh",
                            str(Path(__file__).parent / "src" / "03_rectangular_horn.py"))
                        _rh = _iu.module_from_spec(_iu.spec_from_loader("_rh", _rl))
                        _rl.exec_module(_rh)
                        z, w, h = _rh.get_rectangular_exponential(tw, th, mw, fc, segments)
                        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as _t:
                            _tp = _t.name
                        _rh.generate_rectangular_3d_mesh(z, w, h, thickness, _tp)
                        with open(_tp, "rb") as f:
                            stl_bytes = f.read()
                        os.unlink(_tp)
                        label = f"rect_{tw:.0f}x{th:.0f}_mw{mw:.0f}_fc{fc:.0f}"
                    elif profile == "tractrix":
                        z, r = core.get_tractrix(throat_diam, mouth_diam, segments)
                        label = f"tractrix_{throat_diam:.0f}_{mouth_diam:.0f}"
                    elif profile == "lecleach":
                        z, r = core.get_lecleach(throat_diam, fc, segments)
                        label = f"lecleach_{throat_diam:.0f}_{fc:.0f}hz"
                    else:
                        z, r = core.get_iwata(throat_diam, fc, length, segments)
                        label = f"iwata_{throat_diam:.0f}_fc{fc:.0f}_L{length:.0f}"

                    if profile != "rectangular":
                        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
                            tmp_path = tmp.name
                        core.generate_3d_mesh_from_profile(z, r, thickness, rings, output_path=tmp_path)
                        with open(tmp_path, "rb") as f:
                            stl_bytes = f.read()
                        os.unlink(tmp_path)

                    st.session_state["horn_stl"] = stl_bytes
                    st.session_state["horn_label"] = label

                    try:
                        import trimesh
                        m = trimesh.load(io.BytesIO(stl_bytes), file_type='stl')
                        vol = f"{m.volume:.0f} mm³"
                        tri = len(m.faces)
                        wt  = m.is_watertight
                        z_len = m.bounds[1,2] - m.bounds[0,2]
                        mw_val = m.bounds[1,0] - m.bounds[0,0]  # total X width
                        mh_val = m.bounds[1,1] - m.bounds[0,1]  # total Y height
                    except Exception:
                        vol = "—"; tri = "—"; wt = "—"
                        z_len = z.max() - z.min() if profile != "rectangular" else z[-1]
                        mw_val = mh_val = None

                    c_spd = 343000.0
                    if profile == "rectangular":
                        st.metric("Length", f"{z_len:.0f} mm")
                        st.metric("Mouth W×H", f"{mw_val:.0f}×{mh_val:.0f} mm" if mw_val else "—")
                        st.metric("Fc", f"{fc:.0f} Hz")
                    else:
                        mouth_r = float(mw_val / 2) if profile == "rectangular" else float(
                            (np.sqrt(m.vertices[:,0]**2+m.vertices[:,1]**2).max()) if 'm' in dir() else r.max())
                        fc_hz = fc if profile in ("lecleach", "iwata") else c_spd / (np.pi * mouth_r * 2)
                        st.metric("Length", f"{z_len:.0f} mm")
                        st.metric("Mouth ø", f"{mouth_r*2:.0f} mm")
                        st.metric("Fc", f"{fc_hz:.0f} Hz")

                    st.metric("Triangles", tri)
                    st.metric("Volume", vol)
                    if wt is True:
                        st.success("✅ Watertight")
                    st.download_button("📥 Download STL", stl_bytes,
                        f"{label}_Fc{fc_hz:.0f}hz.stl", "model/stl", use_container_width=True)

                except ValueError as exc:
                    st.error(f"❌ {exc}")
                except Exception as exc:
                    st.error(f"❌ Generation failed: {exc}")
        else:
            st.info("Set parameters on the left and click **Generate STL**")

# ═══════════════════════════════════════════════════════════════════════
#  TAB 2 — Flange
# ═══════════════════════════════════════════════════════════════════════

with tab2:
    st.subheader("Parametric Circular Flange")

    c1, c2 = st.columns([1, 2])
    with c1:
        f_outer   = st.number_input("Outer ø (mm)", 10.0, 250.0, 60.0, 1.0)
        f_inner   = st.number_input("Inner ø (mm)", 5.0, 240.0, 29.0, 0.5)
        f_thick   = st.number_input("Thickness (mm)", 2.0, 20.0, 6.0, 0.5)
        f_bc_rad  = st.number_input("Bolt circle R (mm)", 5.0, 120.0, 22.0, 0.5)
        f_n       = st.number_input("N° bolts", 2, 24, 4, 1)
        f_bd      = st.number_input("Bolt ø (mm)", 1.0, 12.0, 3.5, 0.1)
        f_btn     = st.button("🔩 Generate Flange", type="primary", use_container_width=True)

    with c2:
        if f_btn:
            with st.spinner("Generating flange …"):
                try:
                    _fg = _get_flange()
                    mesh = _fg.generate_flange(
                        outer_diam=f_outer, inner_diam=f_inner,
                        thickness=f_thick,
                        bolt_radius=f_bc_rad, bolt_count=int(f_n),
                        bolt_diam=f_bd, output_path=None)

                    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
                        tmp_path = tmp.name
                    mesh.export(tmp_path)
                    with open(tmp_path, "rb") as f:
                        stl_bytes = f.read()
                    os.unlink(tmp_path)

                    st.session_state["flange_stl"] = stl_bytes
                    st.session_state["_flange_params"] = {
                        "bc_rad": f_bc_rad, "n": int(f_n), "bd": f_bd}
                    st.metric("Outer", f"Ø{f_outer:.0f} mm")
                    st.metric("Inner", f"Ø{f_inner:.0f} mm")
                    st.metric("Bolts", f"{int(f_n)} × Ø{f_bd:.1f} @ R{f_bc_rad:.0f}")
                    st.metric("Triangles", len(mesh.faces))

                    st.success("✅ Watertight" if mesh.is_watertight else "❌")
                    st.download_button("📥 Download STL", stl_bytes,
                        f"flange_OD{f_outer:.0f}_ID{f_inner:.0f}.stl",
                        "model/stl", use_container_width=True)

                except Exception as exc:
                    st.error(str(exc))
        else:
            st.info("Adjust parameters and click **Generate Flange**")

# ═══════════════════════════════════════════════════════════════════════
#  TAB 3 — Merge
# ═══════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader("Merge Flange + Horn Section 1")

    has_horn   = "horn_stl" in st.session_state
    has_flange = "flange_stl" in st.session_state

    c1, c2 = st.columns([1, 2])
    with c1:
        if has_horn:
            st.success(f"✅ Horn: {st.session_state['horn_label']}")
        else:
            st.warning("❌ Generate a horn first (Tab 1)")

        if has_flange:
            st.success(f"✅ Flange loaded")
        else:
            st.warning("❌ Generate a flange first (Tab 2)")

        merge_btn = st.button("🧩 Merge & Download",
            type="primary", use_container_width=True,
            disabled=not (has_horn and has_flange))

    with c2:
        if merge_btn and has_horn and has_flange:
            import trimesh
            from trimesh import creation

            with st.spinner("Merging …"):
                try:
                    horn_m   = trimesh.load(io.BytesIO(st.session_state["horn_stl"]), file_type='stl')
                    flange_m = trimesh.load(io.BytesIO(st.session_state["flange_stl"]), file_type='stl')

                    # Ensure both are watertight volumes
                    for label, mesh in [("Horn", horn_m), ("Flange", flange_m)]:
                        if not mesh.is_watertight:
                            mesh.fill_holes()
                            mesh.remove_unreferenced_vertices()
                            mesh.update_faces(mesh.nondegenerate_faces())
                            if not mesh.is_watertight:
                                st.error(f"❌ {label} is not a watertight volume — merge impossible")
                                st.stop()

                    # Horn outer radius at throat  →  flange wraps AROUND it
                    v = horn_m.vertices[horn_m.vertices[:,2] < 0.5]
                    horn_outer = float(np.sqrt(v[:,0]**2 + v[:,1]**2).max())
                    flange_outer = flange_m.bounds[1,0]
                    f_h = flange_m.bounds[1,2] - flange_m.bounds[0,2]

                    # Rebuild flange ring: inner = horn_outer (wraps around, no step)
                    eps = 0.01  # tiny Z-shift to avoid coplanar face issues
                    horn_inner = float(np.sqrt(v[:,0]**2+v[:,1]**2).min())
                    ring_ok = False
                    for sections in [80, 64, 48, 32]:
                        try:
                            disc = creation.cylinder(radius=flange_outer, height=f_h, sections=sections,
                                transform=np.array([[1,0,0,0],[0,1,0,0],[0,0,1,eps+f_h/2],[0,0,0,1]]))
                            hole = creation.cylinder(radius=horn_outer-0.1, height=f_h+2, sections=sections,
                                transform=np.array([[1,0,0,0],[0,1,0,0],[0,0,1,eps+f_h/2],[0,0,0,1]]))
                            flange_ring = trimesh.boolean.difference([disc, hole], engine="manifold")
                            ring_ok = flange_ring.is_watertight
                            if ring_ok:
                                break
                        except Exception:
                            continue
                    if not ring_ok:
                        # Fallback: create ring by removing center from disc with a larger gap
                        hole = creation.cylinder(radius=horn_outer+2, height=f_h+2, sections=48,
                            transform=np.array([[1,0,0,0],[0,1,0,0],[0,0,1,eps+f_h/2],[0,0,0,1]]))
                        flange_ring = trimesh.boolean.difference([disc, hole], engine="manifold")
                        if not flange_ring.is_watertight:
                            st.error("❌ Flange ring generation failed — not a volume")
                            st.stop()

                    # Bolt holes
                    bc_r = 22.0; bn = 4; bd = 3.5
                    if "_flange_params" in st.session_state:
                        bc_r = st.session_state["_flange_params"].get("bc_rad", bc_r)
                        bn   = st.session_state["_flange_params"].get("n", bn)
                        bd   = st.session_state["_flange_params"].get("bd", bd)
                    for a in np.linspace(0, 2*np.pi, int(bn), False):
                        x,y = bc_r*np.cos(a), bc_r*np.sin(a)
                        sh = creation.cylinder(radius=bd/2, height=f_h+4, sections=32,
                            transform=np.array([[1,0,0,x],[0,1,0,y],[0,0,1,(f_h+4)/2],[0,0,0,1]]))
                        flange_ring = trimesh.boolean.difference([flange_ring, sh], engine="manifold")
                        if not flange_ring.is_watertight:
                            st.error(f"❌ Bolt hole subtraction failed at ({x:.0f},{y:.0f})")
                            st.stop()

                    # Union: flange wraps around horn, merges at outer wall
                    combined = trimesh.boolean.union([horn_m, flange_ring], engine="manifold")

                    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
                        tmp_path = tmp.name
                    combined.export(tmp_path)
                    with open(tmp_path, "rb") as f:
                        stl_bytes = f.read()
                    os.unlink(tmp_path)

                    st.metric("Triangles", len(combined.faces))
                    st.metric("Bodies", combined.body_count)
                    st.success("✅ Watertight" if combined.is_watertight else "❌")
                    st.download_button("📥 Download Merged STL", stl_bytes,
                        "horn_con_flangia.stl", "model/stl", use_container_width=True)

                except Exception as exc:
                    st.error(f"Merge failed: {exc}")
        else:
            st.info("Generate both a horn (Tab 1) and a flange (Tab 2) before merging.")
