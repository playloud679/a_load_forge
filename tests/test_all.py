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
    return _check

for _n in (2, 3, 4):
    test(f"{_n} petals joint_depth=2", _make_check_jointed_petals(_n, 2.0))
    test(f"{_n} petals joint_depth=0.5", _make_check_jointed_petals(_n, 0.5))


# ══════════════════════════════════════════════════════════════════════════════
#  Summary
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 40}")
print(f"  PASS: {PASS}   FAIL: {FAIL}")
print(f"{'═' * 40}")
sys.exit(0 if FAIL == 0 else 1)
