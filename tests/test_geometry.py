"""
Integration tests — output geometry must match the UI parameters.

Strategy: section the mesh at a Z plane, isolate the outer contour entity
(the one with the largest max-radius), then measure max_r / min_r.

  Circular outer:  ratio ≈ 1.0          (< 1.05)
  N-gon outer:     ratio ≈ 1/cos(π/N)   e.g. 4-gon→1.414, 6-gon→1.155
"""

import argparse
import sys, os, tempfile, traceback
import numpy as np

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

import trimesh
from src import profile_generator as _c
from src import polygonal_horn as _ph
from src import flange_generator as _fg

PASS = 0
FAIL = 0
SKIP = 0


def _parse_args():
    parser = argparse.ArgumentParser(description="Run Flare Forge geometry tests.")
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


# ── Geometry helpers ─────────────────────────────────────────────────────────

def _outer_contour_ratio(mesh: trimesh.Trimesh, z: float) -> float:
    """
    Section the mesh at Z, find the outer contour (entity with largest r_max),
    return max_r / min_r of that contour.
    """
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    assert sec is not None, f"No cross-section at z={z}"
    path2d, _ = sec.to_planar()
    pts = np.array(path2d.vertices)
    outer_ent = max(path2d.entities,
                    key=lambda e: np.linalg.norm(pts[e.points], axis=1).max())
    r = np.linalg.norm(pts[outer_ent.points], axis=1)
    return float(r.max() / r.min())


def _expected_ratio(n_sides: int) -> float:
    return 1.0 / np.cos(np.pi / n_sides)


def assert_circular(mesh, z, label, tol=0.05):
    ratio = _outer_contour_ratio(mesh, z)
    assert ratio < 1.0 + tol, \
        f"{label}: looks polygonal (ratio={ratio:.3f}, expected <{1+tol:.2f})"


def assert_ngon(mesh, z, n_sides, label, tol=0.08):
    ratio = _outer_contour_ratio(mesh, z)
    expected = _expected_ratio(n_sides)
    assert abs(ratio - expected) < tol, \
        f"{label}: ratio={ratio:.3f}, expected {expected:.3f} ({n_sides}-gon)"


def assert_inner_radius(mesh, z, inner_R, label, tol=1.5):
    """Inner hole: the entity with the smallest mean radius."""
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    assert sec is not None
    path2d, _ = sec.to_planar()
    pts = np.array(path2d.vertices)
    inner_ent = min(path2d.entities,
                    key=lambda e: np.linalg.norm(pts[e.points], axis=1).mean())
    r = np.linalg.norm(pts[inner_ent.points], axis=1)
    assert abs(r.mean() - inner_R) < tol, \
        f"{label}: inner r={r.mean():.2f}, expected {inner_R:.2f}"


# ══════════════════════════════════════════════════════════════════════════════
#  1. generate_flange — outer shape
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Circular flange — outer shape ═══")

OFFSET = 6.0
Z_MID  = OFFSET / 2   # 3.0 — mid-height of flange

for outer_n, label_shape, check_fn in [
    (0, "circular",     lambda m: assert_circular(m, Z_MID, "circ flange / circular outer")),
    (4, "4-gon (square)", lambda m: assert_ngon(m, Z_MID, 4, "circ flange / 4-gon outer")),
    (6, "6-gon (hex)",  lambda m: assert_ngon(m, Z_MID, 6, "circ flange / 6-gon outer")),
    (8, "8-gon",        lambda m: assert_ngon(m, Z_MID, 8, "circ flange / 8-gon outer")),
]:
    _n, _lbl, _check = outer_n, label_shape, check_fn
    def make(n=_n, check=_check):
        m = _fg.generate_flange(15.0, 35.0, 6.0, 25.0, 4, 3.5,
                                offset=OFFSET, outer_n_sides=n, output_path=None)
        check(m)
    test(f"outer shape → {_lbl}", make)

def test_inner_hole():
    throat_R = 15.0
    m = _fg.generate_flange(throat_R, 35.0, 6.0, 25.0, 4, 3.5,
                            offset=OFFSET, outer_n_sides=0, output_path=None)
    assert_inner_radius(m, z=Z_MID, inner_R=throat_R, label="inner hole radius")

test("inner hole radius matches throat_R", test_inner_hole)


# ══════════════════════════════════════════════════════════════════════════════
#  2. UI combinations: profile + section + flange outer shape
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ UI combinations — profile × section × flange outer ═══")

def _circ_flange(profile_fn, outer_n_sides):
    z, r = profile_fn()
    thickness = 4.0
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _c.generate_3d_mesh_from_profile(z, r, thickness, 64, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    z_min = horn.vertices[:, 2].min()
    throat_R = r[0] + thickness
    flange_R  = throat_R + 15.0
    flange_thick = 6.0
    f = _fg.generate_flange(throat_R, flange_R, flange_thick,
                            throat_R + 8, 4, 3.5,
                            offset=z_min + flange_thick,
                            outer_n_sides=outer_n_sides,
                            output_path=None)
    z_fl = z_min + flange_thick / 2
    return f, z_fl


PROFILES = [
    ("Tractrix",    lambda: _c.get_tractrix(20.0, 100.0, 300)),
    ("Salmon",      lambda: _c.get_salmon(20.0, 600, 80, 300)),
    ("Exponential", lambda: _c.get_exponential(20.0, 100.0, 600, 300)),
]

for prof_name, prof_fn in PROFILES:
    for outer_n, shape_label in [(0, "circ"), (4, "4-gon"), (6, "6-gon")]:
        _pn, _pfn, _on, _sl = prof_name, prof_fn, outer_n, shape_label
        _lbl = f"{_pn} / Circular section / {_sl} flange"
        def make(pfn=_pfn, on=_on, sl=_sl, lbl=_lbl):
            m, z_fl = _circ_flange(pfn, on)
            if on == 0:
                assert_circular(m, z_fl, lbl)
            else:
                assert_ngon(m, z_fl, on, lbl)
        test(_lbl, make)


# ══════════════════════════════════════════════════════════════════════════════
#  3. Polygonal horn — cross-section has correct N-gon shape
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Polygonal horn — cross-section shape ═══")

for n_sides in [3, 4, 6, 8]:
    _n = n_sides
    def make(n=_n):
        z, r = _c.get_tractrix(20.0, 100.0, 300)
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
        _ph.generate_polygonal_3d_mesh(z, r, n, 4.0, p)
        m = trimesh.load(p, file_type="stl"); os.unlink(p)
        z_mid = (m.bounds[0, 2] + m.bounds[1, 2]) / 2
        assert_ngon(m, z_mid, n, f"Tractrix {n}-gon cross-section")
    test(f"Tractrix {_n}-gon horn cross-section", make)


# ══════════════════════════════════════════════════════════════════════════════
#  4. Polygonal horn + polygonal flange: outer shape matches request
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Polygonal horn + flange outer shape ═══")

def _poly_flange(n_horn, outer_n):
    from polygonal_horn import _r_to_circumradius
    import _utils as _uts
    z, r = _c.get_tractrix(20.0, 100.0, 300)
    thickness = 4.0
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t: p = t.name
    _ph.generate_polygonal_3d_mesh(z, r, n_horn, thickness, p)
    horn = trimesh.load(p, file_type="stl"); os.unlink(p)
    R_i = _r_to_circumradius(r, n_horn)
    nml = _uts.compute_profile_normals(z, R_i, flip_if_negative=True)
    R_o = R_i + thickness / np.cos(np.pi / n_horn) * nml[:, 1]
    throat_circumR = R_o[0]
    z_min = horn.vertices[:, 2].min()
    flange_thick = 6.0
    f = _fg.generate_polygonal_flange(
        inner_circumR=throat_circumR, n_sides=n_horn,
        flange_R=throat_circumR + 15.0, thickness=flange_thick,
        bolt_R=throat_circumR + 8, bolt_n=4, bolt_d=3.5,
        offset=z_min + flange_thick, outer_n_sides=outer_n,
        output_path=None)
    z_fl = z_min + flange_thick / 2
    return f, z_fl

for n_horn, outer_n in [(4, 0), (4, 4), (6, 6), (8, 0), (4, 6)]:
    _nh, _no = n_horn, outer_n
    _sl = "circ" if _no == 0 else f"{_no}-gon"
    _lbl = f"{_nh}-gon horn / {_sl} flange outer"
    def make(nh=_nh, no=_no, sl=_sl, lbl=_lbl):
        m, z_fl = _poly_flange(nh, no)
        if no == 0:
            assert_circular(m, z_fl, lbl)
        else:
            assert_ngon(m, z_fl, no, lbl)
    test(_lbl, make)


# ══════════════════════════════════════════════════════════════════════════════
#  5. Regression: default outer_n_sides unchanged → circle
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Large inner hole: auto-expand flange_R ═══")

def test_large_inner_auto_expand():
    """Mouth flange case: inner_R=54, ring_width=15 → square inradius would be 48.8 < 54 → must auto-expand."""
    inner_R = 54.0   # tractrix mouth: r[-1]+thickness
    ring_w  = 15.0
    flange_R_requested = inner_R + ring_w   # = 69, inradius = 69*cos45 = 48.8 < 54 → INVALID
    m = _fg.generate_flange(inner_R, flange_R_requested, 6.0, inner_R + 8, 4, 3.5,
                            offset=6.0, outer_n_sides=4, output_path=None)
    assert m is not None, "auto-expand: returned None"
    assert_ngon(m, z=3.0, n_sides=4, label="large inner / auto-expanded 4-gon")
    # inner hole must not exceed inradius
    sec = m.section(plane_origin=[0,0,3], plane_normal=[0,0,1])
    p2d, _ = sec.to_planar()
    pts = np.array(p2d.vertices)
    r_all = np.linalg.norm(pts, axis=1)
    outer_ent = max(p2d.entities, key=lambda e: np.linalg.norm(pts[e.points],axis=1).max())
    outer_r = np.linalg.norm(pts[outer_ent.points], axis=1)
    inradius = outer_r.min()   # for N-gon, min_r of outer contour = inradius
    inner_ent = min(p2d.entities, key=lambda e: np.linalg.norm(pts[e.points],axis=1).mean())
    inner_r = np.linalg.norm(pts[inner_ent.points], axis=1)
    assert inner_r.max() <= inradius + 1.0, \
        f"inner hole ({inner_r.max():.1f}) exceeds polygon inradius ({inradius:.1f})"

test("large inner_R auto-expands flange_R", test_large_inner_auto_expand)

print("\n═══ Coherent ring width: flat-face wall == ring for any N ═══")

def _flange_R_from_ring(inner_R, ring, outer_n):
    """Mirror of ui_app._flange_R_from_ring: ring = wall at flat faces."""
    if outer_n >= 3:
        return (inner_R + ring) / np.cos(np.pi / outer_n)
    return inner_R + ring

def _flat_face_wall(mesh, z, inner_R):
    """For an N-gon outer, the min radius of the outer contour = inradius."""
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    p2d, _ = sec.to_planar()
    pts = np.array(p2d.vertices)
    outer_ent = max(p2d.entities,
                    key=lambda e: np.linalg.norm(pts[e.points], axis=1).max())
    outer_r = np.linalg.norm(pts[outer_ent.points], axis=1)
    inradius = outer_r.min()
    return inradius - inner_R

# Fixed ring=15, large mouth-like hole, every side count 3..10 must keep ~15mm flat wall
RING = 15.0
INNER_R = 54.0   # tractrix mouth radius + wall — the case that broke before
for n in range(3, 11):
    _n = n
    def make(n=_n):
        flange_R = _flange_R_from_ring(INNER_R, RING, n)
        m = _fg.generate_flange(INNER_R, flange_R, 6.0, INNER_R + 8, 4, 3.5,
                                offset=6.0, outer_n_sides=n, output_path=None)
        assert m is not None, f"{n}-gon: returned None"
        wall = _flat_face_wall(m, z=3.0, inner_R=INNER_R)
        assert abs(wall - RING) < 1.0, \
            f"{n}-gon: flat-face wall={wall:.2f}, expected {RING} (ring not coherent)"
        # and the outer shape must actually be an N-gon
        assert_ngon(m, z=3.0, n_sides=n, label=f"ring=15 / {n}-gon")
    test(f"ring=15mm coherent on {n}-gon (flat wall ≈15)", make)


print("\n═══ Regression: default outer_n_sides=0 ═══")

def test_default_still_circular():
    m = _fg.generate_flange(15.0, 35.0, 6.0, 25.0, 4, 3.5,
                            offset=OFFSET, output_path=None)
    assert_circular(m, Z_MID, "default outer_n_sides=0 → circle")

test("default (no outer_n_sides arg) → circle", test_default_still_circular)


# ══════════════════════════════════════════════════════════════════════════════
#  Summary
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 40}")
print(f"  PASS: {PASS}   FAIL: {FAIL}   SKIP: {SKIP}")
print(f"{'═' * 40}")
import sys as _sys
if MATCHES and PASS == 0 and FAIL == 0:
    print("No tests matched --match filter")
    _sys.exit(2)
_sys.exit(0 if FAIL == 0 else 1)
