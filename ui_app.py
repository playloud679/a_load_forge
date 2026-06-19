"""
flare_forge — Professional single-tab dashboard.
Layout: sidebar parameters + main preview/output workspace.
"""

import io, logging, os, sys, tempfile
from pathlib import Path

# Server-side logger. Tracebacks go HERE (visible to the operator in the app
# logs), never to the browser — a traceback leaks source-code snippets to
# whoever is using the app. See st.error usage below.
logger = logging.getLogger("flare_forge.ui")

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent / "src"))
import profile_generator as _core
import flange_generator as _fg
import rectangular_flange as _rf
import rectangular_horn as _rh
import polygonal_horn as _ph
import _slicer as _slc
import throat_adapter as _ta
import osse_horn as _osse
import _utils as _uts
import _step_export as _step
import dxf_export as _dxf

import importlib
importlib.reload(_core)
importlib.reload(_fg)
importlib.reload(_rf)
importlib.reload(_rh)
importlib.reload(_ph)
importlib.reload(_slc)
importlib.reload(_ta)
importlib.reload(_osse)
importlib.reload(_uts)
importlib.reload(_step)
importlib.reload(_dxf)

export_step = _step.export_step
mesh_to_flange_dxf = _dxf.mesh_to_flange_dxf

# App version — read from the repo VERSION file so the UI badge always matches
# the released version without a second source of truth to keep in sync.
try:
    _VERSION = (Path(__file__).parent / "VERSION").read_text().strip()
except OSError:
    _VERSION = "dev"
_LOGO_PATH = Path(__file__).parent / "assets" / "flare_forge_logo.png"

st.set_page_config(page_title=f"flare_forge v{_VERSION}", layout="wide",
    initial_sidebar_state="expanded", menu_items={})

st.markdown(
    """
    <style>
    @media (max-width: 768px) {
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div,
        div[data-testid="stSidebarContent"] {
            width: 100vw !important;
            min-width: 100vw !important;
            max-width: 100vw !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Support link ─────────────────────────────────────────────────────
# Replace with your Buy Me a Coffee username; the button hides if left blank.
BMC_USERNAME = "steo_lab"
BMC_URL = f"https://buymeacoffee.com/{BMC_USERNAME}"

# ── Flange recalculation callback ────────────────────────────────────

def _on_horn_change():
    """Recalculate geometry-dependent flange defaults when horn changes."""
    for _k in ("ft_ring", "ft_bc", "ft_bc_rad", "ft_ow", "ft_oh",
               "fm_spess", "fm_ring", "fm_bc", "fm_ow", "fm_oh",
               "fm_custom_d", "fm_custom_w", "fm_custom_h",
               "mid_ring", "mid_bc", "mid_ow", "mid_oh",
               "mid_custom_d", "mid_custom_w", "mid_custom_h"):
        st.session_state.pop(_k, None)
    st.session_state.pop("_combined", None)
    st.session_state.pop("_flange_bodies", None)
    st.session_state.pop("_adapter_cut_z", None)
    st.session_state.pop("_dxf_items", None)

def _sync_throat_w():
    """Update throat H when W changes, keeping the aspect ratio."""
    ar = st.session_state.get("rect_ar", 2.0)
    st.session_state["throat_h_key"] = st.session_state["throat_w_key"] / ar
    _on_horn_change()

def _sync_throat_h():
    """Update throat W when H changes, keeping the aspect ratio."""
    ar = st.session_state.get("rect_ar", 2.0)
    st.session_state["throat_w_key"] = st.session_state["throat_h_key"] * ar
    _on_horn_change()

def _sync_throat_ar():
    """Update throat H when aspect ratio changes, keeping W constant."""
    ar = st.session_state.get("rect_ar", 2.0)
    if "throat_w_key" in st.session_state:
        st.session_state["throat_h_key"] = st.session_state["throat_w_key"] / ar
    _on_horn_change()

if _LOGO_PATH.exists():
    st.image(str(_LOGO_PATH), width="stretch")
st.caption(f":gray[v{_VERSION}] · Acoustic profile + mounting flanges · watertight assembly for 3D printing")
st.warning(
    "🚧 **Vibe-coded / AI-assisted beta**: geometric and acoustic accuracy is "
    "still being validated. Generated STL files may contain imperfections; "
    "always inspect and verify models before printing.",
    icon="⚠️",
)

# ═══════════════════════════════════════════════════════════════════════
#  ROW 1 — Sidebar horn profile + live 2D preview
# ═══════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.subheader("Acoustic Profile")

    # ── Shape — the two primary design choices ───────────────────────────
    sh1, sh2 = st.columns([1, 1])
    with sh1:
        profile_type = st.selectbox("Profile",
            ["Tractrix", "Salmon", "Iwata", "Le Cléac'h (isophase)", "Oblate spheroidal", "Conical", "R-OSSE", "OS-SE (ATH)", "Exponential"], index=6,
            on_change=_on_horn_change, key="profile_type")
    with sh2:
        section_type = st.radio("Section", ["Circular", "Polygonal", "Rectangular", "Elliptical"],
                          index=0, horizontal=True, key="section_type",
                          on_change=_on_horn_change)

    is_radial   = False
    is_poly     = section_type == "Polygonal"
    is_rect     = section_type == "Rectangular"
    is_ellip    = section_type == "Elliptical"
    is_tractrix = profile_type.startswith("Tract")
    is_salmon    = profile_type.startswith("Salmon")
    is_iwata    = profile_type.startswith("Iwata")
    is_lecleach = profile_type.startswith("Le Cl")
    is_oblate   = profile_type.startswith("Oblate")
    is_conical  = profile_type.startswith("Conical")
    is_rosse    = profile_type.startswith("R-OSSE")
    is_osse     = profile_type.startswith("OS-SE")
    is_exp      = profile_type.startswith("Exp")
    has_fc      = is_salmon or is_lecleach or is_exp
    is_T_variable = is_salmon or is_lecleach
    # Conical and Oblate share the same constant-directivity inputs
    # (throat + coverage + length, mouth derived) and the same dispatch shape,
    # so a single pair of function handles keeps every branch below to one line.
    is_cd       = is_oblate or is_conical
    _cd_fn      = _core.get_conical if is_conical else _core.get_oblate_spheroidal
    _cd_rect_fn = _rh.get_rectangular_conical if is_conical else _rh.get_rectangular_oblate_spheroidal

    # Iwata is the real l'Audiophile horn: a fixed *rectangular* dual-flare
    # geometry digitized from the plan, driven only by throat size + length.
    # It always renders as a rectangular section, whatever the Section selector.
    # Elliptical reuses the rectangular profile math + inputs (independent W/H),
    # but lofts each slice as a true ellipse instead of a rectangle. So it forces
    # is_rect for inputs/profile dispatch and is special-cased at the body,
    # flange, and adapter mesh paths.
    if is_ellip:
        is_rect = True
        is_poly = is_radial = False

    if is_iwata:
        is_rect = True
        is_poly = is_radial = False
        st.caption("ℹ️ Iwata = fixed rectangular dual-flare horn (l'Audiophile plan) — "
                   "the Section selector is ignored.")

    # OS-SE (ATH) is a full non-axisymmetric waveguide with its own r(z,φ) loft
    # engine (round throat → superelliptical mouth + diagonal ridges). Like
    # radial/Iwata it is special: it ignores the Section selector and the generic
    # profile/flange machinery, and drives its own input set + generation branch.
    if is_osse:
        is_rect = is_poly = is_ellip = is_radial = False
        st.caption("ℹ️ OS-SE (ATH) = round-throat → superelliptical-mouth waveguide "
                   "with azimuth-dependent coverage (diagonal ridges). Section selector ignored.")
    # ── Section / flare modifiers — only those relevant to the current shape
    rect_ar, n_sides, salmon_T, lecleach_angle = 2.0, 4, 0.707, 160.0
    rollback_complete, rollback_angle = False, 330.0
    _mods = (["ar"] if (is_rect and not is_iwata) else []) + (["sides"] if is_poly else []) \
            + (["T"] if is_T_variable else []) + (["angle"] if is_lecleach else []) \
            + (["rollback"] if (is_lecleach or is_rosse) else [])
    if _mods:
        _mcols = st.columns(len(_mods))
        for _mcol, _mk in zip(_mcols, _mods):
            with _mcol:
                if _mk == "ar":
                    rect_ar = st.number_input("Aspect ratio (W:H)", 1.0, 10.0, 2.0, 0.1,
                        key="rect_ar", on_change=_sync_throat_ar,
                        help="Throat width / throat height")
                elif _mk == "sides":
                    n_sides = st.select_slider("Sides", options=list(range(3, 13)),
                        value=4, key="n_sides")
                elif _mk == "T":
                    salmon_T = st.number_input("Flare parameter T", 0.0, 10.0, 0.707, 0.01,
                        key="salmon_T", on_change=_on_horn_change,
                        help="Hornresp T: 0 = catenoidal · <1 = cosh · 1 = exponential · >1 = sinh")
                elif _mk == "angle":
                    lecleach_angle = st.number_input("Termination angle (°)", 90.0, 179.0, 160.0, 5.0,
                        key="lecleach_angle", on_change=_on_horn_change,
                        help="Defines where the Le Cléac'h roll-back terminates; larger angles curl farther back")
                elif _mk == "rollback":
                    if is_rosse:
                        _rb_opts = ["Normal", "Extended"]
                        _rb_help = "Normal keeps the native Batík rollback; Extended adds an inward return curl"
                    else:
                        if st.session_state.get("rollback_mode") == "Complete":
                            st.session_state["rollback_mode"] = "Extended"
                        _rb_opts = ["Truncated", "Extended"]
                        _rb_help = "Truncated keeps the current acoustic lip; Extended adds an inward return curl"
                    rollback_mode = st.radio("Rollback lip", _rb_opts,
                        index=0, horizontal=True, key="rollback_mode",
                        on_change=_on_horn_change,
                        help=_rb_help)
                    rollback_complete = rollback_mode in ("Complete", "Extended")
                    if rollback_complete:
                        rollback_angle = st.number_input("Curl end (°)", 210.0, 360.0, 330.0, 5.0,
                            key="rollback_angle", on_change=_on_horn_change,
                            help="Final tangent angle of the added return curl")

    st.markdown("##### Acoustic Medium")
    _c_ms = st.number_input("Speed of sound (m/s)", 320.0, 360.0, 344.0, 1.0,
        on_change=_on_horn_change, key="c_sound",
        help="Temperature-dependent (≈343 at 20°C, ≈349 at 30°C). "
             "Hornresp default is 344.")

    st.markdown("##### Wall")
    thickness = st.number_input("Wall thickness (mm)", 1.0, 20.0, 4.0, 0.5,
        help="Uniform thickness applied along the profile normal",
        on_change=_on_horn_change, key="thickness")
    _quality_preset = st.session_state.get("quality_preset", "Draft 64×64")
    if _quality_preset.startswith("Fine"):
        segments, rings_n = 256, 256
    elif _quality_preset == "Custom":
        segments = int(st.session_state.get("custom_segments", st.session_state.get("segments", 300)))
        rings_n = int(st.session_state.get("custom_rings_n", st.session_state.get("rings_n", 64)))
    else:
        segments, rings_n = 64, 64

    # Engines whose historical angular default is finer than 64 keep it as a
    # floor, so default output quality never drops: elliptical loft 96,
    # OS-SE φ-grid 160. Every site lofting/offsetting the same shape MUST use
    # the same value (flange holes are positioned from these offsets).
    rings_ellip = max(96, rings_n)
    rings_osse = max(160, rings_n)

    # All flare math reads SOUND_SPEED from its module global at call time, so
    # overriding it here (after the importlib.reload above) makes the chosen
    # speed of sound flow through every profile, cutoff and mouth calculation.
    c_val = _c_ms * 1000.0  # mm/s
    _core.SOUND_SPEED = c_val
    _rh.SOUND_SPEED = c_val

    # ── Exponential profile delegate ─────────────────────────────────────
    def _get_exp_profile(throat_d, mouth_d, fc, n):
        return _core.get_exponential(throat_d, mouth_d, fc, n)

    rosse_a0, rosse_k, rosse_r = 15.0, 1.8, 0.3
    rosse_m, rosse_b, rosse_q = 0.8, 0.3, 3.7

    def _get_lecleach_profile(throat_d, fc, n):
        return _core.get_lecleach(
            throat_d, fc, n, T=salmon_T, max_angle=lecleach_angle,
            complete_rollback=rollback_complete, rollback_angle=rollback_angle)

    def _get_rosse_profile(throat_d, mouth_d, n):
        return _core.get_rosse(
            throat_d, mouth_d, coverage_h, n, rosse_a0,
            rosse_k, rosse_r, rosse_m, rosse_b, rosse_q,
            complete_rollback=rollback_complete, rollback_angle=rollback_angle)

    def _get_rect_rosse_profile(throat_w, throat_h, mouth_w, n):
        throat_eq = np.sqrt(throat_w * throat_h * 4.0 / np.pi)
        mouth_eq = mouth_w * throat_eq / throat_w
        z, r = _get_rosse_profile(throat_eq, mouth_eq, n)
        return _rh._area_to_rect(z, r, throat_w, throat_h)

    _adapter_driver_labels = {
        'Bolt-on 1" · 2 holes': "bolt_on_1in_2",
        'Bolt-on 1" · 3 holes': "bolt_on_1in_3",
        'Bolt-on 1.4" · 4 holes': "bolt_on_1_4in_4",
        'Bolt-on 2" · 4 holes': "bolt_on_2in_4",
    }

    _ta_include_adapter = False
    _ta_integration_mode = "Integrated"
    _ta_is_separated = False
    _ta_driver_type = "flanged"
    _ta_driver_key = "flanged"
    _ta_thread_key = None
    _ta_driver_clearance = 0.3
    _ta_adapter_len = 0.0
    _ta_socket_depth = 0.0
    _ft_driver_d = None
    _driver_is_custom_flange = False
    _driver_is_bolt_on = False
    _driver_is_threaded = False
    _driver_is_flanged = True

    if not is_radial and not is_iwata:
        st.markdown("##### Driver / Adapter")
        _adapter_suffix = "_osse" if is_osse else ""
        _ta_include_adapter = st.checkbox(
            "Include shape adapter", True,
            key=f"ta_incl_adapter{_adapter_suffix}",
            help="Transitions from the driver throat to the horn profile. "
                 "When enabled, the acoustic profile starts from this driver-side area.",
        )
        if _ta_include_adapter:
            _ta_integration_mode = st.radio(
                "Integration mode", ["Integrated", "Separated"],
                horizontal=True, key=f"ta_mode{_adapter_suffix}",
                help="Integrated: morph replaces the first part of the flare and welds to it. "
                     "Separated: adapter and flare are exported as independent mating parts.",
            )
            _ta_is_separated = _ta_integration_mode == "Separated"
            _driver_options = [
                "Flanged custom",
                *_adapter_driver_labels,
                'Threaded 1\u215c"-18 (25 mm bore)',
            ]
            _ta_driver_type = st.radio(
                "Driver interface", _driver_options,
                index=0 if is_osse else 2,
                key=f"ta_driver_type{_adapter_suffix}",
            )
            _driver_is_custom_flange = _ta_driver_type == "Flanged custom"
            _driver_is_bolt_on = _ta_driver_type in _adapter_driver_labels
            _driver_is_threaded = _ta_driver_type.startswith("Threaded")
            _driver_is_flanged = _driver_is_custom_flange or _driver_is_bolt_on
            _ta_driver_key = (
                _adapter_driver_labels[_ta_driver_type] if _driver_is_bolt_on
                else "1_375in" if _driver_is_threaded else "flanged"
            )
            _ta_thread_key = "1_375in" if _driver_is_threaded else None

            _ta_adapter_len = st.number_input(
                "Morph length inside horn (mm)", 5.0, 200.0, 30.0, 5.0,
                key=f"ta_adapter_len{_adapter_suffix}",
                help="Length of the round-to-shape transition. It replaces the first "
                     "part of the flare, so it does not increase horn depth.",
            )
            if _driver_is_threaded:
                _thread_spec = _ta.THREAD_SPECS[_ta_thread_key]
                _ft_driver_d = float(_thread_spec.bore_diam)
                st.caption(
                    f"Female thread: {_thread_spec.name} · acoustic bore "
                    f"\u00d8{_thread_spec.bore_diam:.1f} mm.")
                _ta_socket_depth = st.number_input(
                    "Socket depth (mm)", 5.0, 30.0, 15.0, 1.0,
                    key=f"ta_socket_depth{_adapter_suffix}",
                    help="Depth of the threaded bore for the driver.",
                )
            elif _driver_is_bolt_on:
                _driver_spec = _fg.DRIVER_FLANGE_SPECS[_ta_driver_key]
                _ta_driver_clearance = st.number_input(
                    "Throat clearance (mm)", 0.0, 2.0, 0.3, 0.1,
                    key=f"ta_driver_clearance{_adapter_suffix}",
                    help="Added to the nominal driver throat diameter.",
                )
                _ft_driver_d = float(_driver_spec.throat_diam + _ta_driver_clearance)
                st.caption(
                    f"{_driver_spec.name}: acoustic throat \u00d8{_ft_driver_d:.1f} mm.")
                _ta_socket_depth = 0.0
            else:
                _default_driver_d = float(st.session_state.get(
                    f"ft_driver_d{_adapter_suffix}",
                    25.4 if is_osse else 20.0,
                ))
                _ft_driver_d = st.number_input(
                    "Driver throat \u00d8 (mm)", 5.0, 200.0,
                    _default_driver_d, 1.0,
                    key=f"ft_driver_d{_adapter_suffix}",
                    help="Circular acoustic diameter at the driver end.",
                )
                _ta_socket_depth = 0.0

    _adapter_controls_throat = bool(_ta_include_adapter and _ft_driver_d and not is_iwata)

    st.markdown("##### Dimensions")

    # Each profile is driven by a different set of inputs; the rest are solved
    # from the math and shown as results in the "Computed" panel on the right.
    _hint = ("Set **throat + mouth**. Acoustic gap follows."         if is_radial   else
             "Set **throat + length + H/V coverage**. Mouth W×H & ridges follow." if is_osse else
             "Set **throat + mouth**. Length and Fc follow."          if is_tractrix else
             "Set **throat + outer diameter + coverage**. Shape factors control the roll-back." if is_rosse else
             "Real **Iwata** (l'Audiophile): set **throat + length**; mouth W×H & loading estimate follow." if is_iwata else
             "Set **throat + coverage + length**. Mouth follows the CD asymptote." if is_cd and not is_radial else
             "Set **throat + Fc + length** (T=0.707 Hypex)."          if is_salmon    else
             "Set **throat + Fc + termination angle**. Roll-back at mouth." if is_lecleach else
             "Set **throat W×H + mouth W**. Mouth H follows."         if is_rect     else
             "Set **throat + mouth + Fc** (Fc = flare rate). Length follows.")
    st.caption(_hint)

    col_in, col_out = st.columns(2)

    # ---- Inputs: only the parameters that drive the chosen profile --------
    # OS-SE waveguide parameters (defaults; overridden in the is_osse branch).
    osse_k, osse_s, osse_n, osse_q = 1.0, 0.8, 5.0, 0.998
    osse_throat_angle, osse_mouth_exp = 0.0, 6.0
    osse_morph_start, osse_morph_rate = 0.0, 2.0
    with col_in:
        st.markdown("**You set**")
        if is_osse:
            if _adapter_controls_throat:
                throat_d = float(_ft_driver_d)
                st.caption(
                    f"Throat is computed at the adapter exit from driver "
                    f"\u00d8{throat_d:.1f} mm and the expansion profile.")
            else:
                throat_d = st.number_input("Throat Ø (mm)", 4.0, 120.0, 25.4, 0.5,
                    help="Round driver-side opening (the small end). 25.4 mm = 1\"")
            throat_w = throat_h = throat_d
            osse_length = st.number_input("Axial length (mm)", 20.0, 500.0, 120.0, 5.0,
                help="Depth of the waveguide along the axis")
            _ocv = st.columns(2)
            with _ocv[0]:
                coverage_h = st.number_input("Horizontal coverage (°)", 10.0, 170.0, 90.0, 5.0,
                    help="Nominal horizontal beamwidth (full angle)")
            with _ocv[1]:
                coverage_v = st.number_input("Vertical coverage (°)", 10.0, 170.0, 60.0, 5.0,
                    help="Nominal vertical beamwidth (full angle)")
            st.markdown("###### Shape Factors")
            _os1, _os2 = st.columns(2)
            with _os1:
                osse_mouth_exp = st.number_input("Mouth exponent", 2.0, 20.0, 6.0, 0.5,
                    help="Superellipse mouth: 2 = ellipse · large = rectangle. "
                         "Higher pushes the diagonal ridges further to the corners.")
                osse_throat_angle = st.number_input("Throat angle (total °)", 0.0, 90.0, 0.0, 1.0,
                    help="Throat included angle (0 = flat wavefront)")
                osse_k = st.number_input("Throat expansion k", 0.0, 8.0, 1.0, 0.1,
                    help="1 = pure OS hyperbola · 0 = straight cone")
            with _os2:
                osse_n = st.number_input("SE exponent n", 2.0, 12.0, 5.0, 0.5,
                    help="How late/abrupt the mouth termination is")
                osse_s = st.number_input("Flare amount s", 0.0, 2.0, 0.8, 0.05,
                    help="Amount of mouth flare (0 = no flare)")
                osse_q = st.number_input("Truncation q", 0.90, 1.0, 0.998, 0.002,
                    help="Drops the last near-straight bit (≈0.998)")
            _om1, _om2 = st.columns(2)
            with _om1:
                osse_morph_start = st.number_input("Morph start (× L)", 0.0, 0.95, 0.0, 0.05,
                    help="Fraction of length kept as the natural OS-SE shape before the mouth morph")
            with _om2:
                osse_morph_rate = st.number_input("Morph rate γ", 1.0, 6.0, 2.0, 0.5,
                    help="How gradual the morph to the rectangular mouth is (1 = abrupt)")
            mouth_d = mouth_w = None
            _mouth_is_input = False
        elif is_iwata:
            throat_d = st.number_input("Throat Ø (mm)", 10.0, 200.0, 50.0, 1.0,
                help="Square rectangular throat, downstream of the round driver adaptor "
                     "(native plan = 50 mm, for a 1.5\" driver)")
            throat_w = throat_h = throat_d
            iwata_length = st.number_input("Axial length (mm)", 100.0, 1500.0, 572.0, 10.0,
                help="Stretches the l'Audiophile plan along the axis (native = 572 mm)")
            mouth_d = mouth_w = None
            _mouth_is_input = False
        elif is_rect:
            if _adapter_controls_throat:
                throat_d = float(_ft_driver_d)
                _adapter_start_area = np.pi * (throat_d / 2.0) ** 2
                throat_w = float(np.sqrt(_adapter_start_area * rect_ar))
                throat_h = float(np.sqrt(_adapter_start_area / rect_ar))
                st.caption(
                    f"Throat W×H is computed at the adapter exit from driver "
                    f"\u00d8{throat_d:.1f} mm and the expansion profile.")
            else:
                if "throat_w_key" not in st.session_state:
                    st.session_state["throat_w_key"] = 47.0
                    st.session_state["throat_h_key"] = 47.0 / rect_ar
                throat_w = st.number_input("Throat W (mm)", 2.0, 200.0,
                    key="throat_w_key", on_change=_sync_throat_w,
                    help="Driver-side opening — width")
                throat_h = st.number_input("Throat H (mm)", 2.0, 200.0,
                    key="throat_h_key", on_change=_sync_throat_h,
                    help="Driver-side opening — height (auto-set by aspect ratio)")
                throat_d = np.sqrt(throat_w * throat_h * 4 / np.pi)
            # Rectangular/elliptical Salmon and Le Cléac'h derive their mouth
            # from Fc + length + T, just like their circular counterparts.
            _mouth_is_input = is_tractrix or is_rosse or is_exp
        else:
            if _adapter_controls_throat:
                throat_d = float(_ft_driver_d)
                st.caption(
                    f"Throat is computed at the adapter exit from driver "
                    f"\u00d8{throat_d:.1f} mm and the expansion profile.")
            else:
                throat_d = st.number_input("Throat Ø (mm)", 2.0, 200.0,
                    25.0 if is_radial else 20.0, 1.0,
                    help="Driver-side opening — the small end")
            throat_w = throat_h = throat_d
            _mouth_is_input = is_radial or is_tractrix or is_rosse or is_exp

        if _mouth_is_input:
            if is_rect:
                mouth_w = st.number_input("Mouth W (mm)", 4.0, 500.0, 320.0, 5.0,
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

        if not is_osse:            # OS-SE already set its own H/V coverage above
            coverage_h = coverage_v = 90.0
        if (is_cd or is_rosse) and not is_radial:
            if is_rect and not is_rosse:
                _cov_cols = st.columns(2)
                with _cov_cols[0]:
                    coverage_h = st.number_input("Horizontal coverage (°)", 1.0, 179.0, 90.0, 5.0,
                        help="Nominal/asymptotic horizontal angle; actual polar response depends on frequency and driver")
                with _cov_cols[1]:
                    coverage_v = st.number_input("Vertical coverage (°)", 1.0, 179.0, 45.0, 5.0,
                        help="Nominal/asymptotic vertical angle; actual polar response depends on frequency and driver")
            else:
                coverage_h = st.number_input("Coverage (°)", 1.0, 179.0, 90.0, 5.0,
                    help="Nominal/asymptotic angle; actual polar response depends on frequency and driver")
                coverage_v = coverage_h

        if is_rosse:
            st.markdown("###### Shape Factors")
            _rc1, _rc2 = st.columns(2)
            with _rc1:
                rosse_a0 = st.number_input("Throat opening (total °)", 0.0, 179.0, 15.0, 1.0)
                rosse_k = st.number_input("Throat expansion k", 0.1, 10.0, 1.8, 0.1)
                rosse_r = st.number_input("Apex radius r", 0.01, 5.0, 0.3, 0.05)
            with _rc2:
                rosse_m = st.number_input("Apex shift m", 0.0, 1.0, 0.8, 0.05)
                rosse_b = st.number_input("Bending b", -5.0, 5.0, 0.3, 0.05)
                rosse_q = st.number_input("Throat shape q", 0.1, 20.0, 3.7, 0.1)

        if has_fc:
            _fc_help = ("Flare rate — how fast the horn opens. The mouth sets where it ends."
                        if is_exp else
                        "Cutoff frequency — sets the flare rate, and with it the mouth size.")
            fc = st.number_input("Flare Fc (Hz)", 50, 20000, 600, 50, help=_fc_help)
        else:
            fc = None

        if is_osse:
            axial_len = osse_length
        elif is_iwata:
            axial_len = iwata_length
        elif (is_salmon and not is_rect or is_cd) and not is_radial:
            axial_len = st.number_input("Axial length (mm)", 10.0, 500.0, 80.0, 5.0,
                help="Horn depth along the axis")
        else:
            axial_len = 80.0

    _adapter_profile_start_d = float(_ft_driver_d) if _ta_include_adapter and _ft_driver_d else None
    _adapter_profile_len = None
    _adapter_handoff_z = None
    if _adapter_profile_start_d is not None and not is_iwata:
        _adapter_profile_len = float(_ta_adapter_len)
        _adapter_profile_start_d = float(_adapter_profile_start_d)
        if is_rect:
            _adapter_start_area = np.pi * (_adapter_profile_start_d / 2.0) ** 2
            throat_w = float(np.sqrt(_adapter_start_area * rect_ar))
            throat_h = float(np.sqrt(_adapter_start_area / rect_ar))
            throat_d = float(np.sqrt(throat_w * throat_h * 4.0 / np.pi))
            st.caption(
                f"Adapter active: expansion starts from driver Ø{_adapter_profile_start_d:.1f} mm; "
                "flare throat is sampled at the adapter exit.")
        else:
            throat_d = float(_adapter_profile_start_d)
            throat_w = throat_h = throat_d
            st.caption(
                f"Adapter active: expansion starts from driver Ø{throat_d:.1f} mm; "
                "flare throat and S_t are sampled at the adapter exit.")

    # Compute the profile once; derive the remaining scalars.
    _len = None
    _mouth_d_eff = mouth_d or mouth_w  # circular-equivalent mouth diameter
    _fc_eff = fc
    _gap_t = _gap_m = None
    _err = False
    _zw = _zh = None  # rectangular profile arrays
    _iwata_mw = _iwata_mh = None  # iwata mouth W, H (mm)
    _mouth_w_eff = _mouth_h_eff = None  # derived rectangular/elliptical mouth
    _rect_w_o_0 = _rect_h_o_0 = 0.0  # actual outer at throat (rect)
    _rect_w_o_n = _rect_h_o_n = 0.0  # actual outer at mouth  (rect)
    # Rect-flange holes are sized to the horn's OUTER wall. Making the hole
    # exactly equal to the outer wall makes the flange's hole face *coincide*
    # with the horn's faceted outer wall → the manifold union of the two is
    # degenerate (coincident coplanar walls) and leaves a non-manifold edge
    # plus a visible ledge. Shrinking the hole by this much (per side) makes
    # the flange bite *into* the wall so the union is a clean volumetric weld.
    _FLANGE_WALL_BITE = 0.5  # mm per side
    _osse_mouth_w = _osse_mouth_h = None
    try:
        if is_osse:
            # Same grid as the mesh engine (nz≥120, nphi=rings_osse): the
            # throat-adapter sections are sampled from THIS field, so keeping
            # the grids identical makes the adapter ring sit exactly on the
            # horn facets (no chordal mismatch at the junction).
            _z_os, _phi_os, _R_os = _osse.osse_surface(
                throat_d / 2.0, axial_len,
                np.radians(coverage_h / 2.0), np.radians(coverage_v / 2.0),
                np.radians(osse_throat_angle / 2.0),
                osse_k, osse_s, osse_n, osse_q,
                osse_mouth_exp, osse_morph_start, osse_morph_rate,
                nz=max(120, int(segments) // 6), nphi=rings_osse)
            _len = float(axial_len)
            _osse_mouth_w = 2.0 * float(np.max(np.abs(_R_os[-1] * np.cos(_phi_os))))
            _osse_mouth_h = 2.0 * float(np.max(np.abs(_R_os[-1] * np.sin(_phi_os))))
            _mouth_w_eff, _mouth_h_eff = _osse_mouth_w, _osse_mouth_h
            _mouth_d_eff = float(np.sqrt(_osse_mouth_w * _osse_mouth_h))
            # Area-equivalent axisymmetric proxy for the preview plot / S_m.
            zp = _z_os
            rp = np.sqrt(np.mean(_R_os ** 2, axis=1))
        elif is_radial:
            _Rr, _Zb, _Zt = _rd.get_radial_profiles(throat_d, mouth_d, fc, 50, profile_type)
            _gap_t = _Zt[0] - _Zb[0]; _gap_m = _Zt[-1] - _Zb[-1]
        elif is_rect:
            if is_tractrix:
                zr, wr, hr = _rh.get_rectangular_tractrix(throat_w, throat_h, mouth_w, segments)
                _len = zr[-1]
                zp, rp = zr, np.sqrt(wr * hr / np.pi)
                _mouth_d_eff = 2.0 * rp[-1]
                _fc_eff = c_val / (np.pi * _mouth_d_eff)
            elif is_exp:
                zr, wr, hr = _rh.get_rectangular_exponential(throat_w, throat_h, mouth_w, fc, segments)
                _len = zr[-1]
                zp, rp = zr, np.sqrt(wr * hr / np.pi)
                _mouth_d_eff = 2.0 * rp[-1]
            elif is_salmon:
                zr, wr, hr = _rh.get_rectangular_salmon(throat_w, throat_h, fc, axial_len, segments)
                _len = axial_len
                zp, rp = zr, np.sqrt(wr * hr / np.pi)
                _mouth_d_eff = 2.0 * rp[-1]
            elif is_rosse:
                zr, wr, hr = _get_rect_rosse_profile(throat_w, throat_h, mouth_w, segments)
                _len = zr.max()
                zp, rp = zr, np.sqrt(wr * hr / np.pi)
                _mouth_d_eff = 2.0 * rp.max()
                _fc_eff = c_val / (np.pi * _mouth_d_eff)
            elif is_cd:
                zr, wr, hr = _cd_rect_fn(throat_w, throat_h, coverage_h, coverage_v, axial_len, segments)
                _len = axial_len
                zp, rp = zr, np.sqrt(wr * hr / np.pi)
                _mouth_d_eff = 2.0 * rp[-1]
                if is_oblate:
                    _fc_eff = 0.2 * c_val * min(
                        np.sin(np.radians(coverage_h / 2.0)) / (np.pi * (throat_w / 2.0)),
                        np.sin(np.radians(coverage_v / 2.0)) / (np.pi * (throat_h / 2.0)),
                    )
                else:
                    _fc_eff = c_val / (np.pi * (2.0 * np.sqrt((wr[-1] * hr[-1]) / np.pi)))
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
                zp, rp = _get_lecleach_profile(throat_d_eq, fc, segments)
                zr, wr, hr = _rh._area_to_rect(zp, rp, throat_w, throat_h)
                _mouth_d_eff = 2.0 * rp.max()
                _len = zp.max()
            if is_rosse or is_lecleach:
                _im_inner = int(np.argmax(wr * hr))
                _mouth_w_eff, _mouth_h_eff = float(wr[_im_inner]), float(hr[_im_inner])
            else:
                _mouth_w_eff, _mouth_h_eff = float(wr[-1]), float(hr[-1])
            # Actual outer dimensions at throat and mouth (normal offset)
            _nw_rect = _uts.compute_profile_normals(zr, wr, flip_if_negative=True)
            _nh_rect = _uts.compute_profile_normals(zr, hr, flip_if_negative=True)
            _z_o_rect = zr + thickness * (_nw_rect[:, 0] + _nh_rect[:, 0]) / 2.0
            # Roll-back profiles (Le Cléac'h/oblate/rosse) have non-monotonic Z;
            # clip to the true axial extent (zr.max()), NOT zr[-1] — the latter is
            # the curled-back lip and would crush the whole flare onto one plane.
            _z_o_rect = np.clip(_z_o_rect, zr.min(), zr.max())
            _z_o_rect[0] = zr[0]
            _z_o_rect[-1] = zr[-1]
            _w_o_rect = wr + 2.0 * thickness * _nw_rect[:, 1]
            _h_o_rect = hr + 2.0 * thickness * _nh_rect[:, 1]
            if is_ellip:
                # True parallel offset of the elliptical loft — identical to the
                # mesh engine — so flange holes line up with the real outer wall
                # (the radial-only rx+t/ry+t shortcut drifts off the wall in Z).
                _, _Vo_e = _core._elliptical_parallel_offset_vertices(
                    zr, wr / 2.0, hr / 2.0, thickness, rings_ellip)
                _z_o_rect = np.mean(_Vo_e[:, :, 2], axis=1)
                _w_o_rect = 2.0 * np.max(np.abs(_Vo_e[:, :, 0]), axis=1)
                _h_o_rect = 2.0 * np.max(np.abs(_Vo_e[:, :, 1]), axis=1)
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
            zp, rp = _get_lecleach_profile(throat_d, fc, segments)
            _len = zp.max(); _mouth_d_eff = rp.max() * 2
        elif is_rosse:
            zp, rp = _get_rosse_profile(throat_d, mouth_d, segments)
            _len = zp.max(); _mouth_d_eff = rp.max() * 2
            _fc_eff = c_val / (np.pi * _mouth_d_eff)
        elif is_cd:
            zp, rp = _cd_fn(throat_d, coverage_h, axial_len, segments)
            _len = zp[-1]; _mouth_d_eff = rp[-1] * 2
            if is_oblate:
                _fc_eff = 0.2 * c_val * np.sin(np.radians(coverage_h / 2.0)) / (np.pi * (throat_d / 2.0))
            else:
                _fc_eff = c_val / (np.pi * _mouth_d_eff)
        elif is_exp:
            zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
            _len = zp[-1]
    except Exception:
        _err = True

    # ---- Computed: derived scalars, shown as results (not editable) -------
    _S_t_label = "S_t"
    _adapter_handoff_value = None
    _S_t_cm2 = (throat_w * throat_h if is_rect else np.pi * (throat_d / 2) ** 2) / 100.0
    if (not _err and _adapter_profile_start_d is not None
            and _adapter_profile_len is not None and not is_iwata):
        try:
            _profile_extent_for_adapter = float(np.max(_z_os if is_osse else (zr if is_rect else zp)))
            _, _, _adapter_handoff_z = _ta.embedded_morph_span(
                float(_adapter_profile_len), _profile_extent_for_adapter,
                desired_overlap=20.0)
            _adapter_handoff_z = float(_adapter_handoff_z)

            if is_osse:
                _R_handoff = np.array([
                    np.interp(_adapter_handoff_z, _z_os, _R_os[:, j])
                    for j in range(_R_os.shape[1])
                ])
                _pts_handoff = np.column_stack([
                    _R_handoff * np.cos(_phi_os),
                    _R_handoff * np.sin(_phi_os),
                ])
                _S_t_cm2 = float(_ta._polygon_area(_pts_handoff) / 100.0)
                _adapter_handoff_value = (
                    f"{np.ptp(_pts_handoff[:, 0]):.1f}×"
                    f"{np.ptp(_pts_handoff[:, 1]):.1f} mm")
            elif is_rect:
                _peak = int(np.argmax(zr)) + 1
                _zz = np.asarray(zr[:_peak], dtype=float)
                _area = np.asarray(wr[:_peak] * hr[:_peak], dtype=float)
                _keep = np.concatenate([[True], np.diff(_zz) > 1e-8])
                _S_t_cm2 = float(np.interp(_adapter_handoff_z, _zz[_keep], _area[_keep]) / 100.0)
                _w_handoff = float(np.interp(_adapter_handoff_z, _zz[_keep], np.asarray(wr[:_peak])[_keep]))
                _h_handoff = float(np.interp(_adapter_handoff_z, _zz[_keep], np.asarray(hr[:_peak])[_keep]))
                _adapter_handoff_value = f"{_w_handoff:.1f}×{_h_handoff:.1f} mm"
            else:
                _peak = int(np.argmax(zp)) + 1
                _zz = np.asarray(zp[:_peak], dtype=float)
                _rr = np.asarray(rp[:_peak], dtype=float)
                _keep = np.concatenate([[True], np.diff(_zz) > 1e-8])
                _r_handoff = float(np.interp(_adapter_handoff_z, _zz[_keep], _rr[_keep]))
                _S_t_cm2 = float(np.pi * _r_handoff ** 2 / 100.0)
                _adapter_handoff_value = f"\u00d8{2.0 * _r_handoff:.1f} mm"
            _S_t_label = "S_t @ adapter"
        except Exception:
            _adapter_handoff_z = None
    if _err or _mouth_d_eff is None:
        _S_m_cm2 = None
    elif is_iwata and _iwata_mw is not None:
        _S_m_cm2 = _iwata_mw * _iwata_mh / 100.0   # true rectangular mouth area
    elif is_rect and _mouth_w_eff is not None:
        _S_m_cm2 = _mouth_w_eff * _mouth_h_eff / 100.0
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
            if not has_fc and _fc_eff:
                _fc_label = "OS loading estimate" if is_oblate else "Mouth-loading estimate"
                _mets.append((_fc_label, f"{_fc_eff:.0f} Hz"))
            if is_osse and _osse_mouth_w is not None:        # superelliptical mouth
                _mets.append(("Mouth W×H", f"{_osse_mouth_w:.0f}×{_osse_mouth_h:.0f} mm"))
            elif is_iwata and _iwata_mw is not None:         # real Iwata: rectangular mouth
                _mets.append(("Mouth W×H", f"{_iwata_mw:.0f}×{_iwata_mh:.0f} mm"))
            elif is_rect and not _mouth_is_input and _mouth_w_eff is not None:
                _mets.append(("Mouth W×H", f"{_mouth_w_eff:.0f}×{_mouth_h_eff:.0f} mm"))
            elif not _mouth_is_input and _mouth_d_eff:       # mouth derived (salmon/lecleach)
                _mets.append(("Mouth Ø", f"{_mouth_d_eff:.0f} mm"))
            elif is_rect and _mouth_d_eff:
                _mets.append(("Mouth Ø eq", f"{_mouth_d_eff:.0f} mm"))
            if _adapter_handoff_value:
                _mets.append(("Throat @ adapter", _adapter_handoff_value))
            _mets.append((_S_t_label, f"{_S_t_cm2:.2f} cm²"))
            if _S_m_cm2:
                _mets.append(("S_m", f"{_S_m_cm2:.2f} cm²"))
            for _lbl, _val in _mets:
                st.metric(_lbl, _val)
            if is_poly and _mouth_d_eff:
                from polygonal_horn import _r_to_circumradius
                _Rp = _r_to_circumradius(_mouth_d_eff / 2.0, n_sides)
                st.caption(f"Polygonal mouth: Ø{2*_Rp:.0f} across corners ({n_sides}-gon)")
            if _adapter_handoff_z is not None:
                st.caption(
                    f"Adapter start: Ø{_adapter_profile_start_d:.1f} mm · "
                    f"adapter exit sampled at Z={_adapter_handoff_z:.1f} mm. "
                    "Overall flare length is unchanged.")

            # ── Mouth-size adequacy check ─────────────────────────────────
            # Mouth circumference is a practical termination guideline, not a
            # prediction of the complete horn/driver acoustic response.
            _fc_used = fc if has_fc else _fc_eff
            if _fc_used and _S_m_cm2:
                _D_eq = np.sqrt(400.0 * _S_m_cm2 / np.pi)      # area-equivalent mouth Ø (mm)
                _D_min = c_val / (np.pi * _fc_used)
                if _D_eq < 0.9 * _D_min:
                    st.warning(
                        f"⚠️ Mouth ≈Ø{_D_eq:.0f} mm (area-equivalent) is below the "
                        f"~{_D_min:.0f} mm one-wavelength mouth guideline at {_fc_used:.0f} Hz. "
                        f"Expect stronger mouth reflections or weaker loading near that frequency.")

with st.container():
    st.subheader("2D Preview — Cross-section")

    try:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        fig.patch.set_facecolor("#050505")
        ax.set_facecolor("#050505")
        for _spine in ax.spines.values():
            _spine.set_color("#8a8f98")
        ax.tick_params(colors="#d7dce2")
        ax.xaxis.label.set_color("#d7dce2")
        ax.yaxis.label.set_color("#d7dce2")
        if is_poly:
            if is_tractrix:
                zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
            elif is_salmon:
                zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
            elif is_lecleach:
                zp, rp = _get_lecleach_profile(throat_d, fc, segments)
            elif is_rosse:
                zp, rp = _get_rosse_profile(throat_d, mouth_d, segments)
            elif is_cd:
                zp, rp = _cd_fn(throat_d, coverage_h, axial_len, segments)
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
            z_poly_o = np.clip(z_poly_o, np.min(zp), np.max(zp))
            z_poly_o[0] = zp[0]; z_poly_o[-1] = zp[-1]
            ax.plot(zp, R_poly_arr, label=f"Inner ({n_sides}-gon)", c="#2196F3")
            ax.plot(z_poly_o, R_poly_o, label="+ wall", c="#FF5722", alpha=.5, linestyle="--")
            ax.set_xlabel("Z (mm)")
        elif is_osse:
            # Half-width / half-height envelopes of the morphed OS-SE field.
            _wz = np.max(np.abs(_R_os * np.cos(_phi_os)[None, :]), axis=1)
            _hz = np.max(np.abs(_R_os * np.sin(_phi_os)[None, :]), axis=1)
            _dz = _R_os[:, int(np.argmin(np.abs(_phi_os - np.pi / 4.0)))]
            ax.plot(_z_os, 2.0 * _wz, label="Width W(z)", c="#2196F3")
            ax.plot(_z_os, 2.0 * _hz, label="Height H(z)", c="#FF5722")
            ax.plot(_z_os, 2.0 * _dz, label="Diagonal (ridge)", c="#4CAF50", linestyle="--", alpha=.7)
            ax.set_xlabel("Z (mm)")
        elif is_rect:
            if is_tractrix:
                zr, wr, hr = _rh.get_rectangular_tractrix(throat_w, throat_h, mouth_w, segments)
            elif is_exp:
                zr, wr, hr = _rh.get_rectangular_exponential(throat_w, throat_h, mouth_w, fc, segments)
            elif is_salmon:
                zr, wr, hr = _rh.get_rectangular_salmon(throat_w, throat_h, fc, axial_len, segments)
            elif is_rosse:
                zr, wr, hr = _get_rect_rosse_profile(throat_w, throat_h, mouth_w, segments)
            elif is_cd:
                zr, wr, hr = _cd_rect_fn(throat_w, throat_h, coverage_h, coverage_v, axial_len, segments)
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
                zp, rp = _get_lecleach_profile(throat_d, fc, segments)
            elif is_rosse:
                zp, rp = _get_rosse_profile(throat_d, mouth_d, segments)
            elif is_cd:
                zp, rp = _cd_fn(throat_d, coverage_h, axial_len, segments)
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
        ax.set_ylabel("R (mm)")
        ax.grid(True, color="#4b5563", alpha=.45)
        _legend = ax.legend(fontsize=8, facecolor="#111318", edgecolor="#4b5563", framealpha=.92)
        for _txt in _legend.get_texts():
            _txt.set_color("#f4f6f8")
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

st.sidebar.divider()
st.sidebar.subheader("Mounting Flanges")

# --- Auto-calculate flange dimensions from profile ---

def _outgoing_leg(z_o, w_o, h_o):
    """Throat→peak leg of a (possibly rolled-back) outer wall, sorted by Z.

    Roll-back profiles (Le Cléac'h, oblate, rosse) have a non-monotonic Z that
    climbs to a peak then curls the lip back toward the throat. A flange must
    weld onto the *outgoing* leg, and it must be sorted by Z so ``np.interp``
    can sample it. For ordinary monotonic profiles this returns the whole array.
    """
    z_o = np.asarray(z_o, float)
    w_o = np.asarray(w_o, float)
    h_o = np.asarray(h_o, float)
    peak = int(np.argmax(z_o))
    sl = slice(0, peak + 1)
    order = np.argsort(z_o[sl])
    return z_o[sl][order], w_o[sl][order], h_o[sl][order]


def _outer_wh_at_z(z_o, w_o, h_o, z_target):
    """Interpolated outer (w, h) of the wall at physical Z on the outgoing leg.

    Used to size a flat flange's hole from the real outer wall at the plate's
    bottom face, so the widening wall pokes through the ring and welds
    volumetrically instead of merely touching coplanar (which floats apart).
    """
    zb, wb, hb = _outgoing_leg(z_o, w_o, h_o)
    zt = float(np.clip(z_target, zb[0], zb[-1]))
    return float(np.interp(zt, zb, wb)), float(np.interp(zt, zb, hb))


def _osse_airway_wh_at_z(z_target):
    """OS-SE inner (airway) full W, H at throat-relative axial Z (mm).

    Samples the morphed ``r(z, phi)`` field: for each azimuth column interpolate
    the radius at ``z_target``, then project onto the width (phi=0) and height
    (phi=pi/2) extents. Only valid when ``is_osse`` (uses the ``_R_os`` field)."""
    zt = float(np.clip(z_target, _z_os[0], _z_os[-1]))
    Rz = np.array([np.interp(zt, _z_os, _R_os[:, j])
                   for j in range(_R_os.shape[1])])
    w = 2.0 * float(np.max(np.abs(Rz * np.cos(_phi_os))))
    h = 2.0 * float(np.max(np.abs(Rz * np.sin(_phi_os))))
    return w, h


def _osse_contour_xy(z_target):
    """Real OS-SE airway contour (x, y) at throat-relative Z — the full
    superelliptical section with its diagonal ridges, so a flange built on it
    follows the true mouth shape instead of an inscribed ellipse."""
    zt = float(np.clip(z_target, _z_os[0], _z_os[-1]))
    Rz = np.array([np.interp(zt, _z_os, _R_os[:, j])
                   for j in range(_R_os.shape[1])])
    return np.column_stack([Rz * np.cos(_phi_os), Rz * np.sin(_phi_os)])


def _mouth_station(z_o, w_o, h_o):
    """Index of the widest outer cross-section (the acoustic mouth rim).

    For roll-back profiles this is the peak of the flare, not the curled-back
    last array element. Returns (index, z_at_index)."""
    eq = np.asarray(w_o, float) * np.asarray(h_o, float)
    i = int(np.argmax(eq))
    return i, float(np.asarray(z_o, float)[i])


def _rim_weld(z_o, w_o, h_o, plate_thickness):
    """Geometry to weld a flat flange to the OUTER rim (widest cross-section).

    Returns ``(offset, wall_w, wall_h)`` where ``offset`` is the plate's bottom
    face and ``wall_w/h`` is the outer wall at the plate's rim-*distal* face.
    The wall widens toward the rim, so it pokes through the ring and welds
    volumetrically.

    Two cases, so it works for ordinary flares **and** roll-back lips:
    - rim on the outgoing leg (normal mouth, rim is the top): plate sits *below*
      the rim, hole sized at its bottom face.
    - rim on the returning leg (roll-back, rim is the bottom of the curled lip):
      plate sits *above* the rim, hole sized at its top face. This is the
      "bordo esterno" of a Le Cléac'h / R-OSSE / oblate horn.
    """
    z_o = np.asarray(z_o, float)
    w_o = np.asarray(w_o, float)
    h_o = np.asarray(h_o, float)
    rim = int(np.argmax(w_o * h_o))
    peak = int(np.argmax(z_o))
    z_rim = float(z_o[rim])
    if rim <= peak:                       # rim on the outgoing leg → plate below
        seg = slice(0, rim + 1)
        offset = z_rim - plate_thickness
        z_face = offset
    else:                                 # rim on the returning leg → plate above
        seg = slice(peak, rim + 1)
        offset = z_rim
        z_face = z_rim + plate_thickness
    zs, ws, hs = z_o[seg], w_o[seg], h_o[seg]
    order = np.argsort(zs)
    zs, ws, hs = zs[order], ws[order], hs[order]
    z_face = float(np.clip(z_face, zs[0], zs[-1]))
    return float(offset), float(np.interp(z_face, zs, ws)), float(np.interp(z_face, zs, hs))


def _rollback_mouth_geometry():
    """Return real outer-wall rim/peak geometry for a rolled-back mouth."""
    if is_radial or is_iwata or is_osse:
        return None
    if is_rect:
        z_o = np.asarray(_z_o_rect, float)
        w_o = np.asarray(_w_o_rect, float)
        h_o = np.asarray(_h_o_rect, float)
        rim = int(np.argmax(w_o * h_o))
        peak = int(np.argmax(z_o))
        return {
            "is_rollback": rim > peak,
            "shape": "elliptical" if is_ellip else "rectangular",
            "z_rim": float(z_o[rim]),
            "rim_w": float(w_o[rim]), "rim_h": float(h_o[rim]),
            "peak_w": float(w_o[peak]), "peak_h": float(h_o[peak]),
            "rim_R": max(float(w_o[rim]), float(h_o[rim])) / 2.0,
            "peak_R": max(float(w_o[peak]), float(h_o[peak])) / 2.0,
        }

    if is_tractrix:
        z, r = _core.get_tractrix(throat_d, mouth_d, segments)
    elif is_salmon:
        z, r = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
    elif is_lecleach:
        z, r = _get_lecleach_profile(throat_d, fc, segments)
    elif is_rosse:
        z, r = _get_rosse_profile(throat_d, mouth_d, segments)
    elif is_cd:
        z, r = _cd_fn(throat_d, coverage_h, axial_len, segments)
    else:
        z, r = _get_exp_profile(throat_d, mouth_d, fc, segments)

    if is_poly:
        from polygonal_horn import _r_to_circumradius
        inner_R = _r_to_circumradius(r, n_sides)
        normals = _uts.compute_profile_normals(z, inner_R, flip_if_negative=True)
        z_o = np.clip(z + thickness * normals[:, 0], np.min(z), np.max(z))
        z_o[0] = z[0]
        z_o[-1] = z[-1]
        outer_R = inner_R + thickness / np.cos(np.pi / n_sides) * normals[:, 1]
        shape = "polygonal"
    else:
        normals = _uts.compute_profile_normals(z, r)
        z_o = z + thickness * normals[:, 0]
        inner_R = r
        outer_R = r + thickness * normals[:, 1]
        shape = "circular"
    envelope_R = np.maximum(inner_R, outer_R)
    rim = int(np.argmax(envelope_R))
    peak = int(np.argmax(z_o))
    z_rim = z[rim] if inner_R[rim] >= outer_R[rim] else z_o[rim]
    return {
        "is_rollback": rim > peak,
        "shape": shape,
        "z_rim": float(z_rim),
        "rim_R": float(envelope_R[rim]),
        "peak_R": float(outer_R[peak]),
        "rim_w": float(2.0 * envelope_R[rim]),
        "rim_h": float(2.0 * envelope_R[rim]),
        "peak_w": float(2.0 * outer_R[peak]),
        "peak_h": float(2.0 * outer_R[peak]),
    }


def _polygon_radius_at_angle(circum_R, sides, angle):
    """Ray distance to a regular polygon with the project's +pi/2 phase."""
    rel = (angle - np.pi / 2.0 + np.pi / sides) % (2.0 * np.pi / sides)
    return circum_R * np.cos(np.pi / sides) / np.cos(rel - np.pi / sides)


def _calc_flange_dims():
    """Return suggested flange dimensions based on current horn profile."""

    def _mouth_wall_dz(zp, rp):
        """Axial (Z) extent of the wall at the mouth — matches the mesh engine's
        parallel normal offset, so a flange of this thickness sits flush with the
        flare (no protruding rim) instead of using the along-normal thickness."""
        nml = _uts.compute_profile_normals(zp, rp)
        z_o = zp + nml[:, 0] * thickness
        return float(max(0.1, zp[-1] - z_o[-1]))

    def _circular_mouth_hole_R(zp, rp):
        """Mouth flange hole: outermost wall radius at the acoustic rim.

        Rollback-complete profiles end at an inward curl tip, so the rim is the
        maximum envelope station, not necessarily the last sample. Near-90°
        ordinary terminations still resolve to the last sample. Bite the rim
        inward so the flange welds volumetrically instead of touching coplanar.
        """
        nml = _uts.compute_profile_normals(zp, rp)
        r_o = rp + nml[:, 1] * thickness
        rim = int(np.argmax(np.maximum(r_o, rp)))
        return float(max(r_o[rim], rp[rim]) - _FLANGE_WALL_BITE)

    mouth_dz = float(thickness)
    if is_osse:
        # OS-SE: round throat, superelliptical mouth; flanges are disabled but
        # these dims still feed previews/labels. Use the mouth half-extent.
        ir_throat = throat_d / 2.0 + thickness
        ir_mouth = (max(_osse_mouth_w or throat_d, _osse_mouth_h or throat_d) / 2.0
                    + thickness)
        _get_mid_r = lambda pct: None
    elif is_rect:
        ir_throat = throat_w / 2 + thickness
        if is_tractrix:
            zr, wr, hr = _rh.get_rectangular_tractrix(throat_w, throat_h, mouth_w, segments)
        elif is_exp:
            zr, wr, hr = _rh.get_rectangular_exponential(throat_w, throat_h, mouth_w, fc, segments)
        elif is_salmon:
            zr, wr, hr = _rh.get_rectangular_salmon(throat_w, throat_h, fc, axial_len, segments)
        elif is_rosse:
            zr, wr, hr = _get_rect_rosse_profile(throat_w, throat_h, mouth_w, segments)
        elif is_iwata:
            zr, wr, hr = _rh.get_iwata_horn(throat_d, axial_len, segments)
        elif is_cd:
            zr, wr, hr = _cd_rect_fn(throat_w, throat_h, coverage_h, coverage_v, axial_len, segments)
        else:
            throat_d_eq = np.sqrt(throat_w * throat_h * 4 / np.pi)
            zr, wr, hr = _rh._area_to_rect(
                *_get_lecleach_profile(throat_d_eq, fc, segments),
                throat_w, throat_h)
        # Mouth hole = the widest outer cross-section (roll-back aware), not the
        # curled-back last array element.
        _im, _ = _mouth_station(_z_o_rect, _w_o_rect, _h_o_rect)
        ir_mouth = max(_w_o_rect[_im], _h_o_rect[_im]) / 2 - _FLANGE_WALL_BITE
        # Mid radius sampled by physical Z on the outgoing leg (pct·_len == Z mm).
        _get_mid_r = lambda pct, _l=(_len or 1.0): (lambda w, h: max(w, h) / 2)(
            *_outer_wh_at_z(_z_o_rect, _w_o_rect, _h_o_rect, _l * pct / 100.0))
    elif is_poly:
        from polygonal_horn import _r_to_circumradius
        ir_throat = _r_to_circumradius(np.array([throat_d/2]), n_sides)[0]
        if is_tractrix:
            zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
        elif is_salmon:
            zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
        elif is_lecleach:
            zp, rp = _get_lecleach_profile(throat_d, fc, segments)
        elif is_rosse:
            zp, rp = _get_rosse_profile(throat_d, mouth_d, segments)
        elif is_cd:
            zp, rp = _cd_fn(throat_d, coverage_h, axial_len, segments)
        elif is_exp:
            zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
        R_i = _r_to_circumradius(rp, n_sides)
        nml = _uts.compute_profile_normals(zp, R_i, flip_if_negative=True)
        R_o = R_i + thickness / np.cos(np.pi / n_sides) * nml[:, 1]
        # Same rim-bite rule as _circular_mouth_hole_R; rollback-complete
        # profiles use the maximum envelope, not the inward curl tip.
        _rim_poly = int(np.argmax(np.maximum(R_o, R_i)))
        ir_mouth = float(max(R_o[_rim_poly], R_i[_rim_poly]) - _FLANGE_WALL_BITE)
        mouth_dz = _mouth_wall_dz(zp, rp)
        _get_mid_r = lambda pct: _r_to_circumradius(np.array([rp[int(len(rp)*pct/100)]]), n_sides)[0]
    elif is_radial:
        ir_throat = throat_d / 2; ir_mouth = mouth_d / 2
        _get_mid_r = lambda pct: None
    elif is_tractrix:
        ir_throat = throat_d / 2
        zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
        ir_mouth = _circular_mouth_hole_R(zp, rp)
        mouth_dz = _mouth_wall_dz(zp, rp)
        _get_mid_r = lambda pct: rp[int(np.searchsorted(zp, zp[-1]*pct/100))]
    elif is_exp:
        zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
        ir_throat = throat_d / 2
        ir_mouth = _circular_mouth_hole_R(zp, rp)
        mouth_dz = _mouth_wall_dz(zp, rp)
        _get_mid_r = lambda pct: rp[min(int(np.searchsorted(zp, zp[-1]*pct/100)), len(rp)-1)]
    elif is_cd:
        zp, rp = _cd_fn(throat_d, coverage_h, axial_len, segments)
        ir_throat = throat_d / 2
        ir_mouth = _circular_mouth_hole_R(zp, rp)
        mouth_dz = _mouth_wall_dz(zp, rp)
        _get_mid_r = lambda pct: rp[min(int(np.searchsorted(zp, zp[-1]*pct/100)), len(rp)-1)]
    elif is_rosse:
        zp, rp = _get_rosse_profile(throat_d, mouth_d, segments)
        ir_throat = throat_d / 2
        ir_mouth = _circular_mouth_hole_R(zp, rp)
        mouth_dz = _mouth_wall_dz(zp, rp)
        _z_len = zp.max()
        _get_mid_r = lambda pct, _zp=zp, _rp=rp, _zl=_z_len: _rp[np.argmin(np.abs(_zp - _zl*pct/100))]
    else:  # salmon / lecleach
        if is_salmon:
            zp, rp = _core.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
        else:
            zp, rp = _get_lecleach_profile(throat_d, fc, segments)
        ir_throat = throat_d / 2
        ir_mouth = _circular_mouth_hole_R(zp, rp)
        mouth_dz = _mouth_wall_dz(zp, rp)
        _z_len = zp.max()  # for roll-back profiles, use max z (axial extent)
        _get_mid_r = lambda pct, _zp=zp, _rp=rp, _zl=_z_len: _rp[np.argmin(np.abs(_zp - _zl*pct/100))]

    return ir_throat, ir_mouth, _get_mid_r, mouth_dz


ir_throat, ir_mouth, _get_mid_r, _mouth_wall_dz = _calc_flange_dims()

if st.sidebar.button("🔧 Recalculate flanges", use_container_width=True,
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


_FLANGE_SHAPE_LABELS = {
    "Circular": "○ Circular",
    "Polygonal": "⬡ Polygonal",
    "Rectangular": "▭ Rectangular",
    "Elliptical": "⬭ Elliptical",
}


def _flange_shape_selector(key, sides_key):
    """Custom outer-contour selector for mouth and mid flange cards."""
    options = ["Circular", "Polygonal", "Rectangular"]
    shape = st.radio(
        "Flange shape",
        options,
        index=0,
        horizontal=True,
        key=key,
        format_func=lambda value: _FLANGE_SHAPE_LABELS[value],
        help="Outer contour of the flange. The central opening still follows "
             "the horn section.",
    )
    outer_n = (
        st.select_slider(
            "Polygon sides",
            options=list(range(3, 13)),
            value=n_sides,
            key=sides_key,
            help="Number of sides on the flange outer contour.",
        )
        if shape == "Polygonal" else 0
    )
    return shape, outer_n


def _automatic_flange_shape():
    """Outer contour used when sizing is an offset from the flare."""
    if is_ellip:
        return "Elliptical", 0
    if is_rect:
        return "Rectangular", 0
    if is_poly:
        return "Polygonal", n_sides
    return "Circular", 0


def _flange_sizing_selector(key):
    """Choose relative flare offset or explicit outer flange dimensions."""
    return st.radio(
        "Sizing",
        ["Offset from flare", "Custom dimensions"],
        horizontal=True,
        key=key,
        help="Offset from flare grows the real opening by a uniform ring width. "
             "Custom dimensions sets the outer contour explicitly.",
    )


def _bolt_placement_selector(key):
    """Choose automatic radial centring or a fixed bolt circle."""
    return st.radio(
        "Hole placement",
        ["Auto centered", "Fixed from center"],
        horizontal=True,
        key=key,
        help="Auto centered places each hole halfway through the available "
             "material. Fixed from center places every hole on one bolt circle.",
    )


def _shape_limits(inner_R, inner_w, inner_h, outer_shape, outer_n,
                  outer_d, outer_w, outer_h):
    """Conservative radial limits for a fixed circular bolt pattern."""
    inner_limit = (
        np.hypot(inner_w, inner_h) / 2.0 if inner_w > 0.0 and inner_h > 0.0
        else inner_R
    )
    if outer_shape == "Circular":
        outer_limit = outer_d / 2.0
    elif outer_shape == "Polygonal":
        outer_limit = outer_d / 2.0 * np.cos(np.pi / outer_n)
    else:
        outer_limit = min(outer_w, outer_h) / 2.0
    return inner_limit, outer_limit


def _custom_dimension(label, key, minimum, suggested):
    """Positive custom dimension whose persisted value follows changing bounds."""
    minimum = float(max(1.0, minimum))
    maximum = float(max(1000.0, minimum + 10.0))
    if key not in st.session_state:
        st.session_state[key] = float(max(minimum, suggested))
    _clamp_state(key, minimum, maximum)
    return st.number_input(label, minimum, maximum, step=1.0, key=key)


def _clear_throat_flange_inputs():
    """Neutral throat-flange values used when the throat part is disabled."""
    global _ft_sp, _ft_off, _ft_nb, _ft_db, _ft_od, _ft_bc, _ft_ow, _ft_oh
    global _ft_ring, _ft_depth, _ft_outer_n, _ft_bphase, _ft_inner_R
    global _ft_inner_w, _ft_inner_h, _ft_outer_w, _ft_outer_h
    global _ft_chamfer, _ft_chamfer_w, _ft_chamfer_h, throat_outer

    _ft_sp = _ft_off = _ft_nb = _ft_db = _ft_od = _ft_bc = _ft_ow = _ft_oh = 0.0
    _ft_ring = _ft_depth = _ft_bphase = 0.0
    _ft_outer_n = 0
    _ft_inner_R = _ft_inner_w = _ft_inner_h = 0.0
    _ft_outer_w = _ft_outer_h = 0.0
    _ft_chamfer = False
    _ft_chamfer_w = _ft_chamfer_h = 0.0
    throat_outer = "Circular"


def _clear_mouth_flange_inputs():
    """Neutral mouth-flange values used when the mouth part is disabled."""
    global _fm_sp, _fm_off, _fm_nb, _fm_db, _fm_od, _fm_bc, _fm_ow, _fm_oh
    global _fm_ring, _fm_bphase, _fm_outer_n, _fm_outer_w, _fm_outer_h
    global _fm_inward, _fm_seat, _fm_head_d, _fm_seat_depth, _fm_seat_wall
    global _fm_bolt_mode, _fm_custom, mouth_outer

    _fm_sp = _fm_off = _fm_nb = _fm_db = _fm_od = _fm_bc = _fm_ow = _fm_oh = 0.0
    _fm_ring = _fm_bphase = 0.0
    _fm_outer_n = 0
    _fm_outer_w = _fm_outer_h = 0.0
    _fm_inward = _fm_seat = _fm_custom = False
    _fm_head_d = _fm_seat_depth = _fm_seat_wall = 0.0
    _fm_bolt_mode = "auto"
    mouth_outer = "Circular"


def _clear_mid_flange_inputs():
    """Neutral mid-flange values used when the mid part is disabled."""
    global _mid_pos, _mid_sp, _mid_nb, _mid_db, _mid_ring, _mid_off
    global _mid_bphase, _mid_outer_n, _mid_od, _mid_outer_w, _mid_outer_h
    global _mid_inner_R, _mid_inner_w, _mid_inner_h, _mid_bc
    global _mid_bolt_mode, _mid_custom, mid_out

    _mid_pos = 50.0
    _mid_sp = _mid_nb = _mid_db = _mid_ring = _mid_off = 0.0
    _mid_bphase = _mid_od = _mid_outer_w = _mid_outer_h = 0.0
    _mid_inner_R = _mid_inner_w = _mid_inner_h = _mid_bc = 0.0
    _mid_outer_n = 0
    _mid_bolt_mode = "auto"
    _mid_custom = False
    mid_out = "Circular"


# --- Flange inputs ---
fg1 = st.sidebar.container()
fg2 = st.sidebar.container()
fg3 = st.sidebar.container()

with fg1:
    st.markdown("##### Throat Flange / Adapter")
    if is_radial:
        st.caption("Mounting holes on bottom plate")
        gen_throat = st.checkbox("Include", True, key="gen_throat")
        if gen_throat:
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
            _ft_chamfer = False; _ft_chamfer_w = _ft_chamfer_h = 0.0
            throat_outer = "Circular"; _ta_driver_type = "flanged"; _ta_include_adapter = False
            _ta_adapter_len = 0.0; _ta_socket_depth = 0.0; _ta_is_separated = False; _ta_integration_mode = "Integrated"
        else:
            _clear_throat_flange_inputs()
    elif is_osse:
        st.caption("Round throat → flat circular bolt-on flange. Mount the driver "
                   "or an adapter to this plate.")
        if _ta_include_adapter:
            gen_throat = True
            st.caption("Shape adapter enabled above; this throat component will be generated.")
        else:
            gen_throat = st.checkbox("Include", True, key="gen_throat")
        if gen_throat:

            if _ta_include_adapter:
                _ft_chamfer = False; _ft_chamfer_w = _ft_chamfer_h = 0.0
                _ft_depth = 0.0
                _ft_inner_R = float(_ft_driver_d) / 2.0
                _ft_inner_w = _ft_inner_h = 0.0
                st.caption("Adapter acoustic controls are above; this panel only sizes the driver-side hardware.")

                if _driver_is_threaded:
                    _ft_sp = _ft_off = _ft_nb = _ft_db = _ft_od = _ft_bc = 0.0
                    _ft_ring = _ft_outer_n = 0
                    throat_outer = "Circular"; _ft_bphase = 0.0; _ft_ow = _ft_oh = 0.0
                elif _driver_is_bolt_on:
                    _driver_spec = _fg.DRIVER_FLANGE_SPECS[_ta_driver_key]
                    _ft_sp = st.number_input("Flange thickness (mm)", 2.0, 20.0, _flange_sp, 0.5,
                        key="ft_spess_osse")
                    _ft_off = 0.0
                    _ft_nb = _driver_spec.bolt_count
                    _ft_db = _driver_spec.bolt_diam
                    _ft_od = _driver_spec.outer_diam
                    _ft_bc = _driver_spec.pcd
                    _ft_bphase = _driver_spec.bolt_phase
                    _ft_outer_n = 0
                    _ft_ring = (_driver_spec.outer_diam - _ft_driver_d) / 2.0
                    throat_outer = "Circular"; _ft_ow = _ft_oh = 0.0
                    _ta_socket_depth = 0.0
                    st.caption(
                        f"{_driver_spec.name}: throat Ø{_ft_driver_d:.1f} mm · "
                        f"outer Ø{_ft_od:.1f} mm · {_ft_nb} × Ø{_ft_db:.1f} mm · "
                        f"PCD {_ft_bc:.1f} mm"
                    )
                else:
                    _ft_sp  = st.number_input("Flange thickness (mm)", 2.0, 20.0, _flange_sp, 0.5,
                        key="ft_spess_osse")
                    _ft_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="ft_off_osse_ta")
                    _ft_nb  = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="ft_nb_osse_ta")
                    _ft_db  = st.number_input("Bolt hole \u00d8 (mm)", 1.0, 12.0, _bolt_d, 0.1, key="ft_db_osse_ta")
                    st.caption(f"Hole: \u00d8{_ft_driver_d:.0f} mm (circular — driver end)")
                    _ft_bpos = st.radio("Bolt position", ["At vertices", "At mid-faces"],
                        index=0, horizontal=True, key="ft_bpos_osse_ta",
                        help="Align bolts with polygon vertices or face centers"
                        ) if is_poly else "At vertices"
                    _ft_bphase = _bolt_phase(n_sides if is_poly else 4, _ft_bpos)
                    throat_outer = st.radio("Outer shape",
                        ["Circular", "Polygonal"], index=0, horizontal=True, key="throat_outer_osse_ta")
                    _ft_outer_n = (st.select_slider("Outer sides", options=list(range(3, 13)),
                                                    value=n_sides, key="ft_outer_n_osse_ta")
                                   if throat_outer == "Polygonal" else 0)
                    _ft_ring = st.number_input("Ring width (mm)", 5.0, 200.0, 15.0, 1.0, key="ft_ring_osse_ta",
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
                        step=1.0, key="ft_bc_osse_ta")
                    _ta_socket_depth = 0.0; _ft_ow = _ft_oh = 0.0
            else:
                # ── No adapter: flat circular bolt-on throat flange ───────────
                _ft_sp = st.number_input("Thickness (mm)", 2.0, 20.0, 6.0, 0.5, key="ft_sp_osse")
                _ft_nb = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="ft_nb")
                _ft_db = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="ft_db")
                # Hole welds onto the round throat outer wall (throat_R + thickness).
                _ft_throat_R = throat_d / 2.0 + thickness
                _ft_ring = st.number_input("Offset from throat (mm)", 5.0, 100.0, 12.0, 1.0,
                    key="ft_ring_osse", help="Material added outside the throat outer wall")
                _ft_od = 2.0 * (_ft_throat_R + _ft_ring)
                _ft_bc_lo = 2.0 * (_ft_throat_R + _ft_db / 2.0 + 1.0)
                _ft_bc_hi = max(_ft_bc_lo + 2.0, _ft_od - _ft_db - 2.0)
                if "ft_bc_osse" not in st.session_state:
                    st.session_state["ft_bc_osse"] = (_ft_bc_lo + _ft_bc_hi) / 2.0
                _clamp_state("ft_bc_osse", _ft_bc_lo, _ft_bc_hi)
                _ft_bc = st.number_input("Bolt circle Ø (mm)", _ft_bc_lo, _ft_bc_hi,
                    step=1.0, key="ft_bc_osse")
                st.markdown("###### Placement & Shape")
                _ft_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="ft_off_osse")
                _ft_outer_n = int(st.number_input("Outer N-gon sides (0 = round)", 0, 12, 0, 1,
                    key="ft_outer_n_osse"))
                _ft_bphase = 0.0; throat_outer = "Circular"
                _ta_driver_type = "flanged"
                _ta_driver_key = "flanged"
                _ta_driver_clearance = 0.3
                _ta_include_adapter = False
                _ta_adapter_len = 0.0
                _ta_socket_depth = 0.0
                _ta_is_separated = False
                _ta_integration_mode = "Integrated"
                _driver_is_threaded = False
                _driver_is_flanged = True
                _ft_chamfer = False; _ft_chamfer_w = _ft_chamfer_h = 0.0

        else:
            _clear_throat_flange_inputs()
    elif not is_radial:
        if _ta_include_adapter:
            gen_throat = True
            st.caption("Shape adapter enabled above; this throat component will be generated.")
        else:
            gen_throat = st.checkbox("Include", True, key="gen_throat")
        if gen_throat:

            if _ta_include_adapter:
                _ft_chamfer = False; _ft_chamfer_w = _ft_chamfer_h = 0.0
                _ft_depth = 0.0
                _ft_inner_R = float(_ft_driver_d) / 2.0
                _ft_inner_w = _ft_inner_h = 0.0
                st.caption("Adapter acoustic controls are above; this panel only sizes the driver-side hardware.")

                if _driver_is_threaded:
                    _ft_sp = _ft_off = _ft_nb = _ft_db = _ft_od = _ft_bc = 0.0
                    _ft_ring = _ft_outer_n = 0
                    throat_outer = "Circular"; _ft_bphase = 0.0; _ft_ow = _ft_oh = 0.0
                elif _driver_is_bolt_on:
                    _driver_spec = _fg.DRIVER_FLANGE_SPECS[_ta_driver_key]
                    _ft_sp = st.number_input("Flange thickness (mm)", 2.0, 20.0, _flange_sp, 0.5,
                        key="ft_spess")
                    _ft_off = 0.0
                    _ft_nb = _driver_spec.bolt_count
                    _ft_db = _driver_spec.bolt_diam
                    _ft_od = _driver_spec.outer_diam
                    _ft_bc = _driver_spec.pcd
                    _ft_bphase = _driver_spec.bolt_phase
                    _ft_outer_n = 0
                    _ft_ring = (_driver_spec.outer_diam - _ft_driver_d) / 2.0
                    throat_outer = "Circular"; _ft_ow = _ft_oh = 0.0
                    _ta_socket_depth = 0.0
                    st.caption(
                        f"{_driver_spec.name}: throat Ø{_ft_driver_d:.1f} mm · "
                        f"outer Ø{_ft_od:.1f} mm · {_ft_nb} × Ø{_ft_db:.1f} mm · "
                        f"PCD {_ft_bc:.1f} mm"
                    )
                else:
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
            else:
                # ── No adapter: traditional throat flange ─────────────────────
                _ta_driver_type = "flanged"
                _ta_driver_key = "flanged"
                _ta_driver_clearance = 0.3
                _ta_include_adapter = False
                _ta_adapter_len = 0.0
                _ta_socket_depth = 0.0
                _ta_is_separated = False
                _ta_integration_mode = "Integrated"
                _driver_is_threaded = False
                _driver_is_flanged = True

                if is_rect:
                    _ft_inner_w = max(_rect_w_o_0 - 2 * _FLANGE_WALL_BITE, 1.0)
                    _ft_inner_h = max(_rect_h_o_0 - 2 * _FLANGE_WALL_BITE, 1.0)
                    _ft_inner_R = max(_ft_inner_w, _ft_inner_h) / 2
                    st.caption(f"Hole: {_ft_inner_w:.1f}\u00d7{_ft_inner_h:.1f} mm "
                               f"({'elliptical' if is_ellip else 'rectangular'})")
                elif is_poly:
                    from polygonal_horn import _r_to_circumradius
                    _R_poly_g     = _r_to_circumradius(np.array([throat_d/2]), n_sides)[0]
                    _R_o_g_approx = _R_poly_g + thickness / np.cos(np.pi / n_sides)
                    _ft_inner_R   = _R_o_g_approx
                    _ft_inner_w = _ft_inner_h = 0.0
                    st.caption(f"Hole: {n_sides}-gon, R={_ft_inner_R:.1f} mm")
                else:
                    _ft_inner_R = throat_d / 2 + thickness
                    _ft_inner_w = _ft_inner_h = 0.0
                    st.caption(f"Hole: \u00d8{_ft_inner_R*2:.0f} mm (circular)")

                _ft_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, _flange_sp, 0.5, key="ft_spess")
                _ft_nb  = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="ft_nb")
                _ft_db  = st.number_input("Bolt hole \u00d8 (mm)", 1.0, 12.0, _bolt_d, 0.1, key="ft_db")
                _ft_ring = st.number_input("Ring width (mm)", 5.0, 200.0, 15.0, 1.0, key="ft_ring",
                    help="Wall around the hole — this sets the flange size. Widen it to fit bolts further out.")
                st.markdown("###### Placement & Shape")
                _ft_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="ft_off")
                _ft_bpos = st.radio("Bolt position", ["At vertices", "At mid-faces"],
                    index=0, horizontal=True, key="ft_bpos",
                    help="Align bolts with polygon vertices or face centers"
                    ) if (is_poly or is_rect) else "At vertices"
                throat_outer = st.radio("Outer shape",
                    (["Elliptical", "Circular", "Rectangular"] if is_ellip else
                     ["Circular", "Rectangular"]) if is_rect else ["Circular", "Polygonal"],
                    index=0, horizontal=True, key="throat_outer")
                _ft_outer_n = (st.select_slider("Outer sides", options=list(range(3, 13)),
                                                value=n_sides, key="ft_outer_n")
                               if throat_outer == "Polygonal" else 0)
                _ft_bphase = _bolt_phase(n_sides if is_poly else 4, _ft_bpos)
                _ft_flange_R = _flange_R_from_ring(_ft_inner_R, _ft_ring, _ft_outer_n)
                _ft_od = _ft_flange_R * 2
                if is_rect:
                    _ft_outer_w = _ft_inner_w + 2 * _ft_ring
                    _ft_outer_h = _ft_inner_h + 2 * _ft_ring
                    if throat_outer == "Circular":
                        _ft_diag = np.sqrt(_ft_inner_w**2 + _ft_inner_h**2)
                        _ft_od = _ft_diag + 2 * _ft_ring
                        st.caption(f"Outer \u00d8: {_ft_od:.0f} mm (diag + 2\u00d7ring)")
                    elif throat_outer == "Elliptical":
                        st.caption(f"Outer ellipse: {_ft_outer_w:.0f}\u00d7{_ft_outer_h:.0f} mm "
                                   f"extents (true {_ft_ring:.0f} mm offset)")
                    else:
                        st.caption(f"Outer: {_ft_outer_w:.0f}\u00d7{_ft_outer_h:.0f} mm (ring {_ft_ring:.0f} mm)")
                elif _ft_outer_n >= 3:
                    st.caption(f"Across corners \u00d8: {_ft_od:.1f} mm \u00b7 flats wall {_ft_ring:.0f} mm")
                else:
                    st.caption(f"Outer \u00d8: {_ft_od:.1f} mm")
                if is_ellip and throat_outer == "Elliptical":
                    # Elliptical outer: bolts follow the real half-offset curve.
                    _ft_bc = (_ft_inner_w + _ft_outer_w) / 2.0
                    st.caption(f"Bolts auto-placed on the half-offset curve "
                               f"({(_ft_inner_w+_ft_outer_w)/2:.0f}\u00d7{(_ft_inner_h+_ft_outer_h)/2:.0f} mm)")
                else:
                    _ft_bc_lo, _ft_bc_hi = _bolt_circle_band(_ft_inner_R, _ft_flange_R, _ft_db, _ft_outer_n)
                    if "ft_bc" not in st.session_state:
                        st.session_state["ft_bc"] = _def_bc(_ft_bc_lo, _ft_bc_hi)
                    _clamp_state("ft_bc", _ft_bc_lo, _ft_bc_hi)
                    _ft_bc = st.number_input("Bolt circle \u00d8 (mm)", _ft_bc_lo, _ft_bc_hi,
                        step=1.0, key="ft_bc")
                _ft_depth = 0.0; _ft_ow = _ft_oh = 0.0

                # ── Weld-reinforcement chamfer (throat only) ──────────────
                _ft_chamfer = st.checkbox(
                    "Weld reinforcement chamfer", False, key="ft_chamfer",
                    help="Sloped reinforcement ring that bridges the flange top "
                         "to the horn body like a fillet weld")
                if _ft_chamfer:
                    _ft_chamfer_max_w = max(
                        (_ft_ring if _ft_ring > 0 else 15.0) * 0.4, 1.0)
                    if "ft_chamfer_w" not in st.session_state:
                        st.session_state["ft_chamfer_w"] = min(4.0, _ft_chamfer_max_w)
                    _clamp_state("ft_chamfer_w", 1.0, _ft_chamfer_max_w)
                    _ft_chamfer_w = st.number_input(
                        "Chamfer width on flange (mm)", 1.0, _ft_chamfer_max_w,
                        step=0.5, key="ft_chamfer_w",
                        help="How far the chamfer foot extends radially on the flange top")
                    _ft_chamfer_h = st.number_input(
                        "Chamfer height up the wall (mm)", 1.0, 40.0, 8.0, 0.5,
                        key="ft_chamfer_h",
                        help="Vertical extent of the chamfer along the horn body")
                else:
                    _ft_chamfer_w = _ft_chamfer_h = 0.0
        else:
            _clear_throat_flange_inputs()
with fg2:
    st.markdown("##### Mouth Flange")
    if is_radial or is_iwata:
        gen_mouth = False
        _fm_sp = _fm_off = _fm_nb = _fm_db = _fm_od = _fm_bc = _fm_ow = _fm_oh = 0.0
        mouth_outer = "Circular"
        if is_radial:
            st.caption("Not available for radial profile")
        else:
            st.caption("Not available — Iwata mouth is a curved arc (no flat flange)")
    elif rollback_complete:
        gen_mouth = False
        _fm_sp = _fm_off = _fm_nb = _fm_db = _fm_od = _fm_bc = _fm_ow = _fm_oh = 0.0
        _fm_ring = _fm_bphase = 0.0
        _fm_outer_n = 0
        _fm_inward = _fm_seat = False
        mouth_outer = "Circular"
        st.caption("Disabled for complete roll-back: the mouth lip returns inward, so a flat mouth flange is not generated.")
    elif is_osse:
        # Superelliptical mouth → flat elliptical ring welded to the outer rim.
        gen_mouth = st.checkbox("Include", True, key="gen_mouth")
        if gen_mouth:
            _fm_sp = st.number_input("Thickness (mm)", 2.0, 20.0, 6.0, 0.5, key="fm_sp_osse")
            _fm_nb = st.number_input("Bolt count", 0, 24, 12, 1, key="fm_nb")
            _fm_db = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="fm_db")
            _fm_ring = st.number_input("Offset from flare (mm)", 5.0, 200.0, 15.0, 1.0,
                key="fm_ring_osse", help="Material added outside the mouth wall")
            _fm_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="fm_off_osse")
            _fm_bphase = 0.0; mouth_outer = "Elliptical"
            st.caption(f"Elliptical flange ≈ {(_osse_mouth_w or 0) + 2 * thickness:.0f}×"
                       f"{(_osse_mouth_h or 0) + 2 * thickness:.0f} mm hole + {_fm_ring:.0f} mm ring")
        else:
            _clear_mouth_flange_inputs()
    else:
        gen_mouth = st.checkbox("Include", True, key="gen_mouth")
        if gen_mouth:
            # Default to the wall's axial extent at the mouth so the flange sits flush
            # with the flare (no protruding rim). This is thickness·|n_z|, not the raw
            # along-normal wall thickness.
            _fm_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, max(2.0, float(_mouth_wall_dz)), 0.5,
                key="fm_spess",
                help="Defaults to the flare's axial thickness at the mouth, so the "
                     "flange ends flush with the wall (no rim)")
            _fm_nb  = st.number_input("Bolt count", 0, 24, 12, 1, key="fm_nb")
            _fm_db  = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="fm_db")
            _fm_sizing = _flange_sizing_selector("fm_sizing")
            _fm_custom = _fm_sizing == "Custom dimensions"
            if _fm_custom:
                # Used only while evaluating roll-back geometry. Custom dimensions
                # always produce an outward flange, so this is not a user setting.
                _fm_ring = 15.0
            else:
                _fm_ring = st.number_input("Offset from flare (mm)", 5.0, 200.0, 15.0, 1.0, key="fm_ring",
                    help="Uniform material added outside the real flare opening.")

            # --- Flange direction (roll-back lips only) -------------------------
            # Outward: ring beyond the rim (Ø grows) — the default for plain flares.
            # Inward: ring reaches *into* the curled lip so the outer Ø stays = rim;
            # the bolts then pierce the flare toward the front. Only sensible when the
            # roll-back is deep enough to hold the ring + bolts ("ingombro").
            _fm_inward = False
            _fm_inward_ok = False
            _fm_rb = _rollback_mouth_geometry()
            if not is_rect and _fm_rb is not None:
                _fm_is_rollback = _fm_rb["is_rollback"]
                _fm_rim_off = _fm_rb["z_rim"]
                _fm_rim_w, _fm_rim_h = _fm_rb["rim_w"], _fm_rb["rim_h"]
                _fm_peak_w, _fm_peak_h = _fm_rb["peak_w"], _fm_rb["peak_h"]
                _fm_rim_R, _fm_peak_R = _fm_rb["rim_R"], _fm_rb["peak_R"]
                _fm_inward_ok = (
                    _fm_is_rollback
                    and (_fm_rim_R - _fm_ring - _fm_db - 4.0) > _fm_peak_R
                    and (_fm_rim_R - _fm_ring) > 1.0)
                if _fm_is_rollback and not _fm_custom:
                    if _fm_inward_ok:
                        _fm_dir = st.radio(
                            "Flange direction", ["Inward (into roll-back)", "Outward"],
                            index=0, horizontal=True, key="fm_dir_v2",
                            help="Roll-back lip — Inward keeps the flange inside the rim "
                                 "and routes the bolts through the returning lip.")
                        _fm_inward = _fm_dir.startswith("Inward")
                    else:
                        st.caption("Inward unavailable: roll-back cavity too shallow "
                                   "for this offset and bolt diameter.")
            if is_rect:
                _fm_rim_off, _fm_w_o, _fm_h_o = _rim_weld(
                    _z_o_rect, _w_o_rect, _h_o_rect, _fm_sp)
                _fm_rim_idx = int(np.argmax(_w_o_rect * _h_o_rect))
                _fm_peak_idx = int(np.argmax(_z_o_rect))
                _fm_is_rollback = _fm_rim_idx > _fm_peak_idx
                _fm_rim_w = float(_w_o_rect[_fm_rim_idx])
                _fm_rim_h = float(_h_o_rect[_fm_rim_idx])
                _fm_peak_w = float(_w_o_rect[_fm_peak_idx])
                _fm_peak_h = float(_h_o_rect[_fm_peak_idx])
                _fm_rim_R = max(_fm_rim_w, _fm_rim_h) / 2.0
                _fm_peak_R = max(_fm_peak_w, _fm_peak_h) / 2.0
                # Inward bolts ride the mid-ring (≈ rim − ring); they must clear the
                # inner flare (peak radius) so the axial holes only pierce the lip.
                _fm_inward_ok = (
                    _fm_is_rollback
                    and (_fm_rim_w - _fm_ring - _fm_db - 4.0) > _fm_peak_w
                    and (_fm_rim_h - _fm_ring - _fm_db - 4.0) > _fm_peak_h
                    and (_fm_rim_w - 2 * _fm_ring) > 1.0
                    and (_fm_rim_h - 2 * _fm_ring) > 1.0)
                if _fm_is_rollback and not _fm_custom:
                    if _fm_inward_ok:
                        _fm_dir = st.radio(
                            "Flange direction", ["Inward (into roll-back)", "Outward"],
                            index=0, horizontal=True, key="fm_dir_v2",
                            help="Roll-back lip — Inward keeps the outer Ø (= rim) and routes "
                                 "the bolts through the flare toward the front; Outward adds a "
                                 "ring beyond the rim (Ø grows).")
                        _fm_inward = _fm_dir.startswith("Inward")
                    else:
                        st.caption("Inward unavailable: roll-back cavity too shallow "
                                   "for this offset and bolt diameter.")

                if _fm_inward:
                    _fm_inner_w, _fm_inner_h = _fm_rim_w, _fm_rim_h
                else:
                    _fm_inner_w = max(_fm_w_o - 2 * _FLANGE_WALL_BITE, 1.0)
                    _fm_inner_h = max(_fm_h_o - 2 * _FLANGE_WALL_BITE, 1.0)
                _fm_inner_R = max(_fm_inner_w, _fm_inner_h) / 2
                if not _fm_inward:
                    st.caption(f"Hole: {_fm_inner_w:.1f}×{_fm_inner_h:.1f} mm "
                               f"({'elliptical' if is_ellip else 'rectangular'})")
            elif is_ellip:
                # Elliptical mouth outer wall: use the same profile arrays as rect.
                _fm_w_o = float(_w_o_rect[-1])
                _fm_h_o = float(_h_o_rect[-1])
                _fm_is_rollback = False
                _fm_inward = False
                _fm_inward_ok = False
                _fm_rim_w = _fm_w_o; _fm_rim_h = _fm_h_o
                _fm_peak_w = _fm_w_o; _fm_peak_h = _fm_h_o
                _fm_rim_R = max(_fm_rim_w, _fm_rim_h) / 2.0
                _fm_peak_R = _fm_rim_R

                if _fm_inward:
                    # No annulus/ring for inward — bolts are drilled into the lip
                    # itself. These are placeholders (unused); the real bolt placement
                    # is computed at generation from the rim + wall margin.
                    _fm_inner_w, _fm_inner_h = _fm_rim_w, _fm_rim_h
                else:
                    # Weld to the OUTER rim, biting slightly into the wall.
                    _fm_inner_w = max(_fm_w_o - 2 * _FLANGE_WALL_BITE, 1.0)
                    _fm_inner_h = max(_fm_h_o - 2 * _FLANGE_WALL_BITE, 1.0)
                _fm_inner_R = max(_fm_inner_w, _fm_inner_h) / 2
                if not _fm_inward:
                    st.caption(f"Hole: {_fm_inner_w:.1f}×{_fm_inner_h:.1f} mm "
                               f"({'elliptical' if is_ellip else 'rectangular'})")
            elif is_poly:
                _fm_inner_R = _fm_rim_R if _fm_inward else ir_mouth
                st.caption(f"Hole: {n_sides}-gon, R≈{_fm_inner_R:.1f} mm")
            else:
                _fm_inner_R = _fm_rim_R if _fm_inward else ir_mouth
                st.caption(f"Hole: Ø{_fm_inner_R*2:.1f} mm (bites wall)")
            if _fm_inward:
                # Inward ring follows the lip; outer shape is fixed to the rim.
                mouth_outer = (
                    "Elliptical" if is_ellip else "Rectangular" if is_rect
                    else "Polygonal" if is_poly else "Circular")
                _fm_outer_n = n_sides if is_poly else 0
                st.caption(f"Flange shape: {_FLANGE_SHAPE_LABELS[mouth_outer]} · follows the rim")
            elif _fm_custom:
                mouth_outer, _fm_outer_n = _flange_shape_selector(
                    "mouth_outer", "fm_outer_n")
            else:
                mouth_outer, _fm_outer_n = _automatic_flange_shape()
            st.markdown("###### Placement & Bolts")
            _fm_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="fm_off")
            _fm_bpos = st.radio("Bolt position", ["At vertices", "At mid-faces"],
                index=0, horizontal=True, key="fm_bpos",
                help="Align bolts with polygon vertices or face centers"
                ) if (is_poly or is_rect) else "At vertices"
            # --- Screw-head seat (counterbore), inward flange only ----------
            # A flat plate fills the roll-back cavity (welded between the inner
            # flare and the curled lip); the bolts are drilled through it. Annular
            # pillars connect plate to lip around the bolt channels, so tightening
            # the screws cannot collapse the empty cavity.
            _fm_seat = False
            _fm_head_d = _fm_seat_depth = _fm_seat_wall = 0.0
            if _fm_inward:
                _fm_seat = st.checkbox("Screw-head seat (counterbore)", True, key="fm_seat",
                    help="Recess the screw head into the lip. A hidden annular pillar "
                         "supports the lip against the flange while tightening.")
                if _fm_seat:
                    _fm_head_d = st.number_input("Head Ø (mm)", _fm_db + 0.5, 40.0,
                        float(round(_fm_db * 1.9, 1)), 0.5, key="fm_head_d")
                    _fm_seat_depth = st.number_input("Head depth (mm)", 0.5, 30.0,
                        float(round(max(1.0, _fm_db * 0.8), 1)), 0.5, key="fm_seat_depth",
                        help="Depth below the inward flange top plane. All screw-head "
                             "seats are axial with their holes and share one flat plane.")
                _fm_seat_wall = st.number_input("Wall around hole (mm)", 1.0, 20.0, 3.0, 0.5,
                    key="fm_seat_wall",
                    help="Pillar wall around each bolt channel. The pillars connect "
                         "the flange plate to the curled lip and carry screw clamp load.")
            _fm_bphase = _bolt_phase(n_sides if is_poly else 4, _fm_bpos)
            _fm_hole_R = _fm_inner_R
            _fm_flange_R = _flange_R_from_ring(_fm_hole_R, _fm_ring, _fm_outer_n)
            _fm_od = _fm_flange_R * 2
            _fm_outer_w = _fm_outer_h = 0.0
            if _fm_inward:
                # Plate fills the lip cavity; outer = rim (Ø unchanged). Bolt pillars
                # use the head-clearance diameter when counterbores are enabled.
                _fm_bearing_d = _fm_head_d if _fm_seat else _fm_db
                _fm_outer_w = _fm_rim_w; _fm_outer_h = _fm_rim_h
                _fm_od = 2.0 * _fm_rim_R if not is_rect else _fm_rim_w
                _fm_bolt_w = _fm_rim_w - 2 * (_fm_bearing_d / 2.0 + _fm_seat_wall)
                _fm_bolt_h = _fm_rim_h - 2 * (_fm_bearing_d / 2.0 + _fm_seat_wall)
                st.caption(f"Plate fills the roll-back cavity (outer Ø = rim). Bolts on "
                           f"{_fm_bolt_w:.0f}×{_fm_bolt_h:.0f} mm "
                           f"with {_fm_seat_wall:.0f} mm load-bearing pillars"
                           + (f", head seat Ø{_fm_head_d:.0f}×{_fm_seat_depth:.0f} mm" if _fm_seat else ""))
            elif _fm_custom:
                _fm_inner_bound_R = (
                    np.hypot(_fm_inner_w, _fm_inner_h) / 2.0 if is_rect
                    else _fm_hole_R
                )
                _fm_margin = _fm_db + 2.0
                if mouth_outer == "Circular":
                    _fm_min_d = 2.0 * (_fm_inner_bound_R + _fm_margin)
                    _fm_od = _custom_dimension(
                        "Outer diameter (mm)", "fm_custom_d", _fm_min_d,
                        _fm_min_d + 20.0)
                    _fm_flange_R = _fm_od / 2.0
                    st.caption(f"Outer Ø: {_fm_od:.1f} mm")
                elif mouth_outer == "Polygonal":
                    _fm_min_R = (_fm_inner_bound_R + _fm_margin) / np.cos(
                        np.pi / _fm_outer_n)
                    _fm_od = _custom_dimension(
                        "Across corners Ø (mm)", "fm_custom_d", 2.0 * _fm_min_R,
                        2.0 * _fm_min_R + 20.0)
                    _fm_flange_R = _fm_od / 2.0
                    st.caption(f"Across corners Ø: {_fm_od:.1f} mm")
                else:
                    _fm_inner_box_w = _fm_inner_w if is_rect else 2.0 * _fm_hole_R
                    _fm_inner_box_h = _fm_inner_h if is_rect else 2.0 * _fm_hole_R
                    _fm_outer_w = _custom_dimension(
                        "Outer width (mm)", "fm_custom_w",
                        _fm_inner_box_w + 2.0 * _fm_margin,
                        _fm_inner_box_w + 30.0)
                    _fm_outer_h = _custom_dimension(
                        "Outer height (mm)", "fm_custom_h",
                        _fm_inner_box_h + 2.0 * _fm_margin,
                        _fm_inner_box_h + 30.0)
                    _fm_od = max(_fm_outer_w, _fm_outer_h)
                    st.caption(f"Outer: {_fm_outer_w:.1f}×{_fm_outer_h:.1f} mm")
            elif is_rect:
                _fm_outer_w = _fm_inner_w + 2 * _fm_ring
                _fm_outer_h = _fm_inner_h + 2 * _fm_ring
                _fm_od = max(_fm_outer_w, _fm_outer_h)
                if mouth_outer == "Elliptical":
                    st.caption(f"True offset contour: {_fm_outer_w:.0f}×{_fm_outer_h:.0f} mm extents")
                else:
                    st.caption(f"Offset rectangle: {_fm_outer_w:.0f}×{_fm_outer_h:.0f} mm")
            elif is_ellip:
                _fm_outer_w = _fm_inner_w + 2 * _fm_ring
                _fm_outer_h = _fm_inner_h + 2 * _fm_ring
                _fm_od = max(_fm_outer_w, _fm_outer_h)
                st.caption(f"True offset contour: {_fm_outer_w:.0f}×{_fm_outer_h:.0f} mm extents")
            elif is_poly:
                _fm_flange_R = _fm_hole_R + _fm_ring / np.cos(np.pi / n_sides)
                _fm_od = 2.0 * _fm_flange_R
                st.caption(f"Offset {n_sides}-gon · across corners Ø {_fm_od:.1f} mm")
            else:
                _fm_flange_R = _fm_hole_R + _fm_ring
                _fm_od = 2.0 * _fm_flange_R
                st.caption(f"Offset circular · outer Ø {_fm_od:.1f} mm")
            _fm_ow = _fm_od; _fm_oh = _fm_od
            if _fm_inward:
                _fm_bc = max(2.0 * (_fm_rim_R - (_fm_head_d / 2.0 + _fm_seat_wall)), 1.0)
                st.caption("Screws drop in from the front and pass through the lip to "
                           "the back (nothing protrudes into the flare).")
            elif not _fm_custom:
                _fm_bolt_mode = "auto"
                _fm_bc = 0.0
                st.caption("Holes auto-centered in the offset material")
            else:
                _fm_bolt_mode = _bolt_placement_selector("fm_bolt_mode")
                if _fm_bolt_mode == "Fixed from center":
                    _fm_i_lim, _fm_o_lim = _shape_limits(
                        _fm_hole_R, _fm_inner_w if is_rect else 0.0,
                        _fm_inner_h if is_rect else 0.0,
                        mouth_outer, _fm_outer_n, _fm_od, _fm_outer_w, _fm_outer_h)
                    _fm_bc_lo = 2.0 * (_fm_i_lim + _fm_db / 2.0 + 1.0)
                    _fm_bc_hi = 2.0 * (_fm_o_lim - _fm_db / 2.0 - 1.0)
                    _fm_bc_hi = max(_fm_bc_hi, _fm_bc_lo + 2.0)
                    if "fm_bc" not in st.session_state:
                        st.session_state["fm_bc"] = _def_bc(_fm_bc_lo, _fm_bc_hi)
                    _clamp_state("fm_bc", _fm_bc_lo, _fm_bc_hi)
                    _fm_bc = st.number_input("Bolt circle Ø (mm)", _fm_bc_lo, _fm_bc_hi,
                        step=1.0, key="fm_bc")
                else:
                    _fm_bc = 0.0

        else:
            _clear_mouth_flange_inputs()
with fg3:
    st.markdown("##### Mid Flange")
    if is_radial:
        gen_mid = False; _mid_pos = 50
        _mid_sp = _mid_nb = _mid_db = 0.0
        st.caption("Not available for radial profile")
    elif is_osse:
        # Intermediate joining/reinforcement ring around the superelliptical body.
        gen_mid = st.checkbox("Include", False, key="gen_mid")
        if gen_mid:
            _mid_max = max(5.0, _len or 120.0)
            _mid_pos = st.number_input("Distance from throat (mm)", 5.0, _mid_max,
                max(5.0, _mid_max * 0.5), 5.0, key="mid_z")
            _mid_sp = st.number_input("Thickness (mm)", 2.0, 20.0, 6.0, 0.5, key="mid_spess")
            _mid_nb = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="mid_nb")
            _mid_db = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="mid_db")
            _mid_ring = st.number_input("Offset from flare (mm)", 5.0, 200.0, 15.0, 1.0, key="mid_ring")
            _mid_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="mid_off")
            _mid_bphase = 0.0
            _w_os_mid, _h_os_mid = _osse_airway_wh_at_z(_mid_pos - _mid_sp)
            st.caption(f"Elliptical hole ≈ {_w_os_mid + 2 * thickness:.0f}×"
                       f"{_h_os_mid + 2 * thickness:.0f} mm + {_mid_ring:.0f} mm ring")
        else:
            _clear_mid_flange_inputs()
    else:
        # Roll-back rect/ellip now get a real mouth flange welded to the outer
        # rim, so the mid-flange workaround is no longer on by default there.
        gen_mid = st.checkbox("Include", is_lecleach and not is_rect, key="gen_mid")
        if gen_mid:
            _mid_max = max(5.0, _len or 200.0)
            _mid_pos = st.number_input("Distance from throat (mm)", 5.0, _mid_max,
                max(5.0, _mid_max * 0.5), 5.0, key="mid_z")
            _mid_sp  = st.number_input("Thickness (mm)", 2.0, 20.0, 4.0, 0.5, key="mid_spess")
            _mid_nb = st.number_input("Bolt count", 0, 24, _bolt_n, 1, key="mid_nb")
            _mid_db = st.number_input("Bolt hole Ø (mm)", 1.0, 12.0, _bolt_d, 0.1, key="mid_db")
            _mid_pct = min(100.0, _mid_pos / max(_len or 1, 1) * 100)
            mid_r = _get_mid_r(_mid_pct) if _len else 10
            if is_rect:
                # Hole sized from the real outer wall at the plate's bottom face
                # (throat-relative Z ≈ _mid_pos − thickness) on the outgoing leg, so
                # the widening wall welds into the ring. Index-by-fraction breaks on
                # roll-back profiles whose Z is non-monotonic.
                _mid_w_o, _mid_h_o = _outer_wh_at_z(
                    _z_o_rect, _w_o_rect, _h_o_rect, _mid_pos - _mid_sp)
                _mid_inner_w = max(_mid_w_o - 2 * _FLANGE_WALL_BITE, 1.0)
                _mid_inner_h = max(_mid_h_o - 2 * _FLANGE_WALL_BITE, 1.0)
                _mid_inner_R = max(_mid_inner_w, _mid_inner_h) / 2
                st.caption(f"Hole: {_mid_inner_w:.0f}×{_mid_inner_h:.0f} mm "
                           f"({'elliptical' if is_ellip else 'rectangular'})")
            elif is_poly:
                _mid_inner_R = mid_r
                st.caption(f"Hole: {n_sides}-gon, R≈{_mid_inner_R:.0f} mm")
            else:
                _mid_inner_R = mid_r + thickness
                st.caption(f"Hole: Ø{_mid_inner_R*2:.0f} mm (circular)")
            _mid_sizing = _flange_sizing_selector("mid_sizing")
            _mid_custom = _mid_sizing == "Custom dimensions"
            _mid_ring = (15.0 if _mid_custom else
                st.number_input("Offset from flare (mm)", 5.0, 200.0, 15.0, 1.0, key="mid_ring",
                    help="Uniform material added outside the real flare opening."))
            if _mid_custom:
                mid_out, _mid_outer_n = _flange_shape_selector("mid_out", "mid_outer_n")
            else:
                mid_out, _mid_outer_n = _automatic_flange_shape()
            st.markdown("###### Placement & Bolts")
            _mid_off = st.number_input("Z offset (mm)", -50.0, 50.0, 0.0, 0.5, key="mid_off")
            _mid_bpos = st.radio("Bolt position", ["At vertices", "At mid-faces"],
                index=0, horizontal=True, key="mid_bpos",
                help="Align bolts with polygon vertices or face centers"
                ) if (is_poly or is_rect) else "At vertices"
            _mid_bphase = _bolt_phase(n_sides if is_poly else 4, _mid_bpos)
            _mid_flange_R = _flange_R_from_ring(_mid_inner_R, _mid_ring, _mid_outer_n)
            _mid_od = _mid_flange_R * 2
            _mid_outer_w = _mid_outer_h = 0.0
            if _mid_custom:
                _mid_inner_bound_R = (
                    np.hypot(_mid_inner_w, _mid_inner_h) / 2.0 if is_rect
                    else _mid_inner_R
                )
                _mid_margin = _mid_db + 2.0
                if mid_out == "Circular":
                    _mid_min_d = 2.0 * (_mid_inner_bound_R + _mid_margin)
                    _mid_od = _custom_dimension(
                        "Outer diameter (mm)", "mid_custom_d", _mid_min_d,
                        _mid_min_d + 20.0)
                    _mid_flange_R = _mid_od / 2.0
                    st.caption(f"Outer Ø: {_mid_od:.1f} mm")
                elif mid_out == "Polygonal":
                    _mid_min_R = (_mid_inner_bound_R + _mid_margin) / np.cos(
                        np.pi / _mid_outer_n)
                    _mid_od = _custom_dimension(
                        "Across corners Ø (mm)", "mid_custom_d", 2.0 * _mid_min_R,
                        2.0 * _mid_min_R + 20.0)
                    _mid_flange_R = _mid_od / 2.0
                    st.caption(f"Across corners Ø: {_mid_od:.1f} mm")
                else:
                    _mid_inner_box_w = _mid_inner_w if is_rect else 2.0 * _mid_inner_R
                    _mid_inner_box_h = _mid_inner_h if is_rect else 2.0 * _mid_inner_R
                    _mid_outer_w = _custom_dimension(
                        "Outer width (mm)", "mid_custom_w",
                        _mid_inner_box_w + 2.0 * _mid_margin,
                        _mid_inner_box_w + 30.0)
                    _mid_outer_h = _custom_dimension(
                        "Outer height (mm)", "mid_custom_h",
                        _mid_inner_box_h + 2.0 * _mid_margin,
                        _mid_inner_box_h + 30.0)
                    _mid_od = max(_mid_outer_w, _mid_outer_h)
                    st.caption(f"Outer: {_mid_outer_w:.1f}×{_mid_outer_h:.1f} mm")
            elif is_rect:
                _mid_outer_w = _mid_inner_w + 2 * _mid_ring
                _mid_outer_h = _mid_inner_h + 2 * _mid_ring
                _mid_od = max(_mid_outer_w, _mid_outer_h)
                if mid_out == "Elliptical":
                    st.caption(f"True offset contour: {_mid_outer_w:.0f}×{_mid_outer_h:.0f} mm extents")
                else:
                    st.caption(f"Offset rectangle: {_mid_outer_w:.0f}×{_mid_outer_h:.0f} mm")
            elif is_poly:
                _mid_flange_R = _mid_inner_R + _mid_ring / np.cos(np.pi / n_sides)
                _mid_od = 2.0 * _mid_flange_R
                st.caption(f"Offset {n_sides}-gon · across corners Ø {_mid_od:.1f} mm")
            else:
                _mid_flange_R = _mid_inner_R + _mid_ring
                _mid_od = 2.0 * _mid_flange_R
                st.caption(f"Offset circular · outer Ø {_mid_od:.1f} mm")
            if not _mid_custom:
                _mid_bolt_mode = "auto"
                _mid_bc = 0.0
                st.caption("Holes auto-centered in the offset material")
            else:
                _mid_bolt_mode = _bolt_placement_selector("mid_bolt_mode")
                if _mid_bolt_mode == "Fixed from center":
                    _mid_i_lim, _mid_o_lim = _shape_limits(
                        _mid_inner_R, _mid_inner_w if is_rect else 0.0,
                        _mid_inner_h if is_rect else 0.0,
                        mid_out, _mid_outer_n, _mid_od, _mid_outer_w, _mid_outer_h)
                    _mid_bc_lo = 2.0 * (_mid_i_lim + _mid_db / 2.0 + 1.0)
                    _mid_bc_hi = 2.0 * (_mid_o_lim - _mid_db / 2.0 - 1.0)
                    _mid_bc_hi = max(_mid_bc_hi, _mid_bc_lo + 2.0)
                    if "mid_bc" not in st.session_state:
                        st.session_state["mid_bc"] = _def_bc(_mid_bc_lo, _mid_bc_hi)
                    _clamp_state("mid_bc", _mid_bc_lo, _mid_bc_hi)
                    _mid_bc = st.number_input("Bolt circle Ø (mm)", _mid_bc_lo, _mid_bc_hi,
                        step=1.0, key="mid_bc")
                else:
                    _mid_bc = 0.0

        else:
            _clear_mid_flange_inputs()
# ═══════════════════════════════════════════════════════════════════════
#  ROW 3 — Generate Assembly
# ═══════════════════════════════════════════════════════════════════════

st.sidebar.divider()
st.sidebar.subheader("Generate Assembly")

chk = st.sidebar.container()
with chk:
    st.markdown("##### Resolution")
    if st.session_state.get("quality_preset") == "Grezzo 64×64":
        st.session_state["quality_preset"] = "Draft 64×64"
    _quality_preset = st.radio(
        "Quality preset",
        ["Draft 64×64", "Fine 256×256", "Custom"],
        horizontal=True,
        key="quality_preset",
        on_change=_on_horn_change,
        help="Draft: 64 axial / 64 radial. Fine: 256 axial / 256 radial.",
    )
    if _quality_preset.startswith("Fine"):
        segments, rings_n = 256, 256
    elif _quality_preset == "Custom":
        _res1, _res2 = st.columns(2)
        with _res1:
            segments = st.number_input("Axial segments", 64, 50000, 300, 16,
                help="Stations ALONG the profile (z direction). Smooths the "
                     "flare lengthwise — the roundness of the cross-section is "
                     "set by Radial segments",
                on_change=_on_horn_change, key="custom_segments")
        with _res2:
            rings_n = int(st.number_input("Radial segments", 32, 512, 64, 16,
                help="Facets AROUND the axis for round horns (revolution "
                     "resolution). This is what removes the visible faceting "
                     "of the flare; raise to 128–256 for large mouths",
                on_change=_on_horn_change, key="custom_rings_n"))
    else:
        segments, rings_n = 64, 64
    st.caption(f"Using {segments} axial × {rings_n} radial segments")
    gen_horn = st.checkbox("Include horn", True, key="gen_horn")
    _tos_path = Path(__file__).parent / "TERMS_OF_SERVICE.md"
    if _tos_path.exists():
        st.download_button(
            label="📜 Terms of Service",
            data=_tos_path.read_text(encoding="utf-8"),
            file_name="TERMS_OF_SERVICE.md",
            mime="text/markdown",
            use_container_width=True,
        )
    if BMC_USERNAME and BMC_USERNAME != "your_username":
        st.link_button("☕ Buy me a coffee", BMC_URL, use_container_width=True)

gen_btn = st.sidebar.button("Generate Assembly STL", type="primary", use_container_width=True)

if gen_btn:
    with st.spinner("Generating…"):
        try:
            import trimesh as _tm
            C = _core

            def _slope_start(z_arr, v_arr):
                z_arr = np.asarray(z_arr, dtype=float)
                v_arr = np.asarray(v_arr, dtype=float)
                for i in range(1, len(z_arr)):
                    dz = z_arr[i] - z_arr[0]
                    if abs(dz) > 1e-6:
                        return float((v_arr[i] - v_arr[0]) / dz)
                return 0.0

            def _profile_value_slope(z_arr, v_arr, z_target):
                """Interpolate value and dv/dz on the first advancing profile branch."""
                z_arr = np.asarray(z_arr, dtype=float)
                v_arr = np.asarray(v_arr, dtype=float)
                end = int(np.argmax(z_arr)) + 1
                zz = z_arr[:end]
                vv = v_arr[:end]
                keep = np.concatenate([[True], np.diff(zz) > 1e-8])
                zz = zz[keep]
                vv = vv[keep]
                if len(zz) < 2:
                    return float(vv[0]), 0.0
                z_target = float(np.clip(z_target, zz[0], zz[-1]))
                slopes = np.gradient(vv, zz)
                return (float(np.interp(z_target, zz, vv)),
                        float(np.interp(z_target, zz, slopes)))

            def _profile_curv(z_arr, v_arr, z_target):
                """Second derivative d²v/dz² on the first advancing branch.

                Feeds the adapter's quintic raccordo so it meets the flare with
                matching curvature (C2), killing the inflection line at the join.
                """
                z_arr = np.asarray(z_arr, dtype=float)
                v_arr = np.asarray(v_arr, dtype=float)
                end = int(np.argmax(z_arr)) + 1
                zz = z_arr[:end]
                vv = v_arr[:end]
                keep = np.concatenate([[True], np.diff(zz) > 1e-8])
                zz = zz[keep]
                vv = vv[keep]
                if len(zz) < 3:
                    return 0.0
                z_target = float(np.clip(z_target, zz[0], zz[-1]))
                curv = np.gradient(np.gradient(vv, zz), zz)
                return float(np.interp(z_target, zz, curv))

            _adapter_target_slope = 0.0
            _adapter_target_curv = None
            _adapter_outer_target_R = None
            _adapter_outer_target_slope = None
            _adapter_outer_target_curv = None
            _adapter_outer_rw = None
            _adapter_outer_rh = None
            _adapter_custom_pts = None
            _adapter_custom_outer = None
            _adapter_custom_z = None
            _embedded_adapter_cut_z = None

            # --- 3a. Generate horn ---
            if is_osse:
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                _osse.generate_osse_3d_mesh(
                    throat=throat_d, length=axial_len,
                    coverage_h=coverage_h, coverage_v=coverage_v,
                    throat_angle=osse_throat_angle,
                    k=osse_k, s=osse_s, n=osse_n, q=osse_q,
                    mouth_exp=osse_mouth_exp,
                    morph_start=osse_morph_start, morph_rate=osse_morph_rate,
                    thickness=thickness,
                    # Same grid as the _R_os field above — keeps the embedded
                    # adapter's sections vertex-aligned with the horn facets.
                    nz=_R_os.shape[0], nphi=_R_os.shape[1],
                    output_path=tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                horn.fix_normals()
                # Mouth rim extent (superelliptical) + round throat references.
                mouth_bx = (_osse_mouth_w or 0.0) + 2.0 * thickness
                mouth_by = (_osse_mouth_h or 0.0) + 2.0 * thickness
                _rp_mouth = max(mouth_bx, mouth_by) / 2.0
                _zp_mouth = float(axial_len)
            elif is_poly:
                if is_tractrix:
                    zp, rp = _core.get_tractrix(throat_d, mouth_d, segments)
                elif is_salmon:
                    zp, rp = C.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
                elif is_lecleach:
                    zp, rp = _get_lecleach_profile(throat_d, fc, segments)
                elif is_rosse:
                    zp, rp = _get_rosse_profile(throat_d, mouth_d, segments)
                elif is_cd:
                    zp, rp = _cd_fn(throat_d, coverage_h, axial_len, segments)
                elif is_exp:
                    zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                _ph.generate_polygonal_3d_mesh(zp, rp, n_sides, thickness, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                horn.fix_normals()
                from polygonal_horn import _r_to_circumradius
                _R_i_arr   = _r_to_circumradius(rp, n_sides)
                _nml_poly  = _uts.compute_profile_normals(zp, _R_i_arr, flip_if_negative=True)
                _cos_pn    = np.cos(np.pi / n_sides)
                _R_o_arr   = _R_i_arr + thickness / _cos_pn * _nml_poly[:, 1]
                _z_o_poly  = zp + thickness * _nml_poly[:, 0]
                _z_o_poly  = np.clip(_z_o_poly, np.min(zp), np.max(zp))
                _z_o_poly[0] = zp[0]; _z_o_poly[-1] = zp[-1]
                _R_o_eq_arr = np.sqrt(
                    (0.5 * n_sides * _R_o_arr**2 * np.sin(2*np.pi/n_sides)) / np.pi)
                _R_o_throat_poly = _R_o_arr[0]
                _i_rim_poly = int(np.argmax(np.maximum(_R_o_arr, _R_i_arr)))
                _R_o_mouth_poly  = _R_o_arr[_i_rim_poly]
                mouth_bx = mouth_by = _R_o_arr[_i_rim_poly] * 2
                _i_inner_rim_poly = int(np.argmax(rp))
                _rp_mouth = rp[_i_inner_rim_poly]
                _zp_mouth = zp[_i_inner_rim_poly]
                _adapter_target_slope = _slope_start(zp, rp)
                _adapter_outer_target_R = float(_R_o_eq_arr[0])
                _adapter_outer_target_slope = _slope_start(_z_o_poly, _R_o_eq_arr)
            elif is_radial:
                with tempfile.TemporaryDirectory() as _tmp:
                    _rd.generate_radial_horn(throat_d, mouth_d, fc, rings_n, _tmp, profile_type)
                    horn = _tm.load(os.path.join(_tmp, "radial_bottom.stl"), file_type="stl")
                    R, Zb, Zt = _rd.get_radial_profiles(throat_d, mouth_d, fc, segments, profile_type)
                    Rm, Rt_rad = R[-1], R[0]
                    Z_top_flat = Zt[-1] + 4.0
                    eps = 0.01
                    r_poly = np.concatenate([[eps], R, [Rm, eps, eps]])
                    z_poly = np.concatenate([[Zt[0]], Zt, [Z_top_flat, Z_top_flat, Zt[0]]])
                    top_mesh = _rd._revolve_polygon(r_poly, z_poly, rings_n)
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
                elif is_rosse:
                    zr, wr, hr = _get_rect_rosse_profile(throat_w, throat_h, mouth_w, segments)
                elif is_cd:
                    zr, wr, hr = _cd_rect_fn(throat_w, throat_h, coverage_h, coverage_v, axial_len, segments)
                elif is_iwata:
                    zr, wr, hr = _rh.get_iwata_horn(throat_d, axial_len, segments)
                else:
                    throat_d_eq = np.sqrt(throat_w * throat_h * 4 / np.pi)
                    zp_c, rp_c = _get_lecleach_profile(throat_d_eq, fc, segments)
                    zr, wr, hr = _rh._area_to_rect(zp_c, rp_c, throat_w, throat_h)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                if is_ellip:
                    # Same (z, w, h) profile math as rectangular, but each slice is a
                    # true ellipse (semi-axes w/2, h/2) via the elliptical loft engine.
                    _core.generate_elliptical_3d_mesh_from_profiles(
                        zr, wr / 2.0, hr / 2.0, thickness, rings_ellip, tp)
                else:
                    # With an embedded adapter, sample the rectangular walls with
                    # the SAME point count the adapter uses (rings_n) so the weld
                    # surfaces share vertices — a 4-corner horn vs an N-point
                    # adapter makes the union spew a jagged sliver band ("bordello"
                    # su flare rect"). 4 corners stay the default when no adapter
                    # welds here (and for Iwata's arc-mouth intersection).
                    _rect_perim_n = (rings_n if (_ta_include_adapter and not is_iwata)
                                     else 4)
                    _rh.generate_rectangular_3d_mesh(
                        zr, wr, hr, thickness, tp, perim_n=_rect_perim_n)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                horn.fix_normals()
                if is_ellip:
                    _V_i_ellip, _V_o_ellip = _core._elliptical_parallel_offset_vertices(
                        zr, wr / 2.0, hr / 2.0, thickness, rings_ellip)
                    _z_o_rect = np.mean(_V_o_ellip[:, :, 2], axis=1)
                    _w_o_rect = 2.0 * np.max(np.abs(_V_o_ellip[:, :, 0]), axis=1)
                    _h_o_rect = 2.0 * np.max(np.abs(_V_o_ellip[:, :, 1]), axis=1)
                    _inner_eq_rect = np.sqrt(wr * hr) / 2.0
                    _outer_eq_rect = np.sqrt(_w_o_rect * _h_o_rect) / 2.0
                else:
                    _nw_rect = _uts.compute_profile_normals(zr, wr, flip_if_negative=True)
                    _nh_rect = _uts.compute_profile_normals(zr, hr, flip_if_negative=True)
                    _z_o_rect = zr + thickness * (_nw_rect[:, 0] + _nh_rect[:, 0]) / 2.0
                    # Roll-back aware: clamp to the true axial extent, not the
                    # curled-back lip at zr[-1] (see param-block note above).
                    _z_o_rect = np.clip(_z_o_rect, zr.min(), zr.max())
                    _z_o_rect[0] = zr[0]; _z_o_rect[-1] = zr[-1]
                    _w_o_rect = wr + 2 * thickness * _nw_rect[:, 1]
                    _h_o_rect = hr + 2 * thickness * _nh_rect[:, 1]
                    _inner_eq_rect = np.sqrt(wr * hr / np.pi)
                    _outer_eq_rect = np.sqrt(_w_o_rect * _h_o_rect / np.pi)
                _adapter_target_slope = _slope_start(zr, _inner_eq_rect)
                _adapter_outer_target_R = float(_outer_eq_rect[0])
                _adapter_outer_target_slope = _slope_start(_z_o_rect, _outer_eq_rect)
                _adapter_outer_rw = float(_w_o_rect[0])
                _adapter_outer_rh = float(_h_o_rect[0])
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
                # Mouth rim = widest outer cross-section, roll-back aware. For
                # ordinary monotonic flares this is the last station (≈ zr[-1]);
                # for Le Cléac'h/oblate/rosse it is the flare peak, where the
                # mouth flange must sit (not the curled-back lip).
                _i_rim_rect, _zp_mouth = _mouth_station(_z_o_rect, _w_o_rect, _h_o_rect)
                _rp_mouth = max(_w_o_rect[_i_rim_rect], _h_o_rect[_i_rim_rect]) / 2.0
                if is_iwata:
                    # The arc trim narrows the wide-plane mouth — report the real extent.
                    mouth_bx = float(horn.bounds[1, 0] - horn.bounds[0, 0])
                    mouth_by = float(horn.bounds[1, 1] - horn.bounds[0, 1])
                else:
                    mouth_bx, mouth_by = _w_o_rect[_i_rim_rect], _h_o_rect[_i_rim_rect]
            else:
                if is_tractrix:
                    zp, rp = C.get_tractrix(throat_d, mouth_d, segments)
                elif is_salmon:
                    zp, rp = C.get_salmon(throat_d, fc, axial_len, segments, T=salmon_T)
                elif is_lecleach:
                    zp, rp = _get_lecleach_profile(throat_d, fc, segments)
                elif is_rosse:
                    zp, rp = _get_rosse_profile(throat_d, mouth_d, segments)
                elif is_cd:
                    zp, rp = _cd_fn(throat_d, coverage_h, axial_len, segments)
                elif is_exp:
                    zp, rp = _get_exp_profile(throat_d, mouth_d, fc, segments)
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                C.generate_3d_mesh_from_profile(zp, rp, thickness, rings_n, tp)
                horn = _tm.load(tp, file_type="stl"); os.unlink(tp)
                _nml_circ = _uts.compute_profile_normals(zp, rp)
                _z_o_circ = zp + thickness * _nml_circ[:, 0]
                _r_o_circ = rp + thickness * _nml_circ[:, 1]
                _adapter_target_slope = _slope_start(zp, rp)
                _adapter_outer_target_R = float(_r_o_circ[0])
                _adapter_outer_target_slope = _slope_start(_z_o_circ, _r_o_circ)
                if is_lecleach or is_rosse:
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

            def _mesh_outer_section_xy(mesh, z_target):
                """Largest real XY exterior at a horizontal mesh section."""
                z_lo, z_hi = map(float, mesh.bounds[:, 2])
                eps = max((z_hi - z_lo) * 1e-6, 1e-3)
                z = float(np.clip(z_target, z_lo + eps, z_hi - eps))
                section = mesh.section(
                    plane_origin=[0.0, 0.0, z],
                    plane_normal=[0.0, 0.0, 1.0],
                )
                if section is None:
                    return None
                path2d = section.to_2D()
                if isinstance(path2d, tuple):
                    path2d = path2d[0]
                if path2d is None or len(path2d.entities) == 0:
                    return None
                polygons = list(path2d.polygons_full)
                if not polygons:
                    return None
                exterior = max(polygons, key=lambda poly: poly.area).exterior
                points = np.asarray(exterior.coords, dtype=float)[:, :2]
                return points if len(points) >= 6 else None

            def _grid_branch_section_xy(grid, z_target, returning):
                """Sample one side of a roll-back loft at a constant Z plane."""
                grid = np.asarray(grid, dtype=float)
                points = np.empty((grid.shape[1], 2), dtype=float)
                for j in range(grid.shape[1]):
                    z_col = grid[:, j, 2]
                    peak = int(np.argmax(z_col))
                    branch = slice(peak, None) if returning else slice(0, peak + 1)
                    z_branch = z_col[branch]
                    x_branch = grid[branch, j, 0]
                    y_branch = grid[branch, j, 1]
                    order = np.argsort(z_branch)
                    z_branch = z_branch[order]
                    x_branch = x_branch[order]
                    y_branch = y_branch[order]
                    z = float(np.clip(z_target, z_branch[0], z_branch[-1]))
                    points[j, 0] = np.interp(z, z_branch, x_branch)
                    points[j, 1] = np.interp(z, z_branch, y_branch)
                return points

            # --- 3d. Generate flanges ---
            f_throat = f_mouth = f_mid = f_throat_chamfer = None
            _mouth_bolt_cuts = []   # bolt shafts + head seats drilled into the lip (inward flange)
            _mouth_bolt_pillars = []  # compression sleeves between inward plate and curled lip
            _mouth_flare_opening_cuts = []  # surface-normal cuts applied to horn only
            _mouth_head_seat_cuts = []  # shallow normal pockets applied after pillar union

            if gen_throat and is_radial:
                bolt_angles = np.linspace(0, 2 * np.pi, int(_ft_nb), endpoint=False)
                for angle in bolt_angles:
                    x = (_ft_bc / 2.0) * np.cos(angle)
                    y = (_ft_bc / 2.0) * np.sin(angle)
                    cyl = _tm.creation.cylinder(radius=_ft_db / 2.0, height=_ft_depth + 2.0)
                    cyl.apply_translation([x, y, _ft_depth / 2.0])
                    horn = _tm.boolean.difference([horn, cyl], engine="manifold", check_volume=False)

            if gen_throat and not is_radial:
                if _ta_include_adapter:
                    # The morph replaces the first section of the flare instead of
                    # being prepended below the throat. Trim the original horn at
                    # the requested distance and match the real profile there.
                    _profile_z = _z_os if is_osse else (zr if is_rect else zp)
                    _profile_extent = float(np.max(_profile_z))
                    # The morph target must stay inside the advancing branch of
                    # the flare (cannot exceed peak Z). The returning lip is
                    # preserved via a local cylindrical cut later.
                    _safe_embed_extent = _profile_extent
                    _morph_len, _overlap, _target_local_z = _ta.embedded_morph_span(
                        float(_ta_adapter_len), _safe_embed_extent,
                        desired_overlap=20.0)
                    _trim_z = float(z_min + _morph_len)
                    _adapter_top_z = float(z_min + _target_local_z)
                    _profile_peak = int(np.argmax(_profile_z))
                    _return_min_z = (float(np.min(_profile_z[_profile_peak:]))
                                     if _profile_peak < len(_profile_z) - 1
                                     else float("inf"))
                    _adapter_preserve_return_lip = _return_min_z <= _morph_len + 1e-6
                    _embedded_adapter_cut_z = None if _adapter_preserve_return_lip else _trim_z
                    _handoff_local_z = float(_target_local_z)
                    _adapter_length_actual = float(_target_local_z)
                    _adapter_z_offset = float(_adapter_top_z)
                    _adapter_match_from_z = float(_morph_len)

                    # Perimeter point count of the adapter's cross-sections.
                    # It MUST match the flare's revolution resolution at the
                    # junction, otherwise the adapter's coarse N-gon and the
                    # flare's fine N-gon sit at slightly different radii through
                    # the weld overlap and print as a visible seam ring. The
                    # adapter derives its vertex count from these custom
                    # sections, so this value flows into the morph, the threads
                    # and the caps. OS-SE samples its own (nz, nphi) grid below.
                    _adapter_n = rings_ellip if is_ellip else rings_n

                    if _adapter_preserve_return_lip:
                        st.warning(
                            "Complete rollback returns into the adapter trim zone; "
                            "the throat adapter will replace only the central throat "
                            "zone, preserving the outer return lip.")
                    else:
                        _trimmed_horn = horn.slice_plane(
                            [0.0, 0.0, _trim_z], [0.0, 0.0, 1.0], cap=True)
                        if _trimmed_horn is not None and not _trimmed_horn.is_empty:
                            horn = _trimmed_horn
                            horn.remove_unreferenced_vertices()
                            horn.fix_normals()

                    # NOTE: no weld "bite" here. A previous version grew the
                    # adapter wall outward through the overlap to force a clean
                    # interpenetration (fewer boolean slivers), but ANY outward
                    # bite leaves a visible, measurable circumferential step on
                    # the throat cone (≈0.34 mm, confirmed with Bambu's measure
                    # tool) — far worse than the slivers it removed. The adapter
                    # therefore follows the EXACT flare contour through the
                    # overlap so the outer wall stays flush and stepless. The
                    # residual coincident-surface slivers are degenerate (zero
                    # area), do not affect the printed surface, and are hidden in
                    # the 3-D preview by smooth shading.
                    def _profile_stack(z_arr, z_end, inner_fn, outer_fn):
                        z_arr = np.asarray(z_arr, dtype=float)
                        peak = int(np.argmax(z_arr)) + 1
                        z_arr = z_arr[:peak]
                        z_stack = np.append(z_arr[z_arr < z_end - 1e-9], z_end)
                        z_stack = z_stack[np.concatenate([[True], np.diff(z_stack) > 1e-9])]
                        inner_stack = np.stack([inner_fn(float(zz)) for zz in z_stack])
                        outer_stack = np.stack([outer_fn(float(zz)) for zz in z_stack])
                        return z_stack, inner_stack, outer_stack

                    if is_rect:
                        horn_shape = "elliptical" if is_ellip else "rectangular"
                        rect_w, _ = _profile_value_slope(zr, wr, _handoff_local_z)
                        rect_h, _ = _profile_value_slope(zr, hr, _handoff_local_z)
                        poly_n_sides = 0
                        poly_circumR = 0.0
                        _inner_eq = (np.sqrt(wr * hr) / 2.0 if is_ellip
                                     else np.sqrt(wr * hr / np.pi))
                        horn_R_eq, _adapter_target_slope = _profile_value_slope(
                            zr, _inner_eq, _handoff_local_z)
                        _adapter_target_curv = _profile_curv(
                            zr, _inner_eq, _handoff_local_z)
                        _outer_eq = (np.sqrt(_w_o_rect * _h_o_rect) / 2.0 if is_ellip
                                     else np.sqrt(_w_o_rect * _h_o_rect / np.pi))
                        _outer_target_R, _outer_target_slope = _profile_value_slope(
                            _z_o_rect, _outer_eq, _handoff_local_z)
                        _adapter_outer_target_curv = _profile_curv(
                            _z_o_rect, _outer_eq, _handoff_local_z)
                        _outer_rw, _ = _profile_value_slope(
                            _z_o_rect, _w_o_rect, _handoff_local_z)
                        _outer_rh, _ = _profile_value_slope(
                            _z_o_rect, _h_o_rect, _handoff_local_z)
                        def _rect_section(z_loc):
                            _wz, _ = _profile_value_slope(zr, wr, z_loc)
                            _hz, _ = _profile_value_slope(zr, hr, z_loc)
                            if is_ellip:
                                return _ta._ellipse_points(_wz / 2.0, _hz / 2.0, n=_adapter_n)
                            # lockstep: same twist-free sampling the rect horn
                            # walls use (perim_n), so the weld surfaces match.
                            return _ta._rect_points(_wz / 2.0, _hz / 2.0,
                                                    n=_adapter_n, lockstep=True)

                        if is_ellip:
                            # The elliptical loft's outer wall is a 3-D normal
                            # offset whose ring Z varies with azimuth, so an
                            # ellipse through the (w, h) extremes at the mean-Z
                            # stations misses the real wall by up to ~0.5 mm on
                            # the wide axis — a visible step at the junction.
                            # Sample the offset field per azimuth column at the
                            # adapter's own vertex count instead (same approach
                            # as the OS-SE branch).
                            _, _V_o_ad = _core._elliptical_parallel_offset_vertices(
                                zr, wr / 2.0, hr / 2.0, thickness, _adapter_n)

                            def _rect_outer_section(z_loc):
                                _out = np.empty((_adapter_n, 2))
                                for _j in range(_adapter_n):
                                    _zc = _V_o_ad[:, _j, 2]
                                    _end = int(np.argmax(_zc)) + 1
                                    _zt = float(np.clip(z_loc, _zc[0], _zc[_end - 1]))
                                    _out[_j, 0] = np.interp(_zt, _zc[:_end],
                                                            _V_o_ad[:_end, _j, 0])
                                    _out[_j, 1] = np.interp(_zt, _zc[:_end],
                                                            _V_o_ad[:_end, _j, 1])
                                return _out
                        else:
                            def _rect_outer_section(z_loc):
                                _wz, _ = _profile_value_slope(_z_o_rect, _w_o_rect, z_loc)
                                _hz, _ = _profile_value_slope(_z_o_rect, _h_o_rect, z_loc)
                                return _ta._rect_points(_wz / 2.0, _hz / 2.0,
                                                        n=_adapter_n, lockstep=True)

                        _adapter_custom_z, _adapter_custom_pts, _adapter_custom_outer = _profile_stack(
                            zr, _handoff_local_z, _rect_section, _rect_outer_section)
                    elif is_poly:
                        horn_shape = "polygonal"
                        rect_w = rect_h = 0.0
                        poly_n_sides = n_sides
                        poly_circumR, _ = _profile_value_slope(
                            zp, _R_i_arr, _handoff_local_z)
                        horn_R_eq, _adapter_target_slope = _profile_value_slope(
                            zp, rp, _handoff_local_z)
                        _adapter_target_curv = _profile_curv(
                            zp, rp, _handoff_local_z)
                        _outer_target_R, _outer_target_slope = _profile_value_slope(
                            _z_o_poly, _R_o_eq_arr, _handoff_local_z)
                        _adapter_outer_target_curv = _profile_curv(
                            _z_o_poly, _R_o_eq_arr, _handoff_local_z)
                        _outer_rw = _outer_rh = None
                        def _poly_section(z_loc):
                            _Rz, _ = _profile_value_slope(zp, _R_i_arr, z_loc)
                            return _ta._poly_points(n_sides, _Rz, n=_adapter_n)

                        def _poly_outer_section(z_loc):
                            _Rz, _ = _profile_value_slope(_z_o_poly, _R_o_arr, z_loc)
                            return _ta._poly_points(n_sides, _Rz, n=_adapter_n)

                        _adapter_custom_z, _adapter_custom_pts, _adapter_custom_outer = _profile_stack(
                            zp, _handoff_local_z, _poly_section, _poly_outer_section)
                    elif is_osse:
                        # The OS-SE cross-section is NOT an ellipse (elliptical-
                        # cone coverage under a sqrt, plus the superellipse mouth
                        # morph), so an area-matched ellipse target leaves a
                        # visible step ring at the adapter↔flare junction
                        # (~0.5 mm, max on the diagonals). Hand the adapter the
                        # EXACT r(z,φ) contour at the handoff plane instead —
                        # inner airway and outer wall (true 3-D normal offset,
                        # same as the mesh engine).
                        horn_shape = "custom"
                        rect_w = rect_h = 0.0
                        poly_n_sides = 0
                        poly_circumR = 0.0
                        _nphi_os = _R_os.shape[1]

                        def _osse_section(z_loc):
                            _zt = float(np.clip(z_loc, _z_os[0], _z_os[-1]))
                            _Rz = np.array([np.interp(_zt, _z_os, _R_os[:, j])
                                            for j in range(_nphi_os)])
                            return np.column_stack([_Rz * np.cos(_phi_os),
                                                    _Rz * np.sin(_phi_os)])

                        def _osse_r_eq(z_loc):
                            return float(np.sqrt(
                                _ta._polygon_area(_osse_section(z_loc)) / np.pi))

                        _end_section = _osse_section(_handoff_local_z)
                        horn_R_eq = float(np.sqrt(
                            _ta._polygon_area(_end_section) / np.pi))
                        # Slope/curvature of the equivalent radius from the
                        # r(z,φ) grid — step by one grid spacing (the field is
                        # piecewise linear between rings).
                        _zg = float(_z_os[1] - _z_os[0])
                        _re_m = _osse_r_eq(_handoff_local_z - _zg)
                        _re_p = _osse_r_eq(_handoff_local_z + _zg)
                        _adapter_target_slope = (_re_p - _re_m) / (2.0 * _zg)
                        _adapter_target_curv = (
                            _re_p - 2.0 * horn_R_eq + _re_m) / (_zg * _zg)

                        # Outer-wall contours: per-vertex true 3-D normal
                        # offset, identical to generate_osse_3d_mesh.
                        _V_in_os = np.empty((len(_z_os), _nphi_os, 3))
                        _V_in_os[:, :, 0] = _R_os * np.cos(_phi_os)[None, :]
                        _V_in_os[:, :, 1] = _R_os * np.sin(_phi_os)[None, :]
                        _V_in_os[:, :, 2] = _z_os[:, None]
                        _V_out_os = _V_in_os + thickness * _osse._vertex_normals(_V_in_os)

                        def _osse_outer_section(z_loc):
                            _zt = float(np.clip(z_loc, _z_os[0], _z_os[-1]))
                            _out = np.empty((_nphi_os, 2))
                            for _j in range(_nphi_os):
                                _zo_col = _V_out_os[:, _j, 2]
                                _end = int(np.argmax(_zo_col)) + 1
                                _out[_j, 0] = np.interp(_zt, _zo_col[:_end],
                                                        _V_out_os[:_end, _j, 0])
                                _out[_j, 1] = np.interp(_zt, _zo_col[:_end],
                                                        _V_out_os[:_end, _j, 1])
                            return _out

                        # Section STACK (one per field ring below the handoff
                        # plane + the plane itself): the adapter's tail then
                        # follows the real flare — aspect ratio included —
                        # through the weld overlap. A single uniformly scaled
                        # end section still left a ~0.06 mm step ring because
                        # the OS-SE aspect ratio changes with z.
                        _adapter_custom_z, _adapter_custom_pts, _adapter_custom_outer = _profile_stack(
                            _z_os, _handoff_local_z, _osse_section, _osse_outer_section)

                        _outer_target_R = _outer_target_slope = _adapter_outer_target_curv = None
                        _outer_rw = _outer_rh = None
                    else:
                        horn_shape = "circular"
                        rect_w = rect_h = 0.0
                        poly_n_sides = 0
                        poly_circumR = 0.0
                        horn_R_eq, _adapter_target_slope = _profile_value_slope(
                            zp, rp, _handoff_local_z)
                        _adapter_target_curv = _profile_curv(
                            zp, rp, _handoff_local_z)
                        _outer_target_R, _outer_target_slope = _profile_value_slope(
                            _z_o_circ, _r_o_circ, _handoff_local_z)
                        _adapter_outer_target_curv = _profile_curv(
                            _z_o_circ, _r_o_circ, _handoff_local_z)
                        _outer_rw = _outer_rh = None
                        def _circ_section(z_loc):
                            _Rz, _ = _profile_value_slope(zp, rp, z_loc)
                            return _ta._circle_points(_Rz, n=_adapter_n)

                        def _circ_outer_section(z_loc):
                            _Rz, _ = _profile_value_slope(_z_o_circ, _r_o_circ, z_loc)
                            return _ta._circle_points(_Rz, n=_adapter_n)

                        _adapter_custom_z, _adapter_custom_pts, _adapter_custom_outer = _profile_stack(
                            zp, _handoff_local_z, _circ_section, _circ_outer_section)

                    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: tp = t.name
                    f_throat, _adapter_cutter = _ta.make_adapter_assembly(
                        driver_type=_ta_driver_key,
                        driver_diam=_ft_driver_d if _driver_is_custom_flange else None,
                        thread_key=_ta_thread_key,
                        horn_shape=horn_shape,
                        rect_w=rect_w, rect_h=rect_h,
                        poly_n_sides=poly_n_sides,
                        poly_circumR=poly_circumR,
                        horn_R_eq=horn_R_eq,
                        adapter_length=_adapter_length_actual,
                        wall_thickness=thickness,
                        flange_R=_ft_od / 2.0 if _driver_is_custom_flange else 0.0,
                        flange_thickness=_ft_sp if _driver_is_flanged else 0.0,
                        flange_bolt_R=_ft_bc / 2.0 if _driver_is_custom_flange else 0.0,
                        flange_bolt_n=int(_ft_nb) if _driver_is_custom_flange else 0,
                        flange_bolt_d=_ft_db if _driver_is_custom_flange else 0.0,
                        flange_bolt_phase=_ft_bphase if _driver_is_custom_flange else 0.0,
                        flange_outer_n=_ft_outer_n if _driver_is_custom_flange else 0,
                        driver_clearance=_ta_driver_clearance,
                        socket_length=_ta_socket_depth if _driver_is_threaded else 0.0,
                        outer_target_R=_outer_target_R,
                        outer_rect_w=_outer_rw,
                        outer_rect_h=_outer_rh,
                        target_slope=_adapter_target_slope,
                        outer_target_slope=_outer_target_slope,
                        target_curv=_adapter_target_curv,
                        outer_target_curv=_adapter_outer_target_curv,
                        custom_pts=_adapter_custom_pts,
                        custom_outer_pts=_adapter_custom_outer,
                        custom_pts_z=_adapter_custom_z,
                        custom_match_from_z=_adapter_match_from_z,
                        z_offset=_adapter_z_offset,
                        return_cutter=True,
                        output_path=tp,
                    )
                    if _ta_is_separated and f_throat is not None:
                        adapter_mesh = f_throat
                        cut_z = float(_adapter_length_actual)
                        
                        # Generate adapter exit mating flange
                        _ad_contour = _mesh_outer_section_xy(adapter_mesh, cut_z - 1e-3)
                        _ring_val = _ft_ring if is_osse else 15.0
                        if _ad_contour is not None:
                            _ad_flange = _fg.generate_contour_flange(
                                inner_xy=_ad_contour, thickness=_ft_sp, wall=0.0,
                                ring=_ring_val, bite=_FLANGE_WALL_BITE,
                                bolt_n=int(_ft_nb), bolt_d=_ft_db, bolt_phase=_ft_bphase,
                                offset=cut_z)
                            if _ad_flange:
                                adapter_mesh = _tm.boolean.union([adapter_mesh, _ad_flange], engine="manifold")
                        
                        st.session_state["adapter_mesh_exported"] = adapter_mesh
                        
                        # Slice horn and translate back
                        sliced = horn.slice_plane([0.0, 0.0, cut_z], [0.0, 0.0, 1.0], cap=True)
                        if sliced is not None and not sliced.is_empty:
                            horn = sliced
                        horn.apply_translation([0.0, 0.0, -cut_z])
                        
                        # Generate horn throat mating flange
                        _horn_contour = _mesh_outer_section_xy(horn, 1e-3)
                        if _horn_contour is not None:
                            f_throat = _fg.generate_contour_flange(
                                inner_xy=_horn_contour, thickness=_ft_sp, wall=0.0,
                                ring=_ring_val, bite=_FLANGE_WALL_BITE,
                                bolt_n=int(_ft_nb), bolt_d=_ft_db, bolt_phase=_ft_bphase,
                                offset=0.0)
                        else:
                            f_throat = None
                            
                        # Skip cutter difference
                        _adapter_cutter = None

                    if not _ta_is_separated:
                        st.session_state["adapter_mesh_exported"] = None
                        if _adapter_preserve_return_lip and f_throat is not None and _adapter_cutter is not None:
                            try:
                                # Use the exact internal cutter generated by the adapter loft
                                # to hollow out the original horn's throat. This removes only
                                # the advancing airway without touching the returning lip
                                # (unlike a straight cylinder cut).
                                _cut_horn = _tm.boolean.difference(
                                    [horn, _adapter_cutter],
                                    engine="manifold",
                                    check_volume=False)
                                if _cut_horn is not None and not _cut_horn.is_empty:
                                    horn = _cut_horn
                                    horn.remove_unreferenced_vertices()
                                    horn.fix_normals()
                            except Exception:
                                pass
                elif is_ellip and throat_outer == "Elliptical":
                    # Sample the contour at the actual flange top face, not at
                    # the very bottom of the horn mesh. On roll-backs the base
                    # section can sit on the returning lip, which makes the
                    # plate inherit that split instead of following the clean
                    # throat-facing contour inside the rollback.
                    _ft_contour_z = float(z_min + _ft_off + _ft_sp)
                    _ft_contour = _mesh_outer_section_xy(horn, _ft_contour_z)
                    if _ft_contour is not None:
                        f_throat = _fg.generate_contour_flange(
                            inner_xy=_ft_contour,
                            thickness=_ft_sp,
                            wall=0.0,
                            ring=_ft_ring,
                            bite=_FLANGE_WALL_BITE,
                            bolt_n=int(_ft_nb),
                            bolt_d=_ft_db,
                            bolt_phase=_ft_bphase,
                            offset=_ft_contour_z,
                            output_path=None,
                        )
                elif is_rect:
                    _ft_ot = ("circular" if throat_outer == "Circular"
                              else "elliptical" if throat_outer == "Elliptical"
                              else "rectangular")
                    f_throat = _rf.generate_rectangular_flange(
                        outer_diam=_ft_od if _ft_ot == "circular" else None,
                        inner_w=_ft_inner_w, inner_h=_ft_inner_h,
                        thickness=_ft_sp,
                        bolt_radius=_ft_bc/2, bolt_count=int(_ft_nb), bolt_diam=_ft_db,
                        bolt_phase=_ft_bphase,
                        outer_type=_ft_ot,
                        outer_w=_ft_outer_w if _ft_ot in ("rectangular", "elliptical") else None,
                        outer_h=_ft_outer_h if _ft_ot in ("rectangular", "elliptical") else None,
                        offset=z_min + _ft_off,
                        inner_type="elliptical" if is_ellip else "rectangular",
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
                        seg=rings_n,
                        outer_n_sides=_ft_outer_n,
                        output_path=None)

            if gen_throat and is_osse and not _ta_include_adapter:
                # Round throat → flat circular flange welded to the throat outer
                # wall (fiw_g/2 = throat_R + thickness), like the axisymmetric path.
                # With the shape adapter active, f_throat already holds the
                # adapter assembly — do NOT overwrite it with the flat flange.
                f_throat = _fg.generate_flange(
                    throat_R=fiw_g / 2.0, flange_R=_ft_od / 2.0,
                    thickness=_ft_sp, bolt_R=_ft_bc / 2.0,
                    bolt_n=int(_ft_nb), bolt_d=_ft_db, bolt_phase=_ft_bphase,
                    offset=z_min + _ft_off + _ft_sp,
                    seg=rings_n,
                    outer_n_sides=int(_ft_outer_n), output_path=None)

            # ── Weld-reinforcement chamfer ───────────────────────────
            if (gen_throat and not is_radial and _ft_chamfer
                    and _ft_chamfer_w > 0 and _ft_chamfer_h > 0
                    and f_throat is not None):
                # Identify which body the chamfer wraps around
                if _ta_include_adapter:
                    _chamfer_source = f_throat
                    _chamfer_flange_top = float(f_throat.bounds[0, 2] + _ft_sp)
                else:
                    _chamfer_source = horn
                    _chamfer_flange_top = float(z_min + _ft_off + _ft_sp)

                _chamfer_top = min(
                    _chamfer_flange_top + float(_ft_chamfer_h),
                    float(_chamfer_source.bounds[1, 2]) - 1e-3)

                if _chamfer_top > _chamfer_flange_top + 0.5:
                    _chamfer_base_xy = _mesh_outer_section_xy(
                        _chamfer_source, _chamfer_flange_top + 1e-3)
                    _chamfer_top_xy = _mesh_outer_section_xy(
                        _chamfer_source, _chamfer_top)

                    if _chamfer_base_xy is not None and _chamfer_top_xy is not None:
                        f_throat_chamfer = _fg.generate_throat_chamfer(
                            base_xy=_chamfer_base_xy,
                            top_xy=_chamfer_top_xy,
                            base_z=_chamfer_flange_top,
                            height=_chamfer_top - _chamfer_flange_top,
                            width=float(_ft_chamfer_w))

            if gen_mouth and is_osse:
                # Superelliptical mouth → flange built from the INNER airway
                # contour.  The hole = airway bitten inward so the wall pokes
                # through; outer = airway + wall + ring.  The mesh engine's
                # normal blend keeps the outer wall at ~wall mm radially at
                # the mouth, so the flange outer naturally matches the horn.
                f_mouth = _fg.generate_contour_flange(
                    inner_xy=_osse_contour_xy(_len),
                    thickness=_fm_sp, wall=thickness, ring=_fm_ring,
                    bite=_FLANGE_WALL_BITE,
                    bolt_n=int(_fm_nb), bolt_d=_fm_db, bolt_phase=_fm_bphase,
                    offset=z_mouth + _fm_off, output_path=None)

            if gen_mid and is_osse:
                # Intermediate ring on the real inner airway section at the
                # plate's mouth-ward face.
                f_mid = _fg.generate_contour_flange(
                    inner_xy=_osse_contour_xy(_mid_pos),
                    thickness=_mid_sp, wall=thickness, ring=_mid_ring,
                    bite=_FLANGE_WALL_BITE,
                    bolt_n=int(_mid_nb), bolt_d=_mid_db, bolt_phase=_mid_bphase,
                    offset=z_min + _mid_pos + _mid_off, output_path=None)

            if gen_mouth and not is_radial and not is_osse:
                if _fm_inward:
                    # Inward flange: a flat plate that FILLS the roll-back cavity,
                    # welded between the inner flare and the curled-back lip. The
                    # outer contour stays = rim (nothing protrudes beyond the mouth
                    # Ø); the hole = flare wall at the peak so the airway is clear
                    # and the wall pokes through to weld. Bolts sit just inside the
                    # rim (≥ wall margin). Annular pillars bridge the empty cavity
                    # between plate and lip before the shaft/head channels are cut.
                    _fm_inward_shape = (
                        "elliptical" if is_ellip else "rectangular" if is_rect
                        else "polygonal" if is_poly else "circular")
                    _fm_plate_top = _fm_rim_off + _fm_off + _fm_sp
                    if is_ellip:
                        # Build the ring on the cavity-facing side of the
                        # returning wall. The previous rim-station contour was
                        # wider than the return wall across the plate thickness,
                        # so the flat ring emerged through the outside skin.
                        from shapely.geometry import Polygon as _ShapelyPolygon

                        _fm_return_contour = _grid_branch_section_xy(
                            _V_o_ellip, _fm_plate_top, returning=True)
                        _fm_return_skin_contour = _grid_branch_section_xy(
                            _V_i_ellip, _fm_plate_top, returning=True)
                        _fm_outgoing_contour = _grid_branch_section_xy(
                            _V_o_ellip, _fm_plate_top, returning=False)
                        _fm_return_poly = _ShapelyPolygon(_fm_return_contour)
                        _fm_return_skin_poly = _ShapelyPolygon(
                            _fm_return_skin_contour)
                        _fm_outgoing_poly = _ShapelyPolygon(_fm_outgoing_contour)
                        if not _fm_return_poly.is_valid:
                            _fm_return_poly = _fm_return_poly.buffer(0)
                        if not _fm_return_skin_poly.is_valid:
                            _fm_return_skin_poly = _fm_return_skin_poly.buffer(0)
                        if not _fm_outgoing_poly.is_valid:
                            _fm_outgoing_poly = _fm_outgoing_poly.buffer(0)

                        # A true inward offset gives the requested land width.
                        # The small outward bite embeds only into the returning
                        # wall, keeping the complete flange inside the rollback.
                        _fm_hole_poly = _fm_return_poly.buffer(-_fm_ring)
                        _fm_outer_poly = _fm_return_poly.buffer(_FLANGE_WALL_BITE)
                        if (_fm_hole_poly.is_empty
                                or not _fm_hole_poly.contains(_fm_outgoing_poly)
                                or not _fm_return_skin_poly.contains(_fm_outer_poly)):
                            st.error("Inward flange does not fit inside this roll-back; "
                                     "reduce Offset from flare or flange thickness.")
                        else:
                            f_mouth = _fg.generate_contour_flange(
                                inner_xy=np.asarray(
                                    _fm_hole_poly.exterior.coords, dtype=float)[:, :2],
                                outer_xy=np.asarray(
                                    _fm_outer_poly.exterior.coords, dtype=float)[:, :2],
                                thickness=_fm_sp,
                                bite=0.0,
                                bolt_n=0,
                                bolt_d=_fm_db,
                                offset=_fm_plate_top,
                                output_path=None,
                            )
                    else:
                        f_mouth = _fg.generate_profile_flange(
                            inner_type=_fm_inward_shape,
                            inner_R=max(_fm_peak_R - _FLANGE_WALL_BITE, 1.0),
                            inner_w=max(_fm_peak_w - 2 * _FLANGE_WALL_BITE, 1.0),
                            inner_h=max(_fm_peak_h - 2 * _FLANGE_WALL_BITE, 1.0),
                            inner_n_sides=n_sides if is_poly else 0,
                            outer_mode="custom",
                            outer_type=_fm_inward_shape,
                            outer_diam=2.0 * _fm_rim_R,
                            outer_w=_fm_rim_w, outer_h=_fm_rim_h,
                            outer_n_sides=n_sides if is_poly else 0,
                            # Plate bottom must stay exactly at the rim plane: the
                            # horn mounts on it. The weld does not need a sunk
                            # plate (the old +0.5 thickness left a 0.5 mm step
                            # below the lip): the curled lip dives through the
                            # plate volume from above, which welds volumetrically.
                            thickness=_fm_sp, bolt_n=0, bolt_d=_fm_db,
                            offset=_fm_rim_off + _fm_off + _fm_sp,
                            seg=max(128, rings_n),
                            output_path=None)
                    _fm_channel_d = _fm_head_d if _fm_seat else _fm_db
                    _fm_pillar_R = _fm_channel_d / 2.0 + _fm_seat_wall
                    _bx = max(_fm_rim_w / 2.0 - _fm_pillar_R, 1.0)
                    _by = max(_fm_rim_h / 2.0 - _fm_pillar_R, 1.0)
                    _ang = np.linspace(0, 2 * np.pi, int(_fm_nb), endpoint=False) + _fm_bphase
                    _z_lo = float(horn.bounds[0, 2]) - 10.0
                    _z_hi = float(horn.bounds[1, 2]) + 10.0
                    # Top face of the cavity-filling plate (the flange the heads
                    # bear on). The head counterbore must reach down to it so the
                    # screw head clears the lip + cavity and seats on the flange.
                    # Sample the horn solid along Z. Pillars stop at the first lip
                    # material above the plate across their whole footprint, so
                    # they remain hidden below the curved outer skin.
                    _zsamp = np.linspace(horn.bounds[0, 2], horn.bounds[1, 2], 400)
                    for _a in _ang:
                        if is_ellip:
                            _cx, _cy = _bx * np.cos(_a), _by * np.sin(_a)
                        elif is_rect:
                            # Follow the actual rectangular rim. An ellipse-based
                            # pattern puts diagonal bolts deep in the empty cavity,
                            # so they drill only the plate and never reach the lip.
                            _ca, _sa = np.cos(_a), np.sin(_a)
                            _sx = (_fm_rim_w / 2.0) / max(abs(_ca), 1e-9)
                            _sy = (_fm_rim_h / 2.0) / max(abs(_sa), 1e-9)
                            _edge_R = min(_sx, _sy)
                            _ex, _ey = _edge_R * _ca, _edge_R * _sa
                            _cx = float(np.clip(
                                _ex, -_fm_rim_w / 2.0 + _fm_pillar_R,
                                _fm_rim_w / 2.0 - _fm_pillar_R))
                            _cy = float(np.clip(
                                _ey, -_fm_rim_h / 2.0 + _fm_pillar_R,
                                _fm_rim_h / 2.0 - _fm_pillar_R))
                        elif is_poly:
                            _edge_R = _polygon_radius_at_angle(
                                _fm_rim_R, n_sides, _a)
                            _bolt_R = max(_edge_R - _fm_pillar_R, 1.0)
                            _cx, _cy = _bolt_R * np.cos(_a), _bolt_R * np.sin(_a)
                        else:
                            _bolt_R = max(_fm_rim_R - _fm_pillar_R, 1.0)
                            _cx, _cy = _bolt_R * np.cos(_a), _bolt_R * np.sin(_a)
                        # shaft through-hole, full span (open front-to-back)
                        _sh = _tm.creation.cylinder(
                            radius=_fm_db / 2.0, height=_z_hi - _z_lo, sections=64)
                        _sh.apply_translation([_cx, _cy, (_z_lo + _z_hi) / 2.0])
                        _mouth_bolt_cuts.append(_sh)
                        _col = np.column_stack(
                            [np.full_like(_zsamp, _cx), np.full_like(_zsamp, _cy), _zsamp])
                        _ins = horn.contains(_col)
                        _ztop = float(_zsamp[_ins][-1]) if _ins.any() else _fm_plate_top
                        # Finish the visible flare opening with a short cylinder
                        # normal to the local curved surface. The long axial bore
                        # remains vertical for the screw/pillar, while this final
                        # cut makes the mouth-facing opening circular instead of
                        # the teardrop produced by a vertical cylinder crossing an
                        # inclined surface.
                        try:
                            _surf_p, _, _surf_face = horn.nearest.on_surface(
                                np.array([[_cx, _cy, _ztop]], dtype=float))
                            _surf_p = _surf_p[0]
                            _surf_n = horn.face_normals[int(_surf_face[0])]
                            # Only the screw shaft opens through the visible flare
                            # skin. The larger head counterbore stays hidden below.
                            _mouth_d = _fm_db
                            _mouth_in = thickness + 0.5
                            _mouth_out = 2.0
                            _mouth_len = _mouth_in + _mouth_out
                            _mouth_cut = _tm.creation.cylinder(
                                radius=_mouth_d / 2.0,
                                height=_mouth_len,
                                sections=96)
                            _mouth_cut.apply_transform(
                                _tm.geometry.align_vectors([0.0, 0.0, 1.0], _surf_n))
                            _mouth_cut.apply_translation(
                                _surf_p + _surf_n * ((_mouth_out - _mouth_in) / 2.0))
                            _mouth_flare_opening_cuts.append(_mouth_cut)
                        except Exception:
                            # The axial bore is still valid if proximity lookup
                            # fails on an unusual/partially repaired mesh.
                            pass
                        # Create the complete pillar through and beyond the flare,
                        # then boolean-clip it against a closed local volume whose
                        # top follows the real curved outer surface. This removes
                        # every protruding fragment while preserving full support
                        # from the plate to the lip.
                        _pillar_bot = _fm_plate_top - 0.3
                        _pillar_full = _tm.creation.cylinder(
                            radius=_fm_pillar_R,
                            height=_z_hi - _pillar_bot,
                            sections=64)
                        _pillar_full.apply_translation(
                            [_cx, _cy, (_z_hi + _pillar_bot) / 2.0])

                        _nr, _na = 6, 64
                        _radii = np.linspace(
                            (_fm_pillar_R + 0.3) / _nr,
                            _fm_pillar_R + 0.3, _nr)
                        _theta = np.linspace(0.0, 2 * np.pi, _na, endpoint=False)
                        _top_grid = np.empty((_nr, _na), dtype=float)
                        _valid_clip = True
                        _ccol = np.column_stack([
                            np.full_like(_zsamp, _cx),
                            np.full_like(_zsamp, _cy),
                            _zsamp])
                        _cins = horn.contains(_ccol)
                        _top_center = float(_zsamp[_cins][-1]) if _cins.any() else _fm_plate_top
                        for _ri, _pr in enumerate(_radii):
                            for _ai, _pa in enumerate(_theta):
                                _px = _cx + _pr * np.cos(_pa)
                                _py = _cy + _pr * np.sin(_pa)
                                _pcol = np.column_stack([
                                    np.full_like(_zsamp, _px),
                                    np.full_like(_zsamp, _py),
                                    _zsamp])
                                _pins = horn.contains(_pcol)
                                if not _pins.any():
                                    _valid_clip = False
                                    break
                                _top_grid[_ri, _ai] = float(_zsamp[_pins][-1])
                            if not _valid_clip:
                                break

                        if _valid_clip:
                            _clip_v = [[_cx, _cy, _pillar_bot]]
                            for _ri, _pr in enumerate(_radii):
                                for _ai, _pa in enumerate(_theta):
                                    _clip_v.append([
                                        _cx + _pr * np.cos(_pa),
                                        _cy + _pr * np.sin(_pa),
                                        _pillar_bot])
                            _top_center_i = len(_clip_v)
                            _clip_v.append([_cx, _cy, _top_center])
                            _top_ring0 = len(_clip_v)
                            for _ri, _pr in enumerate(_radii):
                                for _ai, _pa in enumerate(_theta):
                                    _clip_v.append([
                                        _cx + _pr * np.cos(_pa),
                                        _cy + _pr * np.sin(_pa),
                                        _top_grid[_ri, _ai]])
                            _clip_f = []
                            for _ai in range(_na):
                                _aj = (_ai + 1) % _na
                                _clip_f.extend([
                                    [0, 1 + _aj, 1 + _ai],
                                    [_top_center_i, _top_ring0 + _ai, _top_ring0 + _aj]])
                            for _ri in range(_nr - 1):
                                for _ai in range(_na):
                                    _aj = (_ai + 1) % _na
                                    _b0 = 1 + _ri * _na + _ai
                                    _b1 = 1 + _ri * _na + _aj
                                    _b2 = 1 + (_ri + 1) * _na + _aj
                                    _b3 = 1 + (_ri + 1) * _na + _ai
                                    _t0 = _top_ring0 + _ri * _na + _ai
                                    _t1 = _top_ring0 + _ri * _na + _aj
                                    _t2 = _top_ring0 + (_ri + 1) * _na + _aj
                                    _t3 = _top_ring0 + (_ri + 1) * _na + _ai
                                    _clip_f.extend([
                                        [_b0, _b2, _b1], [_b0, _b3, _b2],
                                        [_t0, _t1, _t2], [_t0, _t2, _t3]])
                            _outer_b = 1 + (_nr - 1) * _na
                            _outer_t = _top_ring0 + (_nr - 1) * _na
                            for _ai in range(_na):
                                _aj = (_ai + 1) % _na
                                _b0, _b1 = _outer_b + _ai, _outer_b + _aj
                                _t0, _t1 = _outer_t + _ai, _outer_t + _aj
                                _clip_f.extend([[_b0, _b1, _t1], [_b0, _t1, _t0]])
                            _clip = _tm.Trimesh(
                                vertices=np.asarray(_clip_v),
                                faces=np.asarray(_clip_f),
                                process=True)
                            _clip.fix_normals()
                            _pillar = _tm.boolean.intersection(
                                [_pillar_full, _clip], engine="manifold",
                                check_volume=False)
                            if _pillar is not None and not _pillar.is_empty:
                                _mouth_bolt_pillars.append(_pillar)
                        if _fm_seat and int(_fm_nb) > 0:
                            # Axial, concentric, coplanar head seats. Every bore
                            # ends on the same Z plane in the inward flange/pillar
                            # assembly, regardless of local flare curvature.
                            _fm_plate_bot = _fm_rim_off + _fm_off
                            _seat_floor = max(
                                _fm_plate_top - _fm_seat_depth,
                                _fm_plate_bot + 0.5)
                            _seat_top = _z_hi
                            _seat_cut = _tm.creation.cylinder(
                                radius=_fm_head_d / 2.0,
                                height=_seat_top - _seat_floor,
                                sections=96)
                            _seat_cut.apply_translation(
                                [_cx, _cy, (_seat_top + _seat_floor) / 2.0])
                            _mouth_head_seat_cuts.append(_seat_cut)
                elif is_ellip and not _fm_custom:
                    _fm_contour = _mesh_outer_section_xy(horn, _fm_rim_off)
                    if _fm_contour is not None:
                        f_mouth = _fg.generate_contour_flange(
                            inner_xy=_fm_contour,
                            thickness=_fm_sp,
                            wall=0.0,
                            ring=_fm_ring,
                            bite=_FLANGE_WALL_BITE,
                            bolt_n=int(_fm_nb),
                            bolt_d=_fm_db,
                            bolt_phase=_fm_bphase,
                            offset=_fm_rim_off + _fm_off + _fm_sp,
                            output_path=None,
                        )
                else:
                    _fm_inner_type = (
                        "elliptical" if is_ellip else
                        "rectangular" if is_rect else
                        "polygonal" if is_poly else "circular")
                    _fm_top = (
                        _fm_rim_off + _fm_off + _fm_sp if is_rect
                        else z_mouth + _fm_off)
                    f_mouth = _fg.generate_profile_flange(
                        inner_type=_fm_inner_type,
                        inner_R=_fm_hole_R,
                        inner_w=_fm_inner_w if (is_rect or is_ellip) else 0.0,
                        inner_h=_fm_inner_h if (is_rect or is_ellip) else 0.0,
                        inner_n_sides=n_sides if is_poly else 0,
                        outer_mode="custom" if _fm_custom else "offset",
                        outer_type=mouth_outer.lower(),
                        outer_offset=_fm_ring,
                        outer_diam=_fm_od,
                        outer_w=_fm_outer_w,
                        outer_h=_fm_outer_h,
                        outer_n_sides=_fm_outer_n,
                        thickness=_fm_sp,
                        bolt_mode="fixed" if _fm_bolt_mode == "Fixed from center" else "auto",
                        bolt_R=_fm_bc / 2.0,
                        bolt_n=int(_fm_nb), bolt_d=_fm_db,
                        bolt_phase=_fm_bphase,
                        offset=_fm_top,
                        seg=max(128, rings_n),
                        output_path=None)

            if gen_mid and not is_radial and not is_osse:
                z_mid = z_min + _mid_pos + _mid_off
                if is_poly:
                    _R_o_mid_poly = float(np.interp(_mid_pos, zp, _R_o_arr))
                else:
                    _R_o_mid_poly = _mid_inner_R
                _mid_inner_type = (
                    "elliptical" if is_ellip else
                    "rectangular" if is_rect else
                    "polygonal" if is_poly else "circular")
                if is_ellip and not _mid_custom:
                    _mid_contour = _mesh_outer_section_xy(
                        horn, z_min + _mid_pos - _mid_sp)
                    if _mid_contour is not None:
                        f_mid = _fg.generate_contour_flange(
                            inner_xy=_mid_contour,
                            thickness=_mid_sp,
                            wall=0.0,
                            ring=_mid_ring,
                            bite=_FLANGE_WALL_BITE,
                            bolt_n=int(_mid_nb),
                            bolt_d=_mid_db,
                            bolt_phase=_mid_bphase,
                            offset=z_mid,
                            output_path=None,
                        )
                else:
                    f_mid = _fg.generate_profile_flange(
                        inner_type=_mid_inner_type,
                        inner_R=_R_o_mid_poly,
                        inner_w=_mid_inner_w if is_rect else 0.0,
                        inner_h=_mid_inner_h if is_rect else 0.0,
                        inner_n_sides=n_sides if is_poly else 0,
                        outer_mode="custom" if _mid_custom else "offset",
                        outer_type=mid_out.lower(),
                        outer_offset=_mid_ring,
                        outer_diam=_mid_od,
                        outer_w=_mid_outer_w,
                        outer_h=_mid_outer_h,
                        outer_n_sides=_mid_outer_n,
                        thickness=_mid_sp,
                        bolt_mode="fixed" if _mid_bolt_mode == "Fixed from center" else "auto",
                        bolt_R=_mid_bc / 2.0,
                        bolt_n=int(_mid_nb), bolt_d=_mid_db,
                        bolt_phase=_mid_bphase,
                        offset=z_mid,
                        seg=max(128, rings_n),
                        output_path=None)

            # --- 3e. Merge ---
            # Circular mouth-facing openings affect only the flare skin. Applying
            # them after the pillar union would carve the load-bearing sleeves.
            if _mouth_flare_opening_cuts:
                try:
                    horn = _tm.boolean.difference(
                        [horn] + _mouth_flare_opening_cuts,
                        engine="manifold",
                        check_volume=False)
                except Exception:
                    pass

            bodies = []
            if gen_horn:
                bodies.append(horn)
                if is_radial:
                    bodies.append(horn_top)
            if f_throat is not None: bodies.append(f_throat)
            if f_throat_chamfer is not None: bodies.append(f_throat_chamfer)
            if f_mouth  is not None: bodies.append(f_mouth)
            if f_mid    is not None: bodies.append(f_mid)
            bodies.extend(_mouth_bolt_pillars)

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
            # Inward mouth flange: drill the bolt channels through the welded
            # plate, compression pillars, and curled lip so they reach the front.
            if _mouth_bolt_cuts:
                try:
                    combined = _tm.boolean.difference(
                        [combined] + _mouth_bolt_cuts, engine="manifold")
                except Exception:
                    pass
            if _mouth_head_seat_cuts:
                try:
                    combined = _tm.boolean.difference(
                        [combined] + _mouth_head_seat_cuts,
                        engine="manifold",
                        check_volume=False)
                except Exception:
                    pass
            st.session_state["_combined"] = combined
            # Stash the individual flange bodies so each can be exported as a 2-D
            # DXF drilling template (bolt holes + bore + outline) on demand.
            # The inward mouth flange is generated with bolt_count=0 (its shafts
            # are drilled into `combined`, not the plate), so drill the shaft
            # cuts into a DXF-only copy here — otherwise its template has no
            # holes. Pillars/head-seats are left out; only the through-shafts
            # define the drilling pattern.
            _f_mouth_dxf = f_mouth
            if f_mouth is not None and _mouth_bolt_cuts:
                try:
                    _f_mouth_dxf = _tm.boolean.difference(
                        [f_mouth] + _mouth_bolt_cuts, engine="manifold")
                except Exception:
                    _f_mouth_dxf = f_mouth
            st.session_state["_flange_bodies"] = {
                name: body for name, body in (
                    ("throat", f_throat if not is_radial else None),
                    ("mouth", _f_mouth_dxf),
                    ("mid", f_mid),
                ) if body is not None
            }
            if (gen_throat and not is_radial and _ta_include_adapter
                    and f_throat is not None and _embedded_adapter_cut_z is not None):
                st.session_state["_adapter_cut_z"] = float(_embedded_adapter_cut_z)
            else:
                st.session_state.pop("_adapter_cut_z", None)
            if gen_throat and f_throat is not None:
                st.session_state["_throat_keep_z"] = float(f_throat.bounds[1, 2])
            else:
                st.session_state.pop("_throat_keep_z", None)

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
            _wt   = combined.is_watertight if hasattr(combined, 'is_watertight') else None
            _vol  = combined.volume if hasattr(combined, 'volume') else 0
            _tris = len(combined.faces) if hasattr(combined, 'faces') else 0

            st.session_state["_assembly_stl_bytes"] = stl_bytes
            st.session_state["_assembly_step_bytes"] = step_bytes
            st.session_state["_assembly_stats"] = {
                "length": horn.bounds[1,2]-z_min if gen_horn else None,
                "mouth_bx": mouth_bx if gen_horn else None,
                "mouth_by": mouth_by if gen_horn else None,
                "wt": _wt,
                "vol": _vol,
                "tris": _tris,
                "gen_horn": gen_horn
            }
            st.session_state["_assembly_generated"] = True

        except Exception as exc:
            # Show a short, safe message to the user; keep the full traceback
            # server-side only (it would otherwise expose source snippets).
            st.error(f"❌ Generation failed: {type(exc).__name__}: {exc}")
            logger.exception("Assembly generation failed")
            st.session_state["_assembly_generated"] = False

if st.session_state.get("_assembly_generated"):
    stats = st.session_state["_assembly_stats"]
    st.success("✅ Assembly generated successfully")

    r1, r2, r3, r4 = st.columns(4)
    with r1:
        st.metric("Length", f"{stats['length']:.0f} mm" if stats["gen_horn"] else "—")
    with r2:
        if stats["gen_horn"]:
            st.metric("Mouth", f"Ø{stats['mouth_bx']:.0f}" if abs(stats['mouth_bx']-stats['mouth_by'])<1
                      else f"{stats['mouth_bx']:.0f}×{stats['mouth_by']:.0f}")
        else:
            st.metric("Mouth", "—")
    with r3:
        st.metric("Triangles", f"{stats['tris']:,}")
    with r4:
        st.metric("Volume", f"{stats['vol']:.0f} mm³")

    if stats["wt"] is True:
        st.success("Watertight mesh — ready for 3D printing")
    elif stats["wt"] is False:
        st.warning("Non-watertight mesh — check parameters")
    else:
        st.info("Multi-body output (separate flanges)")

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button("📥 Download STL", st.session_state["_assembly_stl_bytes"], "flare_forge_assembly.stl",
            "model/stl", use_container_width=True)
    with col_dl2:
        _step_bytes = st.session_state.get("_assembly_step_bytes")
        if _step_bytes is not None:
            st.download_button("📥 Download STEP", _step_bytes, "flare_forge_assembly.step",
                "model/step", use_container_width=True)
        else:
            st.caption("STEP not available")
    
    if st.session_state.get("adapter_mesh_exported") is not None:
        _adapter_mesh = st.session_state["adapter_mesh_exported"]
        _ad_stl = _adapter_mesh.export(file_type="stl")
        st.download_button("📥 Download Separated Adapter (STL)", _ad_stl, "adapter_assembly.stl",
            "model/stl", use_container_width=True)

    # 2-D DXF drilling templates — one per mounting flange (bolt holes,
    # bore and outline on separate layers). Generated lazily from each
    # flange body so any flange type (round/poly/rect, custom/bolt-on)
    # exports without re-deriving parameters.
    _flange_bodies = st.session_state.get("_flange_bodies", {})
    _dxf_labels = {"throat": "Throat", "mouth": "Mouth", "mid": "Mid"}
    
    if "_dxf_items" not in st.session_state:
        _dxf_items = []
        for _key, _body in _flange_bodies.items():
            try:
                _dxf = mesh_to_flange_dxf(_body)
            except Exception:
                _dxf = None
            if _dxf:
                _dxf_items.append((_key, _dxf))
        st.session_state["_dxf_items"] = _dxf_items
    else:
        _dxf_items = st.session_state["_dxf_items"]

    if _dxf_items:
        st.caption("📐 Flange drilling templates (DXF — bolt holes, bore, outline)")
        _dxf_cols = st.columns(len(_dxf_items))
        for _col, (_key, _dxf) in zip(_dxf_cols, _dxf_items):
            with _col:
                st.download_button(
                    f"📥 {_dxf_labels.get(_key, _key)} flange DXF",
                    _dxf.encode("ascii"),
                    f"{_key}_flange_holes.dxf",
                    "application/dxf",
                    use_container_width=True,
                    key=f"dxf_{_key}")

else:
    st.info("Configure the parameters and click **Generate Assembly STL**")

# ══════════════════════════════════════════════════════════════
#  Interactive 3-D preview of the last generated assembly
# ══════════════════════════════════════════════════════════════
# Opt-in (default off): the assembly can be ~175k triangles, and Streamlit
# re-runs this whole script on every widget change. Rendering the mesh only
# when the toggle is on keeps normal parameter tweaking snappy; once on, the
# rotation/zoom itself is client-side WebGL and never triggers a rerun.
if "_combined" in st.session_state:
    st.divider()
    _pc1, _pc2 = st.columns([3, 1])
    with _pc1:
        st.subheader("3D Preview")
    with _pc2:
        _show_3d = st.toggle("Show", value=False, key="show_3d_preview",
                             help="Interactive view of the generated assembly — "
                                  "drag to rotate, scroll to zoom, right-drag to pan")
    if _show_3d:
        try:
            import plotly.graph_objects as go
            _pm = st.session_state["_combined"]
            _pv = np.asarray(_pm.vertices, dtype=float)
            _pf = np.asarray(_pm.faces)
            # Smooth (Gouraud) shading, NOT flat: the flare wall is built from
            # ~160 azimuthal facets per ring, and flat shading lights each facet
            # discretely → a radial "sunburst" down the throat that looks like a
            # defect but is just the tessellation. Averaged vertex normals blend
            # the facets into the true smooth surface.
            _fig3d = go.Figure(go.Mesh3d(
                x=_pv[:, 0], y=_pv[:, 1], z=_pv[:, 2],
                i=_pf[:, 0], j=_pf[:, 1], k=_pf[:, 2],
                color="#7cb342", flatshading=False, hoverinfo="skip",
                lighting=dict(ambient=0.5, diffuse=0.85, specular=0.15,
                              roughness=0.7, fresnel=0.1),
                lightposition=dict(x=200, y=400, z=800)))
            _fig3d.update_layout(
                height=620, showlegend=False,
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                scene=dict(
                    aspectmode="data",            # equal scale → true proportions
                    bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(visible=False), yaxis=dict(visible=False),
                    zaxis=dict(visible=False),
                    camera=dict(eye=dict(x=1.5, y=-1.6, z=0.9))))
            st.plotly_chart(_fig3d, use_container_width=True,
                            config={"displaylogo": False})
            st.caption("Drag to rotate · scroll to zoom · right-drag to pan · "
                       "double-click to reset")
        except ModuleNotFoundError:
            st.warning("3D preview needs `plotly` — run `pip install plotly`.")
        except Exception as _exc3d:
            st.warning(f"3D preview unavailable: {type(_exc3d).__name__}: {_exc3d}")

with st.sidebar:
    # ══════════════════════════════════════════════════════════════
    #  ROW 4 — STL Slicing (always visible, works on generated or uploaded STL)
    # ══════════════════════════════════════════════════════════════

    st.divider()
    st.subheader("Slice STL")

    load_choice = st.radio("Source", ["Generated assembly", "Upload STL file"],
                           index=0, horizontal=True, key="slice_src")
    slice_strategy = st.radio("Slicing mode", ["Axial / petals", "Print volume boxes"],
                              horizontal=True, key="slice_strategy")
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
        if slice_strategy == "Print volume boxes":
            st.caption("Generate an assembly or upload an STL to enable print-volume slicing.")
        st.stop()

    # ── Slicing workflow ────────────────────────────────────────────────
    import zipfile

    # Shift mesh so Z_min = 0 for clean segmentation
    _z_off = mesh_to_slice.bounds[0, 2]
    if abs(_z_off) > 0.5:
        mesh_to_slice = mesh_to_slice.copy()
        mesh_to_slice.apply_translation([0, 0, -_z_off])
        st.caption(f"Mesh shifted by {-_z_off:.0f} mm so Z starts at 0")

    _adapter_cut_z = None
    _throat_keep_z = None
    if load_choice == "Generated assembly":
        _adapter_cut_raw = st.session_state.get("_adapter_cut_z")
        if _adapter_cut_raw is not None:
            _adapter_cut_z = float(_adapter_cut_raw) - float(_z_off)
            if not (mesh_to_slice.bounds[0, 2] + 1e-6 < _adapter_cut_z < mesh_to_slice.bounds[1, 2] - 1e-6):
                _adapter_cut_z = None
        _throat_keep_raw = st.session_state.get("_throat_keep_z")
        if _throat_keep_raw is not None:
            _throat_keep_z = float(_throat_keep_raw) - float(_z_off)
            if not (mesh_to_slice.bounds[0, 2] + 1e-6 < _throat_keep_z < mesh_to_slice.bounds[1, 2] - 1e-6):
                _throat_keep_z = None

    _joint = st.checkbox("Axial joint lip", True, key="joint_en",
                         help="Add a joint lip on each axial cut so stacked segments "
                              "register and glue together.")
    _joint_w = st.number_input("Lip wall (mm)", 0.5, 10.0, 4.0, 0.5, key="joint_w",
                                help="Wall thickness of the axial joint lip") if _joint else 0.0

    _flange_joint = st.checkbox("Axial bolted flange", False, key="flange_joint_en",
                                help="Add an external flange with bolt holes at each axial cut.")
    _flange_params = None
    if _flange_joint:
        _fj_cols = st.columns(2)
        with _fj_cols[0]:
            _fj_thick = st.number_input("Flange thickness (mm)", 1.0, 30.0, 6.0, 1.0, key="fj_thick")
            _fj_offset = st.number_input("Offset da parete (mm)", 0.0, 50.0, 0.0, 1.0, key="fj_offset",
                                         help="Clearance distance from the outer horn wall.")
            _fj_bolt_n = st.number_input("Bolt count", 2, 32, 8, 1, key="fj_bolt_n")
        with _fj_cols[1]:
            _fj_ring = st.number_input("Larghezza anello (mm)", 5.0, 50.0, 15.0, 1.0, key="fj_ring",
                                       help="Width of the bolting land. Bolts are centered here.")
            _fj_bolt_d = st.number_input("Bolt hole Ø (mm)", 1.0, 20.0, 4.5, 0.5, key="fj_bolt_d")
            _fj_phase = st.number_input("Fase fori (deg)", -180.0, 180.0, 0.0, 5.0, key="fj_phase")
        _flange_params = {
            "thickness": float(_fj_thick),
            "ring": float(_fj_ring),
            "wall": float(_fj_offset),
            "bolt_n": int(_fj_bolt_n),
            "bolt_d": float(_fj_bolt_d),
            "bolt_phase": float(np.radians(_fj_phase)),
        }

    _cut_adapter_segment = False
    if _adapter_cut_z is not None:
        _cut_adapter_segment = st.checkbox("Adapter as axial segment", False,
                                           key="slice_adapter_segment",
                                           help="Add a dedicated cut where the adapter enters "
                                                "the flare; the adapter becomes its own bottom "
                                                "segment and receives the axial joint lip.")
        if _cut_adapter_segment:
            st.caption(f"Adapter cut at Z={_adapter_cut_z:.1f} mm; flare segmentation starts above it.")

    _radial_joint = st.checkbox("Radial joint (tongue & groove)", False, key="radial_joint_en",
                                help="Add a vertical tongue & groove on each radial "
                                     "seam so petals interlock and self-align.")
    # Defaults that work for most prints; only depth is in the primary flow.
    _radial_clearance, _radial_outer_keep, _radial_inner_margin = 0.0, None, 0.5
    if _radial_joint:
        _radial_joint_d = st.number_input("Joint depth (mm)", 0.5, 5.0, 2.0, 0.5,
                                          key="radial_joint_d",
                                          help="How far the tongue sticks out / groove goes in")
        with st.expander("Advanced radial joint"):
            _radial_clearance = st.number_input("Clearance (mm)", 0.0, 0.5, 0.1, 0.05,
                                                key="radial_clearance",
                                                help="Total gap between tongue and groove "
                                                     "(split evenly: 0.05 mm per side at default)")
            _radial_outer_keep = st.number_input("Outer skin keep (mm)", 0.5, 5.0, 1.5, 0.5,
                                                key="radial_outer_keep",
                                                help="Hard minimum protected external wall strip. "
                                                     "The slicer errors out if the wall cannot keep this much.")
            _radial_inner_margin = st.number_input("Inner margin (mm)", 0.5, 5.0, 0.5, 0.5,
                                                  key="radial_inner_margin",
                                                  help="Margin kept on the inner side of the wall. "
                                                       "Together with Outer skin keep, controls how "
                                                       "thick the tongue/groove will be.")
    else:
        _radial_joint_d = 0.0

    if st.button("Reset slicer cache", use_container_width=True):
        st.session_state.pop("_ax_segs", None)
        st.session_state.pop("_pieces", None)
        for _k in list(st.session_state.keys()):
            if _k.startswith("_pet_ax") or _k.startswith("_sel_ax"):
                del st.session_state[_k]
        st.rerun()

    if slice_strategy == "Print volume boxes":
        _pv_cols = st.columns(3)
        with _pv_cols[0]:
            _pv_x = st.number_input("Max X (mm)", 10.0, 2000.0, 220.0, 10.0, key="pv_x")
        with _pv_cols[1]:
            _pv_y = st.number_input("Max Y (mm)", 10.0, 2000.0, 220.0, 10.0, key="pv_y")
        with _pv_cols[2]:
            _pv_z = st.number_input("Max Z (mm)", 10.0, 2000.0, 250.0, 10.0, key="pv_z")
        _pv_strategy = st.radio("Packing", ["Center-up core first", "Adaptive largest pieces", "Regular grid"],
                                horizontal=True, key="pv_strategy",
                                help="Center-up cuts the central stack bottom-to-top first, then side wings. "
                                     "Adaptive recursively splits oversized pieces. "
                                     "Regular grid cuts the whole bounding box into fixed cells.")
        _pv_joint = st.checkbox("Box joints (tongue & groove)", False, key="pv_joint_en",
                                help="Add male/female alignment joints on shared print-volume cut faces.")
        _pv_clearance, _pv_margin = 0.0, 1.0
        if _pv_joint:
            _pv_joint_d = st.number_input("Box joint depth (mm)", 0.5, 5.0, 2.0, 0.5,
                                          key="pv_joint_d")
            with st.expander("Advanced box joint"):
                _pv_clearance = st.number_input("Box joint clearance (mm)", 0.0, 0.5, 0.1, 0.05,
                                                key="pv_clearance")
                _pv_margin = st.number_input("Box joint margin (mm)", 0.5, 8.0, 1.0, 0.5,
                                             key="pv_margin",
                                             help="Inset from the cut-face perimeter before placing the tongue/groove.")
        else:
            _pv_joint_d = 0.0

        _keep_throat = False
        _manual_keep_z = None
        if _throat_keep_z is not None:
            _keep_throat = st.checkbox("Keep throat adapter/flange monolithic", True,
                                       key="pv_keep_throat",
                                       help="Do not split the generated throat-side hardware. "
                                            "It stays inside the first center-bottom chunk, "
                                            "which may exceed the print volume.")
            if _keep_throat:
                st.caption(f"Protected throat inside first core block: Z=0–{_throat_keep_z:.1f} mm")
        elif load_choice != "Generated assembly":
            _manual_keep = st.checkbox("Keep throat-side section monolithic", False,
                                       key="pv_keep_manual")
            if _manual_keep:
                _manual_keep_z = st.number_input("Protected Z height (mm)", 1.0,
                                                 float(mesh_to_slice.bounds[1, 2] - mesh_to_slice.bounds[0, 2]),
                                                 30.0, 1.0, key="pv_keep_z")

        _pv_keep_z = _throat_keep_z if (_keep_throat and _throat_keep_z is not None) else _manual_keep_z
        _pv_sig = (
            tuple(np.round(mesh_to_slice.bounds.reshape(-1), 4)),
            round(float(_pv_x), 4), round(float(_pv_y), 4), round(float(_pv_z), 4),
            None if _pv_keep_z is None else round(float(_pv_keep_z), 4),
            _pv_strategy,
            bool(_pv_joint), round(float(_pv_joint_d), 4),
            round(float(_pv_clearance), 4), round(float(_pv_margin), 4),
        )
        if st.session_state.get("_pv_sig") != _pv_sig:
            st.session_state["_pv_sig"] = _pv_sig
            st.session_state.pop("_pieces", None)

        if st.button("Slice to print volume", use_container_width=True):
            with st.spinner("Cutting into print-volume boxes…"):
                _box_meshes = _slc.slice_to_print_volume(
                    mesh_to_slice, _pv_x, _pv_y, _pv_z, keep_z_max=_pv_keep_z,
                    strategy=(
                        "center_up" if _pv_strategy.startswith("Center") else
                        "adaptive" if _pv_strategy.startswith("Adaptive") else
                        "grid"
                    ),
                    joint_depth=_pv_joint_d,
                    joint_margin=_pv_margin,
                    clearance=_pv_clearance,
                )
                _pieces = []
                for _i, _part in enumerate(_box_meshes):
                    _dims = _part.bounds[1] - _part.bounds[0]
                    if _part.metadata.get("print_volume_core") and _pv_keep_z is not None and _i == 0:
                        _prefix = "core_throat001"
                    elif _part.metadata.get("print_volume_core"):
                        _prefix = f"core{_i+1:03d}"
                    else:
                        _prefix = f"wing{_i+1:03d}"
                    _pieces.append((
                        f"{_prefix}_{_dims[0]:.0f}x{_dims[1]:.0f}x{_dims[2]:.0f}mm",
                        _part,
                    ))
                st.session_state["_pieces"] = _pieces
            st.rerun()

    ax_mode = st.radio("Define segments by", ["Count", "Height (mm)"],
                       horizontal=True, key="ax_mode")
    if ax_mode == "Count":
        _n_ax_label = "Flare axial segments" if _cut_adapter_segment else "Number of axial segments"
        n_ax = st.number_input(_n_ax_label, 1, 50, 1, step=1, key="n_ax")
        seg_ref = ("count", n_ax)
    else:
        seg_h = st.number_input("Cut every (mm)", 5, 500, 50, step=5, key="seg_h")
        total_z = mesh_to_slice.bounds[1, 2] - (_adapter_cut_z if _cut_adapter_segment else mesh_to_slice.bounds[0, 2])
        cuts = [seg_h * k for k in range(1, int(total_z / seg_h) + 1)]
        n_seg = len(cuts) + 1 + (1 if _cut_adapter_segment else 0)
        _total_label = "Total flare Z" if _cut_adapter_segment else "Total Z"
        st.caption(f"{_total_label}={total_z:.0f} mm → {n_seg} segment{'s' if n_seg>1 else ''}")
        seg_ref = ("height", seg_h)

    _slice_sig = (
        3,  # slicer algorithm cache version
        tuple(np.round(mesh_to_slice.bounds.reshape(-1), 4)),
        bool(_joint), float(_joint_w),
        bool(_flange_joint), None if not _flange_params else tuple(_flange_params.values()),
        bool(_cut_adapter_segment),
        None if _adapter_cut_z is None else round(float(_adapter_cut_z), 4),
        seg_ref,
    )
    if slice_strategy == "Axial / petals" and st.session_state.get("_slice_sig") != _slice_sig:
        st.session_state["_slice_sig"] = _slice_sig
        st.session_state.pop("_ax_segs", None)
        st.session_state.pop("_pieces", None)
        for _k in list(st.session_state.keys()):
            if _k.startswith("_pet_ax") or _k.startswith("_sel_ax"):
                del st.session_state[_k]

    if st.button("❶ Slice axially", use_container_width=True,
                 disabled=(slice_strategy != "Axial / petals")):
        with st.spinner("Cutting axially…"):
            if _cut_adapter_segment and _adapter_cut_z is not None:
                if seg_ref[0] == "count":
                    st.session_state["_ax_segs"] = _slc.slice_with_adapter_segment(
                        mesh_to_slice, _adapter_cut_z,
                        flare_segments=int(seg_ref[1]),
                        joint_wall=_joint_w,
                        flange_params=_flange_params)
                else:
                    st.session_state["_ax_segs"] = _slc.slice_with_adapter_segment(
                        mesh_to_slice, _adapter_cut_z,
                        flare_height=float(seg_ref[1]),
                        joint_wall=_joint_w,
                        flange_params=_flange_params)
            elif seg_ref[0] == "count":
                n = seg_ref[1]
                if n <= 1:
                    st.session_state["_ax_segs"] = [mesh_to_slice]
                else:
                    st.session_state["_ax_segs"] = _slc.slice_into_segments(
                        mesh_to_slice, n, joint_wall=_joint_w, flange_params=_flange_params)
            else:
                dz = seg_ref[1]
                z0, z1 = mesh_to_slice.bounds[0, 2], mesh_to_slice.bounds[1, 2]
                cuts = [dz * k for k in range(1, int((z1 - z0) / dz) + 1)]
                if not cuts:
                    st.session_state["_ax_segs"] = [mesh_to_slice]
                else:
                    st.session_state["_ax_segs"] = _slc.slice_at_heights(
                        mesh_to_slice, cuts, joint_wall=_joint_w, flange_params=_flange_params)
        st.session_state.pop("_pieces", None)
        # cleanup old per-segment petal keys
        for k in list(st.session_state.keys()):
            if k.startswith("_pet_ax") or k.startswith("_sel_ax"):
                del st.session_state[k]

    ax_segs = st.session_state.get("_ax_segs", None) if slice_strategy == "Axial / petals" else None
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
                default_pet = int(st.session_state.get(pet_key, 2))
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
            st.caption(f"🔩 {len(_hole_angles)} bolt hole(s) detected.")

        _auto_phase = st.checkbox("Auto-avoid bolt holes", False, key="auto_phase_en",
                                  help="If checked, seams will be rotated to fall between bolt holes. Uncheck to set a manual starting angle.")
        _manual_phase_deg = 0.0
        if not _auto_phase:
            _manual_phase_deg = st.number_input("Seam angle (°)", -180.0, 180.0, 0.0, 1.0, key="manual_phase_deg",
                                                help="Angle of the first seam (0 = X axis).")

        if _radial_joint:
            st.caption(f"✔ Tongue & groove — depth {_radial_joint_d} mm, clearance {_radial_clearance} mm, outer skin {_radial_outer_keep} mm, inner margin {_radial_inner_margin} mm")

        _petal_sig = (
            3,  # radial petal algorithm cache version
            tuple(int(v) for v in petals_per),
            bool(_radial_joint),
            round(float(_radial_joint_d), 4),
            round(float(_radial_clearance), 4),
            None if _radial_outer_keep is None else round(float(_radial_outer_keep), 4),
            round(float(_radial_inner_margin), 4),
            tuple(round(float(a), 6) for a in _hole_angles),
            bool(_auto_phase),
            round(float(_manual_phase_deg), 4),
        )
        if st.session_state.get("_petal_sig") != _petal_sig:
            st.session_state["_petal_sig"] = _petal_sig
            st.session_state.pop("_pieces", None)

        if st.button("❷ Apply petals", use_container_width=True):
            with st.spinner("Cutting petals…"):
                pieces = []
                for ai, (seg, np_) in enumerate(zip(ax_segs, petals_per)):
                    if np_ > 1:
                        if _auto_phase and _hole_angles:
                            phase = _slc.seam_phase_avoiding_holes(np_, _hole_angles)
                        else:
                            phase = np.radians(_manual_phase_deg)
                        pets = _slc.slice_into_petals(seg, np_, phase=phase,
                                                        joint_depth=_radial_joint_d,
                                                        joint_margin=_radial_inner_margin,
                                                        clearance=_radial_clearance,
                                                        outer_margin=_radial_outer_keep)
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

    if st.session_state.get("_pieces_cache_sig") != st.session_state.get("_petal_sig"):
        with st.spinner("Preparing downloads..."):
            zip_buf = io.BytesIO()
            pieces_bytes = {}
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, mesh in pieces:
                    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as _t:
                        _tp = _t.name
                        mesh.export(_tp)
                    with open(_tp, "rb") as f:
                        b = f.read()
                        pieces_bytes[name] = b
                        zf.writestr(f"{name}.stl", b)
                    os.unlink(_tp)
            st.session_state["_pieces_zip"] = zip_buf.getvalue()
            st.session_state["_pieces_bytes"] = pieces_bytes
            st.session_state["_pieces_cache_sig"] = st.session_state.get("_petal_sig")

    _, col_zip, _ = st.columns([1, 2, 1])
    with col_zip:
        st.download_button("📦 Download all as ZIP", st.session_state["_pieces_zip"],
                           "flare_forge_slices.zip", "application/zip",
                           use_container_width=True, key="dl_zip_slices")

    for name, mesh in pieces:
        b = st.session_state["_pieces_bytes"].get(name)
        if b is None: continue
        label = f"📥 {name}"
        if "_pet" not in name:
            z_lo, z_hi = mesh.bounds[0, 2], mesh.bounds[1, 2]
            label += f"  (Z={z_lo:.0f}–{z_hi:.0f} mm)"
        st.download_button(label, b, f"{name}.stl", "model/stl", key=f"dl_{name}")
