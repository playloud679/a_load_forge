"""
Horn Generator — parametric acoustic horn + mounting flanges.
"""

import io, os, sys, tempfile
from pathlib import Path
import streamlit as st
import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "src"))

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

st.set_page_config(page_title="Horn Generator", layout="wide")
st.title("Horn Generator")

# ═══ LEFT COLUMN: Horn Profile + Preview ═══
# ═══ RIGHT COLUMN: Flanges + Assembly ═══

col_L, col_M, col_R = st.columns([2, 3, 2])

with col_L:
    st.subheader("Horn Profile")

    c1, c2, c3 = st.columns(3)
    with c1:
        profilo = st.selectbox("Profile", ["tractrix","lecleach","iwata","rectangular","radial"], index=0)
    with c2:
        spessore = st.number_input("Wall Thickness (mm)", 1.0, 20.0, 4.0, 0.5)
    with c3:
        segmenti = st.number_input("Profile Points", 100, 50000, 300, 50)

    is_rect = profilo == "rectangular"
    is_radial = profilo == "radial"
    has_fc = profilo in ("lecleach","iwata","rectangular","radial")

    c4, c5, c6, c7 = st.columns(4)
    with c4:
        if is_rect:   tw = st.number_input("Throat Width (mm)", 4.0, 200.0, 20.0, 1.0)
        elif is_radial: td = st.number_input("Throat Ø (mm)", 5.0, 100.0, 25.0, 1.0)
        else:          td = st.number_input("Throat Ø (mm)", 2.0, 200.0, 20.0, 1.0)
    with c5:
        if is_rect:   th = st.number_input("Throat Height (mm)", 2.0, 200.0, 10.0, 1.0)
        elif is_radial: md = st.number_input("Mouth Ø (mm)", 20.0, 500.0, 200.0, 5.0)
        elif profilo=="tractrix": md = st.number_input("Mouth Ø (mm)", 4.0, 500.0, 100.0, 5.0)
        else: st.caption("Mouth — computed from Fc")
    with c6:
        if has_fc: fc = st.number_input("Cutoff Fc (Hz)", 50, 20000, 600, 50)
        else: fc = None; st.caption("—")
    with c7:
        if is_rect: mw = st.number_input("Mouth Width (mm)", 10.0, 500.0, 160.0, 5.0)
        elif profilo=="iwata": ln = st.number_input("Length (mm)", 10.0, 500.0, 80.0, 5.0)
        else: st.caption("—")

    # Derived metrics
    for _k in ("horn_fc","horn_len","horn_mouth"):
        if _k not in st.session_state: st.session_state[_k] = None
    try:
        if is_rect:
            z_p,w_p,h_p=_rh().get_rectangular_exponential(tw,th,mw,fc,segmenti)
            st.session_state.horn_len=z_p[-1]; st.session_state.horn_mouth=f"{w_p[-1]:.0f}×{h_p[-1]:.0f}"; st.session_state.horn_fc=None
        elif is_radial:
            st.session_state.horn_len=st.session_state.horn_mouth=st.session_state.horn_fc=None
        elif profilo=="tractrix":
            z_p,r_p=_core().get_tractrix(td,md,segmenti)
            st.session_state.horn_len=z_p[-1]; st.session_state.horn_mouth=f"Ø{r_p[-1]*2:.0f}"; st.session_state.horn_fc=343_000/(np.pi*md)
        elif profilo=="lecleach":
            z_p,r_p=_core().get_lecleach(td,fc,segmenti)
            mi=int(np.argmax(z_p)); st.session_state.horn_len=z_p.max(); st.session_state.horn_mouth=f"Ø{r_p[mi]*2:.0f}"; st.session_state.horn_fc=None
        elif profilo=="iwata":
            z_p,r_p=_core().get_iwata(td,fc,ln,segmenti)
            st.session_state.horn_len=None; st.session_state.horn_mouth=f"Ø{r_p.max()*2:.0f}"; st.session_state.horn_fc=None
    except: pass
    _m=[]
    if st.session_state.horn_len is not None: _m.append(f"L={st.session_state.horn_len:.0f} mm")
    if st.session_state.horn_mouth is not None: _m.append(f"Mouth {st.session_state.horn_mouth}")
    if st.session_state.horn_fc is not None: _m.append(f"Fc={st.session_state.horn_fc:.0f} Hz")
    if _m: st.caption(" · ".join(_m))

    # 2D Preview
    with st.expander("2D Profile Preview"):
        if st.button("Show Preview", use_container_width=True):
            import matplotlib.pyplot as plt
            C=_core()
            try:
                if is_rect:
                    z_p,w_p,h_p=_rh().get_rectangular_exponential(tw,th,mw,fc,segmenti)
                    f,ax=plt.subplots()
                    ax.plot(z_p,w_p/2,label="Half-width",c="#2196F3"); ax.plot(z_p,h_p/2,label="Half-height",c="#FF5722")
                    ax.plot(z_p,w_p/2+spessore,"--",c="#2196F3",alpha=.4); ax.plot(z_p,h_p/2+spessore,"--",c="#FF5722",alpha=.4)
                    ax.set_xlabel("Z (mm)"); ax.set_ylabel("R (mm)"); ax.legend(); ax.grid(True,alpha=.3)
                    st.pyplot(f); st.caption(f"Mouth: {w_p[-1]:.0f}×{h_p[-1]:.0f} mm · L={z_p[-1]:.0f} mm")
                elif is_radial:
                    Rr,Zb,Zt=_rd().get_radial_profiles(td,md,fc,segmenti)
                    f,ax=plt.subplots()
                    ax.plot(Rr,Zb,label="Bottom",c="#FF5722"); ax.plot(Rr,Zt,label="Top",c="#2196F3")
                    ax.fill_between(Rr,Zb,Zt,alpha=.15,color="#4CAF50"); ax.set_xlabel("R"); ax.set_ylabel("Z")
                    ax.legend(); ax.grid(True,alpha=.3); st.pyplot(f)
                    st.caption(f"Gap: H(Rt)={Zt[0]-Zb[0]:.1f} → H(Rm)={Zt[-1]-Zb[-1]:.1f} mm")
                else:
                    z_p,r_p=C.get_tractrix(td,md,segmenti) if profilo=="tractrix" else \
                           (C.get_lecleach(td,fc,segmenti) if profilo=="lecleach" else C.get_iwata(td,fc,ln,segmenti))
                    f,ax=plt.subplots()
                    ax.plot(z_p,r_p,label="Inner",c="#2196F3"); ax.plot(z_p,r_p+spessore,"--",label="+ wall",c="#FF5722",alpha=.5)
                    ax.set_xlabel("Z (mm)"); ax.set_ylabel("R (mm)"); ax.legend(); ax.grid(True,alpha=.3)
                    st.pyplot(f); st.caption(f"Mouth: Ø{r_p[-1]*2:.0f} mm · L={z_p[-1]:.0f} mm")
            except Exception as exc: st.error(f"Preview failed: {exc}")
        else: st.info("Click **Show Preview**")

# ═══ MIDDLE COLUMN: Flanges ═══

with col_M:
    st.subheader("Mounting Flanges")

    f_tipo = "rectangular" if is_rect else "circular"

    def _calc_flange_defaults():
        if is_rect:
            inner_r_g=max(tw,th)/2; inner_r_m=mw/2; mid_pct=50
            z_p,w_p,h_p=_rh().get_rectangular_exponential(tw,th,mw,fc,segmenti)
            mid_idx=int(np.searchsorted(z_p,z_p[-1]*mid_pct/100.0)); inner_r_mid=max(w_p[mid_idx],h_p[mid_idx])/2
        elif is_radial:
            inner_r_g=td/2; inner_r_m=md/2; mid_pct=50; inner_r_mid=None
        elif profilo=="tractrix":
            inner_r_g=td/2; inner_r_m=md/2; mid_pct=50
            z_p,r_p=_core().get_tractrix(td,md,segmenti)
            mid_idx=int(np.searchsorted(z_p,z_p[-1]*mid_pct/100.0)); inner_r_mid=r_p[mid_idx]
        else:
            C=_core(); mid_pct=50
            if profilo=="lecleach":
                z_p,r_p=C.get_lecleach(td,fc,segmenti); inner_r_m=r_p.max()
                mid_idx=int(np.searchsorted(z_p,z_p.max()*mid_pct/100.0)); inner_r_mid=r_p[mid_idx]
            else:
                z_p,r_p=C.get_iwata(td,fc,ln,segmenti); inner_r_m=r_p.max()
                mid_idx=int(np.searchsorted(z_p,z_p[-1]*mid_pct/100.0)); inner_r_mid=r_p[mid_idx]
            inner_r_g=td/2

        fg_od=inner_r_g*2+20
        if profilo=="lecleach": fm_od=inner_r_m*2; fm_hole=fm_od-20
        else: fm_od=inner_r_m*2+20; fm_hole=inner_r_m*2

        outer_r_g=inner_r_g+spessore; outer_r_m=inner_r_m+spessore
        fg_bc=outer_r_g+fg_od/2
        fm_bc=(fm_hole/2+fm_od/2) if profilo=="lecleach" else outer_r_m+fm_od/2

        if inner_r_mid is not None:
            mid_od=inner_r_mid*2+20; mid_hole=inner_r_mid*2; outer_r_mid=inner_r_mid+spessore; mid_bc=outer_r_mid+mid_od/2
        else: mid_od=mid_hole=mid_bc=outer_r_mid=0.0

        return fg_od,fm_od,fg_bc,fm_bc,outer_r_g,outer_r_m,fm_hole,mid_pct,mid_od,mid_hole,mid_bc,outer_r_mid

    _need_recalc = "fg_od" not in st.session_state or st.session_state.get("_profile","")!=profilo
    st.session_state["_profile"]=profilo

    if _need_recalc:
        fg_od_d,fm_od_d,fg_bc_d,fm_bc_d,fg_br,fm_br,fm_hole_d,mid_pos,mid_od_d,mid_hole_d,mid_bc_d,mid_br=_calc_flange_defaults()
        st.session_state.update({"fg_od":fg_od_d,"fm_od":fm_od_d,"fg_bc":fg_bc_d,"fm_bc":fm_bc_d,
            "fg_outer_r":fg_br,"fm_outer_r":fm_br,"fm_hole":fm_hole_d,
            "mid_pos":mid_pos,"mid_od":mid_od_d,"mid_hole":mid_hole_d,"mid_bc":mid_bc_d,"mid_outer_r":mid_br})

    if st.button("Auto-calculate Flanges", use_container_width=True):
        fg_od_d,fm_od_d,fg_bc_d,fm_bc_d,fg_br,fm_br,fm_hole_d,mid_pos,mid_od_d,mid_hole_d,mid_bc_d,mid_br=_calc_flange_defaults()
        st.session_state.update({"fg_od":fg_od_d,"fm_od":fm_od_d,"fg_bc":fg_bc_d,"fm_bc":fm_bc_d,
            "fg_outer_r":fg_br,"fm_outer_r":fm_br,"fm_hole":fm_hole_d,
            "mid_pos":mid_pos,"mid_od":mid_od_d,"mid_hole":mid_hole_d,"mid_bc":mid_bc_d,"mid_outer_r":mid_br})

    # Throat + Mouth + Mid — 3 columns
    cg1,cg2,cg3=st.columns(3)
    with cg1:
        st.markdown("##### Throat")
        gen_gola=st.checkbox("Include",True,key="gen_gola")
        fg_esterno=st.number_input("Outer Ø",10.0,300.0,key="fg_od",step=1.0,label_visibility="collapsed")
        st.caption(f"Outer Ø: {st.session_state.fg_od:.0f}")
        fg_spess=st.number_input("Thickness",2.0,20.0,6.0,0.5,key="fg_spess",label_visibility="collapsed")
        fg_offset=st.number_input("Z Offset",-50.0,50.0,0.0,0.5,label_visibility="collapsed")
        fg_cfori=st.number_input("Bolt Circle Ø",10.0,280.0,key="fg_bc",step=1.0,label_visibility="collapsed")
        fg_nbull=st.number_input("Bolts",2,24,4,1,key="fg_nbull",label_visibility="collapsed")
        fg_dboll=st.number_input("Bolt Hole Ø",1.0,12.0,3.5,0.1,key="fg_dboll",label_visibility="collapsed")
    with cg2:
        st.markdown("##### Mouth")
        gen_bocca=st.checkbox("Include",True,key="gen_bocca")
        fm_esterno=st.number_input("Outer Ø",10.0,1000.0,key="fm_od",step=1.0,label_visibility="collapsed")
        fm_spess=st.number_input("Thickness",2.0,20.0,6.0,0.5,key="fm_spess",label_visibility="collapsed")
        fm_offset=st.number_input("Z Offset",-50.0,50.0,0.0,0.5,key="fm_offset",label_visibility="collapsed")
        fm_cfori=st.number_input("Bolt Circle Ø",10.0,980.0,key="fm_bc",step=1.0,label_visibility="collapsed")
        fm_nbull=st.number_input("Bolts",2,24,4,1,key="fm_nbull",label_visibility="collapsed")
        fm_dboll=st.number_input("Bolt Hole Ø",1.0,12.0,3.5,0.1,key="fm_dboll",label_visibility="collapsed")
    with cg3:
        st.markdown("##### Mid")
        if not is_radial:
            gen_mid=st.checkbox("Include",False,key="gen_mid")
            mid_pos=st.number_input("Position %",5,95,key="mid_pos",step=5,label_visibility="collapsed")
            mid_esterno=st.number_input("Outer Ø",10.0,1000.0,key="mid_od",step=1.0,label_visibility="collapsed")
            mid_spess=st.number_input("Thickness",2.0,20.0,4.0,0.5,key="mid_spess",label_visibility="collapsed")
            mid_cfori=st.number_input("Bolt Circle Ø",10.0,980.0,key="mid_bc",step=1.0,label_visibility="collapsed")
            mid_nbull=st.number_input("Bolts",2,24,4,1,key="mid_nbull",label_visibility="collapsed")
            mid_dboll=st.number_input("Bolt Hole Ø",1.0,12.0,3.5,0.1,key="mid_dboll",label_visibility="collapsed")
        else:
            gen_mid=False

# ═══ RIGHT COLUMN: Assembly + Download ═══

with col_R:
    st.subheader("Assembly")
    cg,_=st.columns([1,3])
    with cg: gen_horn=st.checkbox("Include Horn",True,key="gen_horn")
    gen_btn=st.button("Generate Assembly STL",type="primary",use_container_width=True)

    if gen_btn:
        with st.spinner("Generating …"):
            try:
                C=_core(); import trimesh as _tm
                if is_rect:
                    z,w,h=_rh().get_rectangular_exponential(tw,th,mw,fc,segmenti)
                    with tempfile.NamedTemporaryFile(suffix=".stl",delete=False) as t: tp=t.name
                    _rh().generate_rectangular_3d_mesh(z,w,h,spessore,tp)
                    horn=_tm.load(tp,file_type="stl"); os.unlink(tp)
                    bocca_w=float(horn.bounds[1,0]-horn.bounds[0,0]); bocca_h=float(horn.bounds[1,1]-horn.bounds[0,1])
                elif is_radial:
                    with tempfile.TemporaryDirectory() as _tmp:
                        _rd().generate_radial_horn(td,md,fc,48,_tmp)
                        horn=_tm.load(os.path.join(_tmp,"radial_bottom.stl"),file_type="stl")
                    bocca_w=bocca_h=md
                else:
                    z_p,r_p=C.get_tractrix(td,md,segmenti) if profilo=="tractrix" else \
                           (C.get_lecleach(td,fc,segmenti) if profilo=="lecleach" else C.get_iwata(td,fc,ln,segmenti))
                    with tempfile.NamedTemporaryFile(suffix=".stl",delete=False) as t: tp=t.name
                    C.generate_3d_mesh_from_profile(z_p,r_p,spessore,64,tp)
                    horn=_tm.load(tp,file_type="stl"); os.unlink(tp)
                    bocca_w=bocca_h=float(np.sqrt(horn.vertices[:,0]**2+horn.vertices[:,1]**2).max())*2

                def _dim1(v):
                    if is_rect: return float(np.abs(v[:,0]).max())*2,float(np.abs(v[:,1]).max())*2
                    ho=float(np.sqrt(v[:,0]**2+v[:,1]**2).max()); return ho*2,ho*2

                z_min=horn.vertices[:,2].min()
                v_gola=horn.vertices[np.abs(horn.vertices[:,2]-z_min)<1.0]
                if len(v_gola)<4: v_gola=horn.vertices[np.abs(horn.vertices[:,2]-z_min)<5.0]
                fiw_g,fih_g=_dim1(v_gola)

                rr_mouth=np.sqrt(horn.vertices[:,0]**2+horn.vertices[:,1]**2)
                idx_max_r=int(rr_mouth.argmax())
                if profilo=="lecleach":
                    z_mouth=float(horn.vertices[idx_max_r,2])
                    v_bocca=horn.vertices[rr_mouth>(rr_mouth[idx_max_r]-2.0)]
                    if len(v_bocca)<4: v_bocca=horn.vertices[rr_mouth>(rr_mouth[idx_max_r]-10.0)]
                else:
                    z_mouth=horn.vertices[:,2].max()
                    v_bocca=horn.vertices[np.abs(horn.vertices[:,2]-z_mouth)<1.0]
                    if len(v_bocca)<4: v_bocca=horn.vertices[np.abs(horn.vertices[:,2]-z_mouth)<5.0]
                fiw_m,fih_m=_dim1(v_bocca)
                if profilo=="lecleach": fiw_m=fiw_m-20

                f_gola=f_bocca=None
                if gen_gola:
                    if f_tipo=="rectangular":
                        f_gola=_rf().generate_rectangular_flange(outer_diam=fg_esterno,inner_w=fiw_g,inner_h=fih_g,
                            thickness=fg_spess,bolt_radius=fg_cfori/2,bolt_count=int(fg_nbull),bolt_diam=fg_dboll,output_path=None)
                    else:
                        f_gola=_fg().generate_flange(throat_R=fiw_g/2,flange_R=fg_esterno/2,
                            thickness=fg_spess,bolt_R=fg_cfori/2,bolt_n=int(fg_nbull),bolt_d=fg_dboll,offset=fg_offset+fg_spess)
                if gen_bocca:
                    if f_tipo=="rectangular":
                        f_bocca=_rf().generate_rectangular_flange(outer_diam=fm_esterno,inner_w=fiw_m,inner_h=fih_m,
                            thickness=fm_spess,bolt_radius=fm_cfori/2,bolt_count=int(fm_nbull),bolt_diam=fm_dboll,output_path=None)
                    else:
                        _fm_R=fm_esterno/2
                        if profilo=="lecleach":
                            _fm_R=min(_fm_R,rr_mouth[idx_max_r])
                            fiw_m=min(fiw_m,_fm_R*2-4)
                        f_bocca=_fg().generate_flange(throat_R=fiw_m/2,flange_R=_fm_R,
                            thickness=fm_spess,bolt_R=fm_cfori/2,bolt_n=int(fm_nbull),bolt_d=fm_dboll,offset=z_mouth+fm_offset)

                f_mid=None
                if not is_radial and gen_mid:
                    z_len=horn.vertices[:,2].max()-z_min; z_mid_pos=z_min+z_len*mid_pos/100.0
                    v_mid=horn.vertices[np.abs(horn.vertices[:,2]-z_mid_pos)<1.0]
                    if len(v_mid)<4: v_mid=horn.vertices[np.abs(horn.vertices[:,2]-z_mid_pos)<5.0]
                    fiw_mid,fih_mid=_dim1(v_mid)
                    if f_tipo=="rectangular":
                        f_mid=_rf().generate_rectangular_flange(outer_diam=mid_esterno,inner_w=fiw_mid,inner_h=fih_mid,
                            thickness=mid_spess,bolt_radius=mid_cfori/2,bolt_count=int(mid_nbull),bolt_diam=mid_dboll,output_path=None)
                    else:
                        f_mid=_fg().generate_flange(throat_R=fiw_mid/2,flange_R=mid_esterno/2,
                            thickness=mid_spess,bolt_R=mid_cfori/2,bolt_n=int(mid_nbull),bolt_d=mid_dboll,offset=z_mid_pos)

                bodies=[]
                if gen_horn: bodies.append(horn)
                if f_gola is not None: bodies.append(f_gola)
                if f_bocca is not None: bodies.append(f_bocca)
                if f_mid is not None: bodies.append(f_mid)
                if not bodies: st.error("Select at least one element"); st.stop()

                if is_rect: combined=_tm.util.concatenate(bodies)
                elif len(bodies)==1: combined=bodies[0]
                else:
                    try: combined=_tm.boolean.union(bodies,engine="manifold")
                    except: combined=_tm.util.concatenate(bodies)

                with tempfile.NamedTemporaryFile(suffix=".stl",delete=False) as t: tp=t.name
                combined.export(tp)
                with open(tp,"rb") as f: stl_bytes=f.read()
                os.unlink(tp)

                st.success("Assembly generated")
                _wt=combined.is_watertight if hasattr(combined,'is_watertight') else None
                _vol=combined.volume if hasattr(combined,'volume') else 0
                _tris=len(combined.faces) if hasattr(combined,'faces') else 0

                cm1,cm2,cm3,cm4=st.columns(4)
                _lbl = f"<small>Length</small><br><b>{horn.bounds[1,2]-horn.bounds[0,2]:.0f} mm</b>" if gen_horn else "<small>Length</small><br>—"
                with cm1: st.markdown(_lbl, unsafe_allow_html=True)
                _m = f"Ø{bocca_w:.0f}" if abs(bocca_w-bocca_h)<1 else f"{bocca_w:.0f}×{bocca_h:.0f}"
                _lbl2 = f"<small>Mouth</small><br><b>{_m} mm</b>" if gen_horn else "<small>Mouth</small><br>—"
                with cm2: st.markdown(_lbl2, unsafe_allow_html=True)
                with cm3: st.markdown(f"<small>Triangles</small><br><b>{_tris:,}</b>", unsafe_allow_html=True)
                with cm4: st.markdown(f"<small>Volume</small><br><b>{_vol:.0f} mm³</b>", unsafe_allow_html=True)
                if _wt is True: st.success("Watertight — ready for 3D printing")
                elif _wt is False: st.warning("Not watertight — check parameters")
                else: st.info("Multi-body output")
                st.download_button("Download STL",stl_bytes,"horn_assembly.stl","model/stl",use_container_width=True)

            except Exception as exc:
                import traceback; st.error(f"Generation failed: {exc}"); st.code(traceback.format_exc())
