"""
Full integration test: generate STL assemblies for all profile types.
"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import importlib.machinery, importlib.util
import numpy as np
import trimesh as _tm


def _load(name, filename):
    l = importlib.machinery.SourceFileLoader(name, f"src/{filename}")
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, l))
    l.exec_module(m)
    return m


core   = _load("_c", "01_profile_generator.py")
fg     = _load("_f", "02_flange_generator.py")
rh     = _load("_rh", "03_rectangular_horn.py")
rd     = _load("_rd", "03_omni_radial_horn.py")
rf     = _load("_rf", "04_rectangular_flange.py")

os.makedirs("io", exist_ok=True)

PASS = 0
FAIL = 0


def test(label, fn):
    global PASS, FAIL
    try:
        result = fn()
        print(f"  ✅ {label}")
        PASS += 1
        return result
    except Exception as e:
        print(f"  ❌ {label}: {e}")
        FAIL += 1
        return None


def _hole_size(mesh, near_z):
    v = mesh.vertices[np.abs(mesh.vertices[:, 2] - near_z) < 1.0]
    if len(v) < 4:
        v = mesh.vertices[np.abs(mesh.vertices[:, 2] - near_z) < 5.0]
    return float(np.sqrt(v[:, 0]**2 + v[:, 1]**2).max()) * 2


def make_assembly(label, horn_mesh, z_mouth, is_rect=False, is_lecleach=False,
                  fg_spess=6, fm_spess=6, mid_pct=None):
    """Build full assembly: horn + throat + mouth + optional mid flange."""
    z_min = horn_mesh.vertices[:, 2].min()

    if is_rect:
        fg_hole = max(float(np.abs(horn_mesh.vertices[:, 0]).max()) * 2,
                      float(np.abs(horn_mesh.vertices[:, 1]).max()) * 2)
        fm_hole = fg_hole
        def _hole_at(mesh, z):
            v = mesh.vertices[np.abs(mesh.vertices[:, 2] - z) < 1.0]
            if len(v) < 4:
                v = mesh.vertices[np.abs(mesh.vertices[:, 2] - z) < 5.0]
            return max(float(np.abs(v[:, 0]).max()) * 2,
                       float(np.abs(v[:, 1]).max()) * 2)
    else:
        fg_hole = _hole_size(horn_mesh, z_min)
        fm_hole = _hole_size(horn_mesh, z_mouth)
        def _hole_at(mesh, z):
            return _hole_size(mesh, z)

    fg_od = max(fg_hole + 20, 40)
    fg_bc = fg_hole / 2 + fg_od / 2

    # Mouth: LeCleach → inward (outer edge = mouth, hole smaller)
    if is_lecleach:
        fm_od = fm_hole            # flush with mouth, no outward margin
        fm_hole_actual = fm_od - 20  # hole 10mm inward from edge
        fm_bc = (fm_hole_actual / 2 + fm_od / 2)
    else:
        fm_od = max(fm_hole + 20, 40)
        fm_hole_actual = fm_hole
        fm_bc = fm_hole / 2 + fm_od / 2

    flanges = []

    f = fg.generate_flange(throat_R=fg_hole/2, flange_R=fg_od/2, thickness=fg_spess,
                           bolt_R=fg_bc/2, bolt_n=4, bolt_d=3.5, offset=0 + fg_spess)
    if f is None: raise RuntimeError("Throat flange failed")
    flanges.append(f)
    print(f"    Throat: hole=Ø{fg_hole:.0f} od=Ø{fg_od:.0f} bc=Ø{fg_bc:.0f}")

    f = fg.generate_flange(throat_R=fm_hole_actual/2, flange_R=fm_od/2, thickness=fm_spess,
                           bolt_R=fm_bc/2, bolt_n=4, bolt_d=3.5, offset=z_mouth)
    if f is None: raise RuntimeError("Mouth flange failed")
    flanges.append(f)
    extra = " (verso centro)" if is_lecleach else ""
    print(f"    Mouth:  hole=Ø{fm_hole_actual:.0f} od=Ø{fm_od:.0f} bc=Ø{fm_bc:.0f}{extra}")

    if mid_pct is not None:
        z_len = horn_mesh.vertices[:, 2].max() - z_min
        z_mid = z_min + z_len * mid_pct / 100.0
        mid_hole = _hole_at(horn_mesh, z_mid)
        mid_od = mid_hole + 20
        mid_bc = mid_hole / 2 + mid_od / 2
        f = fg.generate_flange(throat_R=mid_hole/2, flange_R=mid_od/2, thickness=4,
                               bolt_R=mid_bc/2, bolt_n=4, bolt_d=3.5, offset=z_mid)
        if f is None: raise RuntimeError("Mid flange failed")
        flanges.append(f)
        print(f"    Mid:    hole=Ø{mid_hole:.0f} od=Ø{mid_od:.0f} bc=Ø{mid_bc:.0f} @ Z={z_mid:.0f}")

    bodies = [horn_mesh] + flanges
    if is_rect or len(bodies) == 1:
        combined = _tm.util.concatenate(bodies)
    else:
        combined = _tm.boolean.union(bodies, engine="manifold")
    if combined is None:
        raise RuntimeError("Merge failed")

    out_path = f"io/{label}.stl"
    combined.export(out_path)
    wt = combined.is_watertight if hasattr(combined, 'is_watertight') else False
    print(f"    Assembly: {len(combined.faces)} tris  vol={combined.volume if hasattr(combined,'volume') else '?'}  WT={wt}")
    return combined


# ═══════════════════════════════════════════════════════════════════════
#  TRACTRIX
# ═══════════════════════════════════════════════════════════════════════
print("\n═══ Tractrix (20→100, t=4) ═══")
z, r = core.get_tractrix(20, 100, 300)
with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
    tp = t.name
core.generate_3d_mesh_from_profile(z, r, 4.0, 64, tp)
horn = _tm.load(tp, file_type="stl")
os.unlink(tp)
test("Tractrix assembly", lambda: make_assembly("tractrix_full", horn,
      horn.vertices[:, 2].max(), mid_pct=50))

# ═══════════════════════════════════════════════════════════════════════
#  LE CLÉAC'H
# ═══════════════════════════════════════════════════════════════════════
print("\n═══ Le Cléac'h (20/800Hz, t=4) ═══")
z, r = core.get_lecleach(20, 800, 300)
with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
    tp = t.name
core.generate_3d_mesh_from_profile(z, r, 4.0, 64, tp)
horn = _tm.load(tp, file_type="stl")
os.unlink(tp)
rr = np.sqrt(horn.vertices[:, 0]**2 + horn.vertices[:, 1]**2)
z_mouth = float(horn.vertices[int(rr.argmax()), 2])
test("LeCleach assembly", lambda: make_assembly("lecleach_full", horn, z_mouth,
      is_lecleach=True, mid_pct=40))

# ═══════════════════════════════════════════════════════════════════════
#  IWATA
# ═══════════════════════════════════════════════════════════════════════
print("\n═══ Iwata (20/600Hz/L=80, t=4) ═══")
z, r = core.get_iwata(20, 600, 80, 300)
with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
    tp = t.name
core.generate_3d_mesh_from_profile(z, r, 4.0, 64, tp)
horn = _tm.load(tp, file_type="stl")
os.unlink(tp)
test("Iwata assembly", lambda: make_assembly("iwata_full", horn,
      horn.vertices[:, 2].max(), mid_pct=50))

# ═══════════════════════════════════════════════════════════════════════
#  RECTANGULAR
# ═══════════════════════════════════════════════════════════════════════
print("\n═══ Rectangular (20×10→160, 600Hz, t=4) ═══")
z, w, h = rh.get_rectangular_exponential(20, 10, 160, 600, 300)
with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
    tp = t.name
rh.generate_rectangular_3d_mesh(z, w, h, 4.0, tp)
horn = _tm.load(tp, file_type="stl")
os.unlink(tp)
test("Rectangular assembly", lambda: make_assembly("rectangular_full", horn,
      horn.vertices[:, 2].max(), is_rect=True, mid_pct=50))

# ═══════════════════════════════════════════════════════════════════════
#  RADIAL
# ═══════════════════════════════════════════════════════════════════════
print("\n═══ Radial (25/200, 600Hz) ═══")
test("Radial dual-piece", lambda: rd.generate_radial_horn(25, 200, 600, 48, "io"))


# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'═' * 50}")
print(f"  PASS: {PASS}   FAIL: {FAIL}")
print(f"{'═' * 50}")
print("\nOutput files in io/:")
for f in sorted(os.listdir("io")):
    if f.endswith(".stl"):
        size_kb = os.path.getsize(f"io/{f}") / 1024
        print(f"  {f:30s} {size_kb:8.1f} KB")
