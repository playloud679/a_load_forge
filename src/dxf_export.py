"""
DXF export — 2D drilling/cut template of a flange, derived from its mesh.

No third-party dependency: writes a plain AutoCAD R12 (AC1009) ASCII DXF, the
most universally accepted flavour (LibreCAD, QCAD, Fusion, Illustrator, every
CAM tool). Entities used: CIRCLE, POLYLINE/VERTEX (closed), POINT.

The template is taken straight from the generated flange **mesh** by cutting a
horizontal cross-section through the plate, so it works for every flange type
(circular / polygonal / rectangular / elliptical, custom or bolt-on) without
re-deriving any parameters. Each closed loop of the section becomes an entity:

  * exterior loop  → layer ``OUTLINE`` (the plate boundary)
  * the loop centred on the axis → layer ``BORE`` (the throat opening)
  * every off-axis loop → layer ``HOLES`` (a bolt hole) + a centre mark on
    layer ``CENTERS``

Bolt holes are always round, so they are emitted as true ``CIRCLE`` entities
with the **nominal** radius recovered as the circumscribed (max) vertex radius
— a faceted 12-gon cylinder hole comes back out as an exact circle, with its
centre exactly on the bolt-circle. The bore keeps its real shape (a hexagonal
or rectangular opening stays a polyline; a round one becomes a circle).

Layers let the user keep only what they need: delete OUTLINE/BORE to get a
pure hole template, or keep everything for registration when drilling a plate.

Elliptical-offset flanges also have an **analytic** path
(``elliptical_flange_dxf``) that builds the same template straight from the
source parameters instead of a mesh section — exact and immune to boolean/mesh
artefacts that can mis-centre mesh-derived holes.
"""
from __future__ import annotations

import numpy as np

# Layer name → (ACI colour index)
_LAYERS = {
    "OUTLINE": 7,   # white/black
    "BORE": 5,      # blue
    "HOLES": 1,     # red
    "CENTERS": 8,   # grey
}


def _fit_circle(pts: np.ndarray) -> tuple[float, float, float, float, float]:
    """Least-squares circle through 2-D points.

    Returns ``(cx, cy, r_fit, r_min, r_max)`` where ``r_min``/``r_max`` are the
    inscribed/circumscribed vertex radii about the fitted centre.
    """
    x, y = pts[:, 0], pts[:, 1]
    A = np.c_[2.0 * x, 2.0 * y, np.ones(len(x))]
    b = x * x + y * y
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = float(sol[0]), float(sol[1])
    r_fit = float(np.sqrt(max(0.0, sol[2] + cx * cx + cy * cy)))
    d = np.hypot(x - cx, y - cy)
    return cx, cy, r_fit, float(d.min()), float(d.max())


def _is_round(r_min: float, r_max: float, n_pts: int) -> bool:
    """A loop is "round" when it has enough facets and a tight radius band."""
    if r_max <= 1e-9:
        return False
    return n_pts >= 16 and (r_max - r_min) / r_max < 0.05


# ── DXF primitive emitters (R12 / AC1009) ───────────────────────────────────

def _circle(layer: str, cx: float, cy: float, r: float) -> str:
    return (f"0\nCIRCLE\n8\n{layer}\n"
            f"10\n{cx:.6f}\n20\n{cy:.6f}\n30\n0.0\n40\n{r:.6f}\n")


def _polyline(layer: str, pts: np.ndarray) -> str:
    out = [f"0\nPOLYLINE\n8\n{layer}\n66\n1\n70\n1\n"]  # 70 bit-1 = closed
    for px, py in pts:
        out.append(f"0\nVERTEX\n8\n{layer}\n10\n{px:.6f}\n20\n{py:.6f}\n30\n0.0\n")
    out.append("0\nSEQEND\n")
    return "".join(out)


def _point(layer: str, cx: float, cy: float) -> str:
    return f"0\nPOINT\n8\n{layer}\n10\n{cx:.6f}\n20\n{cy:.6f}\n30\n0.0\n"


def _document(entities: str) -> str:
    layers = "".join(
        f"0\nLAYER\n2\n{name}\n70\n0\n62\n{color}\n6\nCONTINUOUS\n"
        for name, color in _LAYERS.items()
    )
    return (
        "0\nSECTION\n2\nHEADER\n"
        "9\n$ACADVER\n1\nAC1009\n"
        "9\n$INSUNITS\n70\n4\n"          # 4 = millimetres
        "0\nENDSEC\n"
        "0\nSECTION\n2\nTABLES\n"
        f"0\nTABLE\n2\nLAYER\n70\n{len(_LAYERS)}\n{layers}0\nENDTAB\n"
        "0\nENDSEC\n"
        "0\nSECTION\n2\nENTITIES\n"
        f"{entities}"
        "0\nENDSEC\n"
        "0\nEOF\n"
    )


# ── Public API ───────────────────────────────────────────────────────────────

def _ring_xy(ring) -> np.ndarray:
    """Shapely ring → unique XY vertices (drops the duplicate closing point)."""
    c = np.asarray(ring.coords, dtype=float)[:, :2]
    if len(c) > 1 and np.allclose(c[0], c[-1]):
        c = c[:-1]
    return c


def _candidate_section_zs(mesh, samples: int) -> list[float]:
    """Z heights worth sectioning to locate the drilling plane.

    A flange plate is bounded by two horizontal faces (top + bottom), so the
    midpoint between consecutive horizontal-face levels is guaranteed to cut
    *through* the plate and catch every vertical bolt hole — even a thin plate
    sitting atop a long throat adapter, where uniform fractional sampling can
    step right over it. Those midpoints are tried first; a uniform sweep is
    appended as a fallback for meshes with no clear horizontal plate faces.
    """
    z0, z1 = float(mesh.bounds[0, 2]), float(mesh.bounds[1, 2])
    span = z1 - z0
    zs: list[float] = []
    try:
        nz = mesh.face_normals[:, 2]
        cz = mesh.triangles_center[:, 2]
        horiz = np.abs(nz) > 0.99
        if horiz.any():
            levels = np.unique(np.round(cz[horiz], 3))
            if len(levels) >= 2:
                zs.extend(((levels[:-1] + levels[1:]) / 2.0).tolist())
    except Exception:
        pass
    zs.extend((z0 + np.linspace(0.08, 0.92, samples) * span).tolist())
    return zs


def _best_section_z(mesh, samples: int = 11):
    """Pick the Z that cuts the plate where the bolt pattern lives.

    Scans candidate heights and keeps the one whose cross-section has the most
    closed interior loops (the drilling plane); ties broken by exterior area.
    Returns ``(z, polygons)`` or ``(None, [])`` if nothing sections.
    """
    z0, z1 = float(mesh.bounds[0, 2]), float(mesh.bounds[1, 2])
    span = z1 - z0
    if span <= 1e-6:
        return None, []
    best = (None, [], -1, -1.0)  # z, polygons, n_holes, ext_area
    for z in _candidate_section_zs(mesh, samples):
        sec = mesh.section(plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
        if sec is None:
            continue
        try:
            p2d, _ = sec.to_planar()
            polys = list(p2d.polygons_full)
        except Exception:
            continue
        if not polys:
            continue
        n_holes = sum(len(p.interiors) for p in polys)
        ext_area = sum(p.area for p in polys)
        if (n_holes, ext_area) > (best[2], best[3]):
            best = (z, polys, n_holes, ext_area)
    return best[0], best[1]


def elliptical_flange_dxf(
    inner_w: float,
    inner_h: float,
    ring: float | None = None,
    bolt_count: int = 0,
    bolt_diam: float = 0.0,
    bolt_phase: float = 0.0,
    sections: int = 128,
    output_path: str | None = None,
    outer_w: float | None = None,
    outer_h: float | None = None,
) -> str:
    """Analytic 2-D DXF drilling template for an elliptical-offset flange.

    Built directly from the source parameters (not by sectioning a mesh), so the
    geometry is exact and immune to boolean/mesh artefacts that can mis-centre
    mesh-derived holes. Matches the solid produced by
    ``rectangular_flange.generate_rectangular_flange`` with
    ``outer_type="elliptical"`` / ``inner_type="elliptical"`` — the OUTLINE
    is a **true geometric offset** (parallel curve via Shapely buffer), not a
    scaled copy of the BORE ellipse, giving constant ring width:

      * BORE    — the hole ellipse, semi-axes ``(a, b) = (inner_w/2, inner_h/2)``
      * OUTLINE — true parallel curve at distance ``ring``, polyline with
                  ``sections`` vertices
      * HOLES   — ``bolt_count`` circles on the true half-offset curve
                  ``BORE.buffer(ring/2)`` + a centre mark each

    ``inner_w``/``inner_h`` are full axis lengths. Returns the DXF text (and
    writes *output_path* if given).
    """
    a, b = inner_w / 2.0, inner_h / 2.0
    if outer_w is None or outer_h is None:
        if ring is None:
            raise ValueError("ring or both outer_w/outer_h are required")
        outer_w, outer_h = inner_w + 2.0 * ring, inner_h + 2.0 * ring
    ao, bo = outer_w / 2.0, outer_h / 2.0
    ring_w, ring_h = ao - a, bo - b
    theta = np.linspace(0.0, 2.0 * np.pi, sections, endpoint=False)
    ct, st = np.cos(theta), np.sin(theta)
    bore = np.column_stack([a * ct, b * st])

    # True geometric offset (parallel curve) via Shapely buffer.
    # The old outline = (ao*cos, bo*sin) was a scaled ellipse, not a
    # constant-distance ring.
    if abs(ring_w - ring_h) < 0.01:
        from shapely.geometry import Point
        from shapely import affinity
        unit = Point(0, 0).buffer(1.0, resolution=sections)
        inner_ellipse = affinity.scale(unit, xfact=a, yfact=b)
        outer_topo = inner_ellipse.buffer(ring_w)
        midline = np.asarray(
            inner_ellipse.buffer(ring_w / 2.0).exterior.coords)[:, :2]
        outline_xy = np.asarray(outer_topo.exterior.coords)[:, :2]
        # Resample to exactly *sections* points
        from shapely.geometry import LineString
        ls = LineString(outline_xy)
        outline = np.empty((sections, 2), dtype=float)
        for i in range(sections):
            p = ls.interpolate(ls.length * i / sections)
            outline[i] = [p.x, p.y]
    else:
        outline = np.column_stack([ao * ct, bo * st])
        midline = np.column_stack([
            ((a + ao) / 2.0) * ct,
            ((b + bo) / 2.0) * st,
        ])
        midline = np.vstack([midline, midline[0]])

    ent: list[str] = [_polyline("OUTLINE", outline), _polyline("BORE", bore)]

    if bolt_count and bolt_count > 0 and bolt_diam > 0.0:
        def _ray_extent(points: np.ndarray, angle: float) -> float:
            ray = np.array([np.cos(angle), np.sin(angle)])
            best = np.inf
            for p0, p1 in zip(points, points[1:]):
                edge = p1 - p0
                cross = ray[0] * edge[1] - ray[1] * edge[0]
                if abs(cross) < 1e-12:
                    continue
                t = (p0[0] * edge[1] - p0[1] * edge[0]) / cross
                u = (p0[0] * ray[1] - p0[1] * ray[0]) / cross
                if t > 0.0 and -1e-9 <= u <= 1.0 + 1e-9:
                    best = min(best, t)
            return float(best)

        ang = np.linspace(0.0, 2.0 * np.pi, int(bolt_count),
                          endpoint=False) + bolt_phase
        for t in ang:
            radius = _ray_extent(midline, t)
            cx, cy = radius * np.cos(t), radius * np.sin(t)
            ent.append(_circle("HOLES", float(cx), float(cy), bolt_diam / 2.0))
            ent.append(_point("CENTERS", float(cx), float(cy)))

    dxf = _document("".join(ent))
    if output_path:
        with open(output_path, "w") as fh:
            fh.write(dxf)
    return dxf


def mesh_to_flange_dxf(mesh, z: float | None = None,
                       output_path: str | None = None) -> str | None:
    """Build a 2-D DXF drilling template from a flange mesh.

    *z* — explicit section height; if ``None`` the drilling plane is located
    automatically. Returns the DXF text (and writes *output_path* if given), or
    ``None`` when the mesh yields no usable cross-section.
    """
    if z is None:
        z, polys = _best_section_z(mesh)
        if z is None:
            return None
    else:
        sec = mesh.section(plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
        if sec is None:
            return None
        p2d, _ = sec.to_planar()
        polys = list(p2d.polygons_full)
        if not polys:
            return None

    if not any(len(p.interiors) for p in polys):
        # Solid outline with no bore or bolt holes — not a flange template.
        return None

    ent: list[str] = []
    for poly in polys:
        ext = _ring_xy(poly.exterior)
        cx, cy, r_fit, r_min, r_max = _fit_circle(ext)
        if _is_round(r_min, r_max, len(ext)):
            ent.append(_circle("OUTLINE", cx, cy, r_fit))
        else:
            ent.append(_polyline("OUTLINE", ext))

        for ring in poly.interiors:
            pts = _ring_xy(ring)
            cx, cy, r_fit, r_min, r_max = _fit_circle(pts)
            centred = np.hypot(cx, cy) < max(2.0, 0.25 * r_max)
            if centred:
                # Throat bore — keep its true shape.
                if _is_round(r_min, r_max, len(pts)):
                    ent.append(_circle("BORE", cx, cy, r_fit))
                else:
                    ent.append(_polyline("BORE", pts))
            else:
                # Off-axis loop = bolt hole; always round → nominal circle.
                ent.append(_circle("HOLES", cx, cy, r_max))
                ent.append(_point("CENTERS", cx, cy))

    if not ent:
        return None
    dxf = _document("".join(ent))
    if output_path:
        with open(output_path, "w") as fh:
            fh.write(dxf)
    return dxf
