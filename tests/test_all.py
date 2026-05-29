"""
Test all profiles and mesh engines.
Reports failures with full traceback — no manual trial & error.
"""

import sys, os, tempfile, traceback

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np

PASS = 0
FAIL = 0


def test(label, fn, cleanup=True):
    global PASS, FAIL
    try:
        result = fn()
        if cleanup:
            for f in ["io/horn.stl", "io/rectangular_horn.stl",
                       "io/radial_bottom.stl", "io/radial_top.stl"]:
                if os.path.exists(f):
                    os.unlink(f)
        print(f"  ✅ {label}")
        PASS += 1
        return result
    except Exception:
        print(f"  ❌ {label}")
        traceback.print_exc()
        FAIL += 1
        return None


# ======================================================================
#  1. Profile math — returns (z, r) or (z, w, h)
# ======================================================================

print("\n═══ 2-D Profile Math ═══")

from src import profile_generator as _c
from src import rectangular_horn as _r
from src import radial_horn as _d
from src import rectangular_flange as _rf

test("Tractrix 20→100",        lambda: _c.get_tractrix(20, 100, 300))
test("Tractrix 20→200",        lambda: _c.get_tractrix(20, 200, 300))
test("LeCléac'h 20/800Hz",     lambda: _c.get_lecleach(20, 800, 300))
test("LeCléac'h 20/5000Hz",    lambda: _c.get_lecleach(20, 5000, 300))
test("Iwata 20/600/L80",       lambda: _c.get_iwata(20, 600, 80, 300))

test("Rectangular 20×10→160 600Hz",
      lambda: _r.get_rectangular_exponential(20, 10, 160, 600, 300))

test("Radial profiles 25/200 600Hz",
      lambda: _d.get_radial_profiles(25, 200, 600, 300))


# ======================================================================
#  2. Axisymmetric 3-D mesh  (generate_3d_mesh_from_profile)
# ======================================================================

print("\n═══ Axisymmetric 3-D Mesh ═══")

import trimesh

for label, throat, mouth, fc in [
    ("Tractrix 20→100",            20, 100,  None),
    ("Tractrix 20→200",            20, 200,  None),
    ("LeCléac'h 20/800Hz",         20, None, 800),
    ("LeCléac'h 20/5000Hz",        20, None, 5000),
    ("Iwata 20/600/L80",           20, None, 600),
]:
    def make(th=throat, mo=mouth, f=fc):
        z, r = (_c.get_tractrix(th, mo, 300) if mo else
                _c.get_lecleach(th, f, 300) if f else
                _c.get_iwata(th, f, 80, 300))
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
            p = t.name
        _c.generate_3d_mesh_from_profile(z, r, 4.0, 64, p)
        m = trimesh.load(p, file_type="stl")
        os.unlink(p)
        assert m.is_watertight, "Not watertight"
        assert m.body_count == 1, f"{m.body_count} bodies"
        assert m.volume > 0, f"Volume {m.volume}"
        return m

    test(label, make)


# ======================================================================
#  3. Rectangular 3-D lofting
# ======================================================================

print("\n═══ Rectangular 3-D Mesh ═══")

for label, tw, th, mw, fc in [
    ("20×10→160 600Hz",  20, 10, 160, 600),
    ("30×15→200 400Hz",  30, 15, 200, 400),
]:
    def make(tw=tw, th=th, mw=mw, fc=fc):
        z, w, h = _r.get_rectangular_exponential(tw, th, mw, fc, 300)
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
            p = t.name
        _r.generate_rectangular_3d_mesh(z, w, h, 4.0, p)
        m = trimesh.load(p, file_type="stl")
        os.unlink(p)
        assert m.is_watertight, "Not watertight"
        assert m.body_count == 1, f"{m.body_count} bodies"
        assert m.volume > 0, f"Volume {m.volume}"
        return m

    test(label, make)


# ======================================================================
#  4. Radial 3-D mesh  (both pieces)
# ======================================================================

print("\n═══ Radial 3-D Mesh ═══")

for label, th, mo, fc in [
    ("25/200 600Hz",     25, 200, 600),
    ("30/180 800Hz",     30, 180, 800),
]:
    def make(th=th, mo=mo, fc=fc):
        _d.generate_radial_horn(th, mo, fc, rings=48, output_dir="io")
        for sfx in ["bottom", "top"]:
            p = f"io/radial_{sfx}.stl"
            m = trimesh.load(p, file_type="stl")
        # Check closed: 0 boundary edges (multi edges OK for revolution)
        from collections import Counter
        _edges = Counter()
        for _tri in m.faces:
            for _j in range(3):
                _v0 = tuple(np.round(m.vertices[_tri[_j]], 4))
                _v1 = tuple(np.round(m.vertices[_tri[(_j + 1) % 3]], 4))
                _key = (_v0, _v1) if _v0 < _v1 else (_v1, _v0)
                _edges[_key] += 1
        _b = sum(1 for _c in _edges.values() if _c == 1)
        assert _b == 0, f"{p} has {_b} boundary edges"
        assert m.body_count == 1, f"{p} {m.body_count} bodies"
        assert m.volume > 0, f"{p} Volume {m.volume}"
        os.unlink(p)
        return True

    test(label, make)


# ======================================================================
#  5. Rectangular flange
# ======================================================================

print("\n═══ Rectangular Flange ═══")

for label, ow, oh, iw, ih in [
    ("60×50 / 20×10", 60, 50, 20, 10),
    ("80×60 / 30×15", 80, 60, 30, 15),
]:
    def make(ow=ow, oh=oh, iw=iw, ih=ih):
        m = _rf.generate_rectangular_flange(ow, oh, iw, ih, output_path=None)
        assert m is not None, "Flange generation returned None"
        assert m.is_watertight, "Not watertight"
        assert m.body_count == 1, f"{m.body_count} bodies"
        assert m.volume > 0, f"Volume {m.volume}"
        return m

    test(label, make)


# ======================================================================
#  Summary
# ======================================================================

print(f"\n{'═' * 40}")
print(f"  PASS: {PASS}   FAIL: {FAIL}")
print(f"{'═' * 40}")
sys.exit(0 if FAIL == 0 else 1)
