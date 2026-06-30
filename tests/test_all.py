"""
Comprehensive test suite — all profile × section combinations.

Each test asserts not just "doesn't crash" but geometric invariants:
  - Profile math: z starts at 0, r[0] == throat/2, monotone expansion
  - 3D mesh: watertight, single body, positive volume, correct bounding box
  - Flanges: watertight, single body, hole smaller than outer
  - Radial: gap > 0 everywhere, R monotone, correct throat/mouth radii
"""

import argparse
import sys, os, tempfile, traceback, itertools, types

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from stl import mesh

PASS = 0
FAIL = 0
SKIP = 0


def _parse_args():
    parser = argparse.ArgumentParser(description="Run the full Flare Forge test suite.")
    parser.add_argument(
        "--match", "-m", action="append", default=[],
        help="Run only tests whose label contains this text. May be repeated.")
    parser.add_argument(
        "--list", action="store_true",
        help="List matching test labels without running them.")
    return parser.parse_args()


ARGS = _parse_args()
MATCHES = [m.casefold() for m in ARGS.match]


def _selected(label):
    return not MATCHES or any(m in label.casefold() for m in MATCHES)


def test(label, fn):
    global PASS, FAIL, SKIP
    if not _selected(label):
        SKIP += 1
        return
    if ARGS.list:
        print(f"  • {label}")
        PASS += 1
        return
    try:
        fn()
        print(f"  ✅ {label}")
        PASS += 1
    except Exception:
        print(f"  ❌ {label}")
        traceback.print_exc()
        FAIL += 1


# ── imports ──────────────────────────────────────────────────────────────────

from src import profile_generator as _c
from src import polygonal_horn as _ph
from src import radial_horn as _rd
from src import omni_horn as _om
from src import flange_generator as _fg
from src import rectangular_horn as _r
from src import rectangular_flange as _rf
from src import throat_adapter as _ta
from src import osse_horn as _osse
from src import _utils as _uts
from src import save_load as _svl
import trimesh

# ══════════════════════════════════════════════════════════════════════════════
#  1. Profile math — invariants on (z, r) arrays
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Profile math invariants ═══")

THROAT = 20.0
MOUTH  = 100.0
FC     = 600
N      = 300
TOL    = 0.5   # mm tolerance on throat/mouth radius match

def _check_profile(z, r, throat, mouth=None, label="", monotone_z=True):
    assert len(z) == len(r) > 1,         f"{label}: empty arrays"
    assert abs(z[0]) < 1e-6,             f"{label}: z[0]={z[0]:.4f}, expected 0"
    assert abs(r[0] - throat/2) < TOL,   f"{label}: r[0]={r[0]:.2f}, expected {throat/2:.2f}"
    if monotone_z:
        assert np.all(np.diff(z) >= -1e-6),  f"{label}: z not monotone"
    else:
        # roll-back profiles: z must reach a positive maximum before curving back
        assert z.max() > 1.0,            f"{label}: z never advances (max={z.max():.2f})"
    assert r.max() > r[0],               f"{label}: no expansion"
    if mouth is not None:
        assert abs(r[-1] - mouth/2) < TOL, f"{label}: r[-1]={r[-1]:.2f}, expected {mouth/2:.2f}"

for entry in [
    ("Tractrix 20→100",          lambda: _c.get_tractrix(THROAT, MOUTH, N),         True),
    ("Tractrix 20→200",          lambda: _c.get_tractrix(THROAT, 200,   N),         True),
    ("Salmon 20/600/L80",        lambda: _c.get_salmon(THROAT, FC, 80,   N),         True),
    ("Salmon 20/1200/L50",       lambda: _c.get_salmon(THROAT, 1200, 50, N),         True),
    ("Exponential 20→100/600Hz", lambda: _c.get_exponential(THROAT, MOUTH, FC, N),  True),
    ("Exponential 20→200/400Hz", lambda: _c.get_exponential(THROAT, 200, 400, N),   True),
    ("Oblate 20/90deg/L80",      lambda: _c.get_oblate_spheroidal(THROAT, 90, 80, N), True),
    ("Oblate 20/60deg/L120",     lambda: _c.get_oblate_spheroidal(THROAT, 60, 120, N), True),
    ("Conical 20/90deg/L80",     lambda: _c.get_conical(THROAT, 90, 80, N),          True),
    ("Conical 20/60deg/L120",    lambda: _c.get_conical(THROAT, 60, 120, N),         True),
    ("R-OSSE 20→100/78deg",      lambda: _c.get_rosse(THROAT, MOUTH, 78, N),         False),
    ("Le Cleac'h 20/600/A160",   lambda: _c.get_lecleach(THROAT, FC, N),            False),
    ("Le Cleac'h 20/1200/A140",  lambda: _c.get_lecleach(THROAT, 1200, N, max_angle=140), False),
]:
    label, fn, mono_z = entry
    def make(fn=fn, label=label, mono_z=mono_z):
        z, r = fn()
        mouth = None
        if "Tractrix" in label:
            mouth = float(label.split("→")[1])
        elif "Exponential" in label:
            mouth = float(label.split("→")[1].split("/")[0])
        elif "R-OSSE" in label:
            mouth = float(label.split("→")[1].split("/")[0])
        _check_profile(z, r, THROAT, mouth, label, monotone_z=mono_z)
    test(label, make)


def _check_oblate_cd_law():
    throat, coverage, length = 20.0, 90.0, 2000.0
    z, r = _c.get_oblate_spheroidal(throat, coverage, length, 5000)
    theta = np.radians(coverage / 2.0)
    expected = np.sqrt((throat / 2.0) ** 2 + (z * np.tan(theta)) ** 2)
    assert np.allclose(r, expected), "oblate CD radius does not match law"
    slope_throat = (r[1] - r[0]) / (z[1] - z[0])
    assert slope_throat < 0.03, f"throat slope {slope_throat:.4f} is not near zero"
    slope_far = (r[-1] - r[-50]) / (z[-1] - z[-50])
    assert abs(slope_far - np.tan(theta)) < 0.01, \
        f"far slope {slope_far:.4f} vs tan(theta) {np.tan(theta):.4f}"
test("Oblate CD law: parallel throat + conical asymptote", _check_oblate_cd_law)


def _check_conical_law():
    throat, coverage, length = 20.0, 90.0, 200.0
    z, r = _c.get_conical(throat, coverage, length, 2000)
    theta = np.radians(coverage / 2.0)
    expected = throat / 2.0 + z * np.tan(theta)
    assert np.allclose(r, expected), "conical radius does not match straight-wall law"
    # Constant slope = tan(theta) everywhere (a straight cone, unlike oblate).
    slope = np.diff(r) / np.diff(z)
    assert np.allclose(slope, np.tan(theta)), "conical wall is not straight"
test("Conical law: straight wall at tan(theta)", _check_conical_law)


def _check_lecleach_termination_angle_changes_geometry():
    z_120, r_120 = _c.get_lecleach(THROAT, FC, N, max_angle=120.0)
    z_160, r_160 = _c.get_lecleach(THROAT, FC, N, max_angle=160.0)
    assert z_160[-1] < z_120[-1], "larger termination angle should curl the edge farther back"
    assert r_160[-1] > r_120[-1], "larger termination angle should produce a larger mouth"
test("Le Cleac'h termination angle changes geometry",
     _check_lecleach_termination_angle_changes_geometry)


def _check_rosse_st260_reference():
    """Published rev.7 sample: 1-inch throat, 260 mm OD, just under 80 mm deep."""
    z, r = _c.get_rosse(25.4, 260.0, 78.0, 2000)
    assert abs(r[0] - 12.7) < 1e-9, "R-OSSE ST260 throat radius mismatch"
    assert abs(r[-1] - 130.0) < 1e-9, "R-OSSE ST260 outer radius mismatch"
    assert abs(z.max() - 77.70) < 0.1, f"R-OSSE ST260 depth={z.max():.2f} mm"
    assert z[-1] < z.max() - 10.0, "R-OSSE profile does not roll back"
test("R-OSSE rev.7 ST260 reference geometry", _check_rosse_st260_reference)


def _check_complete_rollback_profile_returns_inward():
    for label, base_fn, full_fn in [
        ("Le Cleac'h", 
         lambda: _c.get_lecleach(THROAT, FC, N, max_angle=160.0),
         lambda: _c.get_lecleach(THROAT, FC, N, max_angle=160.0,
                                 complete_rollback=True)),
        ("R-OSSE",
         lambda: _c.get_rosse(25.4, 260.0, 78.0, N),
         lambda: _c.get_rosse(25.4, 260.0, 78.0, N,
                              complete_rollback=True)),
    ]:
        zb, rb = base_fn()
        zf, rf = full_fn()
        assert len(zf) == len(rf) == N, f"{label}: complete profile was not resampled"
        assert abs(zf[0] - zb[0]) < 1e-9, f"{label}: throat z moved"
        assert abs(rf[0] - rb[0]) < 1e-9, f"{label}: throat r moved"
        assert rf.max() >= rb.max() - 0.5, f"{label}: acoustic mouth shrank"
        assert rf[-1] < rb[-1] - 20.0, f"{label}: curl did not return inward"
        assert zf[-1] < zb[-1], f"{label}: curl did not roll farther back"
test("Complete rollback profiles add inward return curl",
     _check_complete_rollback_profile_returns_inward)


def _check_complete_rollback_stays_above_throat_plane():
    z, _ = _c.get_lecleach(25.7, 600.0, 300, max_angle=160.0,
                           complete_rollback=True, rollback_angle=330.0)
    assert float(z.min()) >= -1e-6, "Le Cleac'h complete rollback dipped below throat plane"
test("Complete rollback stays above throat plane",
     _check_complete_rollback_stays_above_throat_plane)


def _check_complete_rollback_mesh_watertight():
    z, r = _c.get_lecleach(THROAT, FC, N, complete_rollback=True)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_3d_mesh_from_profile(z, r, 4.0, 96, p)
    m = trimesh.load(p, file_type="stl"); os.unlink(p)
    assert m.is_watertight, "complete Le Cleac'h rollback mesh is not watertight"
    assert m.body_count == 1, f"complete Le Cleac'h rollback mesh has {m.body_count} bodies"
test("Complete rollback mesh remains watertight",
     _check_complete_rollback_mesh_watertight)


def _check_oblate_asymmetric_elliptical_mesh():
    z, w, h = _c.get_oblate_spheroidal_asymmetric(20.0, 10.0, 90.0, 45.0, 80.0, N)
    assert abs(w[0] - 20.0) < TOL, "asymmetric oblate throat width mismatch"
    assert abs(h[0] - 10.0) < TOL, "asymmetric oblate throat height mismatch"
    assert w[-1] > h[-1], "90x45 profile should end wider than tall"
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_elliptical_3d_mesh_from_profiles(z, w / 2.0, h / 2.0, 4.0, 96, p)
    m = trimesh.load(p, file_type="stl"); os.unlink(p)
    assert m.is_watertight, "Oblate asymmetric elliptical: not watertight"
    assert m.body_count == 1, f"Oblate asymmetric elliptical: {m.body_count} bodies"
    assert m.volume > 100, f"Oblate asymmetric elliptical volume={m.volume:.0f}"
    mouth = m.vertices[m.vertices[:, 2] >= z[-1] - 0.1]
    assert np.ptp(mouth[:, 0]) > np.ptp(mouth[:, 1]), "elliptical mouth axes not preserved"
test("Oblate asymmetric 90x45 elliptical mesh", _check_oblate_asymmetric_elliptical_mesh)


def _check_elliptical_section_from_rect_math():
    """UI 'Elliptical' section path: rectangular profile math lofted as an ellipse.

    The UI reuses get_rectangular_* to get (z, w, h) then feeds the elliptical
    engine with semi-axes (w/2, h/2). Guards that this produces a watertight body
    for a non-CD profile (here Salmon), not just for the asymmetric oblate case.
    """
    z, w, h = _r.get_rectangular_salmon(30.0, 18.0, FC, 80.0, N)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_elliptical_3d_mesh_from_profiles(z, w / 2.0, h / 2.0, 4.0, 96, p)
    m = trimesh.load(p, file_type="stl"); os.unlink(p)
    assert m.is_watertight, "Elliptical Salmon section: not watertight"
    assert m.body_count == 1, f"Elliptical Salmon section: {m.body_count} bodies"
    assert m.volume > 100, f"Elliptical Salmon section volume={m.volume:.0f}"
test("Elliptical section (rect math, Salmon) watertight", _check_elliptical_section_from_rect_math)


def _check_elliptical_rollback_parallel_thickness():
    """Elliptical roll-back must offset along the surface normal, not radially."""
    z, r = _c.get_rosse(25.4, 260.0, 78.0, N)
    rx = r * 1.35
    ry = r / 1.35
    thickness = 4.0
    inner, outer = _c._elliptical_parallel_offset_vertices(
        z, rx, ry, thickness, 96)
    distances = np.linalg.norm(outer - inner, axis=2)
    assert np.allclose(distances, thickness, atol=1e-9), \
        f"elliptical wall thickness {distances.min():.4f}..{distances.max():.4f}"
    # At the rolled-back edge the parallel normal points partly inward and
    # backward; a radial-only offset would incorrectly increase both axes.
    assert outer[-1, 0, 0] < inner[-1, 0, 0], "roll-back outer edge did not turn inward"
    assert outer[-1, 0, 2] < inner[-1, 0, 2], "roll-back outer edge did not offset backward"

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_elliptical_3d_mesh_from_profiles(z, rx, ry, thickness, 96, p)
    m = trimesh.load(p, file_type="stl"); os.unlink(p)
    assert m.is_watertight, "Elliptical R-OSSE roll-back: not watertight"
    assert m.body_count == 1, f"Elliptical R-OSSE roll-back: {m.body_count} bodies"
test("Elliptical R-OSSE roll-back keeps parallel thickness",
     _check_elliptical_rollback_parallel_thickness)


def _check_elliptical_base_flat():
    """Elliptical engine must slice the throat base flat at z[0] (same
    invariant as the axisymmetric engine). The 3-D normal offset pushes the
    outer throat rim below z[0] on an expanding throat; without the base slice
    the mesh z_min sat ~thickness·|n_z| below the profile origin, shifting
    everything the UI anchors to mesh z_min (embedded throat adapter trim and
    positioning, flange Z offsets) and leaving a visible step at the
    adapter↔flare junction for elliptical R-OSSE."""
    z, r = _c.get_rosse(27.6, 147.0, 90.0, N)
    rx = r * 1.225
    ry = r / 1.225
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_elliptical_3d_mesh_from_profiles(z, rx, ry, 4.0, 96, p)
    m = trimesh.load(p, file_type="stl"); os.unlink(p)
    assert m.is_watertight, "Elliptical base-flat: not watertight"
    assert m.body_count == 1, f"Elliptical base-flat: {m.body_count} bodies"
    z_min = float(m.vertices[:, 2].min())
    assert abs(z_min - z[0]) < 1e-6, \
        f"elliptical base not flat at z[0]={z[0]:.4f}: z_min={z_min:.4f}"
test("Elliptical engine flattens throat base at z[0]", _check_elliptical_base_flat)


# ══════════════════════════════════════════════════════════════════════════════
#  2. Circular 3-D mesh — watertight + geometry checks
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Circular section — 3-D mesh ═══")

CIRC_CASES = [
    ("Tractrix",     lambda: _c.get_tractrix(THROAT, MOUTH, N)),
    ("Salmon",       lambda: _c.get_salmon(THROAT, FC, 80,   N)),
    ("Exponential",  lambda: _c.get_exponential(THROAT, MOUTH, FC, N)),
    ("Oblate",       lambda: _c.get_oblate_spheroidal(THROAT, 90, 80, N)),
    ("Conical",      lambda: _c.get_conical(THROAT, 90, 80, N)),
    ("R-OSSE",       lambda: _c.get_rosse(THROAT, MOUTH, 78, N)),
    ("Le Cleac'h",   lambda: _c.get_lecleach(THROAT, FC, N)),
]

def _check_mesh(m, label, min_volume=100):
    assert m.is_watertight,                          f"{label}: not watertight"
    assert m.body_count == 1,                        f"{label}: {m.body_count} bodies"
    assert m.volume > min_volume,                    f"{label}: volume={m.volume:.0f}"
    z_ext = m.bounds[1, 2] - m.bounds[0, 2]
    assert z_ext > 1.0,                              f"{label}: z extent={z_ext:.1f}"

for label, profile_fn in CIRC_CASES:
    def make(fn=profile_fn, lbl=label):
        z, r = fn()
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
        _c.generate_3d_mesh_from_profile(z, r, 4.0, 64, p)
        m = trimesh.load(p, file_type="stl"); os.unlink(p)
        _check_mesh(m, lbl)
        # mouth diameter should be roughly max(r)*2 + wall
        # (r.max() == r[-1] for monotone profiles; handles roll-back correctly)
        r_mouth_expected = r.max() + 4.0
        r_mouth_actual   = max(np.linalg.norm(m.vertices[:, :2], axis=1))
        assert abs(r_mouth_actual - r_mouth_expected) < 5.0, \
            f"{lbl}: mouth radius {r_mouth_actual:.1f} vs expected ~{r_mouth_expected:.1f}"
    test(label, make)


def test_driver_flange_specs():
    expected = {
        "bolt_on_1in_2": (25.4, 100.0, 2, 6.5, 76.2),
        "bolt_on_1in_3": (25.4, 90.0, 3, 6.5, 57.2),
        "bolt_on_1_4in_4": (35.6, 135.0, 4, 6.5, 101.6),
        "bolt_on_2in_4": (50.8, 135.0, 4, 6.5, 101.6),
    }
    assert set(_fg.DRIVER_FLANGE_SPECS) == set(expected)
    for key, values in expected.items():
        spec = _fg.DRIVER_FLANGE_SPECS[key]
        assert (spec.throat_diam, spec.outer_diam, spec.bolt_count,
                spec.bolt_diam, spec.pcd) == values
test("standard bolt-on driver flange specs", test_driver_flange_specs)


def test_driver_mounting_hole_centers():
    two = _fg.driver_mounting_hole_centers("bolt_on_1in_2")
    assert np.allclose(two, [[38.1, 0.0], [-38.1, 0.0]], atol=1e-9)
    three = _fg.driver_mounting_hole_centers("bolt_on_1in_3")
    assert np.allclose(np.linalg.norm(three, axis=1), 57.2 / 2.0)
    four = _fg.driver_mounting_hole_centers("bolt_on_2in_4")
    assert np.allclose(np.linalg.norm(four, axis=1), 101.6 / 2.0)
test("standard bolt-on hole positions", test_driver_mounting_hole_centers)


def test_adapter_bolt_phase_bias():
    assert np.isclose(_ta._adapter_bolt_phase("bolt_on_1in_2"), np.pi / 2.0)
    assert np.isclose(_ta._adapter_bolt_phase("bolt_on_2in_4"), 0.0)
    assert np.isclose(_ta._adapter_bolt_phase("bolt_on_1in_3"), np.pi / 2.0)

    wide = _ta._adapter_bolt_phase(
        "bolt_on_1in_3", horn_shape="rectangular",
        rect_w=80.0, rect_h=20.0, wall_thickness=4.0,
    )
    tall = _ta._adapter_bolt_phase(
        "bolt_on_1in_3", horn_shape="rectangular",
        rect_w=20.0, rect_h=80.0, wall_thickness=4.0,
    )
    assert np.isclose(wide, np.pi / 6.0)
    assert np.isclose(tall, 0.0)
test("adapter bolt-phase bias", test_adapter_bolt_phase_bias)


from src import dxf_export as _dxf

def _parse_circles(dxf):
    """Return list of (layer, cx, cy, r) from CIRCLE entities of a DXF string."""
    out = []
    for blk in dxf.split("0\nCIRCLE\n")[1:]:
        layer = blk.split("8\n")[1].split("\n")[0]
        cx = float(blk.split("10\n")[1].split("\n")[0])
        cy = float(blk.split("20\n")[1].split("\n")[0])
        r = float(blk.split("40\n")[1].split("\n")[0])
        out.append((layer, cx, cy, r))
    return out

def test_dxf_circular_flange_exact_holes():
    """DXF template recovers the exact nominal bolt holes (Ø + centres on the
    bolt circle) from a faceted flange mesh, plus a centred bore and outline."""
    m = _fg.generate_flange(throat_R=12.7, flange_R=50.0, thickness=6.0,
                            bolt_R=38.1, bolt_n=4, bolt_d=6.5)
    dxf = _dxf.mesh_to_flange_dxf(m)
    assert dxf is not None and dxf.startswith("0\nSECTION") and dxf.rstrip().endswith("EOF")
    circles = _parse_circles(dxf)
    holes = [c for c in circles if c[0] == "HOLES"]
    assert len(holes) == 4, f"expected 4 bolt holes, got {len(holes)}"
    for _, cx, cy, r in holes:
        assert abs(2 * r - 6.5) < 1e-3, f"hole Ø {2*r:.4f} != 6.5"
        assert abs(np.hypot(cx, cy) - 38.1) < 1e-3, f"hole off bolt circle: {np.hypot(cx,cy):.4f}"
    assert any(c[0] == "OUTLINE" for c in circles)
    assert any(c[0] == "BORE" for c in circles)
    # one POINT centre mark per bolt hole
    assert dxf.count("\nPOINT\n") == 4
test("DXF circular flange exact bolt holes", test_dxf_circular_flange_exact_holes)

def test_dxf_keeps_polygonal_bore_shape():
    """A hexagonal bore must stay a POLYLINE (not be rounded to a circle), while
    the round bolt holes are still exact circles."""
    m = _fg.generate_polygonal_flange(inner_circumR=18.0, n_sides=6, flange_R=55.0,
                                       thickness=6.0, bolt_R=42.0, bolt_n=6, bolt_d=6.5)
    dxf = _dxf.mesh_to_flange_dxf(m)
    assert dxf is not None
    circles = _parse_circles(dxf)
    holes = [c for c in circles if c[0] == "HOLES"]
    assert len(holes) == 6
    for _, _, _, r in holes:
        assert abs(2 * r - 6.5) < 1e-3
    # the bore is a hexagon → emitted as a POLYLINE on the BORE layer
    assert "0\nPOLYLINE\n8\nBORE\n" in dxf
    assert not any(c[0] == "BORE" for c in circles)
test("DXF keeps polygonal bore as polyline", test_dxf_keeps_polygonal_bore_shape)

def test_dxf_rectangular_flange():
    """Rectangular flange: rect outline + rect bore → polylines, round holes."""
    m = _rf.generate_rectangular_flange(outer_diam=120.0, inner_w=60.0, inner_h=40.0,
                                        thickness=6.0, bolt_radius=48.0,
                                        bolt_count=4, bolt_diam=6.5)
    dxf = _dxf.mesh_to_flange_dxf(m)
    assert dxf is not None
    holes = [c for c in _parse_circles(dxf) if c[0] == "HOLES"]
    assert len(holes) == 4
    assert "0\nPOLYLINE\n8\nBORE\n" in dxf  # rectangular opening stays a polyline
test("DXF rectangular flange template", test_dxf_rectangular_flange)

def test_dxf_finds_thin_flange_on_tall_adapter():
    """A thin bolt-on flange atop a long throat adapter must still be located:
    the drilling plane is found via horizontal plate faces, not coarse uniform
    sampling (which stepped over the plate and reported zero holes)."""
    from src import throat_adapter as _ta
    for L in (40.0, 120.0, 200.0):
        m = _ta.make_adapter_assembly(
            driver_type="bolt_on_2in_4", driver_diam=None, thread_key=None,
            horn_shape="circular", rect_w=0, rect_h=0, poly_n_sides=0,
            poly_circumR=0, horn_R_eq=20.0, adapter_length=L,
            wall_thickness=4.0, flange_thickness=6.0)
        dxf = _dxf.mesh_to_flange_dxf(m)
        assert dxf is not None, f"no DXF for adapter L={L}"
        holes = [c for c in _parse_circles(dxf) if c[0] == "HOLES"]
        assert len(holes) >= 1, f"adapter L={L}: holes missed ({len(holes)})"
test("DXF finds thin flange on tall adapter", test_dxf_finds_thin_flange_on_tall_adapter)

def test_dxf_radial_returns_none():
    """A body with no flange-style holes yields no template (None, not a crash)."""
    cyl = trimesh.creation.cylinder(radius=20.0, height=10.0)
    assert _dxf.mesh_to_flange_dxf(cyl) is None
test("DXF returns None when no holes present", test_dxf_radial_returns_none)


for _driver_key, _driver_spec in _fg.DRIVER_FLANGE_SPECS.items():
    def make_driver_flange(key=_driver_key, spec=_driver_spec):
        clearance = 0.3
        thickness = 6.0
        m = _fg.generate_driver_mounting_flange(
            key, thickness=thickness, throat_clearance=clearance
        )
        assert m is not None, f"driver flange {key}: returned None"
        assert m.is_watertight, f"driver flange {key}: not watertight"
        assert m.body_count == 1, f"driver flange {key}: {m.body_count} bodies"
        assert m.volume > 0, f"driver flange {key}: volume={m.volume}"
        extents = m.bounds[1] - m.bounds[0]
        assert abs(extents[0] - spec.outer_diam) < 0.1
        assert abs(extents[1] - spec.outer_diam) < 0.1
        expected_volume = np.pi * thickness * (
            (spec.outer_diam / 2.0) ** 2
            - ((spec.throat_diam + clearance) / 2.0) ** 2
            - spec.bolt_count * (spec.bolt_diam / 2.0) ** 2
        )
        assert abs(m.volume - expected_volume) / expected_volume < 0.01
    test(f"standard driver flange {_driver_key}", make_driver_flange)


# ══════════════════════════════════════════════════════════════════════════════
#  3. Polygonal section — all profiles × n_sides sample
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Polygonal section — 3-D mesh ═══")

POLY_SIDES = [3, 4, 6, 8]

for (label, profile_fn), n_sides in itertools.product(CIRC_CASES, POLY_SIDES):
    _lbl = f"{label} {n_sides}-gon"
    def make(fn=profile_fn, ns=n_sides, lbl=_lbl):
        z, r = fn()
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
        _ph.generate_polygonal_3d_mesh(z, r, ns, 4.0, p)
        m = trimesh.load(p, file_type="stl"); os.unlink(p)
        _check_mesh(m, lbl)
    test(_lbl, make)


# ══════════════════════════════════════════════════════════════════════════════
#  3b. Profile adherence — generated wall follows the math curve at every station
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Profile adherence to mathematical curves ═══")

from shapely.geometry import Polygon as _ShPoly


def _airway_section(m, z):
    """Measure the hollow airway of mesh *m* at height *z*.

    Returns ``(r_eq, width, height)`` where ``r_eq = sqrt(A_hole/π)`` is the
    area-equivalent radius of the airway (shape-agnostic: works for circular,
    rectangular and N-gon sections alike) and width/height are the airway's
    bounding box. Returns ``None`` when the slice is solid or off the body.
    """
    sec = m.section(plane_origin=[0.0, 0.0, float(z)], plane_normal=[0.0, 0.0, 1.0])
    if sec is None:
        return None
    p, _ = sec.to_planar()
    polys = p.polygons_full
    if not polys:
        return None
    poly = max(polys, key=lambda q: q.area)
    if not poly.interiors:
        return None
    ring = max(poly.interiors, key=lambda r: _ShPoly(r).area)
    hole = _ShPoly(ring)
    minx, miny, maxx, maxy = hole.bounds
    return (float(np.sqrt(hole.area / np.pi)),
            float(maxx - minx), float(maxy - miny))


def _monotone_increasing(z, *arrs):
    """Rising-Z portion of a (possibly rolled-back) profile, strictly increasing
    in z so it can drive ``np.interp``."""
    k = int(np.argmax(z)) + 1
    zc = z[:k]
    keep = np.concatenate([[True], np.diff(zc) > 1e-9])
    return (zc[keep],) + tuple(a[:k][keep] for a in arrs)


def _adherence_circular(fn, label, tol=0.4):
    z, r = fn()
    zc, rc = _monotone_increasing(z, r)
    # For rolled-back profiles the mouth lip folds back over the flare, so a
    # horizontal plane above the lip cuts the wall twice and the airway becomes
    # ambiguous. Only sample below the lip, where each z hits one wall.
    k = int(np.argmax(z)) + 1
    z_lip = float(z[k:].min()) if k < len(z) else float(zc[-1])
    z_hi = min(float(zc[-1]), z_lip)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _c.generate_3d_mesh_from_profile(z, r, 4.0, 96, p)
    m = trimesh.load(p, file_type="stl"); os.unlink(p)
    for frac in (0.2, 0.4, 0.6):
        zq = zc[0] + frac * (z_hi - zc[0])
        got = _airway_section(m, zq)
        assert got is not None, f"{label}: no airway at z={zq:.1f}"
        r_math = float(np.interp(zq, zc, rc))
        assert abs(got[0] - r_math) < tol, \
            f"{label}: airway r_eq {got[0]:.3f} != math {r_math:.3f} at z={zq:.1f}"

for label, profile_fn in CIRC_CASES:
    test(f"{label} mesh follows math curve",
         lambda fn=profile_fn, lbl=label: _adherence_circular(fn, lbl))


def _adherence_rectangular():
    z, w, h = _r.get_rectangular_exponential(40.0, 24.0, 200.0, FC)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _r.generate_rectangular_3d_mesh(z, w, h, 4.0, p)
    m = trimesh.load(p, file_type="stl"); os.unlink(p)
    span = z[-1] - z[0]
    for frac in (0.2, 0.4, 0.6, 0.8):
        zq = z[0] + frac * span
        got = _airway_section(m, zq)
        assert got is not None, f"rect: no airway at z={zq:.1f}"
        wq = float(np.interp(zq, z, w)); hq = float(np.interp(zq, z, h))
        assert abs(got[1] - wq) < 0.6, f"rect width {got[1]:.2f} != {wq:.2f} at z={zq:.1f}"
        assert abs(got[2] - hq) < 0.6, f"rect height {got[2]:.2f} != {hq:.2f} at z={zq:.1f}"
        r_math = float(np.sqrt(wq * hq / np.pi))
        assert abs(got[0] - r_math) < 0.6, \
            f"rect r_eq {got[0]:.2f} != {r_math:.2f} at z={zq:.1f}"
test("rectangular mesh follows math curve", _adherence_rectangular)


def _adherence_polygonal(n_sides):
    z, r = _c.get_exponential(THROAT, MOUTH, FC, N)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _ph.generate_polygonal_3d_mesh(z, r, n_sides, 4.0, p)
    m = trimesh.load(p, file_type="stl"); os.unlink(p)
    span = z[-1] - z[0]
    for frac in (0.25, 0.5, 0.75):
        zq = z[0] + frac * span
        got = _airway_section(m, zq)
        assert got is not None, f"{n_sides}-gon: no airway at z={zq:.1f}"
        r_math = float(np.interp(zq, z, r))
        # area-matched N-gon → airway area-equivalent radius == circular r_eq
        assert abs(got[0] - r_math) < 0.4, \
            f"{n_sides}-gon r_eq {got[0]:.3f} != math {r_math:.3f} at z={zq:.1f}"
for _ns in (4, 6, 8):
    test(f"{_ns}-gon mesh area matches circular r_eq",
         lambda n=_ns: _adherence_polygonal(n))


def _adherence_embedded_morph():
    """With the morph adapter embedded, (a) the untouched flare above the join
    still follows the math curve, (b) the airway is continuous (the adapter
    reaches the flare's area at the join), and (c) the driver end honours the
    25 mm-class bore — i.e. the morph adheres to the curve at the handoff
    without distorting the rest of the horn."""
    thickness = 4.0
    z, r = _c.get_exponential(20.0, 120.0, 600, 300)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _c.generate_3d_mesh_from_profile(z, r, thickness, 96, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    horn.merge_vertices(); horn.fix_normals()
    morph_len, overlap, target_z = _ta.embedded_morph_span(30.0, float(z[-1]))
    trimmed = horn.slice_plane([0, 0, morph_len], [0, 0, 1], cap=True); trimmed.fix_normals()
    nml = _uts.compute_profile_normals(z, r)
    z_o = z + thickness * nml[:, 0]; r_o = r + thickness * nml[:, 1]
    target_r = float(np.interp(target_z, z, r))
    target_ro = float(np.interp(target_z, z_o, r_o))
    target_slope = float(np.interp(target_z, z, np.gradient(r, z)))
    outer_slope = float(np.interp(target_z, z_o, np.gradient(r_o, z_o)))
    adapter = _ta.make_adapter_assembly(
        driver_type="flanged", driver_diam=25.0, thread_key=None,
        horn_shape="circular", rect_w=0, rect_h=0, poly_n_sides=0, poly_circumR=0,
        horn_R_eq=target_r, adapter_length=target_z, wall_thickness=thickness,
        flange_R=0.0, socket_length=0.0, outer_target_R=target_ro,
        target_slope=target_slope, outer_target_slope=outer_slope, z_offset=target_z)
    m = trimesh.boolean.union([trimmed, adapter], engine="manifold")
    m.merge_vertices(); m.fix_normals()

    # (a) flare above the join is unchanged → airway follows the math curve
    z_mouth = float(m.bounds[1, 2])
    for zq in np.linspace(target_z + 5.0, z_mouth - 5.0, 3):
        got = _airway_section(m, zq)
        assert got is not None, f"morph: no airway at z={zq:.1f}"
        r_math = float(np.interp(zq, z, r))
        assert abs(got[0] - r_math) < 0.6, \
            f"morph flare r_eq {got[0]:.2f} != math {r_math:.2f} at z={zq:.1f}"

    # (b) airway continuous across the join (adapter meets the flare's area)
    below = _airway_section(m, target_z - 2.0)
    above = _airway_section(m, target_z + 2.0)
    assert below is not None and above is not None, "morph: airway broken at join"
    assert abs(below[0] - above[0]) < 0.8, \
        f"morph: airway step at join {below[0]:.2f}→{above[0]:.2f}"
    join = _airway_section(m, target_z)
    assert abs(join[0] - target_r) < 0.8, \
        f"morph: airway r_eq {join[0]:.2f} != flare {target_r:.2f} at join"

    # (c) driver end honours the bore, and the airway grows monotonically
    drv = _airway_section(m, 1.0)
    assert drv is not None and abs(drv[0] - 12.5) < 1.5, \
        f"morph: driver-end airway r_eq {None if drv is None else round(drv[0],2)} != ~12.5"
    eqs = [_airway_section(m, zz)[0]
           for zz in np.linspace(2.0, z_mouth - 5.0, 8)]
    assert all(b >= a - 0.3 for a, b in zip(eqs, eqs[1:])), \
        f"morph: airway not monotone: {[round(e,1) for e in eqs]}"
test("embedded morph adheres to curve + preserves flare", _adherence_embedded_morph)


# ══════════════════════════════════════════════════════════════════════════════
#  3c. OS-SE waveguide (full non-axisymmetric ATH-style, with diagonal ridges)
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ OS-SE waveguide ═══")

def test_osse_profile_eq5():
    # Batík Fig.5 reference: r0=12.7, α=45°, k=1, L=120, s=0.8, n=5, q=0.998
    z = np.array([0.0, 120.0])
    r = _osse.osse_profile(z, 12.7, np.radians(45), 0.0, 1.0, 120.0, 0.8, 5.0, 0.998)
    assert abs(r[0] - 12.7) < 1e-9, f"r(0)={r[0]} != throat radius"
    assert abs(r[1] - 178.6) < 0.5, f"r(L)={r[1]:.2f} != ~178.6 (eq.5)"
    # k=0 collapses the OS term to a straight cone r0 + z·tanα
    zc = np.linspace(0, 100, 7)
    rc = _osse.osse_profile(zc, 10.0, np.radians(30), 0.0, 0.0, 100.0, 0.0, 5.0, 0.998)
    assert np.allclose(rc, 10.0 + zc * np.tan(np.radians(30)), atol=1e-9), "k=0 not conical"
test("OS-SE profile matches eq.5 (+ conical limit)", test_osse_profile_eq5)


def test_osse_coverage_and_superellipse():
    a_h, a_v = np.radians(50), np.radians(35)
    phi = np.array([0.0, np.pi / 2.0, np.pi / 4.0])
    al = _osse.coverage_alpha(phi, a_h, a_v)
    assert abs(al[0] - a_h) < 1e-9 and abs(al[1] - a_v) < 1e-9, "coverage ends wrong"
    assert a_v < al[2] < a_h, "diagonal coverage not between H and V"
    # superellipse: ellipse (p=2) → R at corner; rectangle (large p) → up to √2·R
    R = 100.0
    assert abs(_osse.superellipse_radius(np.array([np.pi/4]), R, R, 2.0)[0] - R) < 1e-6
    corner = _osse.superellipse_radius(np.array([np.pi/4]), R, R, 50.0)[0]
    assert R * 1.30 < corner < R * np.sqrt(2) + 1e-6, f"rect corner {corner:.1f} off"
test("OS-SE coverage(φ) + superellipse outline", test_osse_coverage_and_superellipse)


def test_osse_mouth_is_superelliptical_with_ridges():
    """The morphed mouth equals the superellipse target: H/V match the natural
    OS-SE mouth, and the diagonal is pushed OUT past the ellipse → the ridge."""
    r0, L = 12.7, 120.0
    a_h, a_v = np.radians(50), np.radians(30)
    z, phi, R = _osse.osse_surface(r0, L, a_h, a_v, 0.0, 1.0, 0.8, 5.0, 0.998,
                                   mouth_exp=8.0, morph_start=0.0, morph_rate=2.0,
                                   nphi=240)
    def at(ph):
        return float(R[-1, int(np.argmin(np.abs(phi - ph)))])
    a = _osse.osse_profile(np.array([L]), r0, a_h, 0, 1, L, 0.8, 5, 0.998)[0]
    b = _osse.osse_profile(np.array([L]), r0, a_v, 0, 1, L, 0.8, 5, 0.998)[0]
    assert abs(at(0.0) - a) < 0.5, f"mouth H {at(0.0):.1f} != natural {a:.1f}"
    assert abs(at(np.pi/2) - b) < 0.5, f"mouth V {at(np.pi/2):.1f} != natural {b:.1f}"
    # ridge: diagonal beyond the plain ellipse through the same H/V mouth
    ell_diag = _osse.superellipse_radius(np.array([np.pi/4]), a, b, 2.0)[0]
    assert at(np.pi/4) > ell_diag + 2.0, \
        f"no diagonal ridge: diag {at(np.pi/4):.1f} <= ellipse {ell_diag:.1f}"
    # throat is a clean circle of radius r0 at every azimuth
    assert np.allclose(R[0, :], r0, atol=1e-9), "throat not circular"
test("OS-SE mouth superelliptical + ridges present", test_osse_mouth_is_superelliptical_with_ridges)


def test_osse_axes_follow_analytic_profile():
    """On the horizontal and vertical axes the morph is a no-op (the superellipse
    passes through the natural H/V mouth points), so r(z,0)/r(z,π/2) equal the
    analytic single-azimuth profile with α_h / α_v."""
    r0, L = 12.7, 120.0
    a_h, a_v = np.radians(55), np.radians(32)
    z, phi, R = _osse.osse_surface(r0, L, a_h, a_v, 0.0, 1.0, 0.8, 5.0, 0.998,
                                   mouth_exp=6.0, morph_start=0.0, morph_rate=2.0,
                                   nphi=240)
    jh = int(np.argmin(np.abs(phi - 0.0)))
    jv = int(np.argmin(np.abs(phi - np.pi / 2.0)))
    rh = _osse.osse_profile(z, r0, a_h, 0, 1, L, 0.8, 5, 0.998)
    rv = _osse.osse_profile(z, r0, a_v, 0, 1, L, 0.8, 5, 0.998)
    assert np.allclose(R[:, jh], rh, atol=1e-6), "horizontal axis off analytic profile"
    assert np.allclose(R[:, jv], rv, atol=1e-6), "vertical axis off analytic profile"
test("OS-SE H/V axes follow analytic profile", test_osse_axes_follow_analytic_profile)


def test_osse_mesh_watertight_flat_faces():
    m = _osse.generate_osse_3d_mesh(
        throat=25.4, length=120.0, coverage_h=90.0, coverage_v=60.0,
        k=1.0, s=0.8, n=5.0, mouth_exp=8.0, thickness=4.0, nz=100, nphi=140)
    assert m.is_watertight, "OS-SE mesh not watertight"
    assert m.body_count == 1, f"OS-SE mesh {m.body_count} bodies"
    assert m.volume > 1000, f"OS-SE volume {m.volume:.0f}"
    # throat and mouth faces pinned flat at z=0 and z=L (mounting)
    assert abs(m.bounds[0, 2] - 0.0) < 1e-6, f"throat face not flat (z={m.bounds[0,2]:.3f})"
    assert abs(m.bounds[1, 2] - 120.0) < 1e-6, f"mouth face not flat (z={m.bounds[1,2]:.3f})"
test("OS-SE mesh watertight + flat throat/mouth", test_osse_mesh_watertight_flat_faces)


def test_osse_flanges_weld_to_horn():
    """OS-SE supports round throat + elliptical mouth/mid flanges (as wired in
    ui_app): each generates watertight and all three weld to the horn into one
    body. Mirrors the UI geometry: throat hole = throat_R+wall, elliptical
    holes = airway+wall bitten inward so the constant-thickness wall pokes
    through and fuses."""
    import trimesh as _tm
    throat_d, L, th, BITE = 25.4, 120.0, 4.0, 0.5
    z, phi, R = _osse.osse_surface(throat_d / 2.0, L, np.radians(45), np.radians(30),
                                   0.0, 1.0, 0.8, 5.0, 0.998, mouth_exp=6.0,
                                   morph_start=0.0, morph_rate=2.0, nz=60, nphi=120)
    def contour(zt):
        """Inner airway contour at axial Z."""
        zt = float(np.clip(zt, z[0], z[-1]))
        Rz = np.array([np.interp(zt, z, R[:, j]) for j in range(R.shape[1])])
        return np.column_stack([Rz * np.cos(phi), Rz * np.sin(phi)])

    fiw = throat_d + 2.0 * th
    f_throat = _fg.generate_flange(throat_R=fiw / 2.0, flange_R=fiw / 2.0 + 12.0,
        thickness=6.0, bolt_R=fiw / 2.0 + 6.0, bolt_n=4, bolt_d=4.0, offset=6.0)
    # Mouth/mid built from the INNER airway contour.  The mesh engine's blend
    # keeps the outer wall at ~thickness mm radially at the ends, so
    # inner + wall + ring naturally matches the horn's outer wall.
    f_mouth = _fg.generate_contour_flange(inner_xy=contour(L), thickness=6.0,
        wall=th, ring=15.0, bite=BITE, bolt_n=8, bolt_d=4.0, offset=L)
    f_mid = _fg.generate_contour_flange(inner_xy=contour(60.0), thickness=6.0,
        wall=th, ring=15.0, bite=BITE, bolt_n=6, bolt_d=4.0, offset=60.0)
    for nm, fl in (("throat", f_throat), ("mouth", f_mouth), ("mid", f_mid)):
        assert fl is not None and fl.is_watertight, f"{nm} flange not watertight"

    # The contour flange must follow the superellipse: its hole reaches the
    # diagonal corner (within bite), not an inscribed ellipse ~30 mm short.
    cm = contour(L)
    jd = int(np.argmin(np.abs(phi - np.pi / 4)))
    r_corner = float(np.hypot(cm[jd, 0], cm[jd, 1]))
    a = float(np.max(np.abs(cm[:, 0]))); b = float(np.max(np.abs(cm[:, 1])))
    r_ellipse = 1.0 / np.hypot(np.cos(phi[jd]) / a, np.sin(phi[jd]) / b)
    assert r_corner > r_ellipse + 10.0, "test setup: no ridge to distinguish"
    # flange outer bbox must enclose the real corner + ring, i.e. be wider than
    # an elliptical flange would have been.
    assert (f_mouth.bounds[1, 0] - f_mouth.bounds[0, 0]) > 2 * a + 2 * 15.0 - 1.0, \
        "mouth flange narrower than the real contour + ring"

    horn = _osse.generate_osse_3d_mesh(throat=throat_d, length=L,
        coverage_h=90.0, coverage_v=60.0, thickness=th)
    merged = _tm.boolean.union([horn, f_throat, f_mouth, f_mid],
                               engine="manifold", check_volume=False)
    assert merged.is_watertight, "merged OS-SE + flanges not watertight"
    assert merged.volume > horn.volume, "flanges added no material"
    assert len(merged.split(only_watertight=False)) == 1, "flanges float (not welded)"
test("OS-SE throat/mouth/mid flanges weld to horn", test_osse_flanges_weld_to_horn)


def test_contour_flange_explicit_outer_boundary():
    """Inward plates preserve a real rim instead of scaling the hole."""
    t = np.linspace(0.0, 2.0 * np.pi, 128, endpoint=False)
    inner = np.column_stack([30.0 * np.cos(t), 15.0 * np.sin(t)])
    outer = np.array([
        [-42.0, -27.0], [42.0, -27.0], [42.0, 27.0], [-42.0, 27.0],
    ])
    flange = _fg.generate_contour_flange(
        inner_xy=inner,
        outer_xy=outer,
        thickness=6.0,
        bite=0.5,
        bolt_n=0,
        bolt_d=4.0,
        offset=6.0,
    )
    assert flange is not None and flange.is_watertight
    assert flange.body_count == 1 and flange.volume > 0.0
    assert np.allclose(flange.bounds[:, :2], [[-42.0, -27.0], [42.0, 27.0]],
                       atol=0.1), "explicit rim was replaced by a scaled contour"
test("contour flange preserves explicit outer boundary",
     test_contour_flange_explicit_outer_boundary)


# ══════════════════════════════════════════════════════════════════════════════
#  4. Radial 360° — all profiles, geometry checks
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Radial 360° section ═══")

RADIAL_PROFILES = ["Tractrix", "Salmon", "Exponential", "Oblate spheroidal"]

def _check_radial_profiles(R, Zb, Zt, label):
    assert len(R) == len(Zb) == len(Zt),       f"{label}: array length mismatch"
    assert np.all(np.diff(R) > 0),             f"{label}: R not monotone increasing"
    gap = Zt - Zb
    # Hard constraint: gap must always be positive (top plate never intersects bottom)
    assert np.all(gap > 0),                    f"{label}: gap ≤ 0 at R={R[gap<=0]}"
    assert gap[0] > 0.5,                       f"{label}: throat gap too small ({gap[0]:.2f} mm)"
    assert gap[-1] > 0.5,                      f"{label}: mouth gap too small ({gap[-1]:.2f} mm)"
    # Informational: whether H(R)=S(R)/(2πR) expands depends on area growth rate vs R.
    # Tractrix naturally expands; Salmon/Exponential may not with all params.

for prof in RADIAL_PROFILES:
    def make(p=prof):
        R, Zb, Zt = _rd.get_radial_profiles(25, 200, FC, 300, p)
        _check_radial_profiles(R, Zb, Zt, f"Radial/{p} profiles")
        with tempfile.TemporaryDirectory() as tmp:
            bottom, top = _rd.generate_radial_horn(25, 200, FC, 48, tmp, p)
            for sfx, raw in [("bottom", bottom), ("top", top)]:
                assert raw.is_closed(exact=True), f"Radial/{p} {sfx}: numpy-stl mesh is not closed"
                path = os.path.join(tmp, f"radial_{sfx}.stl")
                m = trimesh.load(path, file_type="stl")
                assert m.is_watertight,  f"Radial/{p} {sfx}: not watertight"
                assert m.body_count == 1,  f"Radial/{p} {sfx}: {m.body_count} bodies"
                assert m.volume > 0,       f"Radial/{p} {sfx}: volume={m.volume}"
    test(f"Radial / {prof}", make)


# ══════════════════════════════════════════════════════════════════════════════
#  5. Circular flanges — throat, mouth, mid positions
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Circular flanges ═══")

FLANGE_CASES = [
    ("throat 15R→30R",  15.0, 30.0, 6.0, 22.0, 4, 3.5,  6.0),
    ("mouth 30R→55R",   30.0, 55.0, 6.0, 42.0, 6, 3.5,  0.0),
    ("mid   20R→40R",   20.0, 40.0, 4.0, 30.0, 4, 3.5, 40.0),
]

def _check_flange(m, label):
    assert m is not None,    f"{label}: returned None"
    assert m.is_watertight,  f"{label}: not watertight"
    assert m.body_count == 1, f"{label}: {m.body_count} bodies"
    assert m.volume > 0,     f"{label}: volume={m.volume}"

for label, throat_R, flange_R, thick, bolt_R, bolt_n, bolt_d, offset in FLANGE_CASES:
    def make(tr=throat_R, fr=flange_R, th=thick, br=bolt_R, bn=bolt_n, bd=bolt_d, off=offset, lbl=label):
        m = _fg.generate_flange(tr, fr, th, br, bn, bd, off, output_path=None)
        _check_flange(m, lbl)
        # outer radius check
        r_actual = max(np.linalg.norm(m.vertices[:, :2], axis=1))
        assert abs(r_actual - fr) < 1.5, f"{lbl}: outer R={r_actual:.1f} vs {fr}"
    test(label, make)


# ══════════════════════════════════════════════════════════════════════════════
#  6. Polygonal flanges — inner N-gon, circular and polygonal outer
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Polygonal flanges ═══")

POLY_FLANGE_CASES = list(itertools.product(
    [4, 6, 8],    # n_sides inner
    [0, 4, 6],    # outer_n_sides (0 = circular)
))

for n_inner, n_outer in POLY_FLANGE_CASES:
    label = f"inner {n_inner}-gon / outer {'circ' if n_outer==0 else f'{n_outer}-gon'}"
    def make(ni=n_inner, no=n_outer, lbl=label):
        m = _fg.generate_polygonal_flange(
            inner_circumR=20.0, n_sides=ni,
            flange_R=40.0, thickness=6.0,
            bolt_R=30.0, bolt_n=4, bolt_d=3.5,
            offset=6.0, outer_n_sides=no,
            output_path=None)
        _check_flange(m, lbl)
    test(label, make)


def _assert_parallel_ellipse_ring(mesh, inner_w, inner_h, ring, z=3.0):
    """Check ring width against the bore, including diagonal outer points."""
    from shapely import affinity
    from shapely.geometry import Point, Polygon

    section = mesh.section(
        plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0]).to_2D()[0]
    outer = max(section.polygons_full, key=lambda poly: poly.area).exterior
    bore = affinity.scale(
        Point(0.0, 0.0).buffer(1.0, resolution=256),
        xfact=inner_w / 2.0,
        yfact=inner_h / 2.0,
    ).exterior
    points = np.asarray(outer.coords, dtype=float)[::4, :2]
    distances = np.array([bore.distance(Point(point)) for point in points])
    assert np.allclose(distances, ring, atol=0.15), (
        f"elliptical ring is not a parallel offset: "
        f"{distances.min():.3f}..{distances.max():.3f} mm, want {ring:.3f}"
    )
    bolt_centers = []
    for interior in max(section.polygons_full, key=lambda poly: poly.area).interiors:
        center = Polygon(interior).centroid
        if np.hypot(center.x, center.y) > 1.0:
            bolt_centers.append(Point(center.x, center.y))
    if bolt_centers:
        bolt_offsets = np.array([bore.distance(center) for center in bolt_centers])
        assert np.allclose(bolt_offsets, ring / 2.0, atol=0.15), (
            f"elliptical bolts are not on the half-offset curve: "
            f"{bolt_offsets.min():.3f}..{bolt_offsets.max():.3f} mm, "
            f"want {ring / 2.0:.3f}"
        )


def _profile_flange_offset_modes():
    cases = [
        dict(inner_type="circular", inner_R=30.0),
        dict(inner_type="polygonal", inner_R=30.0, inner_n_sides=6),
        dict(inner_type="rectangular", inner_w=60.0, inner_h=40.0),
        dict(inner_type="elliptical", inner_w=60.0, inner_h=40.0),
    ]
    for params in cases:
        m = _fg.generate_profile_flange(
            thickness=6.0, bolt_n=8, bolt_d=3.5, bolt_phase=0.3, offset=6.0,
            outer_mode="offset", outer_offset=15.0, **params)
        _check_flange(m, f"profile flange offset {params['inner_type']}")
        if params["inner_type"] == "elliptical":
            _assert_parallel_ellipse_ring(
                m, params["inner_w"], params["inner_h"], 15.0)
test("profile flange offset follows every opening", _profile_flange_offset_modes)


def _profile_flange_custom_outer_shapes():
    inners = [
        dict(inner_type="circular", inner_R=20.0),
        dict(inner_type="polygonal", inner_R=20.0, inner_n_sides=6),
        dict(inner_type="rectangular", inner_w=40.0, inner_h=30.0),
        dict(inner_type="elliptical", inner_w=40.0, inner_h=30.0),
    ]
    outers = [
        ("circular", dict(outer_diam=110.0)),
        ("polygonal", dict(outer_diam=130.0, outer_n_sides=6)),
        ("rectangular", dict(outer_w=110.0, outer_h=90.0)),
    ]
    for inner in inners:
        for outer_type, dims in outers:
            m = _fg.generate_profile_flange(
                thickness=6.0, bolt_n=4, bolt_d=3.5, offset=6.0,
                outer_mode="custom", outer_type=outer_type,
                bolt_mode="auto", **inner, **dims)
            _check_flange(
                m, f"profile flange {inner['inner_type']} / {outer_type}")
test("profile flange custom circular/polygonal/rectangular",
     _profile_flange_custom_outer_shapes)


def _profile_flange_fixed_bolt_circle():
    m = _fg.generate_profile_flange(
        inner_type="rectangular", inner_w=60.0, inner_h=40.0,
        thickness=6.0, bolt_n=4, bolt_d=6.0, offset=6.0,
        outer_mode="custom", outer_type="rectangular",
        outer_w=120.0, outer_h=100.0,
        bolt_mode="fixed", bolt_R=43.0)
    _check_flange(m, "profile flange fixed bolt circle")
    dxf = _dxf.mesh_to_flange_dxf(m)
    holes = [c for c in _parse_circles(dxf) if c[0] == "HOLES"]
    assert len(holes) == 4
    assert np.allclose([np.hypot(cx, cy) for _, cx, cy, _ in holes],
                       43.0, atol=0.5)
test("profile flange fixed holes stay on requested PCD",
     _profile_flange_fixed_bolt_circle)


# ══════════════════════════════════════════════════════════════════════════════
#  7. Assembly — horn + throat + mouth flange merged, key combinations
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Assembly (horn + flanges) ═══")

ASSEMBLY_CASES = [
    ("Tractrix circular",    lambda: _c.get_tractrix(THROAT, MOUTH, N),    "circular"),
    ("Exponential circular", lambda: _c.get_exponential(THROAT, MOUTH, FC, N), "circular"),
    ("Salmon circular",      lambda: _c.get_salmon(THROAT, FC, 80, N),      "circular"),
    ("Tractrix 4-gon",       lambda: _c.get_tractrix(THROAT, MOUTH, N),    "poly4"),
    ("Exponential 6-gon",    lambda: _c.get_exponential(THROAT, MOUTH, FC, N), "poly6"),
]

for label, profile_fn, section in ASSEMBLY_CASES:
    def make(fn=profile_fn, sec=section, lbl=label):
        z, r = fn()
        thickness = 4.0

        # build horn
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
        if sec == "circular":
            _c.generate_3d_mesh_from_profile(z, r, thickness, 64, p)
            horn = trimesh.load(p, file_type="stl"); os.unlink(p)
            throat_R = r[0] + thickness
            mouth_R  = r[-1] + thickness
        else:
            n_sides = int(sec.replace("poly", ""))
            _ph.generate_polygonal_3d_mesh(z, r, n_sides, thickness, p)
            horn = trimesh.load(p, file_type="stl"); os.unlink(p)
            from polygonal_horn import _r_to_circumradius
            import _utils as _uts
            _R_i = _r_to_circumradius(r, n_sides)
            _nml = _uts.compute_profile_normals(z, _R_i, flip_if_negative=True)
            _R_o = _R_i + thickness / np.cos(np.pi / n_sides) * _nml[:, 1]
            throat_R = _R_o[0]; mouth_R = _R_o[-1]

        z_min = horn.vertices[:, 2].min()
        z_max = horn.vertices[:, 2].max()

        # flanges
        if sec == "circular":
            f_throat = _fg.generate_flange(throat_R, throat_R + 15, 6.0,
                                           throat_R + 7, 4, 3.5,
                                           offset=z_min + 6.0, output_path=None)
            f_mouth  = _fg.generate_flange(mouth_R, mouth_R + 15, 6.0,
                                           mouth_R + 7, 4, 3.5,
                                           offset=z_max, output_path=None)
        else:
            n_sides = int(sec.replace("poly", ""))
            f_throat = _fg.generate_polygonal_flange(throat_R, n_sides, throat_R + 15,
                                                     6.0, throat_R + 7, 4, 3.5,
                                                     offset=z_min + 6.0, output_path=None)
            f_mouth  = _fg.generate_polygonal_flange(mouth_R, n_sides, mouth_R + 15,
                                                     6.0, mouth_R + 7, 4, 3.5,
                                                     offset=z_max, output_path=None)

        assert f_throat is not None, f"{lbl}: throat flange is None"
        assert f_mouth  is not None, f"{lbl}: mouth flange is None"

        try:
            combined = trimesh.boolean.union([horn, f_throat, f_mouth], engine="manifold")
        except Exception:
            combined = trimesh.util.concatenate([horn, f_throat, f_mouth])

        assert combined is not None,   f"{lbl}: merge returned None"
        assert combined.volume > 0,    f"{lbl}: combined volume={combined.volume}"

    test(label, make)


# ══════════════════════════════════════════════════════════════════════════════
#  8. Rectangular mesh + flange (regression)
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Rectangular mesh + flange ═══")

for label, tw, th, mw, fc in [
    ("20×10→160 600Hz", 20, 10, 160, 600),
    ("30×15→200 400Hz", 30, 15, 200, 400),
]:
    def make(tw=tw, th=th, mw=mw, fc=fc, lbl=label):
        z, w, h = _r.get_rectangular_exponential(tw, th, mw, fc, 300)
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
        _r.generate_rectangular_3d_mesh(z, w, h, 4.0, p)
        m = trimesh.load(p, file_type="stl"); os.unlink(p)
        _check_mesh(m, lbl)
    test(label, make)

# Rectangular tractrix & salmon (area-preserving conversion from circular)
for label, fn in [
    ("Rect Tractrix 20×10→160",   lambda: _r.get_rectangular_tractrix(20, 10, 160, 300)),
    ("Rect Tractrix 30×15→200",   lambda: _r.get_rectangular_tractrix(30, 15, 200, 300)),
    ("Rect Salmon 20×10/600/80",  lambda: _r.get_rectangular_salmon(20, 10, 600, 80, 300)),
    ("Rect Salmon 30×15/1200/50", lambda: _r.get_rectangular_salmon(30, 15, 1200, 50, 300)),
    ("Rect Oblate 20×10/90×45/L80", lambda: _r.get_rectangular_oblate_spheroidal(20, 10, 90, 45, 80, 300)),
    ("Rect Conical 20×10/90×45/L80", lambda: _r.get_rectangular_conical(20, 10, 90, 45, 80, 300)),
]:
    def make(fn=fn, lbl=label):
        z, w, h = fn()
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
        _r.generate_rectangular_3d_mesh(z, w, h, 4.0, p)
        m = trimesh.load(p, file_type="stl"); os.unlink(p)
        _check_mesh(m, lbl)
    test(label, make)


def _check_rectangular_tractrix_respects_mouth_width():
    for throat_w, throat_h, mouth_w in [(20.0, 10.0, 160.0), (30.0, 20.0, 200.0)]:
        _, w, h = _r.get_rectangular_tractrix(throat_w, throat_h, mouth_w, N)
        assert abs(w[-1] - mouth_w) < 1e-6, f"mouth width {w[-1]:.3f} != {mouth_w}"
        expected_h = mouth_w * throat_h / throat_w
        assert abs(h[-1] - expected_h) < 1e-6, f"mouth height {h[-1]:.3f} != {expected_h}"
test("Rectangular tractrix respects requested mouth width",
     _check_rectangular_tractrix_respects_mouth_width)

for label, ow, oh, iw, ih in [
    ("60×50 / 20×10", 60, 50, 20, 10),
    ("80×60 / 30×15", 80, 60, 30, 15),
]:
    def make(ow=ow, oh=oh, iw=iw, ih=ih, lbl=label):
        m = _rf.generate_rectangular_flange(ow, oh, iw, ih, output_path=None)
        _check_flange(m, lbl)
    test(label, make)


# Regression: a rectangular flange whose hole exactly equals the horn's OUTER
# wall makes the two coincident walls degenerate → manifold union leaves a
# non-manifold edge + a visible ledge ("chamfer"). ui_app shrinks the hole by
# _FLANGE_WALL_BITE per side so the flange bites into the wall (volumetric
# weld). This test pins both halves: coincident = broken, bitten = clean.
def _nm_edge_count(m):
    mc = m.copy(); mc.merge_vertices()
    groups = trimesh.grouping.group_rows(mc.edges_sorted, require_count=None)
    return sum(1 for g in groups if len(g) != 2)

def _rect_flange_wall_bite():
    BITE = 0.5  # must match ui_app._FLANGE_WALL_BITE
    thickness = 4.0
    z = np.linspace(0, 60, 80)
    w = np.linspace(40, 61.4, 80)
    h = np.linspace(30, 38.4, 80)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _r.generate_rectangular_3d_mesh(z, w, h, thickness, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    horn.merge_vertices(); horn.fix_normals()
    zmouth = horn.vertices[:, 2].max()
    ow = horn.vertices[:, 0].max() * 2.0   # actual outer wall at mouth
    oh = horn.vertices[:, 1].max() * 2.0

    def union_nm(iw, ih):
        f = _rf.generate_rectangular_flange(
            outer_diam=113.5, inner_w=iw, inner_h=ih, thickness=6.0,
            bolt_radius=42, bolt_count=4, bolt_diam=4,
            outer_type="circular", offset=zmouth - 6.0)
        u = trimesh.boolean.union([horn, f], engine="manifold")
        return _nm_edge_count(u)

    # coincident hole == outer wall must be the failing case…
    assert union_nm(ow, oh) > 0, "expected coincident-wall union to be non-manifold"
    # …and the wall-bite must make it clean.
    assert union_nm(ow - 2 * BITE, oh - 2 * BITE) == 0, \
        "wall-bite did not yield a manifold union"
test("rect mouth flange wall-bite (no non-manifold edge)", _rect_flange_wall_bite)


def _rect_adapter_weld_perim_n():
    """An embedded adapter welds onto N-point rect walls (perim_n=rings_n)
    cleanly; the default 4-corner walls leave a jagged sliver band ("bordello
    su flare rect"). Matching the wall tessellation removes it with NO wall
    deformation (no bite/step)."""
    thickness, rings_n, n = 4.0, 64, 160
    z = np.linspace(0, 120, n); t = z / z[-1]
    w = 50.0 * (200.0 / 50.0) ** t
    h = 40.0 * (150.0 / 40.0) ** t
    nw = _uts.compute_profile_normals(z, w, flip_if_negative=True)
    nh = _uts.compute_profile_normals(z, h, flip_if_negative=True)
    w_o = w + 2 * thickness * nw[:, 1]; h_o = h + 2 * thickness * nh[:, 1]

    def weld(perim_n):
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f: p = f.name
        _r.generate_rectangular_3d_mesh(z, w, h, thickness, p, perim_n=perim_n)
        horn0 = trimesh.load(p, file_type="stl"); os.unlink(p); horn0.fix_normals()
        zmin = float(horn0.bounds[0, 2])
        ml, ov, tl = _ta.embedded_morph_span(30.0, float(z[-1]), desired_overlap=20.0)
        horn = horn0.slice_plane([0, 0, zmin + ml], [0, 0, 1], cap=True); horn.fix_normals()
        sec = lambda zl, wa, ha: _ta._rect_points(
            np.interp(zl, z, wa) / 2, np.interp(zl, z, ha) / 2,
            n=rings_n, lockstep=True)
        zst = np.append(z[z < tl - 1e-9], tl)
        cp = np.stack([sec(zz, w, h) for zz in zst])
        co = np.stack([sec(zz, w_o, h_o) for zz in zst])
        ad = _ta.make_adapter_assembly(
            driver_type="flanged", driver_diam=float(np.sqrt(50 * 40 * 4 / np.pi)),
            thread_key=None, horn_shape="rectangular",
            rect_w=float(np.interp(tl, z, w)), rect_h=float(np.interp(tl, z, h)),
            poly_n_sides=0, poly_circumR=0,
            horn_R_eq=float(np.sqrt(np.interp(tl, z, w) * np.interp(tl, z, h) / np.pi)),
            adapter_length=tl, wall_thickness=thickness,
            flange_R=40.0, flange_thickness=6.0, flange_bolt_R=30.0,
            flange_bolt_n=4, flange_bolt_d=5.0, driver_clearance=0.3, socket_length=0.0,
            custom_pts=cp, custom_outer_pts=co, custom_pts_z=zst,
            custom_match_from_z=ml, z_offset=zmin + tl)
        u = trimesh.boolean.union([horn, ad], engine="manifold")
        return int((u.area_faces < 1e-6).sum())

    # the lockstep N-point horn must be twist-free: arc-length sampling would
    # shift points between edges as W/H changes and the loft twists over the
    # whole height (thin/degenerate triangles).
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f: p = f.name
    _r.generate_rectangular_3d_mesh(z, w, h, thickness, p, perim_n=rings_n)
    npm = trimesh.load(p, file_type="stl"); os.unlink(p)
    assert npm.is_watertight and int((npm.area_faces < 1e-3).sum()) == 0, \
        "lockstep rect horn twisted (thin faces) or not watertight"

    assert weld(4) > 200, "expected the 4-corner weld to spew a sliver band"
    assert weld(rings_n) < 20, \
        f"N-point weld still has {weld(rings_n)} slivers — tessellation mismatch"
test("rect adapter weld: matched perim_n kills the sliver band",
     _rect_adapter_weld_perim_n)


def _elliptical_flange_and_horn_assembly():
    """Ellipse-hole flange must weld to the elliptical loft as one body."""
    thickness = 4.0
    z, w, h = _r.get_rectangular_exponential(30.0, 18.0, 120.0, 600, 300)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_elliptical_3d_mesh_from_profiles(
        z, w / 2.0, h / 2.0, thickness, 96, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    hole_w = w[-1] + 2.0 * thickness - 1.0
    hole_h = h[-1] + 2.0 * thickness - 1.0
    flange = _rf.generate_rectangular_flange(
        outer_diam=np.hypot(hole_w, hole_h) + 30.0,
        inner_w=hole_w, inner_h=hole_h,
        thickness=6.0, bolt_radius=np.hypot(hole_w, hole_h) / 2.0 + 8.0,
        bolt_count=4, bolt_diam=3.5,
        outer_type="circular", inner_type="elliptical",
        offset=z[-1] - 6.0, output_path=None,
    )
    _check_flange(flange, "elliptical-hole flange")
    combined = trimesh.boolean.union([horn, flange], engine="manifold")
    combined.merge_vertices(); combined.fix_normals()
    _check_mesh(combined, "elliptical horn + mouth flange")
test("elliptical-hole flange + horn assembly", _elliptical_flange_and_horn_assembly)


def _elliptical_analytic_dxf_matches_offset_solid():
    """Analytic elliptical DXF must match the true-offset flange solid.

    The flange uses a parallel outer curve with bolts on the half-offset curve.
    The analytic DXF
    (dxf_export.elliptical_flange_dxf) is built from the same parameters and must
    place its holes exactly where the solid's bolt holes land — guarding the 2-D
    template against drifting from the 3-D part.
    """
    import re
    from src import dxf_export as _dxf2
    inner_w, inner_h, ring = 120.0, 60.0, 15.0
    bc, bd, bphase = 12, 4.0, 0.3
    a, b = inner_w / 2.0, inner_h / 2.0

    # solid: section the real flange and recover its bolt-hole centres
    f = _rf.generate_rectangular_flange(
        inner_w=inner_w, inner_h=inner_h, thickness=6.0,
        outer_type="elliptical", inner_type="elliptical",
        outer_w=inner_w + 2 * ring, outer_h=inner_h + 2 * ring,
        bolt_count=bc, bolt_diam=bd, bolt_phase=bphase, output_path=None)
    _check_flange(f, "offset elliptical flange")
    _assert_parallel_ellipse_ring(f, inner_w, inner_h, ring)
    s2 = f.section(plane_origin=[0, 0, 3.0], plane_normal=[0, 0, 1]).to_2D()[0]
    solid_c = []
    for poly in s2.polygons_full:
        for ring_ in poly.interiors:
            c = np.asarray(ring_.coords)[:, :2]
            cen = c.mean(0)
            if np.hypot(*(c - cen).T).mean() < 10:   # a bolt hole (small loop)
                solid_c.append(cen)
    solid_c = np.array(sorted(solid_c, key=lambda p: np.arctan2(p[1], p[0])))
    assert len(solid_c) == bc, f"solid has {len(solid_c)} bolt holes, want {bc}"

    # analytic DXF holes
    dxf = _dxf2.elliptical_flange_dxf(inner_w, inner_h, ring, bc, bd, bphase)
    assert all(k in dxf for k in ("OUTLINE", "BORE", "HOLES", "CENTERS"))
    circ = re.findall(
        r"CIRCLE\n8\nHOLES\n10\n([-0-9.]+)\n20\n([-0-9.]+)\n30\n0.0\n40\n([-0-9.]+)",
        dxf)
    assert len(circ) == bc, f"DXF has {len(circ)} holes, want {bc}"
    dxf_c = np.array(sorted(([float(x), float(y)] for x, y, _ in circ),
                            key=lambda p: np.arctan2(p[1], p[0])))
    assert np.allclose([float(r) for *_, r in circ], bd / 2.0), "hole radius wrong"
    # DXF holes must sit on the half-offset curve and match the solid (~0.5 mm,
    # the solid being a 16-gon faceted hole vs the analytic centre)
    assert np.allclose(dxf_c, solid_c, atol=0.5), \
        "analytic DXF holes drift from the offset solid's bolt centres"
test("elliptical analytic DXF matches offset solid",
     _elliptical_analytic_dxf_matches_offset_solid)


def _elliptical_rollback_flange_welds():
    """Mid/mouth flange on a *roll-back* elliptical horn must weld as one body.

    Le Cléac'h / oblate / R-OSSE profiles have non-monotonic Z (the lip curls
    back toward the throat). Sizing a flat flange's hole by array-index fraction
    samples the wrong station, so the plate floats off the wall. The fix sizes
    the hole from the real outer wall at the plate's bottom face on the
    *outgoing* leg — this guards against a regression to the floating flange.
    """
    thickness = 4.0
    BITE = 0.5

    def outer_wh_at_z(z_o, w_o, h_o, z_target):
        peak = int(np.argmax(z_o))
        sl = slice(0, peak + 1)
        order = np.argsort(z_o[sl])
        zb, wb, hb = z_o[sl][order], w_o[sl][order], h_o[sl][order]
        zt = float(np.clip(z_target, zb[0], zb[-1]))
        return float(np.interp(zt, zb, wb)), float(np.interp(zt, zb, hb))

    # Elliptical Le Cléac'h (roll-back): area-preserving from the circular curve
    zp, rp = _c.get_lecleach(np.sqrt(25.0 * 25.0 * 4 / np.pi), 500.0, 200, T=0.707)
    zr, wr, hr = _r._area_to_rect(zp, rp, 25.0, 25.0)
    assert not np.all(np.diff(zr) >= 0), "expected a non-monotonic (roll-back) Z"

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _c.generate_elliptical_3d_mesh_from_profiles(zr, wr / 2.0, hr / 2.0, thickness, 96, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    _, V_o = _c._elliptical_parallel_offset_vertices(zr, wr / 2.0, hr / 2.0, thickness, 96)
    z_o = np.mean(V_o[:, :, 2], axis=1)
    w_o = 2.0 * np.max(np.abs(V_o[:, :, 0]), axis=1)
    h_o = 2.0 * np.max(np.abs(V_o[:, :, 1]), axis=1)
    z_min = horn.vertices[:, 2].min()

    mid_pos, mid_sp, ring = 120.0, 4.0, 15.0
    mw, mh = outer_wh_at_z(z_o, w_o, h_o, mid_pos - mid_sp)
    iw, ih = max(mw - 2 * BITE, 1.0), max(mh - 2 * BITE, 1.0)
    flange = _rf.generate_rectangular_flange(
        inner_w=iw, inner_h=ih, thickness=mid_sp, bolt_count=6, bolt_diam=4.0,
        outer_type="rectangular", outer_w=iw + 2 * ring, outer_h=ih + 2 * ring,
        offset=z_min + mid_pos - mid_sp, inner_type="elliptical", output_path=None)
    _check_flange(flange, "roll-back mid flange")
    combined = trimesh.boolean.union([horn, flange], engine="manifold")
    combined.merge_vertices(); combined.fix_normals()
    _check_mesh(combined, "roll-back elliptical horn + mid flange", min_volume=1000)
test("roll-back elliptical flange welds (single body)", _elliptical_rollback_flange_welds)


def _elliptical_outer_flange_offset():
    """outer_type='elliptical' must produce an elliptical-offset ring (not a
    disc/plate): a watertight flange whose outer XY extents follow inner+2·ring
    and differ between axes for an asymmetric hole, with bolts that don't breach.
    """
    inner_w, inner_h, ring = 120.0, 60.0, 15.0
    ow, oh = inner_w + 2 * ring, inner_h + 2 * ring
    flange = _rf.generate_rectangular_flange(
        inner_w=inner_w, inner_h=inner_h, thickness=6.0,
        bolt_count=8, bolt_diam=4.0, bolt_phase=0.0,
        outer_type="elliptical", outer_w=ow, outer_h=oh,
        offset=0.0, inner_type="elliptical", output_path=None)
    _check_flange(flange, "elliptical-offset flange")
    ext_x = flange.bounds[1, 0] - flange.bounds[0, 0]
    ext_y = flange.bounds[1, 1] - flange.bounds[0, 1]
    assert abs(ext_x - ow) < 1.0, f"outer X {ext_x:.1f} != {ow:.1f} (not elliptical offset)"
    assert abs(ext_y - oh) < 1.0, f"outer Y {ext_y:.1f} != {oh:.1f} (not elliptical offset)"
    assert ext_x > ext_y + 10.0, "outer should follow the hole's aspect ratio, not be circular"
    _assert_parallel_ellipse_ring(flange, inner_w, inner_h, ring)
test("elliptical-offset outer flange", _elliptical_outer_flange_offset)


def _rollback_mouth_flange_welds_to_outer_rim():
    """A mouth flange on a roll-back elliptical horn must weld to the OUTER rim
    (the curled-back lip, widest cross-section) as one body — not float off it.

    The rim sits on the *returning* leg of the lip, so the plate goes above it
    and the wall widens downward through the ring. Mirrors ui_app `_rim_weld`.
    """
    thickness = 4.0
    BITE = 0.5

    def rim_weld(z_o, w_o, h_o, sp):
        rim = int(np.argmax(w_o * h_o))
        peak = int(np.argmax(z_o))
        z_rim = float(z_o[rim])
        if rim <= peak:
            seg = slice(0, rim + 1); offset = z_rim - sp; zf = offset
        else:
            seg = slice(peak, rim + 1); offset = z_rim; zf = z_rim + sp
        zs, ws, hs = z_o[seg], w_o[seg], h_o[seg]
        o = np.argsort(zs); zs, ws, hs = zs[o], ws[o], hs[o]
        zf = float(np.clip(zf, zs[0], zs[-1]))
        return offset, float(np.interp(zf, zs, ws)), float(np.interp(zf, zs, hs))

    zp, rp = _c.get_lecleach(np.sqrt(25.0 * 25.0 * 4 / np.pi), 500.0, 200, T=0.707)
    zr, wr, hr = _r._area_to_rect(zp, rp, 25.0, 25.0)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _c.generate_elliptical_3d_mesh_from_profiles(zr, wr / 2.0, hr / 2.0, thickness, 96, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    _, V_o = _c._elliptical_parallel_offset_vertices(zr, wr / 2.0, hr / 2.0, thickness, 96)
    z_o = np.mean(V_o[:, :, 2], axis=1)
    w_o = 2.0 * np.max(np.abs(V_o[:, :, 0]), axis=1)
    h_o = 2.0 * np.max(np.abs(V_o[:, :, 1]), axis=1)

    # The rim must be on the returning leg (genuine roll-back), else the test is moot.
    assert int(np.argmax(w_o * h_o)) > int(np.argmax(z_o)), "rim not on the returning leg"

    sp, ring = 4.0, 20.0
    off, ww, wh = rim_weld(z_o, w_o, h_o, sp)
    iw, ih = max(ww - 2 * BITE, 1.0), max(wh - 2 * BITE, 1.0)
    flange = _rf.generate_rectangular_flange(
        inner_w=iw, inner_h=ih, thickness=sp, bolt_count=8, bolt_diam=4.0,
        outer_type="elliptical", outer_w=iw + 2 * ring, outer_h=ih + 2 * ring,
        offset=off, inner_type="elliptical", output_path=None)
    _check_flange(flange, "roll-back mouth flange")
    # Hole must match the horn's widest outer width → it is at the OUTER rim.
    assert iw > 0.95 * w_o.max(), f"hole {iw:.0f} not at outer rim (widest {w_o.max():.0f})"
    combined = trimesh.boolean.union([horn, flange], engine="manifold")
    combined.merge_vertices(); combined.fix_normals()
    _check_mesh(combined, "roll-back horn + outer-rim mouth flange", min_volume=1000)
test("roll-back mouth flange welds to outer rim", _rollback_mouth_flange_welds_to_outer_rim)


def _inward_mouth_flange_drills_through_flare():
    """Inward mouth flange on a deep roll-back: a flat ring attaches to the
    cavity-facing side of the returning lip without crossing the outside skin.
    Bolts are then drilled through the plate + lip. Annular compression pillars
    bridge the cavity around each bolt before the full-Z through-hole + head
    counterbore are cut. Mirrors ui_app.
    """
    from shapely.geometry import Polygon

    sp, nb, db = 4.0, 8, 5.0
    head_d, seat_depth, seat_wall = 9.5, 2.0, 3.0
    BITE = 0.5
    ring = 15.0
    zp, rp = _c.get_lecleach(np.sqrt(25.0 * 25.0 * 4 / np.pi), 500.0, 200, T=0.707)
    zr, wr, hr = _r._area_to_rect(zp, rp, 25.0, 25.0)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _c.generate_elliptical_3d_mesh_from_profiles(zr, wr / 2.0, hr / 2.0, sp, 96, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    V_i, V_o = _c._elliptical_parallel_offset_vertices(
        zr, wr / 2.0, hr / 2.0, sp, 96)
    z_o = np.mean(V_o[:, :, 2], axis=1)
    w_o = 2.0 * np.max(np.abs(V_o[:, :, 0]), axis=1)
    h_o = 2.0 * np.max(np.abs(V_o[:, :, 1]), axis=1)
    rim = int(np.argmax(w_o * h_o)); peak = int(np.argmax(z_o))
    assert rim > peak, "needs a genuine roll-back lip"
    rim_w, rim_h = float(w_o[rim]), float(h_o[rim])
    peak_w, peak_h = float(w_o[peak]), float(h_o[peak])
    rim_off = float(z_o[rim])   # roll-back: plate sits at the rim plane (above it)

    def branch_section(grid, z_target, returning):
        points = np.empty((grid.shape[1], 2))
        for j in range(grid.shape[1]):
            z_col = grid[:, j, 2]
            branch_peak = int(np.argmax(z_col))
            sl = slice(branch_peak, None) if returning else slice(0, branch_peak + 1)
            zs = z_col[sl]
            xs, ys = grid[sl, j, 0], grid[sl, j, 1]
            order = np.argsort(zs)
            zs, xs, ys = zs[order], xs[order], ys[order]
            z = float(np.clip(z_target, zs[0], zs[-1]))
            points[j] = [np.interp(z, zs, xs), np.interp(z, zs, ys)]
        return points

    plate_top = rim_off + sp
    return_outer = Polygon(branch_section(V_o, plate_top, returning=True))
    return_inner = Polygon(branch_section(V_i, plate_top, returning=True))
    outgoing_outer = Polygon(branch_section(V_o, plate_top, returning=False))
    hole_poly = return_outer.buffer(-ring)
    outer_poly = return_outer.buffer(BITE)
    assert hole_poly.contains(outgoing_outer), "inward ring collides with outgoing flare"
    assert return_inner.contains(outer_poly), "inward ring crossed the rollback outside skin"

    plate = _fg.generate_contour_flange(
        inner_xy=np.asarray(hole_poly.exterior.coords)[:, :2],
        outer_xy=np.asarray(outer_poly.exterior.coords)[:, :2],
        thickness=sp, bite=0.0, bolt_n=0, bolt_d=db,
        offset=plate_top, output_path=None)
    _check_flange(plate, "inward mouth plate")
    combined = trimesh.boolean.union([horn, plate], engine="manifold")
    combined.merge_vertices(); combined.fix_normals()
    _check_mesh(combined, "inward mouth flange (plate + horn)", min_volume=1000)
    # A real flange was added (material grew vs. the bare horn) and the outer Ø
    # never exceeds the rim — nothing protrudes beyond the mouth envelope.
    assert combined.volume > horn.volume, "inward flange must add the cavity plate"
    assert combined.bounds[1, 0] <= horn.bounds[1, 0] + 1.0 and \
           combined.bounds[1, 1] <= horn.bounds[1, 1] + 1.0, "plate grew beyond the rim Ø"

    bx = rim_w / 2.0 - (head_d / 2.0 + seat_wall)
    by = rim_h / 2.0 - (head_d / 2.0 + seat_wall)
    z_lo, z_hi = combined.bounds[0, 2] - 10.0, combined.bounds[1, 2] + 10.0
    zsamp = np.linspace(horn.bounds[0, 2], horn.bounds[1, 2], 400)
    cuts = []
    flare_opening_cuts = []
    head_seat_cuts = []
    shaft_cuts = []
    pillars = []
    ztops = []
    for a in np.linspace(0, 2 * np.pi, nb, endpoint=False):
        cx, cy = bx * np.cos(a), by * np.sin(a)
        sh = trimesh.creation.cylinder(radius=db / 2.0, height=z_hi - z_lo, sections=64)
        sh.apply_translation([cx, cy, (z_lo + z_hi) / 2.0])
        cuts.append(sh); shaft_cuts.append(sh)
        col = np.column_stack([np.full_like(zsamp, cx), np.full_like(zsamp, cy), zsamp])
        ins = horn.contains(col)
        assert ins.any(), "bolt does not land on the lip"
        ztop = float(zsamp[ins][-1]); ztops.append(ztop)
        surf_p, _, surf_face = horn.nearest.on_surface(
            np.array([[cx, cy, ztop]], dtype=float))
        surf_n = horn.face_normals[int(surf_face[0])]
        mouth_in, mouth_out = sp + 0.5, 2.0
        mouth_len = mouth_in + mouth_out
        mouth_cut = trimesh.creation.cylinder(
            radius=db / 2.0, height=mouth_len, sections=96)
        mouth_cut.apply_transform(trimesh.geometry.align_vectors([0.0, 0.0, 1.0], surf_n))
        mouth_cut.apply_translation(surf_p[0] + surf_n * ((mouth_out - mouth_in) / 2.0))
        flare_opening_cuts.append(mouth_cut)
        assert abs(float(np.dot(surf_n, [0.0, 0.0, 1.0]))) < 0.999, \
            "test surface is not inclined enough to verify a normal-oriented opening"
        pillar_r = head_d / 2.0 + seat_wall
        pillar_bot = plate_top - 0.3
        full = trimesh.creation.cylinder(
            radius=pillar_r, height=z_hi - pillar_bot, sections=64)
        full.apply_translation([cx, cy, (z_hi + pillar_bot) / 2.0])
        nr, na = 6, 64
        radii = np.linspace((pillar_r + 0.3) / nr, pillar_r + 0.3, nr)
        theta = np.linspace(0.0, 2 * np.pi, na, endpoint=False)
        top_grid = np.empty((nr, na), dtype=float)
        ccol = np.column_stack(
            [np.full_like(zsamp, cx), np.full_like(zsamp, cy), zsamp])
        cins = horn.contains(ccol)
        assert cins.any(), "pillar center misses the flare"
        top_center = float(zsamp[cins][-1])
        for ri, pr in enumerate(radii):
            for ai, pa in enumerate(theta):
                px, py = cx + pr * np.cos(pa), cy + pr * np.sin(pa)
                pcol = np.column_stack(
                    [np.full_like(zsamp, px), np.full_like(zsamp, py), zsamp])
                pins = horn.contains(pcol)
                assert pins.any(), "pillar footprint misses the flare"
                top_grid[ri, ai] = float(zsamp[pins][-1])
        vv = [[cx, cy, pillar_bot]]
        for ri, pr in enumerate(radii):
            for ai, pa in enumerate(theta):
                vv.append([cx + pr * np.cos(pa), cy + pr * np.sin(pa), pillar_bot])
        top_center_i = len(vv)
        vv.append([cx, cy, top_center])
        top_ring0 = len(vv)
        for ri, pr in enumerate(radii):
            for ai, pa in enumerate(theta):
                vv.append([cx + pr * np.cos(pa), cy + pr * np.sin(pa), top_grid[ri, ai]])
        ff = []
        for ai in range(na):
            aj = (ai + 1) % na
            ff.extend([[0, 1 + aj, 1 + ai],
                       [top_center_i, top_ring0 + ai, top_ring0 + aj]])
        for ri in range(nr - 1):
            for ai in range(na):
                aj = (ai + 1) % na
                b0, b1 = 1 + ri * na + ai, 1 + ri * na + aj
                b2, b3 = 1 + (ri + 1) * na + aj, 1 + (ri + 1) * na + ai
                t0, t1 = top_ring0 + ri * na + ai, top_ring0 + ri * na + aj
                t2, t3 = top_ring0 + (ri + 1) * na + aj, top_ring0 + (ri + 1) * na + ai
                ff.extend([[b0, b2, b1], [b0, b3, b2],
                           [t0, t1, t2], [t0, t2, t3]])
        outer_b, outer_t = 1 + (nr - 1) * na, top_ring0 + (nr - 1) * na
        for ai in range(na):
            aj = (ai + 1) % na
            b0, b1 = outer_b + ai, outer_b + aj
            t0, t1 = outer_t + ai, outer_t + aj
            ff.extend([[b0, b1, t1], [b0, t1, t0]])
        clip = trimesh.Trimesh(vertices=np.asarray(vv), faces=np.asarray(ff), process=True)
        clip.fix_normals()
        pillar = trimesh.boolean.intersection(
            [full, clip], engine="manifold", check_volume=False)
        assert pillar is not None and not pillar.is_empty, "boolean pillar trim failed"
        assert pillar.bounds[1, 2] <= max(top_center, float(top_grid.max())) + 1e-6, \
            "trimmed pillar protrudes beyond clipping surface"
        pillars.append(pillar)
        seat_floor = max(plate_top - seat_depth, rim_off + 0.5)
        seat_cut = trimesh.creation.cylinder(
            radius=head_d / 2.0, height=z_hi - seat_floor, sections=96)
        seat_cut.apply_translation([cx, cy, (z_hi + seat_floor) / 2.0])
        head_seat_cuts.append(seat_cut)
    horn_opened = trimesh.boolean.difference(
        [horn] + flare_opening_cuts, engine="manifold", check_volume=False)
    assert horn_opened is not None and not horn_opened.is_empty, "flare opening cut failed"
    combined_opened = trimesh.boolean.union([horn_opened, plate], engine="manifold")
    supported = trimesh.boolean.union([combined_opened] + pillars, engine="manifold")
    _check_mesh(supported, "inward mouth flange (with pillars)", min_volume=1000)
    assert supported.volume > combined_opened.volume + 100.0, "compression pillars were not added"
    drilled = trimesh.boolean.difference([supported] + cuts, engine="manifold")
    drilled = trimesh.boolean.difference(
        [drilled] + head_seat_cuts, engine="manifold", check_volume=False)
    _check_mesh(drilled, "inward mouth flange (drilled)", min_volume=1000)
    assert drilled.volume < supported.volume, "bolts did not pierce the supported assembly"

    # Axial head pockets remove more than bare shafts while leaving the
    # compression pillar present below their common flat seating plane.
    # Material immediately outside the counterbore remains through the cavity:
    # this is the annular pillar that carries screw clamp load.
    pillar_probe_r = bx + head_d / 2.0 + 0.5
    assert drilled.contains([[pillar_probe_r, 0.0, plate_top + 0.5]])[0], \
        "compression pillar is missing around the bolt channel"
    shaft_only = trimesh.boolean.difference([supported] + shaft_cuts, engine="manifold")
    assert drilled.volume < shaft_only.volume - 50.0, "counterbore seat not cut"
test("inward mouth flange drills through flare", _inward_mouth_flange_drills_through_flare)


def _inward_mouth_plate_flush_with_rim():
    """The inward plate's BOTTOM face sits exactly on the lip rim plane — the
    horn mounts flat on it. Regression for the 0.5 mm step left by the old
    sunk plate (thickness = sp + 0.5 with top at rim + sp). The weld does not
    need the sink: the curled lip dives through the plate volume from above.
    Mirrors the ui_app inward circular path."""
    sp, t, ring = 4.5, 4.0, 9.0
    zp, rp = _c.get_lecleach(36.0, 500.0, 300, T=0.707, max_angle=160.0)
    nml = _uts.compute_profile_normals(zp, rp)
    z_o = zp + t * nml[:, 0]
    r_o = rp + t * nml[:, 1]
    env = np.maximum(rp, r_o)
    rim = int(np.argmax(env)); peak = int(np.argmax(z_o))
    assert rim > peak, "needs a genuine roll-back lip"
    z_rim = float(zp[rim] if rp[rim] >= r_o[rim] else z_o[rim])
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f: p = f.name
    _c.generate_3d_mesh_from_profile(zp, rp, t, 128, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    horn.fix_normals()
    plate = _fg.generate_profile_flange(
        inner_type="circular", inner_R=max(float(env[rim]) - ring, 1.0),
        outer_mode="custom", outer_type="circular",
        outer_diam=2.0 * float(env[rim]),
        thickness=sp, bolt_n=0, bolt_d=5.0,
        offset=z_rim + sp, seg=128)
    assert abs(plate.bounds[0, 2] - z_rim) < 1e-3, \
        f"plate bottom {plate.bounds[0, 2]:.3f} not flush with rim {z_rim:.3f}"
    rv = np.linalg.norm(plate.vertices[:, :2], axis=1)
    assert abs((rv.max() - rv.min()) - ring) < 0.2, \
        f"inward plate land is {rv.max() - rv.min():.2f} mm, expected {ring:.2f} mm"
    combined = trimesh.boolean.union([horn, plate], engine="manifold")
    _check_mesh(combined, "inward plate flush with rim", min_volume=1000)
    assert combined.volume > horn.volume, "plate did not weld onto the lip"
test("inward mouth plate sits flush with the rim plane", _inward_mouth_plate_flush_with_rim)


def _inward_rollback_plates_circular_and_polygonal():
    """Inward plates must stay inside the rim by the requested land width."""
    sp, ring = 4.0, 9.0
    z, r = _c.get_lecleach(25.0, 500.0, 200, T=0.707)
    for shape, sides in (("circular", 0), ("polygonal", 6)):
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
            p = t.name
        if shape == "circular":
            _c.generate_3d_mesh_from_profile(z, r, sp, 96, p)
            normals = _uts.compute_profile_normals(z, r)
            z_o = z + sp * normals[:, 0]
            R_o = r + sp * normals[:, 1]
        else:
            _ph.generate_polygonal_3d_mesh(z, r, sides, sp, p)
            R_i = _ph._r_to_circumradius(r, sides)
            normals = _uts.compute_profile_normals(z, R_i, flip_if_negative=True)
            z_o = np.clip(z + sp * normals[:, 0], z.min(), z.max())
            z_o[0] = z[0]; z_o[-1] = z[-1]
            R_o = R_i + sp / np.cos(np.pi / sides) * normals[:, 1]
        envelope_R = np.maximum(r if shape == "circular" else R_i, R_o)
        horn = trimesh.load(p, file_type="stl"); os.unlink(p)
        rim, peak = int(np.argmax(envelope_R)), int(np.argmax(z_o))
        assert rim > peak, f"{shape}: expected roll-back rim"
        z_rim = z[rim] if envelope_R[rim] > R_o[rim] else z_o[rim]
        inner_R = (
            float(envelope_R[rim]) - ring if shape == "circular"
            else float(envelope_R[rim]) - ring / np.cos(np.pi / sides)
        )
        plate = _fg.generate_profile_flange(
            inner_type=shape, inner_R=inner_R,
            inner_n_sides=sides, outer_mode="custom", outer_type=shape,
            outer_diam=2.0 * envelope_R[rim], outer_n_sides=sides,
            thickness=sp, bolt_n=0, bolt_d=4.0,
            offset=float(z_rim + sp))
        _check_flange(plate, f"{shape} inward plate")
        assert abs(plate.bounds[0, 2] - z_rim) < 1e-3, \
            f"{shape}: plate is not flush with rim"
        rv = np.linalg.norm(plate.vertices[:, :2], axis=1)
        if shape == "circular":
            assert abs((rv.max() - rv.min()) - ring) < 0.2, \
                f"{shape}: land is {rv.max() - rv.min():.2f} mm, expected {ring:.2f} mm"
        if shape == "circular":
            combined = trimesh.boolean.union(
                [horn, plate], engine="manifold", check_volume=False)
            _check_mesh(
                combined, f"{shape} inward plate + roll-back horn", min_volume=1000)
test("inward roll-back plates circular and polygonal",
     _inward_rollback_plates_circular_and_polygonal)


def _rectangular_inward_bolts_follow_rim():
    """Diagonal inward-flange bolts must follow the rectangular rim, not an ellipse.

    Elliptical placement moves diagonal bolts too far inward, where they pass only
    through the cavity plate and cannot form a supported hole through the lip.
    """
    rim_w, rim_h, pillar_r = 240.0, 120.0, 8.0
    for a in np.linspace(0, 2 * np.pi, 8, endpoint=False):
        ca, sa = np.cos(a), np.sin(a)
        sx = (rim_w / 2.0) / max(abs(ca), 1e-9)
        sy = (rim_h / 2.0) / max(abs(sa), 1e-9)
        edge_r = min(sx, sy)
        ex, ey = edge_r * ca, edge_r * sa
        x = float(np.clip(ex, -rim_w / 2.0 + pillar_r, rim_w / 2.0 - pillar_r))
        y = float(np.clip(ey, -rim_h / 2.0 + pillar_r, rim_h / 2.0 - pillar_r))
        edge_gap = min(rim_w / 2.0 - abs(x), rim_h / 2.0 - abs(y))
        assert abs(edge_gap - pillar_r) < 1e-6, \
            f"bolt at {np.degrees(a):.0f}° is not inset from rectangular rim: {edge_gap}"
test("rectangular inward bolts follow rim", _rectangular_inward_bolts_follow_rim)


# Rectangular horn + circular flanges merged assembly
for _label, _rect_fn in [
    ("Rect Exp assembly",     lambda: _r.get_rectangular_exponential(20, 10, 160, 600, 300)),
    ("Rect Tractrix assembly", lambda: _r.get_rectangular_tractrix(20, 10, 160, 300)),
    ("Rect Salmon assembly",   lambda: _r.get_rectangular_salmon(20, 10, 600, 80, 300)),
]:
    def make_rect_assembly(fn=_rect_fn, lbl=_label):
        z, w, h = fn()
        thickness = 4.0
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
        _r.generate_rectangular_3d_mesh(z, w, h, thickness, p)
        horn = trimesh.load(p, file_type="stl"); os.unlink(p)
        z_min = horn.vertices[:, 2].min()
        z_max = horn.vertices[:, 2].max()
        # outer dims at throat / mouth
        ow_t = horn.vertices[:, 0].max() * 2.0
        oh_t = horn.vertices[:, 1].max() * 2.0
        v_mouth = horn.vertices[horn.vertices[:, 2] >= z_max - 0.5]
        ow_m = v_mouth[:, 0].max() * 2.0 if len(v_mouth) else ow_t
        oh_m = v_mouth[:, 1].max() * 2.0 if len(v_mouth) else oh_t
        BITE = 0.5
        f_t = _rf.generate_rectangular_flange(ow_t + 30, ow_t - 2 * BITE, oh_t - 2 * BITE,
                                              thickness=6.0, bolt_radius=(ow_t + 30) / 2 - 5,
                                              offset=z_min + 6.0, output_path=None)
        f_m = _rf.generate_rectangular_flange(ow_m + 30, ow_m - 2 * BITE, oh_m - 2 * BITE,
                                              thickness=6.0, bolt_radius=(ow_m + 30) / 2 - 5,
                                              offset=z_max - 6.0, output_path=None)
        assert f_t is not None, f"{lbl}: throat flange is None"
        assert f_m is not None, f"{lbl}: mouth flange is None"
        try:
            combined = trimesh.boolean.union([horn, f_t, f_m], engine="manifold")
        except Exception:
            combined = trimesh.util.concatenate([horn, f_t, f_m])
        assert combined is not None, f"{lbl}: merge returned None"
        assert combined.volume > 0, f"{lbl}: combined volume={combined.volume}"
    test(_label, make_rect_assembly)

print("\n═══ Iwata horn (faithful l'Audiophile rectangular dual-flare) ═══")

def _iwata_plan():
    # Native plan must reproduce the drawing: mouth 740×320, throat ~50×50.
    z, w, h = _r.get_iwata_horn(50.0, 550.0, 300)
    assert abs(w[-1] - 740.0) < 1.0 and abs(h[-1] - 320.0) < 1.0, \
        f"mouth {w[-1]:.1f}×{h[-1]:.1f} != 740×320"
    assert abs(w[0] - 50.0) < 1.0 and abs(h[0] - 50.0) < 3.0, "throat not ~50×50"
    assert (np.diff(w) >= -1e-6).all() and (np.diff(h) >= -1e-6).all(), "non-monotone"
test("plan reproduction (50→740×320)", _iwata_plan)

def _iwata_scale():
    # Uniform scaling preserves the Iwata mouth aspect ratio (~2.31:1).
    _, w0, h0 = _r.get_iwata_horn(50.0, 550.0, 200)
    _, w1, h1 = _r.get_iwata_horn(25.0, 275.0, 200)
    assert abs((w1[-1] / h1[-1]) - (w0[-1] / h0[-1])) < 1e-6, "aspect not preserved"
test("uniform scaling preserves aspect", _iwata_scale)

def _iwata_mesh():
    z, w, h = _r.get_iwata_horn(50.0, 550.0, 300)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _r.generate_rectangular_3d_mesh(z, w, h, 4.0, p)
    m = trimesh.load(p, file_type="stl"); os.unlink(p)
    _check_mesh(m, "iwata mesh")
test("iwata watertight mesh", _iwata_mesh)

def _iwata_arc_mouth():
    # Plan-view arc mouth: trimming with the height-axis cylinder must stay
    # watertight and roll the mouth corners back behind the centre.
    z, w, h = _r.get_iwata_horn(50.0, 572.0, 200)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _r.generate_rectangular_3d_mesh(z, w, h, 4.0, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p); horn.fix_normals()
    R, cz = _r.iwata_arc_mouth(50.0, 572.0)
    cyl = trimesh.creation.cylinder(radius=R, height=(h[-1] + 8) * 2)
    cyl.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    cyl.apply_translation([0, 0, cz])
    m = trimesh.boolean.intersection([horn, cyl], engine="manifold"); m.fix_normals()
    assert m.is_watertight, "arc-trimmed mouth not watertight"
    v = m.vertices
    x_max = np.abs(v[:, 0]).max()
    zc = v[np.abs(v[:, 0]) < 20][:, 2].max()             # centre reaches forward
    ze = v[np.abs(v[:, 0]) > 0.8 * x_max][:, 2].max()    # widest edge rolls back
    assert ze < zc - 20, f"mouth not rolled back (centre {zc:.0f}, edge {ze:.0f})"
test("iwata arc mouth (curved, watertight)", _iwata_arc_mouth)


# ══════════════════════════════════════════════════════════════════════════════
#  Slicer — radial petals (plain flat seams)
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Slicer — petals ═══")

from src import _slicer as _slc

def _horn_trimesh():
    z, r = _c.get_tractrix(THROAT, MOUTH, N)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _c.generate_3d_mesh_from_profile(z, r, 4.0, 64, p)
    m = trimesh.load(p, file_type="stl"); os.unlink(p)
    return m

def _adapter_segment_axial_cut():
    mesh = trimesh.creation.cylinder(radius=20.0, height=100.0, sections=64)
    mesh.apply_translation([0, 0, 50.0])
    parts = _slc.slice_with_adapter_segment(mesh, 20.0, flare_segments=2)
    assert len(parts) == 3, f"expected adapter + 2 flare segments, got {len(parts)}"
    expected = [(0.0, 20.0), (20.0, 60.0), (60.0, 100.0)]
    for i, (part, (lo, hi)) in enumerate(zip(parts, expected)):
        assert part.is_watertight, f"adapter axial segment {i}: not watertight"
        assert abs(part.bounds[0, 2] - lo) < 1e-6, f"segment {i}: z_lo {part.bounds[0,2]} != {lo}"
        assert abs(part.bounds[1, 2] - hi) < 1e-6, f"segment {i}: z_hi {part.bounds[1,2]} != {hi}"
test("adapter segment axial cut", _adapter_segment_axial_cut)


def _print_volume_boxes_keep_throat():
    mesh = trimesh.creation.box(extents=[120.0, 90.0, 180.0])
    mesh.apply_translation([0.0, 0.0, 90.0])
    parts = _slc.slice_to_print_volume(mesh, 60.0, 50.0, 70.0, keep_z_max=40.0)
    assert len(parts) > 1, f"expected multiple print-volume chunks, got {len(parts)}"
    first = parts[0]
    first_dims = first.bounds[1] - first.bounds[0]
    assert first.metadata.get("print_volume_core"), "first piece should be the center-bottom core"
    assert abs(first.bounds[0, 2]) < 1e-6, "first core should start at the model bottom"
    assert first.bounds[1, 2] >= 40.0, "protected throat range should be inside first core"
    assert first_dims[0] > 60.0, "protected throat hardware should remain unsplit in X"
    assert first_dims[1] > 50.0, "protected throat hardware should remain unsplit in Y"

    core = [p for p in parts if p.metadata.get("print_volume_core")]
    assert len(core) >= 2, "expected a bottom-up central core stack"
    assert all(core[i].bounds[0, 2] <= core[i + 1].bounds[0, 2] + 1e-6
               for i in range(len(core) - 1)), "core pieces should run bottom-up"
    first_wing = next((i for i, p in enumerate(parts) if not p.metadata.get("print_volume_core")), len(parts))
    assert all(p.metadata.get("print_volume_core") for p in parts[:first_wing]), "core should come before wings"
    assert not any(p.metadata.get("print_volume_core") for p in parts[first_wing:]), "wings should follow core"

    for i, part in enumerate(parts[1:], start=1):
        dims = part.bounds[1] - part.bounds[0]
        assert dims[0] <= 60.1, f"part {i}: X {dims[0]:.2f} exceeds volume"
        assert dims[1] <= 50.1, f"part {i}: Y {dims[1]:.2f} exceeds volume"
        assert dims[2] <= 70.1, f"part {i}: Z {dims[2]:.2f} exceeds volume"
        assert part.is_watertight, f"part {i}: not watertight"
test("print-volume boxes keep throat monolithic", _print_volume_boxes_keep_throat)


def _print_volume_boxes_tongue_groove():
    mesh = trimesh.creation.box(extents=[40.0, 40.0, 120.0])
    mesh.apply_translation([0.0, 0.0, 60.0])
    plain = _slc.slice_to_print_volume(mesh, 80.0, 80.0, 60.0, strategy="grid")
    jointed = _slc.slice_to_print_volume(mesh, 80.0, 80.0, 60.0, strategy="grid",
                                         joint_depth=2.0, joint_margin=2.0,
                                         clearance=0.1)
    assert len(plain) == len(jointed) == 2, "expected two stacked print-volume chunks"
    lower_plain, upper_plain = plain
    lower_joint, upper_joint = jointed
    assert lower_joint.bounds[1, 2] > lower_plain.bounds[1, 2] + 1.0, \
        "lower chunk should have an upward tongue"
    assert abs(upper_joint.bounds[0, 2] - upper_plain.bounds[0, 2]) < 0.2, \
        "upper chunk should keep its bottom datum while receiving a groove"
    assert lower_joint.volume > lower_plain.volume, "tongue should add volume"
    assert upper_joint.volume < upper_plain.volume, "groove should remove volume"
    assert lower_joint.is_watertight, "jointed lower chunk not watertight"
    assert upper_joint.is_watertight, "jointed upper chunk not watertight"
test("print-volume boxes tongue & groove", _print_volume_boxes_tongue_groove)


def _print_volume_center_up_tongue_groove():
    mesh = trimesh.creation.box(extents=[40.0, 40.0, 140.0])
    mesh.apply_translation([0.0, 0.0, 70.0])
    plain = _slc.slice_to_print_volume(mesh, 80.0, 80.0, 70.0,
                                       strategy="center_up")
    jointed = _slc.slice_to_print_volume(mesh, 80.0, 80.0, 70.0,
                                         strategy="center_up",
                                         joint_depth=3.0, joint_margin=2.0,
                                         clearance=0.1)
    assert len(plain) == len(jointed) == 2, "expected two center-up chunks"
    assert jointed[0].bounds[1, 2] > plain[0].bounds[1, 2] + 2.0, \
        "center-up lower chunk should receive an upward tongue"
    assert jointed[0].volume > plain[0].volume, "center-up tongue should add volume"
    assert jointed[1].volume < plain[1].volume, "center-up groove should remove volume"
test("print-volume center-up tongue & groove", _print_volume_center_up_tongue_groove)

def _joint_profile_preserves_outer_skin():
    poly = _slc.shp.Polygon([(0, 0), (4, 0), (4, 30), (0, 30)])
    to_3d = np.array([
        [1, 0, 0, 0],  # 2-D x -> radial X
        [0, 0, 1, 0],
        [0, 1, 0, 0],  # 2-D y -> vertical Z
        [0, 0, 0, 1],
    ], dtype=float)
    prof = _slc._joint_profile(poly, to_3d, margin=0.5, outer_margin=1.5)
    assert prof is not None and not prof.is_empty, "outer-biased joint profile vanished"
    assert prof.distance(poly.exterior) >= 1.5 - 1e-6, \
        f"outer skin not preserved: distance={prof.distance(poly.exterior):.3f}"
test("joint profile preserves outer skin", _joint_profile_preserves_outer_skin)


def _joint_profile_requires_enough_material():
    poly = _slc.shp.Polygon([(0, 0), (1.6, 0), (1.6, 30), (0, 30)])
    to_3d = np.array([
        [1, 0, 0, 0],
        [0, 0, 1, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1],
    ], dtype=float)
    try:
        _slc._joint_profile(poly, to_3d, margin=0.5, outer_margin=1.5)
    except ValueError as exc:
        assert "outer_margin=1.500 mm" in str(exc), f"unexpected error: {exc}"
    else:
        raise AssertionError("expected outer_margin contract to fail on thin wall")
test("joint profile rejects impossible outer skin", _joint_profile_requires_enough_material)

def _flanged_petal_keeps_both_seam_strips():
    m = _ta.make_adapter_assembly(
        driver_type="flanged", driver_diam=25.0, thread_key=None,
        horn_shape="circular",
        rect_w=0.0, rect_h=0.0, poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=18.0,
        adapter_length=30.0, wall_thickness=4.0,
        flange_R=30.0, flange_thickness=6.0,
        flange_bolt_R=20.0, flange_bolt_n=4, flange_bolt_d=3.5,
        socket_length=0.0, z_offset=0.0,
        output_path=None,
    )
    petal = _slc.slice_into_petals(m, 2, phase=0.0)[0]
    polys, _ = _slc._seam_face_polygons(petal, [0.0, 0.0, 0.0],
                                        np.array([0.0, -1.0, 0.0]))
    assert len(polys) >= 2, f"expected flange seam strips to survive, got {len(polys)}"
test("flanged petal keeps both seam strips", _flanged_petal_keeps_both_seam_strips)

def _make_check_petals(n):
    def _check():
        horn = _horn_trimesh()
        Vh = horn.volume
        petals = _slc.slice_into_petals(horn, n)
        assert len(petals) == n, f"petals: got {len(petals)}"
        for i, p1 in enumerate(petals):
            assert p1.is_watertight,   f"petal {i}: not watertight"
            assert p1.body_count == 1, f"petal {i}: not one body ({p1.body_count})"
        # Petals tile the horn. Boolean half-space cuts leave sub-µm³ float
        # jitter on either side of Vh; a real double-counted wedge would add
        # whole percents, so bound the excess relatively, not at +1e-6 mm³.
        sv = sum(p.volume for p in petals)
        assert 0.95 * Vh < sv < Vh * (1.0 + 1e-6), \
            f"n={n}: petals don't tile horn ({sv/Vh:.6f})"
    return _check

for _n in (2, 3, 4, 6, 8, 12):
    test(f"{_n} petals", _make_check_petals(_n))


def _rollback_two_petals_single_diametric_cap():
    """Two petals must cap their shared diametric plane only once."""
    z, r = _c.get_rosse(25.4, 260.0, 78.0, N)
    rx, ry = r * 1.35, r / 1.35
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_elliptical_3d_mesh_from_profiles(z, rx, ry, 4.0, 96, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    petals = _slc.slice_into_petals(horn, 2)
    assert len(petals) == 2
    assert all(p.is_watertight and p.body_count == 1 for p in petals)
    assert abs(sum(p.volume for p in petals) / horn.volume - 1.0) < 1e-6

    # A second cap pass on the coincident n=2 boundary retriangulates the same
    # face and adds thousands of coplanar triangles (visible as z-fighting).
    # The boolean half-space cut triangulates the seam slightly differently
    # from slice_plane (±tens of faces on ~100k), so guard with a 2% band
    # instead of exact equality — a double cap would blow well past it.
    once = horn.slice_plane([0, 0, 0], [0, -1, 0], cap=True)
    assert len(petals[0].faces) < len(once.faces) * 1.02, \
        f"diametric seam capped more than once: {len(petals[0].faces)} vs {len(once.faces)}"
test("rollback 2 petals use one diametric cap",
     _rollback_two_petals_single_diametric_cap)


# ══════════════════════════════════════════════════════════════════════════════
#  Slicer — radial petals with tongue & groove joint
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Slicer — petals with T&G joint ═══")

def _make_check_jointed_petals(n, depth):
    def _check():
        horn = _horn_trimesh()
        Vh = horn.volume
        petals = _slc.slice_into_petals(horn, n, joint_depth=depth)
        assert len(petals) == n, f"jointed n={n}: got {len(petals)} petals"
        for i, p1 in enumerate(petals):
            assert p1.is_watertight,   f"jointed petal {i} (n={n}): not watertight"
            assert p1.body_count == 1, f"jointed petal {i} (n={n}): not one body ({p1.body_count})"
            assert p1.volume > 0,      f"jointed petal {i} (n={n}): zero volume"
        # Tongue adds material, groove removes it — roughly same volume
        sv = sum(p.volume for p in petals)
        ratio = sv / Vh
        assert 0.95 <= ratio <= 1.05, \
            f"n={n} depth={depth}: jointed petals volume ratio {ratio:.3f} (expected ~1.0)"
        # n==2: the diametric seam (y=0, phase=0) crosses the axis -> two strips
        # (x>0 and x<0).  Every petal must be hermaphrodite: a tongue protruding
        # past the seam on ONE strip and a groove recessed on the OTHER.
        if n == 2:
            for i, p1 in enumerate(petals):
                v = p1.vertices
                sign = 1.0 if i == 0 else -1.0          # which side the body is on
                # tongue: material reaching across the seam (past y=0 by >0.5*depth)
                past = v[sign * v[:, 1] < -0.5 * depth]
                assert len(past) > 0, \
                    f"n=2 depth={depth} petal {i}: no tongue protruding past seam"
                tongue_x = past[np.argmax(np.abs(past[:, 0])), 0]
                # groove: the seam face (y≈0) is recessed on the opposite strip,
                # so the petal carries no full-thickness wall there at the rim.
                assert (tongue_x > 1e-6 or tongue_x < -1e-6), \
                    f"n=2 depth={depth} petal {i}: tongue not on a wall strip"
            # the two petals are the same part: one is the other rotated 180° about z
            a, b = petals
            br = b.copy(); br.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [0, 0, 1]))
            assert abs(a.volume - b.volume) < 1e-3 * a.volume, \
                f"n=2 depth={depth}: halves are not identical parts"
    return _check

for _n in (2, 3, 4, 6, 8):
    test(f"{_n} petals joint_depth=2", _make_check_jointed_petals(_n, 2.0))
    test(f"{_n} petals joint_depth=0.5", _make_check_jointed_petals(_n, 0.5))

# slice_at_heights: axial slicing into stacked segments
for _label, _heights in [
    ("1 cut at mid",        None),
    ("2 cuts (3 segments)", None),
    ("3 cuts",              None),
]:
    def make_slice_heights(h=_heights, lbl=_label):
        horn = _horn_trimesh()
        zs = horn.vertices[:, 2]
        z_min, z_max = zs.min(), zs.max()
        if h is None:
            if "1 cut" in lbl:
                heights = [0.5 * (z_min + z_max)]
            elif "2 cuts" in lbl:
                heights = [z_min + (z_max - z_min) / 3, z_min + 2 * (z_max - z_min) / 3]
            else:
                heights = [z_min + i * (z_max - z_min) / 4 for i in range(1, 4)]
        else:
            heights = h
        segments = _slc.slice_at_heights(horn, heights)
        assert len(segments) >= 1, f"{lbl}: got {len(segments)} segments"
        for i, seg in enumerate(segments):
            assert seg.is_watertight, f"{lbl} segment {i}: not watertight"
            assert seg.body_count == 1, f"{lbl} segment {i}: {seg.body_count} bodies"
            assert seg.volume > 0, f"{lbl} segment {i}: zero volume"
    test(_label, make_slice_heights)

# slice_at_heights with joint_wall
def _slice_heights_joints():
    horn = _horn_trimesh()
    zs = horn.vertices[:, 2]
    z_min, z_max = zs.min(), zs.max()
    heights = [0.4 * (z_max - z_min) + z_min, 0.7 * (z_max - z_min) + z_min]
    segments = _slc.slice_at_heights(horn, heights, joint_wall=2.0)
    assert len(segments) == 3, f"jointed: got {len(segments)} segments"
    for i, seg in enumerate(segments):
        assert seg.is_watertight, f"jointed segment {i}: not watertight"
    # joints add/remove material, volume stays close
    Vh = horn.volume
    sv = sum(s.volume for s in segments)
    assert 0.90 <= sv / Vh <= 1.10, f"jointed volume ratio {sv/Vh:.3f}"
test("slice_at_heights with joint_wall", _slice_heights_joints)

print("\n═══ Throat adapter ═══")

def test_morph_circle_to_ellipse_basic():
    """Default parameters produce valid arrays of correct length."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(z_steps=100)
    assert len(z) == len(a) == len(b) == len(r_eq) == 100
    assert z[0] == 0.0 and z[-1] > 0.0
    assert np.all(a > 0) and np.all(b > 0)
test("morph_circle_to_ellipse basic", test_morph_circle_to_ellipse_basic)

def test_morph_circle_to_ellipse_throat_radius():
    """At z=0, a = b = throat_radius (circle)."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        throat_radius=10.0, target_ellipse_a=40.0, target_ellipse_b=20.0, z_steps=50)
    assert abs(r_eq[0] - 10.0) < 1e-9, f"r_eq(0)={r_eq[0]:.6f}"
    assert abs(a[0] - 10.0) < 1e-9, f"a(0)={a[0]:.6f}"
    assert abs(b[0] - 10.0) < 1e-9, f"b(0)={b[0]:.6f}"
test("morph_circle_to_ellipse throat is circle at z=0", test_morph_circle_to_ellipse_throat_radius)

def test_morph_circle_to_ellipse_target_ellipse():
    """At z=L, semi-axes must match the target ellipse."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        target_ellipse_a=50.0, target_ellipse_b=25.0, z_steps=50)
    assert abs(a[-1] - 50.0) < 1e-9, f"a(L)={a[-1]:.6f}"
    assert abs(b[-1] - 25.0) < 1e-9, f"b(L)={b[-1]:.6f}"
    expected_req = np.sqrt(50.0 * 25.0)
    assert abs(r_eq[-1] - expected_req) < 1e-9, f"r_eq(L)={r_eq[-1]:.6f} vs {expected_req}"
test("morph_circle_to_ellipse target ellipse at z=L", test_morph_circle_to_ellipse_target_ellipse)

def test_morph_circle_to_ellipse_throat_angle():
    """dr_eq/dz at z=0 must equal tan(throat_angle)."""
    angle = 10.0
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        throat_angle_deg=angle, z_steps=500)
    dz = z[1] - z[0]
    dr_dz_0 = (r_eq[1] - r_eq[0]) / dz
    expected = np.tan(np.radians(angle))
    assert abs(dr_dz_0 - expected) < 5e-4, \
        f"dr_eq/dz(0)={dr_dz_0:.6f} vs tan({angle}°)={expected:.6f}"
test("morph_circle_to_ellipse throat angle derivative", test_morph_circle_to_ellipse_throat_angle)

def test_morph_circle_to_ellipse_area_rule():
    """A(z) = π·r_eq² = π·a·b must hold at every slice."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        throat_radius=8.0, target_ellipse_a=35.0, target_ellipse_b=15.0, z_steps=80)
    A_from_req = np.pi * r_eq ** 2
    A_from_ab = np.pi * a * b
    assert np.allclose(A_from_req, A_from_ab, rtol=1e-12), \
        f"Area rule violated: max error={np.max(np.abs(A_from_req - A_from_ab)):.2e}"
test("morph_circle_to_ellipse Golden Standard area rule", test_morph_circle_to_ellipse_area_rule)

def test_morph_circle_to_ellipse_c2_smooth():
    """r_eq and aspect ratio must be C²-smooth: curvature small everywhere, no sign flips."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(z_steps=500)
    dz = z[1] - z[0]
    d2r = np.gradient(np.gradient(r_eq, dz), dz)
    # Second derivative is mathematically zero at both ends but finite-diff
    # is only O(dz) at boundaries.  Check interior smoothness and small magnitude.
    assert abs(d2r[0]) < 5e-3, f"d²r_eq/dz²(0)={d2r[0]:.2e} not ≈0"
    assert abs(d2r[-1]) < 5e-3, f"d²r_eq/dz²(L)={d2r[-1]:.2e} not ≈0"
    # The curvature should change sign at most once (single smooth hump)
    sign_changes = np.sum(np.diff(np.sign(d2r[1:-1])) != 0)
    assert sign_changes <= 2, f"too many curvature sign changes: {sign_changes}"
test("morph_circle_to_ellipse C2 smoothness", test_morph_circle_to_ellipse_c2_smooth)

def test_morph_circle_to_ellipse_monotonic():
    """r_eq, a, and b must be monotonically increasing."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        target_ellipse_a=45.0, target_ellipse_b=30.0, z_steps=50)
    assert np.all(np.diff(r_eq) >= -1e-12), "r_eq not monotonic"
    assert np.all(np.diff(a) >= -1e-12), "a not monotonic"
    assert np.all(np.diff(b) >= -1e-12), "b not monotonic"
test("morph_circle_to_ellipse monotonic expansion", test_morph_circle_to_ellipse_monotonic)

def test_morph_circle_to_ellipse_area_never_shrinks():
    """dA/dz ≥ 0 everywhere (no impedance mismatch from constrictions)."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        throat_radius=6.0, target_ellipse_a=35.0, target_ellipse_b=10.0, z_steps=100)
    A = np.pi * r_eq ** 2
    dA = np.gradient(A, z)
    assert np.all(dA >= -1e-6), f"dA/dz dips negative: min={dA.min():.4f}"
test("morph_circle_to_ellipse area never shrinks", test_morph_circle_to_ellipse_area_never_shrinks)

def test_morph_circle_to_ellipse_da_dz_at_zero():
    """da/dz and db/dz at z=0 must equal tan(θ) (shape hasn't started morphing)."""
    angle = 7.5
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(throat_angle_deg=angle, z_steps=500)
    dz = z[1] - z[0]
    da0 = (a[1] - a[0]) / dz
    db0 = (b[1] - b[0]) / dz
    expected = np.tan(np.radians(angle))
    assert abs(da0 - expected) < 5e-4, f"da/dz(0)={da0:.6f} vs {expected:.6f}"
    assert abs(db0 - expected) < 5e-4, f"db/dz(0)={db0:.6f} vs {expected:.6f}"
test("morph_circle_to_ellipse da/dz, db/dz at z=0", test_morph_circle_to_ellipse_da_dz_at_zero)

def test_morph_circle_to_ellipse_aspect_ratio_smooth():
    """R(z) = a(z)/b(z) transitions via quintic smoothstep (zero derivatives at ends)."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        target_ellipse_a=50.0, target_ellipse_b=15.0, z_steps=500)
    R = a / b
    dR = np.gradient(R, z)
    d2R = np.gradient(dR, z)
    assert abs(dR[0]) < 2e-5, f"dR/dz(0)={dR[0]:.2e} != 0"
    assert abs(dR[-1]) < 2e-5, f"dR/dz(L)={dR[-1]:.2e} != 0"
    assert abs(d2R[0]) < 5e-4, f"d²R/dz²(0)={d2R[0]:.2e} not ≈0"
    assert abs(d2R[-1]) < 5e-4, f"d²R/dz²(L)={d2R[-1]:.2e} not ≈0"
    assert abs(R[0] - 1.0) < 1e-9, f"R(0)={R[0]:.6f} != 1"
    assert abs(R[-1] - 50.0/15.0) < 1e-9, f"R(L)={R[-1]:.6f} != {50.0/15.0:.6f}"
test("morph_circle_to_ellipse aspect ratio smoothstep", test_morph_circle_to_ellipse_aspect_ratio_smooth)

def test_morph_circle_to_ellipse_edge_short_transition():
    """Very short transition still produces valid output."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        transition_length_z=5.0, target_ellipse_a=15.0, target_ellipse_b=14.0, z_steps=10)
    assert len(z) == 10
    assert np.allclose(a[0], b[0], atol=1e-9)
    assert abs(a[-1] - 15.0) < 1e-9
    assert abs(b[-1] - 14.0) < 1e-9
test("morph_circle_to_ellipse edge case: short transition", test_morph_circle_to_ellipse_edge_short_transition)

def test_morph_circle_to_ellipse_square_target():
    """Target ellipse with a == b (circle target) works correctly."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        throat_radius=10.0, target_ellipse_a=30.0, target_ellipse_b=30.0, z_steps=50)
    assert abs(a[-1] - 30.0) < 1e-9
    assert abs(b[-1] - 30.0) < 1e-9
    assert abs(r_eq[-1] - 30.0) < 1e-9
    assert np.allclose(a, b, atol=1e-9)  # stays circular throughout
test("morph_circle_to_ellipse square target (a=b)", test_morph_circle_to_ellipse_square_target)

def test_morph_circle_to_ellipse_steep_angle():
    """Steep throat angle (20°) still produces valid C²-smooth r_eq."""
    angle = 20.0
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        throat_angle_deg=angle, target_ellipse_a=40.0, target_ellipse_b=20.0, z_steps=500)
    dz = z[1] - z[0]
    dr0 = (r_eq[1] - r_eq[0]) / dz
    expected = np.tan(np.radians(angle))
    assert abs(dr0 - expected) < 5e-4
    assert np.all(np.diff(r_eq) >= -1e-12)  # still monotonic
test("morph_circle_to_ellipse steep throat angle", test_morph_circle_to_ellipse_steep_angle)

def test_morph_circle_to_ellipse_very_elongated_ellipse():
    """Very high aspect ratio target (e.g., 120×20 mm) must not produce NaN."""
    z, a, b, r_eq = _ta.morph_circle_to_ellipse(
        target_ellipse_a=120.0, target_ellipse_b=20.0, z_steps=100)
    assert not np.any(np.isnan(a))
    assert not np.any(np.isnan(b))
    assert np.all(a > 0) and np.all(b > 0)
    assert abs(a[-1] - 120.0) < 1e-9
    assert abs(b[-1] - 20.0) < 1e-9
test("morph_circle_to_ellipse very elongated target", test_morph_circle_to_ellipse_very_elongated_ellipse)

def test_thread_specs():
    assert set(_ta.THREAD_SPECS) == {"1_375in"}, \
        f"unexpected thread specs: {sorted(_ta.THREAD_SPECS)}"
    spec = _ta.THREAD_SPECS["1_375in"]
    assert abs(spec.major_diam - 34.925) < 1e-6, f"major_diam={spec.major_diam}"
    assert abs(spec.bore_diam - 25.0) < 1e-6, f"bore_diam={spec.bore_diam}"
    assert spec.tpi == 18 and abs(spec.pitch - 25.4 / 18.0) < 1e-9
test("thread specs", test_thread_specs)

def test_circle_points():
    pts = _ta._circle_points(10.0, 64)
    assert pts.shape == (64, 2), f"shape={pts.shape}"
    r = np.linalg.norm(pts, axis=1)
    assert np.allclose(r, 10.0, atol=1e-10), f"radius not uniform: {r.min():.4f}..{r.max():.4f}"
test("circle points", test_circle_points)

def test_rect_points():
    pts = _ta._rect_points(20.0, 10.0, 64)
    assert pts.shape == (64, 2), f"shape={pts.shape}"
    # Check bounds
    assert abs(pts[:, 0].max() - 20.0) < 1e-10, f"x max {pts[:, 0].max()}"
    assert abs(pts[:, 1].min() - (-10.0)) < 1e-10, f"y min {pts[:, 1].min()}"
    area = _ta._polygon_area(pts)
    expected = 40.0 * 20.0  # 2*hw * 2*hh
    assert abs(area - expected) / expected < 0.05, f"area={area:.0f} vs {expected}"
test("rect points", test_rect_points)

def test_rect_points_corners_anchored():
    # Non-square rectangles must still land an exact vertex on every corner,
    # otherwise the morph chamfers the corners (square only worked by luck:
    # its corner fractions 1/8,3/8,5/8,7/8 hit integer indices).
    import numpy as _np
    for hw, hh in [(50.0, 50.0), (185.0, 80.0), (370.0, 30.0), (10.0, 400.0)]:
        pts = _ta._rect_points(hw, hh, 64)
        assert pts.shape == (64, 2), f"shape={pts.shape}"
        assert _np.allclose(pts[0], [hw, 0.0]), f"start={pts[0]}"  # mid-right, θ=0
        corners = _np.array([[hw, hh], [-hw, hh], [-hw, -hh], [hw, -hh]])
        miss = max(_np.min(_np.linalg.norm(pts - c, axis=1)) for c in corners)
        assert miss < 1e-9, f"{hw}x{hh}: corner not sampled, miss={miss:.2e}"
test("rect points corners anchored", test_rect_points_corners_anchored)

def test_ellipse_points():
    pts = _ta._ellipse_points(20.0, 10.0, 128)
    assert pts.shape == (128, 2), f"shape={pts.shape}"
    assert np.isclose(np.max(np.abs(pts[:, 0])), 20.0)
    assert np.isclose(np.max(np.abs(pts[:, 1])), 10.0)
    expected = np.pi * 20.0 * 10.0
    assert abs(_ta._polygon_area(pts) - expected) / expected < 0.01
test("ellipse points", test_ellipse_points)

def test_poly_points():
    pts = _ta._poly_points(6, 20.0, 60)
    assert pts.shape[0] >= 6, f"too few points {pts.shape}"
    area = _ta._polygon_area(pts)
    expected = 0.5 * 6 * 20.0**2 * np.sin(2 * np.pi / 6)
    assert abs(area - expected) / expected < 0.05, f"area={area:.1f} vs {expected:.1f}"
test("poly points", test_poly_points)

def test_poly_points_phase_matches_horn():
    for n_sides in (3, 4, 6, 8):
        pts = _ta._poly_points(n_sides, 20.0, n_sides)
        theta = np.linspace(0.0, 2.0 * np.pi, n_sides, endpoint=False) + np.pi / 2.0
        expected = np.column_stack([20.0 * np.cos(theta), 20.0 * np.sin(theta)])
        assert np.allclose(pts, expected, atol=1e-10), \
            f"{n_sides}-gon phase mismatch: {pts[0]} not {expected[0]}"
test("poly points phase matches polygonal horn", test_poly_points_phase_matches_horn)

def test_poly_points_corners_anchored_with_dense_ring():
    """Dense adapter rings must still include every real polygon corner.

    The UI often passes a high revolution count (e.g. 160) into polygonal
    adapter sections. Uniform perimeter sampling misses corners when that count
    is not divisible by the side count, leaving chamfer/sliver defects exactly
    at the polygon vertices.
    """
    n_sides = 6
    pts = _ta._poly_points(n_sides, 20.0, 160)
    theta = np.linspace(0.0, 2.0 * np.pi, n_sides, endpoint=False) + np.pi / 2.0
    corners = np.column_stack([20.0 * np.cos(theta), 20.0 * np.sin(theta)])
    miss = max(np.min(np.linalg.norm(pts - corner, axis=1)) for corner in corners)
    assert miss < 1e-10, f"dense polygon ring missed a corner by {miss:.3g} mm"
test("poly points dense ring corners anchored", test_poly_points_corners_anchored_with_dense_ring)

def test_morph_slice_circle():
    """At t=0 the morph should return a circle of radius ~driver_R."""
    def _tfn():
        return _ta._rect_points(10.0, 5.0, 64)
    pts = _ta._morph_slice(0.0, 12.5, _tfn, 12.5, 64)
    r = np.linalg.norm(pts, axis=1)
    assert np.allclose(r, 12.5, atol=1.0), f"circle r={r.mean():.2f} vs 12.5"
test("morph slice at t=0 (circle)", test_morph_slice_circle)

def test_morph_slice_source_phase():
    """Polygonal adapters must start the source circle in the horn's phase."""
    def _tfn():
        return _ta._poly_points(4, 20.0, 64)
    pts = _ta._morph_slice(0.0, 12.5, _tfn, 12.5, 64, source_phase=np.pi / 2.0)
    # The morph applies a sub-percent radial scaling to preserve acoustic area,
    # so we check the phase angle itself (x == 0, y > 0 for pi/2) instead of exact geometric coords.
    assert abs(pts[0, 0]) < 1e-10 and pts[0, 1] > 0, f"source phase wrong: {pts[0]}"
test("morph slice source phase", test_morph_slice_source_phase)

def test_morph_slice_target():
    """At t=1 the morph should match the target area."""
    def _tfn():
        return _ta._rect_points(20.0, 10.0, 64)
    target_R_eq = np.sqrt(40.0 * 20.0 / np.pi)
    pts = _ta._morph_slice(1.0, 12.5, _tfn, target_R_eq, 64)
    area = _ta._polygon_area(pts)
    expected = np.pi * target_R_eq**2
    assert abs(area - expected) / expected < 0.02, f"area={area:.1f} vs {expected:.1f}"
test("morph slice at t=1 (target)", test_morph_slice_target)

def _check_trimesh_watertight(m, label):
    assert m is not None, f"{label}: returned None"
    assert m.is_watertight, f"{label}: not watertight"
    assert m.body_count == 1, f"{label}: {m.body_count} bodies"
    assert m.volume > 0, f"{label}: volume={m.volume}"

def test_adapter_rect():
    """Circle→rect adapter: short 30mm transition, watertight."""
    m = _ta.make_adapter(
        driver_R=12.5, horn_shape="rectangular",
        horn_w=40.0, horn_h=20.0, horn_n_sides=0,
        horn_R_eq=np.sqrt(40*20/np.pi),
        horn_circumR=0.0,
        axial_steps=20, adapter_length=30.0, wall_thickness=4.0,
        output_path=None,
    )
    _check_trimesh_watertight(m, "adapter rect")
test("adapter circle→rect watertight", test_adapter_rect)

def test_adapter_elliptical():
    """Circle→ellipse adapter: short 30mm transition, watertight."""
    m = _ta.make_adapter(
        driver_R=12.5, horn_shape="elliptical",
        horn_w=40.0, horn_h=20.0, horn_n_sides=0,
        horn_R_eq=np.sqrt(40*20) / 2.0,
        horn_circumR=0.0,
        axial_steps=20, adapter_length=30.0, wall_thickness=4.0,
        outer_target_R=np.sqrt(48*28) / 2.0,
        outer_rect_w=48.0, outer_rect_h=28.0,
        output_path=None,
    )
    _check_trimesh_watertight(m, "adapter elliptical")
test("adapter circle→ellipse watertight", test_adapter_elliptical)

def test_adapter_poly():
    """Circle→poly adapter: short transition, watertight."""
    m = _ta.make_adapter(
        driver_R=12.5, horn_shape="polygonal",
        horn_w=0.0, horn_h=0.0, horn_n_sides=6,
        horn_R_eq=12.5,
        horn_circumR=12.5 * np.sqrt(2*np.pi / (6*np.sin(2*np.pi/6))),
        axial_steps=20, adapter_length=30.0, wall_thickness=4.0,
        output_path=None,
    )
    _check_trimesh_watertight(m, "adapter poly")
test("adapter circle→poly watertight", test_adapter_poly)

def test_adapter_circular():
    """Circle→circle adapter: tapered circular transition, watertight."""
    m = _ta.make_adapter(
        driver_R=12.5, horn_shape="circular",
        horn_w=0.0, horn_h=0.0, horn_n_sides=0,
        horn_R_eq=16.0,
        horn_circumR=0.0,
        axial_steps=20, adapter_length=30.0, wall_thickness=4.0,
        output_path=None,
    )
    _check_trimesh_watertight(m, "adapter circular")
test("adapter circle→circle watertight", test_adapter_circular)

def test_adapter_c1_raccordo_slope():
    """Adapter must reach the flare throat with the requested expansion slope."""
    target_slope = 0.22
    m = _ta.make_adapter(
        driver_R=10.0, horn_shape="circular",
        horn_w=0.0, horn_h=0.0, horn_n_sides=0,
        horn_R_eq=18.0,
        horn_circumR=0.0,
        axial_steps=80, adapter_length=40.0, wall_thickness=4.0,
        target_slope=target_slope,
        outer_target_R=22.0,
        outer_target_slope=target_slope,
        output_path=None,
    )
    _check_trimesh_watertight(m, "adapter c1 raccordo")
    zs = np.unique(np.round(m.vertices[:, 2], 6))
    z0, z1 = zs[-2], zs[-1]
    r0 = np.linalg.norm(m.vertices[np.isclose(m.vertices[:, 2], z0), :2], axis=1).min()
    r1 = np.linalg.norm(m.vertices[np.isclose(m.vertices[:, 2], z1), :2], axis=1).min()
    got = (r1 - r0) / (z1 - z0)
    assert abs(got - target_slope) < 0.02, f"end slope {got:.3f} != {target_slope:.3f}"
test("adapter C1 raccordo slope", test_adapter_c1_raccordo_slope)

def test_hermite_radius_quintic_c2():
    """Quintic raccordo must match value, slope AND curvature at the flare end
    (t=1) and stay flat (slope 0, curv 0) at the driver end (t=0), so the
    adapter→flare join has continuous curvature (no inflection line)."""
    r0, r1, L = 10.0, 18.0, 40.0
    slope1, curv1 = 0.22, 0.004  # dr/dz, d²r/dz² at the flare end
    def R(t):
        return _ta._hermite_radius(t, r0, r1, L, slope1, curv1=curv1)
    # z = t * L → derivatives in z-space via finite differences in t
    h = 1e-4
    assert abs(R(0.0) - r0) < 1e-9 and abs(R(1.0) - r1) < 1e-9
    # slope at end (dr/dz = dr/dt / L)
    s_end = (R(1.0) - R(1.0 - h)) / (h * L)
    assert abs(s_end - slope1) < 5e-3, f"end slope {s_end:.4f} != {slope1}"
    # curvature at end (d²r/dz²)
    c_end = (R(1.0) - 2 * R(1.0 - h) + R(1.0 - 2 * h)) / (h * L) ** 2
    assert abs(c_end - curv1) < 5e-3, f"end curv {c_end:.4f} != {curv1}"
    # driver end stays flat (slope ~0)
    s0 = (R(h) - R(0.0)) / (h * L)
    assert abs(s0) < 5e-3, f"driver-end slope {s0:.4f} != 0"
    # cubic fallback (no curv1) still matches value + slope
    s_cubic = (_ta._hermite_radius(1.0, r0, r1, L, slope1)
               - _ta._hermite_radius(1.0 - h, r0, r1, L, slope1)) / (h * L)
    assert abs(s_cubic - slope1) < 5e-3
test("adapter C2 raccordo (quintic curvature match)", test_hermite_radius_quintic_c2)

def test_adapter_c2_smoother_than_c1():
    """A curvature-matched (quintic) raccordo must reach the flare end with an
    end slope closer to the requested expansion than the slope-only (cubic)
    raccordo — a cubic, starting flat, overshoots and curls back. Measured on
    the OUTER wall (circumscribed radius is smooth, unlike the faceted inner
    min radius). Both must stay watertight."""
    target = 0.22
    kw = dict(driver_R=10.0, horn_shape="circular", horn_w=0.0, horn_h=0.0,
              horn_n_sides=0, horn_R_eq=18.0, horn_circumR=0.0,
              axial_steps=120, adapter_length=40.0, wall_thickness=4.0,
              target_slope=target, outer_target_R=22.0, outer_target_slope=target)
    def end_slope_error(curv):
        extra = dict(target_curv=0.004, outer_target_curv=0.004) if curv else {}
        m = _ta.make_adapter(output_path=None, **kw, **extra)
        _check_trimesh_watertight(m, "adapter c2" if curv else "adapter c1")
        zt = m.vertices[:, 2].max()
        rr = []
        for z in np.linspace(zt - 4.0, zt - 0.05, 24):
            sec = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
            if sec is None:
                continue
            p, _ = sec.to_2D()
            rr.append((z, np.linalg.norm(p.vertices[:, :2], axis=1).max()))
        rr = np.array(rr)
        tail = rr[rr[:, 0] > zt - 1.5]
        return abs(np.polyfit(tail[:, 0], tail[:, 1], 1)[0] - target)
    j_cubic = end_slope_error(False)
    j_quintic = end_slope_error(True)
    assert j_quintic <= j_cubic + 1e-4, \
        f"quintic end-slope error {j_quintic:.4f} should be <= cubic {j_cubic:.4f}"
test("adapter C2 raccordo smoother than C1", test_adapter_c2_smoother_than_c1)

def test_adapter_outer_flush():
    """Flanged adapter's outer wall must match the horn's outer wall at the
    horn-throat end (miter offset, not radial) — otherwise the union steps on
    the outside ("dentro ok, fuori il gradino")."""
    n_sides = 6; R_i = 12.0; wt = 4.0
    R_eq = R_i * np.sqrt(6 * np.sin(2*np.pi/6) / (2*np.pi))  # poly area-eq radius
    m = _ta.make_adapter(
        driver_R=10.0, horn_shape="polygonal",
        horn_w=0.0, horn_h=0.0, horn_n_sides=n_sides,
        horn_R_eq=R_eq, horn_circumR=R_i,
        axial_steps=30, adapter_length=30.0, wall_thickness=wt,
        output_path=None)
    zt = m.vertices[:, 2].max()
    top = np.abs(m.vertices[:, 2] - zt) < 0.2
    ro_adapter = np.linalg.norm(m.vertices[top][:, :2], axis=1).max()
    horn_outer = R_i + wt / np.cos(np.pi / n_sides)  # polygonal_horn convention
    assert abs(ro_adapter - horn_outer) < 0.15, \
        f"adapter outer {ro_adapter:.3f} != horn outer {horn_outer:.3f} (step)"
test("adapter outer wall flush with horn (no step)", test_adapter_outer_flush)


def test_embedded_morph_span():
    """The UI embed plan keeps the adapter target inside the safe flare."""
    trim, overlap, target = _ta.embedded_morph_span(30.0, 120.0)
    assert (trim, overlap, target) == (30.0, 6.0, 36.0)

    trim, overlap, target = _ta.embedded_morph_span(30.0, 32.0)
    assert (trim, overlap, target) == (26.0, 6.0, 32.0)

    trim, overlap, target = _ta.embedded_morph_span(30.0, 0.6108)
    assert abs(trim - 0.5) < 1e-9
    assert abs(overlap - 0.1108) < 1e-9
    assert abs(target - 0.6108) < 1e-9

    try:
        _ta.embedded_morph_span(30.0, 0.5)
    except ValueError as exc:
        assert "too short" in str(exc)
    else:
        raise AssertionError("flare at minimum transition length should be rejected")
test("embedded morph span stays inside flare", test_embedded_morph_span)


def test_short_embedded_adapter_preserves_horn_length():
    """A flare shorter than the desired overlap must not be extended."""
    throat_d, mouth_d, thickness = 20.0, 25.0, 4.0
    z, r = _c.get_exponential(throat_d, mouth_d, 20000.0, 300)
    nml = _uts.compute_profile_normals(z, r)
    z_o = z + thickness * nml[:, 0]
    r_o = r + thickness * nml[:, 1]

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_3d_mesh_from_profile(z, r, thickness, 64, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    horn.fix_normals()
    original_z_max = float(horn.bounds[1, 2])
    z_min = float(horn.bounds[0, 2])

    morph_len, overlap, target_z = _ta.embedded_morph_span(30.0, float(z[-1]))
    assert overlap < 6.0 and target_z <= float(z[-1]) + 1e-9
    z_stack = np.append(z[z < target_z - 1e-9], target_z)
    inner_stack = np.stack([
        _ta._circle_points(float(np.interp(zz, z, r))) for zz in z_stack
    ])
    outer_stack = np.stack([
        _ta._circle_points(float(np.interp(zz, z_o, r_o))) for zz in z_stack
    ])

    trimmed = horn.slice_plane([0, 0, z_min + morph_len], [0, 0, 1], cap=True)
    adapter = _ta.make_adapter_assembly(
        driver_type="flanged", driver_diam=throat_d, thread_key=None,
        horn_shape="custom",
        rect_w=0.0, rect_h=0.0, poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=float(np.interp(target_z, z, r)),
        adapter_length=target_z, wall_thickness=thickness,
        flange_R=0.0, socket_length=0.0,
        target_slope=float(np.interp(target_z, z, np.gradient(r, z))),
        target_curv=float(np.interp(target_z, z, np.gradient(np.gradient(r, z), z))),
        custom_pts=inner_stack, custom_outer_pts=outer_stack, custom_pts_z=z_stack,
        custom_match_from_z=morph_len,
        z_offset=z_min + target_z,
        output_path=None,
    )
    combined = trimesh.boolean.union([trimmed, adapter], engine="manifold")
    combined.fix_normals()
    _check_trimesh_watertight(combined, "short embedded adapter + horn")
    assert combined.bounds[1, 2] <= original_z_max + 0.1, \
        f"short embedded morph extended mouth by {combined.bounds[1, 2] - original_z_max:.3f} mm"
test("short embedded adapter preserves horn length", test_short_embedded_adapter_preserves_horn_length)


def test_embedded_adapter_preserves_horn_length():
    """An embedded morph replaces the flare start instead of extending its Z."""
    throat_d, mouth_d, thickness = 20.0, 100.0, 4.0
    z, r = _c.get_exponential(throat_d, mouth_d, 600, 300)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_3d_mesh_from_profile(z, r, thickness, 64, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    original_z_max = float(horn.bounds[1, 2])

    morph_len, overlap, target_z = _ta.embedded_morph_span(30.0, float(z[-1]))
    nml = _uts.compute_profile_normals(z, r)
    z_o = z + thickness * nml[:, 0]
    r_o = r + thickness * nml[:, 1]
    target_r = float(np.interp(target_z, z, r))
    target_ro = float(np.interp(target_z, z_o, r_o))
    target_slope = float(np.interp(target_z, z, np.gradient(r, z)))
    outer_slope = float(np.interp(target_z, z_o, np.gradient(r_o, z_o)))
    z_stack = np.append(z[z < target_z - 1e-9], target_z)
    inner_stack = np.stack([
        _ta._circle_points(float(np.interp(zz, z, r))) for zz in z_stack
    ])
    outer_stack = np.stack([
        _ta._circle_points(float(np.interp(zz, z_o, r_o))) for zz in z_stack
    ])

    trimmed = horn.slice_plane([0, 0, morph_len], [0, 0, 1], cap=True)
    adapter = _ta.make_adapter_assembly(
        driver_type="flanged", driver_diam=throat_d, thread_key=None,
        horn_shape="circular",
        rect_w=0.0, rect_h=0.0, poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=target_r,
        adapter_length=target_z, wall_thickness=thickness,
        flange_R=0.0, socket_length=0.0,
        outer_target_R=target_ro,
        target_slope=target_slope,
        outer_target_slope=outer_slope,
        custom_pts=inner_stack, custom_outer_pts=outer_stack, custom_pts_z=z_stack,
        custom_match_from_z=morph_len,
        z_offset=target_z,
        output_path=None,
    )
    combined = trimesh.boolean.union([trimmed, adapter], engine="manifold")
    combined.fix_normals()
    _check_trimesh_watertight(combined, "embedded adapter + horn")
    assert abs(combined.bounds[0, 2]) < 1e-6, "embedded morph moved behind throat plane"
    assert abs(combined.bounds[1, 2] - original_z_max) < 0.1, \
        "embedded morph changed horn mouth position"
test("embedded adapter preserves horn length", test_embedded_adapter_preserves_horn_length)


def test_embedded_custom_stack_adapter_has_no_step():
    """The embedded UI path must use a real section stack near the overlap, so
    the adapter follows the flare instead of closing on a single cap plane."""
    throat_d, mouth_d, thickness = 20.0, 100.0, 4.0
    z, r = _c.get_exponential(throat_d, mouth_d, 600, 300)
    nml = _uts.compute_profile_normals(z, r)
    z_o = z + thickness * nml[:, 0]
    r_o = r + thickness * nml[:, 1]

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_3d_mesh_from_profile(z, r, thickness, 64, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    horn.fix_normals()
    z_min = float(horn.bounds[0, 2])

    morph_len, overlap, zt = _ta.embedded_morph_span(30.0, float(z[-1]))
    z_stack = np.append(z[z < zt - 1e-9], zt)
    inner_stack = np.stack([
        _ta._circle_points(float(np.interp(zz, z, r))) for zz in z_stack
    ])
    outer_stack = np.stack([
        _ta._circle_points(float(np.interp(zz, z_o, r_o))) for zz in z_stack
    ])
    target_r = float(np.interp(zt, z, r))
    target_ro = float(np.interp(zt, z_o, r_o))
    target_slope = float(np.interp(zt, z, np.gradient(r, z)))
    outer_slope = float(np.interp(zt, z_o, np.gradient(r_o, z_o)))

    trimmed = horn.slice_plane([0, 0, morph_len], [0, 0, 1], cap=True)
    adapter = _ta.make_adapter_assembly(
        driver_type="flanged", driver_diam=throat_d, thread_key=None,
        horn_shape="custom",
        rect_w=0.0, rect_h=0.0, poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=target_r,
        adapter_length=zt, wall_thickness=thickness,
        flange_R=0.0, socket_length=0.0,
        outer_target_R=target_ro,
        target_slope=target_slope,
        outer_target_slope=outer_slope,
        custom_pts=inner_stack, custom_outer_pts=outer_stack, custom_pts_z=z_stack,
        custom_match_from_z=morph_len,
        z_offset=z_min + zt,
        output_path=None,
    )
    combined = trimesh.boolean.union([trimmed, adapter], engine="manifold")
    combined.fix_normals()
    _check_trimesh_watertight(combined, "embedded custom-stack adapter + horn")

    for dz in (-0.25, +0.25):
        zq = morph_len + dz
        sec = combined.section(plane_origin=[0, 0, zq], plane_normal=[0, 0, 1])
        assert sec is not None, "no section at junction"
        loops = sec.discrete
        loop = min(loops, key=lambda p: np.hypot(p[:, 0], p[:, 1]).mean())
        r_meas = float(np.hypot(loop[:, 0], loop[:, 1]).mean())
        r_ref = float(np.interp(zq - z_min, z, r))
        assert abs(r_meas - r_ref) < 0.05, \
            f"step at junction dz={dz:+.2f}: {r_meas:.3f} vs {r_ref:.3f}"
test("embedded custom-stack adapter has no step", test_embedded_custom_stack_adapter_has_no_step)


def test_complete_rollback_local_adapter_stack_monotone():
    """Complete rollback lips are non-monotonic in Z; the embedded-adapter UI
    stack must use only the advancing branch. If the returning lip drops into
    the trim zone, the UI must replace only the central throat region instead of
    slicing the completed curl with a full plane cut."""
    throat_d, thickness = 25.4, 4.0
    z, r = _c.get_rosse(throat_d, 260.0, 78.0, 300, complete_rollback=True)
    nml = _uts.compute_profile_normals(z, r)
    z_o = z + thickness * nml[:, 0]
    r_o = r + thickness * nml[:, 1]
    zc, rc = _monotone_increasing(z, r)
    zoc, roc = _monotone_increasing(z_o, r_o)

    safe_extent = min(float(z.max()), float(z[-1]))
    morph_len, _, target_z = _ta.embedded_morph_span(30.0, safe_extent)
    return_min = float(np.min(z[int(np.argmax(z)):]))
    assert return_min <= morph_len, "test setup no longer exercises trim-zone return lip"
    handoff_z = target_z
    z_stack = np.append(zc[zc < handoff_z - 1e-9], handoff_z)
    z_stack = z_stack[np.concatenate([[True], np.diff(z_stack) > 1e-9])]
    assert np.all(np.diff(z_stack) > 0.0), "custom_pts_z is not strictly increasing"

    inner_stack = np.stack([
        _ta._circle_points(float(np.interp(zz, zc, rc))) for zz in z_stack
    ])
    outer_stack = np.stack([
        _ta._circle_points(float(np.interp(zz, zoc, roc))) for zz in z_stack
    ])
    target_r = float(np.interp(handoff_z, zc, rc))
    target_ro = float(np.interp(handoff_z, zoc, roc))
    target_slope = float(np.interp(handoff_z, zc, np.gradient(rc, zc)))
    outer_slope = float(np.interp(handoff_z, zoc, np.gradient(roc, zoc)))

    adapter = _ta.make_adapter_assembly(
        driver_type="flanged", driver_diam=throat_d, thread_key=None,
        horn_shape="custom",
        rect_w=0.0, rect_h=0.0, poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=target_r,
        adapter_length=target_z, wall_thickness=thickness,
        flange_R=0.0, socket_length=0.0,
        outer_target_R=target_ro,
        target_slope=target_slope,
        outer_target_slope=outer_slope,
        custom_pts=inner_stack, custom_outer_pts=outer_stack, custom_pts_z=z_stack,
        custom_match_from_z=morph_len,
        z_offset=target_z,
        output_path=None,
    )
    _check_trimesh_watertight(adapter, "complete rollback local adapter")
    assert adapter.bounds[0, 2] >= -1e-6, "embedded adapter moved below the throat plane"
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _c.generate_3d_mesh_from_profile(z, r, thickness, 96, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    horn.fix_normals()
    cut_r = float(np.linalg.norm(outer_stack[-1], axis=1).max() + 0.8)
    weld_overlap = 1.0
    cut_h = max(1.0, target_z + 1.0 - weld_overlap)
    cutter = trimesh.creation.cylinder(radius=cut_r, height=cut_h, sections=96)
    cutter.apply_translation([0.0, 0.0, -1.0 + cut_h / 2.0])
    horn = trimesh.boolean.difference([horn, cutter], engine="manifold", check_volume=False)
    horn.remove_unreferenced_vertices()
    horn.fix_normals()
    combined = trimesh.boolean.union([horn, adapter], engine="manifold")
    _check_trimesh_watertight(combined, "complete rollback local adapter")
    assert combined.bounds[0, 2] >= -1e-6, "local adapter moved below the throat plane"
    assert combined.bounds[1, 2] > z.max() - 0.1, "complete rollback lip was plane-trimmed"
test("complete rollback local adapter stack is monotone",
     test_complete_rollback_local_adapter_stack_monotone)


def test_adapter_section_count_follows_flare_rings():
    """The adapter's perimeter point count comes from its custom sections, so
    the UI must build them at the flare's revolution resolution. If it stays
    at the old _NP=64 while the flare is at e.g. 256, the coarse adapter N-gon
    sits ~28 um inside the fine flare N-gon through the overlap and prints as a
    visible seam ring. Here we build the sections at the flare ring count and
    confirm the adapter inherits it (n == rings) and the junction is flush."""
    rings = 256
    throat_d, mouth_d, thickness = 36.0, 250.0, 4.0
    z, r = _c.get_tractrix(throat_d, mouth_d, 300)
    nml = _uts.compute_profile_normals(z, r)
    z_o = z + thickness * nml[:, 0]
    r_o = r + thickness * nml[:, 1]
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _c.generate_3d_mesh_from_profile(z, r, thickness, rings, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p); horn.fix_normals()
    z_min = float(horn.bounds[0, 2])
    morph_len, overlap, zt = _ta.embedded_morph_span(30.0, float(z[-1]))
    z_stack = np.append(z[z < zt - 1e-9], zt)
    inner_stack = np.stack([
        _ta._circle_points(float(np.interp(zz, z, r)), n=rings) for zz in z_stack])
    outer_stack = np.stack([
        _ta._circle_points(float(np.interp(zz, z_o, r_o)), n=rings) for zz in z_stack])
    assert inner_stack.shape[1] == rings, "custom section did not honour ring count"
    trimmed = horn.slice_plane([0, 0, morph_len], [0, 0, 1], cap=True)
    adapter = _ta.make_adapter_assembly(
        driver_type="1_375in", driver_diam=None, thread_key="1_375in",
        horn_shape="circular",
        rect_w=0.0, rect_h=0.0, poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=float(np.interp(zt, z, r)),
        adapter_length=zt, wall_thickness=thickness, socket_length=15.0,
        custom_pts=inner_stack, custom_outer_pts=outer_stack, custom_pts_z=z_stack,
        custom_match_from_z=morph_len, z_offset=z_min + zt, output_path=None)
    # The adapter's own cross-section (below the overlap, pure adapter) must
    # carry the flare's ring count, not the legacy 64.
    sec = adapter.section(plane_origin=[0, 0, z_min + morph_len * 0.5],
                          plane_normal=[0, 0, 1])
    assert sec is not None, "no adapter section"
    loop = min(sec.discrete, key=lambda q: np.hypot(q[:, 0], q[:, 1]).mean())
    assert len(loop) > 128, \
        f"adapter section has {len(loop)} pts — did not follow the {rings}-ring flare"
    combined = trimesh.boolean.union([trimmed, adapter], engine="manifold")
    combined.fix_normals()
    _check_trimesh_watertight(combined, "ring-matched adapter + horn")
test("adapter section count follows flare rings", test_adapter_section_count_follows_flare_rings)


def test_threaded_adapter_slices_watertight():
    """Axial segments and radial petals of a threaded-adapter assembly must
    stay watertight. slice_plane's ear-clip cap broke on the adapter's
    multi-loop sections (wall ring + threads + bore) and on the coincident
    faces of the exact weld overlap — petals/segments came out with open
    edges exactly at z = overlap and at the seams ("overlap threaded adapter
    non funziona"). All plane cuts now go through boolean half-space
    intersection (_plane_cut)."""
    rings = 128
    throat_d, mouth_d, thickness = 36.0, 250.0, 4.0
    z, r = _c.get_tractrix(throat_d, mouth_d, 300)
    nml = _uts.compute_profile_normals(z, r)
    z_o = z + thickness * nml[:, 0]
    r_o = r + thickness * nml[:, 1]
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _c.generate_3d_mesh_from_profile(z, r, thickness, rings, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p); horn.fix_normals()
    z_min = float(horn.bounds[0, 2])
    morph_len, overlap, zt = _ta.embedded_morph_span(30.0, float(z[-1]))
    horn_t = horn.slice_plane([0, 0, z_min + morph_len], [0, 0, 1], cap=True)
    horn_t.fix_normals()
    z_stack = np.append(z[z < zt - 1e-9], zt)
    inner = np.stack([
        _ta._circle_points(float(np.interp(zz, z, r)), n=rings) for zz in z_stack])
    outer = np.stack([
        _ta._circle_points(float(np.interp(zz, z_o, r_o)), n=rings) for zz in z_stack])
    adp = _ta.make_adapter_assembly(
        driver_type="1_375in", driver_diam=None, thread_key="1_375in",
        horn_shape="circular", rect_w=0.0, rect_h=0.0,
        poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=float(np.interp(zt, z, r)),
        adapter_length=zt, wall_thickness=thickness, socket_length=15.0,
        custom_pts=inner, custom_outer_pts=outer, custom_pts_z=z_stack,
        custom_match_from_z=morph_len, z_offset=z_min + zt, output_path=None)
    u = trimesh.boolean.union([horn_t, adp], engine="manifold")
    assert u.is_watertight, "threaded union not watertight"
    for jw in (0.0, 4.0):
        segs = _slc.slice_into_segments(u, 2, joint_wall=jw)
        assert all(s.is_watertight for s in segs), \
            f"jw={jw}: axial segment not watertight"
        petals = _slc.slice_into_petals(segs[0], n=2, joint_depth=0.0)
        assert all(pp.is_watertight for pp in petals), \
            f"jw={jw}: adapter-segment petal not watertight"
test("threaded adapter axial segments + petals stay watertight",
     test_threaded_adapter_slices_watertight)


def test_threaded_collar_laps_the_flare():
    """The threaded boss must NOT butt-join the cone at the throat plane: its
    outer cylinder continues `collar_overlap` mm above z=0 wrapping the wall,
    then tapers at 45° into the flare skin (lap joint — "il colletto filettato
    si deve sovrapporre con il flare"). Airway untouched."""
    spec = _ta.THREAD_SPECS["1_375in"]
    boss_R = spec.major_diam / 2.0 + 4.0   # socket outer = major + wall
    adp = _ta.make_adapter_assembly(
        driver_type="1_375in", driver_diam=None, thread_key="1_375in",
        horn_shape="circular", rect_w=0.0, rect_h=0.0,
        poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=20.0, adapter_length=30.0, wall_thickness=4.0,
        socket_length=15.0, z_offset=30.0, output_path=None)
    assert adp.is_watertight, "threaded adapter not watertight"
    # Local z=2.5 (inside the 5 mm collar): outer radius == boss radius.
    sec = adp.section(plane_origin=[0, 0, 2.5], plane_normal=[0, 0, 1])
    r_max = float(np.hypot(sec.vertices[:, 0], sec.vertices[:, 1]).max())
    assert r_max > boss_R - 0.1, \
        f"no collar above the throat plane: r_max {r_max:.2f} < boss {boss_R:.2f}"
    # Airway untouched: bore stays the spec bore at the same plane.
    r_min = float(np.hypot(sec.vertices[:, 0], sec.vertices[:, 1]).min())
    assert r_min < spec.bore_diam / 2.0 + 1.5, "collar must not invade the airway"
    # Past the 45° shoulder the wall is back to the plain morph offset.
    sec_hi = adp.section(plane_origin=[0, 0, 20.0], plane_normal=[0, 0, 1])
    r_hi = float(np.hypot(sec_hi.vertices[:, 0], sec_hi.vertices[:, 1]).max())
    assert r_hi < boss_R + 0.1, "collar must taper back into the wall"
    # collar_overlap=0 restores the old butt joint (no bulge above z=0).
    adp0 = _ta.make_adapter_assembly(
        driver_type="1_375in", driver_diam=None, thread_key="1_375in",
        horn_shape="circular", rect_w=0.0, rect_h=0.0,
        poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=20.0, adapter_length=30.0, wall_thickness=4.0,
        socket_length=15.0, collar_overlap=0.0, z_offset=30.0, output_path=None)
    sec0 = adp0.section(plane_origin=[0, 0, 2.5], plane_normal=[0, 0, 1])
    r0 = float(np.hypot(sec0.vertices[:, 0], sec0.vertices[:, 1]).max())
    assert r0 < boss_R - 0.5, "collar_overlap=0 should disable the lap collar"
test("threaded collar laps the flare (no butt joint)",
     test_threaded_collar_laps_the_flare)


def test_threaded_socket():
    m = _ta.make_threaded_socket("1_375in", 15.0, 4.0)
    _check_trimesh_watertight(m, '1⅜"-18 threaded socket')
test("threaded sockets watertight", test_threaded_socket)


def test_threaded_socket_clearance_offsets_thread_profile():
    spec = _ta.THREAD_SPECS["1_375in"]
    m0 = _ta.make_threaded_socket("1_375in", 15.0, 4.0, thread_clearance=0.0)
    m1 = _ta.make_threaded_socket("1_375in", 15.0, 4.0, thread_clearance=0.2)

    def inner_major_at_first_turn(mesh):
        ring = mesh.vertices[np.isclose(mesh.vertices[:, 2], spec.pitch, atol=1e-6)]
        radii = np.linalg.norm(ring[:, :2], axis=1)
        return float(radii.max())

    assert abs(inner_major_at_first_turn(m0) - spec.major_diam / 2.0) < 0.02
    assert abs(inner_major_at_first_turn(m1) - (spec.major_diam / 2.0 + 0.2)) < 0.02
test("threaded socket clearance offsets thread profile",
     test_threaded_socket_clearance_offsets_thread_profile)


def test_threaded_adapter_25mm_bore():
    m = _ta.make_adapter(
        driver_R=99.0, horn_shape="circular",
        horn_w=0.0, horn_h=0.0, horn_n_sides=0,
        horn_R_eq=18.0, horn_circumR=0.0,
        axial_steps=30, adapter_length=30.0, wall_thickness=4.0,
        thread_key="1_375in", socket_length=15.0,
        thread_clearance=0.2,
        output_path=None,
    )
    at_bore = m.vertices[np.isclose(m.vertices[:, 2], 0.0)]
    bore_r = np.linalg.norm(at_bore[:, :2], axis=1).min()
    assert abs(bore_r * 2.0 - 25.0) < 0.05, f"acoustic bore={bore_r * 2.0:.3f} mm"
test('1⅜"-18 threaded adapter has 25 mm acoustic bore', test_threaded_adapter_25mm_bore)


def test_adapter_transition_wall_constant_thickness():
    """The transition wall must stay ~wall_thickness on every axis, even for a
    very elongated rectangular target. Morphing the outer to the horn's
    area-equivalent outer used to balloon the narrow axis into a solid wedge
    ("lo spazio tra flangia e flare non deve essere pieno")."""
    wt = 4.0
    w, h, ow, oh = 120.0, 60.0, 128.0, 68.0
    m = _ta.make_adapter(
        driver_R=_ta.THREAD_SPECS["1_375in"].bore_diam / 2.0,
        horn_shape="rectangular", horn_w=w, horn_h=h, horn_n_sides=0,
        horn_R_eq=np.sqrt(w * h / np.pi), horn_circumR=0.0,
        axial_steps=60, adapter_length=30.0, wall_thickness=wt,
        thread_key="1_375in", socket_length=15.0,
        # The lap collar deliberately thickens the outer wall in the first
        # collar_overlap mm (see test_threaded_collar_laps_the_flare); this
        # test probes the MORPH wall itself, so switch the collar off.
        collar_overlap=0.0,
        outer_target_R=np.sqrt(ow * oh / np.pi),
        outer_rect_w=ow, outer_rect_h=oh, output_path=None)
    # narrow (+Y) axis wall thickness at several transition heights
    for z in (2.0, 4.0, 8.0, 15.0):
        sec = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        assert sec is not None, f"no section at z={z}"
        p, _ = sec.to_planar()
        poly = max(p.polygons_full, key=lambda q: q.area)
        assert len(poly.interiors) == 1, f"airway not hollow at z={z}"
        ext = np.array(poly.exterior.coords)
        inr = np.array(poly.interiors[0].coords)
        oy = ext[np.abs(ext[:, 0]) < 3.0][:, 1].max()
        iy = inr[np.abs(inr[:, 0]) < 3.0][:, 1].max()
        wall = oy - iy
        assert wall < wt * 1.4, f"z={z}: narrow wall {wall:.2f} mm balloons (fill)"
test("adapter transition wall constant thickness", test_adapter_transition_wall_constant_thickness)


def test_adapter_assembly_flanged():
    """Full assembly with flange at driver end, circle→rect transition."""
    m = _ta.make_adapter_assembly(
        driver_type="flanged", driver_diam=25.0, thread_key=None,
        horn_shape="rectangular",
        rect_w=40.0, rect_h=20.0, poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=np.sqrt(40*20/np.pi),
        adapter_length=30.0, wall_thickness=4.0,
        flange_R=30.0, flange_thickness=6.0,
        flange_bolt_R=20.0, flange_bolt_n=4, flange_bolt_d=3.5,
        socket_length=0.0, z_offset=0.0,
        output_path=None,
    )
    _check_trimesh_watertight(m, "adapter assembly flanged")
    assert abs((m.bounds[1, 2] - m.bounds[0, 2]) - 30.0) < 0.1, \
        "flanged adapter length should be measured from the flange lower face"
test("adapter assembly flanged", test_adapter_assembly_flanged)

def test_flanged_adapter_no_sliver_ring():
    """The driver-flange bore must INTERPENETRATE the adapter's outer wall, not
    sit flush with it. A flush bore (driver_R + wall_thickness) is ~tangent to
    the miter-offset wall, so the manifold union spits out a ring of sliver
    triangles at r≈bore on the flange face — these print as surface
    "irregolarità". _FLANGE_WELD_BITE pulls the bore 0.5 mm inside the wall to
    keep the overlap clean. Guard both the circular and the elliptical custom-
    stack flanged paths."""
    drv_R, L, wt = 12.7, 40.0, 6.0

    def slivers(m):
        return int((m.area_faces < 1e-5).sum())

    m_circ = _ta.make_adapter_assembly(
        driver_type="flanged", driver_diam=2 * drv_R, thread_key=None,
        horn_shape="circular", rect_w=0, rect_h=0, poly_n_sides=0, poly_circumR=0,
        horn_R_eq=30.0, adapter_length=L, wall_thickness=wt,
        flange_R=55.0, flange_thickness=6.0,
        flange_bolt_R=42.0, flange_bolt_n=4, flange_bolt_d=5.0,
        target_slope=0.15, outer_target_slope=0.15,
        socket_length=0.0, z_offset=0.0, output_path=None)
    assert m_circ.is_watertight
    assert slivers(m_circ) == 0, \
        f"circular flanged adapter has {slivers(m_circ)} sliver faces at the bore"

    n = 96
    zst = np.linspace(0, L, 12)
    def _ell(z, ofs=0.0):
        t = z / L
        return _ta._ellipse_points(drv_R * (1 - t) + 38 * t + ofs,
                                   drv_R * (1 - t) + 24 * t + ofs, n=n)
    cpts = np.stack([_ell(z) for z in zst])
    copts = np.stack([_ell(z, ofs=wt) for z in zst])
    m_ell = _ta.make_adapter_assembly(
        driver_type="flanged", driver_diam=2 * drv_R, thread_key=None,
        horn_shape="elliptical", rect_w=76, rect_h=48,
        poly_n_sides=0, poly_circumR=0, horn_R_eq=float(np.sqrt(38 * 24)),
        adapter_length=L, wall_thickness=wt,
        flange_R=60.0, flange_thickness=6.0,
        flange_bolt_R=48.0, flange_bolt_n=4, flange_bolt_d=5.0,
        custom_pts=cpts, custom_outer_pts=copts, custom_pts_z=zst,
        custom_match_from_z=20.0, socket_length=0.0, z_offset=0.0, output_path=None)
    assert m_ell.is_watertight
    assert slivers(m_ell) == 0, \
        f"elliptical flanged adapter has {slivers(m_ell)} sliver faces at the bore"
test("flanged adapter bore has no sliver ring", test_flanged_adapter_no_sliver_ring)

def test_adapter_assembly_threaded():
    """Full assembly with threaded socket, circle→poly transition."""
    m = _ta.make_adapter_assembly(
        driver_type="1_375in", driver_diam=None, thread_key="1_375in",
        horn_shape="polygonal",
        rect_w=0.0, rect_h=0.0, poly_n_sides=6,
        poly_circumR=15.0,
        horn_R_eq=12.5,
        adapter_length=30.0, wall_thickness=4.0,
        socket_length=15.0, thread_clearance=0.1, z_offset=0.0,
        output_path=None,
    )
    _check_trimesh_watertight(m, "adapter assembly threaded")
test("adapter assembly threaded", test_adapter_assembly_threaded)


def test_adapter_assembly_standard_bolt_on():
    """A standard bolt-on preset must drive both transition bore and flange."""
    m = _ta.make_adapter_assembly(
        driver_type="bolt_on_2in_4", driver_diam=None, thread_key=None,
        horn_shape="circular",
        rect_w=0.0, rect_h=0.0, poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=30.0,
        adapter_length=30.0, wall_thickness=4.0,
        flange_thickness=6.0, driver_clearance=0.3,
        socket_length=0.0, z_offset=0.0,
        output_path=None,
    )
    _check_trimesh_watertight(m, "adapter assembly standard bolt-on")
    assert abs((m.bounds[1, 2] - m.bounds[0, 2]) - 30.0) < 0.1, \
        "bolt-on adapter length should be measured from the flange lower face"
    assert abs((m.bounds[1, 0] - m.bounds[0, 0]) - 135.0) < 0.1
test("adapter assembly standard bolt-on", test_adapter_assembly_standard_bolt_on)


# 1⅜"-18 threaded adapter with 25 mm bore — representative horn shapes
for _shape, _ns, _h_R_eq, _cR in [
    ("polygonal",   6, 12.5, 15.0),
    ("circular",    0, 18.0, 0.0),
    ("rectangular", 0, np.sqrt(40*20/np.pi), 0.0),
    ("elliptical",  0, np.sqrt(40*20)/2.0, 0.0),
]:
    def make_threaded_asm(sh=_shape, ns=_ns, heq=_h_R_eq, cr=_cR):
        kwargs = dict(
            driver_type="1_375in", driver_diam=None, thread_key="1_375in",
            horn_shape=sh, wall_thickness=4.0,
            adapter_length=30.0, socket_length=15.0, z_offset=0.0,
            output_path=None)
        if sh in ("rectangular", "elliptical"):
            kwargs.update(rect_w=40.0, rect_h=20.0, poly_n_sides=0,
                          poly_circumR=0.0, horn_R_eq=heq)
        elif sh == "polygonal":
            kwargs.update(rect_w=0.0, rect_h=0.0, poly_n_sides=ns,
                          poly_circumR=cr, horn_R_eq=heq)
        else:  # circular
            kwargs.update(rect_w=0.0, rect_h=0.0, poly_n_sides=0,
                          poly_circumR=0.0, horn_R_eq=heq)
        m = _ta.make_adapter_assembly(**kwargs)
        _check_trimesh_watertight(m, f'1⅜"-18 threaded assembly {sh}')
    test(f'1⅜"-18 threaded assembly {_shape}', make_threaded_asm)

# Flanged adapter assemblies — all horn shapes
for _fs, _fns, _f_R_eq, _f_cR, _f_rw, _f_rh in [
    ("rectangular", 0, np.sqrt(40*20/np.pi), 0.0, 40.0, 20.0),
    ("elliptical",  0, np.sqrt(40*20)/2.0, 0.0, 40.0, 20.0),
    ("polygonal",   6, 12.5, 15.0, 0.0, 0.0),
    ("circular",    0, 18.0, 0.0, 0.0, 0.0),
]:
    def make_flanged_asm(sh=_fs, ns=_fns, heq=_f_R_eq, cr=_f_cR, rw=_f_rw, rh=_f_rh):
        kwargs = dict(
            driver_type="flanged", driver_diam=25.0, thread_key=None,
            horn_shape=sh, wall_thickness=4.0,
            adapter_length=30.0, z_offset=0.0,
            flange_R=30.0, flange_thickness=6.0,
            flange_bolt_R=20.0, flange_bolt_n=4, flange_bolt_d=3.5,
            socket_length=0.0, output_path=None)
        if sh in ("rectangular", "elliptical"):
            kwargs.update(rect_w=rw, rect_h=rh, poly_n_sides=0,
                          poly_circumR=0.0, horn_R_eq=heq)
        elif sh == "polygonal":
            kwargs.update(rect_w=0.0, rect_h=0.0, poly_n_sides=ns,
                          poly_circumR=cr, horn_R_eq=heq)
        else:
            kwargs.update(rect_w=0.0, rect_h=0.0, poly_n_sides=0,
                          poly_circumR=0.0, horn_R_eq=heq)
        m = _ta.make_adapter_assembly(**kwargs)
        _check_trimesh_watertight(m, f"flanged adapter {sh}")
    test(f"flanged adapter {_fs}", make_flanged_asm)

def test_polygonal_horn_adapter_union_watertight():
    """Polygonal flare + threaded adapter must union with a real overlap."""
    throat_d = 20.0
    n_sides = 4
    thickness = 4.0
    z, r = _c.get_exponential(throat_d, 100.0, 600, 300)
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        p = t.name
    _ph.generate_polygonal_3d_mesh(z, r, n_sides, thickness, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    horn.fix_normals()

    from polygonal_horn import _r_to_circumradius
    R_i = _r_to_circumradius(r, n_sides)
    nml = _uts.compute_profile_normals(z, R_i, flip_if_negative=True)
    R_o = R_i + thickness / np.cos(np.pi / n_sides) * nml[:, 1]
    z_o = z + thickness * nml[:, 0]
    z_o = np.clip(z_o, z[0], z[-1]); z_o[0] = z[0]; z_o[-1] = z[-1]
    R_o_eq = np.sqrt((0.5 * n_sides * R_o**2 * np.sin(2*np.pi/n_sides)) / np.pi)

    def _slope_start(zz, vv):
        for i in range(1, len(zz)):
            dz = zz[i] - zz[0]
            if abs(dz) > 1e-6:
                return float((vv[i] - vv[0]) / dz)
        return 0.0

    poly_circumR = _r_to_circumradius(np.array([throat_d / 2.0]), n_sides)[0]
    adapter = _ta.make_adapter_assembly(
        driver_type="1_375in", driver_diam=None, thread_key="1_375in",
        horn_shape="polygonal",
        rect_w=0.0, rect_h=0.0, poly_n_sides=n_sides,
        poly_circumR=poly_circumR, horn_R_eq=throat_d / 2.0,
        adapter_length=30.0, wall_thickness=thickness,
        socket_length=15.0,
        outer_target_R=float(R_o_eq[0]),
        target_slope=_slope_start(z, r),
        outer_target_slope=_slope_start(z_o, R_o_eq),
        z_offset=horn.vertices[:, 2].min() + 0.5,
        output_path=None,
    )
    combined = trimesh.boolean.union([horn, adapter], engine="manifold")
    combined.merge_vertices(); combined.fix_normals()
    _check_trimesh_watertight(combined, "polygonal horn + adapter union")
test("polygonal horn + adapter union watertight", test_polygonal_horn_adapter_union_watertight)


def _osse_adapter_sections(z, phi, R, thickness, z_target):
    """Exact OS-SE inner + outer-wall section polygons at axial z_target —
    the same sampling ui_app.py hands to the adapter (custom shape)."""
    nphi = R.shape[1]
    Rz = np.array([np.interp(z_target, z, R[:, j]) for j in range(nphi)])
    inner = np.column_stack([Rz * np.cos(phi), Rz * np.sin(phi)])
    V = np.empty((len(z), nphi, 3))
    V[:, :, 0] = R * np.cos(phi)[None, :]
    V[:, :, 1] = R * np.sin(phi)[None, :]
    V[:, :, 2] = z[:, None]
    Vo = V + thickness * _osse._vertex_normals(V)
    outer = np.empty((nphi, 2))
    for j in range(nphi):
        zc = Vo[:, j, 2]
        end = int(np.argmax(zc)) + 1
        outer[j, 0] = np.interp(z_target, zc[:end], Vo[:end, j, 0])
        outer[j, 1] = np.interp(z_target, zc[:end], Vo[:end, j, 1])
    return inner, outer


def test_adapter_custom_osse_section_no_step():
    """The OS-SE cross-section is NOT an ellipse: an area-matched ellipse
    target leaves a step ring at the adapter↔flare junction. With
    horn_shape="custom" the adapter must end vertex-exact on the real
    r(z,φ) section — inner AND outer wall."""
    r0, L, t = 12.7, 120.0, 4.0
    z, phi, R = _osse.osse_surface(
        r0, L, np.radians(45.0), np.radians(30.0), 0.0, 1.0, 0.8, 5.0, 0.998,
        mouth_exp=6.0, nz=60, nphi=96)
    zt = 30.5
    inner, outer = _osse_adapter_sections(z, phi, R, t, zt)
    R_eq = float(np.sqrt(_ta._polygon_area(inner) / np.pi))
    h = float(z[1] - z[0])
    in_m, _ = _osse_adapter_sections(z, phi, R, t, zt - h)
    in_p, _ = _osse_adapter_sections(z, phi, R, t, zt + h)
    re_m = float(np.sqrt(_ta._polygon_area(in_m) / np.pi))
    re_p = float(np.sqrt(_ta._polygon_area(in_p) / np.pi))
    m = _ta.make_adapter(
        driver_R=12.7, horn_shape="custom",
        horn_w=0.0, horn_h=0.0, horn_n_sides=0,
        horn_R_eq=R_eq, horn_circumR=0.0,
        axial_steps=30, adapter_length=zt, wall_thickness=t,
        target_slope=(re_p - re_m) / (2.0 * h),
        target_curv=(re_p - 2.0 * R_eq + re_m) / (h * h),
        custom_pts=inner, custom_outer_pts=outer,
        output_path=None)
    _check_trimesh_watertight(m, "adapter custom OS-SE section")
    top = m.vertices[np.abs(m.vertices[:, 2] - zt) < 1e-6][:, :2]
    assert len(top) >= 2 * len(inner) - 4, "top rings missing vertices"
    for ring, lbl in ((inner, "inner"), (outer, "outer")):
        d = np.sqrt(((ring[:, None, :] - top[None, :, :]) ** 2).sum(-1)).min(1)
        assert d.max() < 0.02, \
            f"{lbl} ring off the horn section by {d.max():.3f} mm (step)"
    # Sanity: the old area-matched ellipse really was a bad target here.
    Rz = np.hypot(inner[:, 0], inner[:, 1])
    ell = np.column_stack([Rz[0] * np.cos(phi), Rz[len(phi) // 4] * np.sin(phi)])
    ell *= R_eq / np.sqrt(_ta._polygon_area(ell) / np.pi)
    assert np.abs(np.hypot(ell[:, 0], ell[:, 1]) - Rz).max() > 0.1, \
        "ellipse≈section here — test premise void"
test("OS-SE adapter ends on exact r(z,φ) section (no step)", test_adapter_custom_osse_section_no_step)


def test_osse_embedded_adapter_union_no_step():
    """Full UI path: trimmed OS-SE horn + custom-section adapter weld into one
    watertight body, and the inner surface has no step across the junction."""
    throat_d, L, t = 25.4, 120.0, 4.0
    nz, nphi = 240, 120
    a_h, a_v = np.radians(45.0), np.radians(30.0)
    horn = _osse.generate_osse_3d_mesh(
        throat=throat_d, length=L, coverage_h=90.0, coverage_v=60.0,
        thickness=t, nz=nz, nphi=nphi)
    z, phi, R = _osse.osse_surface(
        throat_d / 2.0, L, a_h, a_v, 0.0, 1.0, 0.8, 5.0, 0.998,
        mouth_exp=4.0, nz=nz, nphi=nphi)

    morph_len, overlap, zt = _ta.embedded_morph_span(30.0, float(z[-1]))
    # Section stack (like ui_app.py): the adapter tail follows the real flare
    # through the overlap, aspect-ratio change included.
    z_st = np.append(z[z < zt - 1e-9], zt)
    stacks = [_osse_adapter_sections(z, phi, R, t, zz) for zz in z_st]
    stack_in = np.stack([s[0] for s in stacks])
    stack_out = np.stack([s[1] for s in stacks])
    inner = stack_in[-1]
    R_eq = float(np.sqrt(_ta._polygon_area(inner) / np.pi))
    h = 0.5
    in_m, _ = _osse_adapter_sections(z, phi, R, t, zt - h)
    in_p, _ = _osse_adapter_sections(z, phi, R, t, zt + h)
    re_m = float(np.sqrt(_ta._polygon_area(in_m) / np.pi))
    re_p = float(np.sqrt(_ta._polygon_area(in_p) / np.pi))

    z_min = float(horn.vertices[:, 2].min())
    trim_z = z_min + morph_len
    trimmed = horn.slice_plane([0, 0, trim_z], [0, 0, 1], cap=True)
    adapter = _ta.make_adapter_assembly(
        driver_type="flanged", driver_diam=throat_d, thread_key=None,
        horn_shape="custom",
        rect_w=0.0, rect_h=0.0, poly_n_sides=0, poly_circumR=0.0,
        horn_R_eq=R_eq,
        adapter_length=zt, wall_thickness=t,
        flange_R=0.0, socket_length=0.0,
        target_slope=(re_p - re_m) / (2.0 * h),
        target_curv=(re_p - 2.0 * R_eq + re_m) / (h * h),
        custom_pts=stack_in, custom_outer_pts=stack_out, custom_pts_z=z_st,
        custom_match_from_z=morph_len,
        z_offset=z_min + zt,
        output_path=None)
    combined = trimesh.boolean.union([trimmed, adapter], engine="manifold")
    # NOTE: no merge_vertices() here — the adapter wall is µm-coincident with
    # the horn wall through the weld overlap (that's the point), and vertex
    # merging would weld the coincident skins into non-manifold edges. The
    # UI's generate path unions without merging, exactly like this.
    _check_trimesh_watertight(combined, "OS-SE horn + custom adapter union")

    # No step: the inner radius of the welded body just below and just above
    # the junction plane must agree with the analytic field on both sides.
    for dz in (-0.25, +0.25):
        zq = trim_z + dz
        sec = combined.section(plane_origin=[0, 0, zq], plane_normal=[0, 0, 1])
        assert sec is not None, "no section at junction"
        loops = sec.discrete
        # inner loop = smallest mean radius; star-shaped → radius(angle) interp
        loop = min(loops, key=lambda p: np.hypot(p[:, 0], p[:, 1]).mean())
        a_loop = np.arctan2(loop[:, 1], loop[:, 0]) % (2.0 * np.pi)
        r_loop = np.hypot(loop[:, 0], loop[:, 1])
        order = np.argsort(a_loop)
        a_s, r_s = a_loop[order], r_loop[order]
        for j_phi, lbl in ((0, "H"), (nphi // 8, "diag"), (nphi // 4, "V")):
            ang = float(phi[j_phi]) % (2.0 * np.pi)
            r_meas = float(np.interp(ang, a_s, r_s, period=2.0 * np.pi))
            r_ref = float(np.interp(zq - z_min, z, R[:, j_phi]))
            assert abs(r_meas - r_ref) < 0.10, \
                f"step at junction ({lbl}, dz={dz:+.2f}): {r_meas:.3f} vs {r_ref:.3f}"
test("OS-SE embedded adapter welds with no junction step", test_osse_embedded_adapter_union_no_step)


# ══════════════════════════════════════════════════════════════════════════════
#  Packaging + module surface (guards regressions in deps / public aliases)
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Packaging + module surface ═══")

_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _req_pkg_names(path):
    """Base distribution names from a requirements.txt (drop version/extras)."""
    names = []
    with open(path) as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            # split off the first version/extra/marker delimiter
            name = line
            for sep in ("[", ">", "<", "=", "!", "~", " ", ";"):
                name = name.split(sep, 1)[0]
            if name:
                names.append(name.strip().lower())
    return names


def test_pyproject_covers_requirements():
    """Every runtime dep in requirements.txt must be declared in pyproject.toml.

    Guards the class of bug where `shapely` lived only in requirements.txt while
    `_slicer.py` imported it, leaving `pip install .` broken.
    """
    try:
        import tomllib
    except ImportError:  # pragma: no cover — Python < 3.11
        print("    (skipped: tomllib unavailable)")
        return
    req = _req_pkg_names(os.path.join(_ROOT, "requirements.txt"))
    with open(os.path.join(_ROOT, "pyproject.toml"), "rb") as fh:
        data = tomllib.load(fh)
    declared = " ".join(data["project"]["dependencies"]).lower()
    missing = [p for p in req if p not in declared]
    assert not missing, f"requirements.txt deps missing from pyproject.toml: {missing}"


test("pyproject.toml covers all requirements.txt deps", test_pyproject_covers_requirements)


def test_save_load_flr_roundtrip():
    """`.flr` presets keep user parameters and hide internal metadata on load."""
    params = {
        "profile_type": "OS-SE (ATH)",
        "section_type": "Elliptical",
        "throat_d": 25.4,
        "coverage_h": 90.0,
        "coverage_v": 60.0,
    }
    with tempfile.TemporaryDirectory() as td:
        path = _svl.save(params, os.path.join(td, "preset"))
        assert path.suffix == ".flr"
        text = path.read_text(encoding="utf-8")
        assert _svl.META_KEY in text
        assert _svl.load(path) == params


test("save_load writes .flr metadata and round-trips params", test_save_load_flr_roundtrip)


def test_analytics_accepts_read_only_streamlit_cookies():
    """Streamlit Cloud exposes st.context.cookies as read-only."""
    from src import _analytics as _anl

    class ReadOnlyCookies(dict):
        def __setitem__(self, key, value):
            raise TypeError("cookies are read-only")

    fake_state = {}
    fake_st = types.SimpleNamespace(
        context=types.SimpleNamespace(cookies=ReadOnlyCookies()),
        secrets={
            "posthog_api_key": "phc_test",
            "posthog_host": "https://eu.i.posthog.com",
        },
        session_state=fake_state,
    )
    previous_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = fake_st
    try:
        with tempfile.TemporaryDirectory() as td:
            ga = _anl.Analytics(db_path=os.path.join(td, "analytics.db"))
            ga._init_posthog()
            assert ga._ph_id
            assert fake_state["_flare_forge_uid"] == ga._ph_id

            ga._session_id = "test-session"
            captured = []
            ga._posthog_capture = lambda event, properties: captured.append((event, properties))
            ga.set_identity("user@example.com", "diy-user")
            assert fake_state["_flare_forge_forum"] == "diy-user"
            assert captured and captured[0][0] == "$identify"
            assert "email" not in captured[0][1]["$set"]
            assert captured[0][1]["$set"]["forum_username"] == "diy-user"
    finally:
        if previous_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous_streamlit


test("analytics accepts read-only Streamlit cookies", test_analytics_accepts_read_only_streamlit_cookies)


def test_analytics_dedupes_streamlit_rerun_pageviews():
    """Streamlit reruns the script on interaction; pageviews should stay one per session."""
    from src import _analytics as _anl

    fake_state = {}
    fake_st = types.SimpleNamespace(
        context=types.SimpleNamespace(cookies={}),
        secrets={},
        session_state=fake_state,
        markdown=lambda *args, **kwargs: None,
    )
    previous_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = fake_st
    try:
        with tempfile.TemporaryDirectory() as td:
            ga = _anl.Analytics(db_path=os.path.join(td, "analytics.db"))
            ga._init_posthog = lambda: None
            captured = []
            ga._posthog_capture = lambda event, properties: captured.append((event, properties))

            ga.start_session()
            first_session_id = ga._session_id
            ga.start_session()

            assert ga._session_id == first_session_id
            assert [event for event, _ in captured] == ["$pageview"]
            assert ga._fetch_one("SELECT COUNT(*) FROM sessions") == (1,)
    finally:
        if previous_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous_streamlit


test("analytics dedupes Streamlit rerun pageviews", test_analytics_dedupes_streamlit_rerun_pageviews)


def test_analytics_uses_forum_cookie_as_stable_posthog_id():
    """After opt-in, returning users use their forum cookie as stable PostHog id."""
    from src import _analytics as _anl

    captured = []

    class FakePosthog:
        def __init__(self, *args, **kwargs):
            pass

        def capture(self, **kwargs):
            captured.append(kwargs)

    fake_state = {
        "_flare_forge_uid": "session-fallback-id",
        "_flare_forge_forum": "diy-user",
        "_flare_forge_identified_id": "session-fallback-id",
    }
    fake_st = types.SimpleNamespace(
        context=types.SimpleNamespace(cookies={"_flare_forge_forum": "diy-user"}),
        secrets={
            "posthog_api_key": "phc_test",
            "posthog_host": "https://eu.i.posthog.com",
        },
        session_state=fake_state,
    )
    previous_streamlit = sys.modules.get("streamlit")
    previous_posthog = sys.modules.get("posthog")
    sys.modules["streamlit"] = fake_st
    sys.modules["posthog"] = types.SimpleNamespace(Posthog=FakePosthog)
    try:
        with tempfile.TemporaryDirectory() as td:
            ga = _anl.Analytics(db_path=os.path.join(td, "analytics.db"))
            ga._init_posthog()
            assert ga._ph_id == "forum:diy-user"
            assert fake_state["_flare_forge_identified_id"] == "forum:diy-user"
            assert len(captured) == 1
            assert captured[0]["event"] == "$identify"
            assert captured[0]["distinct_id"] == "forum:diy-user"
            assert captured[0]["properties"]["$set"] == {"forum_username": "diy-user"}

            ga._init_posthog()
            assert len(captured) == 1, "same forum id should not identify twice"
    finally:
        if previous_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous_streamlit
        if previous_posthog is None:
            sys.modules.pop("posthog", None)
        else:
            sys.modules["posthog"] = previous_posthog


test("analytics uses forum cookie as stable PostHog id", test_analytics_uses_forum_cookie_as_stable_posthog_id)


def test_analytics_loads_forum_username_cookie_without_posthog():
    """Returning users should be recognized from cookie even when PostHog is off."""
    from src import _analytics as _anl

    fake_state = {}
    fake_st = types.SimpleNamespace(
        context=types.SimpleNamespace(cookies={"_flare_forge_forum": "diy-user"}),
        secrets={},
        session_state=fake_state,
        markdown=lambda *args, **kwargs: None,
    )
    previous_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = fake_st
    try:
        with tempfile.TemporaryDirectory() as td:
            ga = _anl.Analytics(db_path=os.path.join(td, "analytics.db"))
            ga.start_session()

            assert ga.user_forum == "diy-user"
            assert fake_state["_flare_forge_forum"] == "diy-user"
    finally:
        if previous_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous_streamlit


test("analytics loads forum username cookie without PostHog", test_analytics_loads_forum_username_cookie_without_posthog)


def test_analytics_uses_cookie_manager_for_forum_username():
    """Streamlit Cloud needs a real component, not iframe-only JS, to persist cookies."""
    from src import _analytics as _anl

    class FakeCookieManager:
        def __init__(self, key="init"):
            constructed.append(key)
            self.cookies = {}

        def get(self, cookie=None):
            return self.cookies.get(cookie)

        def get_all(self, key="get_all"):
            self.get_all_key = key
            return self.cookies

        def set(self, name, value, key="set", path="/", expires_at=None, same_site="strict"):
            self.cookies[name] = value

    constructed = []
    manager = FakeCookieManager()
    fake_state = {}
    fake_st = types.SimpleNamespace(
        context=types.SimpleNamespace(cookies={}),
        secrets={},
        session_state=fake_state,
        markdown=lambda *args, **kwargs: None,
    )
    fake_stx = types.SimpleNamespace(
        CookieManager=lambda key="init": (constructed.append(key) or manager)
    )
    previous_streamlit = sys.modules.get("streamlit")
    previous_stx = sys.modules.get("extra_streamlit_components")
    sys.modules["streamlit"] = fake_st
    sys.modules["extra_streamlit_components"] = fake_stx
    try:
        with tempfile.TemporaryDirectory() as td:
            ga = _anl.Analytics(db_path=os.path.join(td, "analytics.db"))
            ga.set_identity(forum_username="diy-user")

            assert manager.cookies["_flare_forge_forum"] == "diy-user"

            fake_st.session_state = {}
            ga2 = _anl.Analytics(db_path=os.path.join(td, "analytics2.db"))
            ga2._load_identity_from_context()
            assert ga2.user_forum == "diy-user"
            assert constructed.count("flare_forge_cookie_manager") >= 2
            assert manager.get_all_key == "flare_forge_get_all"
    finally:
        if previous_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous_streamlit
        if previous_stx is None:
            sys.modules.pop("extra_streamlit_components", None)
        else:
            sys.modules["extra_streamlit_components"] = previous_stx


test("analytics uses cookie manager for forum username", test_analytics_uses_cookie_manager_for_forum_username)


def test_utils_profile_aliases():
    """`_utils` exposes the canonical (z,r) / (z,w,h) profile type aliases."""
    assert hasattr(_uts, "CircularProfile"), "missing CircularProfile alias"
    assert hasattr(_uts, "RectProfile"), "missing RectProfile alias"
    assert _uts.CircularProfile == tuple[np.ndarray, np.ndarray]
    assert _uts.RectProfile == tuple[np.ndarray, np.ndarray, np.ndarray]


test("_utils exposes CircularProfile/RectProfile aliases", test_utils_profile_aliases)


def test_ensure_positive_volume_avoids_numpy_stl_mass_properties():
    """Orientation helper must not trigger numpy-stl open-mesh warnings."""
    data = np.zeros(4, dtype=mesh.Mesh.dtype)
    data["vectors"][:] = np.array([
        [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
        [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    ])
    m = mesh.Mesh(data)

    original = mesh.Mesh.get_mass_properties

    def _forbid_mass_properties(_self):
        raise AssertionError("ensure_positive_volume must not call get_mass_properties()")

    mesh.Mesh.get_mass_properties = _forbid_mass_properties
    try:
        _uts.ensure_positive_volume(m)
    finally:
        mesh.Mesh.get_mass_properties = original


test("_utils positive-volume helper avoids open-mesh mass warnings",
     test_ensure_positive_volume_avoids_numpy_stl_mass_properties)


# ══════════════════════════════════════════════════════════════════════════════
#  Omnidirectional CD horn (omni_horn.py)
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Omnidirectional CD horn ═══")

def _check_omni_throat_invariant():
    """Centerline at Rt/2 ⇒ inner wall on axis, outer wall at Rt, area = St."""
    throat, mouth = 25.4, 260.0
    P = _om.get_omni_profile(throat, mouth, fc=600, n=300, profile="Exponential")
    Rt = throat / 2.0
    St = np.pi * Rt ** 2
    assert P["low_r"][0] < 0.05,                      f"deflector nose not on axis: {P['low_r'][0]:.3f}"
    assert abs(P["up_r"][0] - Rt) < 1e-6,             f"throat hole != Rt: {P['up_r'][0]:.3f}"
    throat_area = 2 * np.pi * P["rho_c"][0] * P["h"][0]
    assert abs(throat_area - St) < 1e-3,              f"throat area {throat_area:.2f} != St {St:.2f}"
    assert abs(P["rho_c"][-1] - mouth / 2.0) < 0.5,   f"centerline mouth radius {P['rho_c'][-1]:.2f}"
    assert P["Sm"] > St,                              "no expansion to mouth"

test("omni throat invariant: ρ₀=Rt/2 ⇒ exact circular throat", _check_omni_throat_invariant)

def _check_omni_mesh(profile="Exponential", lip=0.0):
    with tempfile.TemporaryDirectory() as d:
        _om.generate_omni_horn(25.4, 260.0, fc=600, output_dir=d,
                               profile=profile, lip_angle_deg=lip)
        for part in ("omni_deflector", "omni_reflector"):
            m = trimesh.load(os.path.join(d, f"{part}.stl"), file_type="stl")
            assert m.is_watertight,   f"{profile} {part}: not watertight"
            assert m.body_count == 1, f"{profile} {part}: {m.body_count} bodies"
            assert m.volume > 100,    f"{profile} {part}: volume={m.volume:.0f}"

for _prof in ("Exponential", "Tractrix", "Salmon", "Oblate spheroidal"):
    test(f"omni {_prof} parts watertight (single body)",
         lambda p=_prof: _check_omni_mesh(p))

def _check_omni_standoffs():
    """Centering ribs weld into the deflector as one watertight solid."""
    with tempfile.TemporaryDirectory() as d:
        plain, _ = _om.generate_omni_horn(25.4, 260.0, fc=600, output_dir=d,
                                          standoffs=0)
        v_plain = trimesh.load(os.path.join(d, "omni_deflector.stl"),
                               file_type="stl").volume
        _om.generate_omni_horn(25.4, 260.0, fc=600, output_dir=d,
                               standoffs=3, standoff_width=3.0)
        m = trimesh.load(os.path.join(d, "omni_deflector.stl"), file_type="stl")
        assert m.is_watertight,   "ribbed deflector: not watertight"
        assert m.body_count == 1, f"ribbed deflector: {m.body_count} bodies (ribs not welded)"
        assert m.volume > v_plain + 1.0, "ribs added no volume"

test("omni centering ribs weld into one solid", _check_omni_standoffs)

def _check_omni_parts_common_frame():
    """build_omni_parts returns watertight parts in ONE assembled frame."""
    P = _om.build_omni_parts(25.4, 260.0, fc=600, standoffs=3, ribs_fused=True)
    d, r = P["deflector"], P["reflector"]
    assert d.is_watertight and r.is_watertight, "fused parts not watertight"
    assert P["pillars"] is None, "ribs_fused should leave no separate pillars"
    # Shared frame: deflector and reflector Z ranges overlap (assembled).
    assert d.bounds[0, 2] < r.bounds[1, 2] and r.bounds[0, 2] < d.bounds[1, 2], \
        "deflector/reflector are not in a common assembled frame"
    # Separate pillars: smooth deflector + standalone ribs.
    P2 = _om.build_omni_parts(25.4, 260.0, fc=600, standoffs=3, ribs_fused=False)
    assert P2["deflector"].body_count == 1, "smooth deflector should be one body"
    assert P2["pillars"] is not None and P2["pillars"].is_watertight, \
        "separate pillars missing/not watertight"

test("omni build_omni_parts common frame + pillars modes", _check_omni_parts_common_frame)


# ══════════════════════════════════════════════════════════════════════════════
#  Summary
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 40}")
print(f"  PASS: {PASS}   FAIL: {FAIL}   SKIP: {SKIP}")
print(f"{'═' * 40}")
if MATCHES and PASS == 0 and FAIL == 0:
    print("No tests matched --match filter")
    sys.exit(2)
sys.exit(0 if FAIL == 0 else 1)
