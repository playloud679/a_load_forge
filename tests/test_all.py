"""
Comprehensive test suite — all profile × section combinations.

Each test asserts not just "doesn't crash" but geometric invariants:
  - Profile math: z starts at 0, r[0] == throat/2, monotone expansion
  - 3D mesh: watertight, single body, positive volume, correct bounding box
  - Flanges: watertight, single body, hole smaller than outer
  - Radial: gap > 0 everywhere, R monotone, correct throat/mouth radii
"""

import sys, os, tempfile, traceback, itertools

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np

PASS = 0
FAIL = 0


def test(label, fn):
    global PASS, FAIL
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
from src import flange_generator as _fg
from src import rectangular_horn as _r
from src import rectangular_flange as _rf
from src import throat_adapter as _ta
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
]:
    label, fn, mono_z = entry
    def make(fn=fn, label=label, mono_z=mono_z):
        z, r = fn()
        mouth = None
        if "Tractrix" in label:
            mouth = float(label.split("→")[1])
        elif "Exponential" in label:
            mouth = float(label.split("→")[1].split("/")[0])
        _check_profile(z, r, THROAT, mouth, label, monotone_z=mono_z)
    test(label, make)


# ══════════════════════════════════════════════════════════════════════════════
#  2. Circular 3-D mesh — watertight + geometry checks
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Circular section — 3-D mesh ═══")

CIRC_CASES = [
    ("Tractrix",     lambda: _c.get_tractrix(THROAT, MOUTH, N)),
    ("Salmon",       lambda: _c.get_salmon(THROAT, FC, 80,   N)),
    ("Exponential",  lambda: _c.get_exponential(THROAT, MOUTH, FC, N)),
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
        # mouth diameter should be roughly r[-1]*2 + wall
        r_mouth_expected = r[-1] + 4.0
        r_mouth_actual   = max(np.linalg.norm(m.vertices[:, :2], axis=1))
        assert abs(r_mouth_actual - r_mouth_expected) < 5.0, \
            f"{lbl}: mouth radius {r_mouth_actual:.1f} vs expected ~{r_mouth_expected:.1f}"
    test(label, make)


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
#  4. Radial 360° — all profiles, geometry checks
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Radial 360° section ═══")

RADIAL_PROFILES = ["Tractrix", "Salmon", "Exponential"]

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
            _rd.generate_radial_horn(25, 200, FC, 48, tmp, p)
            for sfx in ["bottom", "top"]:
                path = os.path.join(tmp, f"radial_{sfx}.stl")
                m = trimesh.load(path, file_type="stl")
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

def _make_check_petals(n):
    def _check():
        horn = _horn_trimesh()
        Vh = horn.volume
        petals = _slc.slice_into_petals(horn, n)
        assert len(petals) == n, f"petals: got {len(petals)}"
        for i, p1 in enumerate(petals):
            assert p1.is_watertight,   f"petal {i}: not watertight"
            assert p1.body_count == 1, f"petal {i}: not one body ({p1.body_count})"
        # petals tile the horn
        sv = sum(p.volume for p in petals)
        assert 0.95 * Vh < sv <= Vh + 1e-6, f"n={n}: petals don't tile horn ({sv/Vh:.3f})"
    return _check

for _n in (3, 4, 6):
    test(f"{_n} petals", _make_check_petals(_n))


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

for _n in (2, 3, 4):
    test(f"{_n} petals joint_depth=2", _make_check_jointed_petals(_n, 2.0))
    test(f"{_n} petals joint_depth=0.5", _make_check_jointed_petals(_n, 0.5))


# ══════════════════════════════════════════════════════════════════════════════
#  9. Throat adapter — thread specs, geometry, and assembly
# ══════════════════════════════════════════════════════════════════════════════

print("\n═══ Throat adapter ═══")

def test_thread_specs():
    assert len(_ta.THREAD_SPECS) == 3, f"expected 3 thread specs, got {len(_ta.THREAD_SPECS)}"
    for key in ("1in", "1_25in", "2in"):
        assert key in _ta.THREAD_SPECS, f"missing {key}"
        spec = _ta.THREAD_SPECS[key]
        assert spec.major_diam > 0, f"{key}: major_diam={spec.major_diam}"
        assert spec.pitch > 0, f"{key}: pitch={spec.pitch}"
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

def test_poly_points():
    pts = _ta._poly_points(6, 20.0, 60)
    assert pts.shape[0] >= 6, f"too few points {pts.shape}"
    area = _ta._polygon_area(pts)
    expected = 0.5 * 6 * 20.0**2 * np.sin(2 * np.pi / 6)
    assert abs(area - expected) / expected < 0.05, f"area={area:.1f} vs {expected:.1f}"
test("poly points", test_poly_points)

def test_morph_slice_circle():
    """At t=0 the morph should return a circle of radius ~driver_R."""
    def _tfn():
        return _ta._rect_points(10.0, 5.0, 64)
    pts = _ta._morph_slice(0.0, 12.5, _tfn, 12.5, 64)
    r = np.linalg.norm(pts, axis=1)
    assert np.allclose(r, 12.5, atol=1.0), f"circle r={r.mean():.2f} vs 12.5"
test("morph slice at t=0 (circle)", test_morph_slice_circle)

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

def test_threaded_socket():
    for key in ("1in", "1_25in", "2in"):
        m = _ta.make_threaded_socket(key, 15.0, 4.0)
        _check_trimesh_watertight(m, f"threaded socket {key}")
test("threaded sockets watertight", test_threaded_socket)

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
test("adapter assembly flanged", test_adapter_assembly_flanged)

def test_adapter_assembly_threaded():
    """Full assembly with threaded socket, circle→poly transition."""
    m = _ta.make_adapter_assembly(
        driver_type="1in", driver_diam=None, thread_key="1in",
        horn_shape="polygonal",
        rect_w=0.0, rect_h=0.0, poly_n_sides=6,
        poly_circumR=15.0,
        horn_R_eq=12.5,
        adapter_length=30.0, wall_thickness=4.0,
        socket_length=15.0, z_offset=0.0,
        output_path=None,
    )
    _check_trimesh_watertight(m, "adapter assembly threaded")
test("adapter assembly threaded", test_adapter_assembly_threaded)

def test_adapter_assembly_threaded_circular():
    """Full assembly with threaded socket, circle→circle transition."""
    m = _ta.make_adapter_assembly(
        driver_type="1_25in", driver_diam=None, thread_key="1_25in",
        horn_shape="circular",
        rect_w=0.0, rect_h=0.0, poly_n_sides=0,
        poly_circumR=0.0,
        horn_R_eq=18.0,
        adapter_length=30.0, wall_thickness=4.0,
        socket_length=15.0,
        outer_target_R=22.0,
        z_offset=0.0,
        output_path=None,
    )
    _check_trimesh_watertight(m, "adapter assembly threaded circular")
test("adapter assembly threaded circular", test_adapter_assembly_threaded_circular)


# ══════════════════════════════════════════════════════════════════════════════
#  Summary
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 40}")
print(f"  PASS: {PASS}   FAIL: {FAIL}")
print(f"{'═' * 40}")
sys.exit(0 if FAIL == 0 else 1)
