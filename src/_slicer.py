"""
STL slicer — cut a horn mesh lengthwise or into radial petals.

Uses trimesh for plane slicing with capping.
"""

import numpy as np
import trimesh
import shapely as shp


def _half_space_box(normal: np.ndarray, size: float) -> trimesh.Trimesh:
    """A large box covering the half-space ``normal·x >= 0`` (origin on its face).

    Used as a boolean cutter for radial petal seams. ``trimesh.slice_plane`` caps
    a planar cut by ear-clipping the section polygon, which fails (non-watertight
    slivers, open edges) when the section is a multi-loop ring — exactly what an
    adapter segment is (wall annulus + threaded socket + bore). A boolean
    intersection against this solid is section-shape agnostic and stays
    watertight."""
    normal = np.asarray(normal, dtype=float)
    normal = normal / (np.linalg.norm(normal) + 1e-12)
    box = trimesh.creation.box(extents=[size, size, size])
    # Align the box's local +X with `normal`, then push it so its near face sits
    # on the origin plane and the body extends to the +normal (keep) side.
    box.apply_transform(trimesh.geometry.align_vectors([1.0, 0.0, 0.0], normal))
    box.apply_translation(normal * size / 2.0)
    return box


def _plane_cut(mesh: trimesh.Trimesh, origin, normal) -> trimesh.Trimesh | None:
    """Keep the half of *mesh* on the +*normal* side of the plane through
    *origin*, via boolean intersection with a half-space solid.

    Why not ``mesh.slice_plane(..., cap=True)``: that caps the cut by
    ear-clipping the section *polygon*, which leaves open edges / non-manifold
    slivers when the section has multiple loops or coincident faces — e.g. a
    throat-adapter segment (wall annulus + threaded socket + bore) or the exact
    adapter↔flare weld overlap, whose coincident surfaces survive the union but
    trip the cap. A boolean intersection is section-shape agnostic and stays
    watertight. Falls back to the legacy cap only if the boolean fails."""
    origin = np.asarray(origin, dtype=float)
    normal = np.asarray(normal, dtype=float)
    size = float((mesh.bounds[1] - mesh.bounds[0]).max()) * 4.0 + 10.0
    box = _half_space_box(normal, size)
    box.apply_translation(origin)
    try:
        out = trimesh.boolean.intersection([mesh, box], engine="manifold")
        if out is not None and not out.is_empty:
            return out
    except Exception:
        pass
    return mesh.slice_plane(origin, normal, cap=True)


def _outer_polygon(mesh, origin, normal):
    """Return the outermost shapely Polygon of a mesh cross-section at *origin*."""
    section = mesh.section(plane_origin=origin, plane_normal=normal)
    if section is None:
        return None
    try:
        planar, _ = section.to_2D()
    except Exception:
        return None
    if planar is None:
        return None
    polys = planar.polygons_closed
    if len(polys) == 0:
        return None
    return max(polys, key=lambda p: p.area)


def _wall_angle_deg(mesh, z):
    """Compute the wall angle (deg from vertical) at Z=z via adjacent cross-sections."""
    dz = max(1.0, (mesh.bounds[1, 2] - mesh.bounds[0, 2]) * 0.02)
    p0 = _outer_polygon(mesh, [0, 0, z], [0, 0, 1])
    p1 = _outer_polygon(mesh, [0, 0, z + dz], [0, 0, 1])
    if p0 is None or p1 is None:
        return 0.0
    pts0 = np.array(p0.exterior.coords)
    pts1 = np.array(p1.exterior.coords)
    c0 = np.array([p0.centroid.x, p0.centroid.y])
    c1 = np.array([p1.centroid.x, p1.centroid.y])
    r0 = np.sqrt(((pts0 - c0)**2).sum(axis=1)).mean()
    r1 = np.sqrt(((pts1 - c1)**2).sum(axis=1)).mean()
    slope = (r1 - r0) / dz
    return float(np.degrees(np.arctan(abs(slope))))


def _precompute_angles(mesh, cuts):
    """Compute wall angles at all cut Z positions from the *original* mesh."""
    return {z: _wall_angle_deg(mesh, z) for z in cuts[1:-1]}


def add_axial_lip(segment: trimesh.Trimesh, z: float, wall: float,
                  direction: str = "up", angle_deg: float = 0.0) -> trimesh.Trimesh:
    """
    Add a joint lip on the OUTER surface of *segment* at Z=*z*, going UP/DOWN.
    """
    eps = 0.01 * (1.0 if direction == "up" else -1.0)
    outer = _outer_polygon(segment, [0, 0, z - eps], [0, 0, 1])
    if outer is None:
        return segment

    ring = outer.buffer(wall, join_style=shp.BufferJoinStyle.mitre)
    ring = shp.difference(ring, outer)
    if ring.is_empty:
        return segment

    s = np.sin(np.radians(angle_deg))
    c = np.cos(np.radians(angle_deg))
    # Extrude the ring vertically by enough height
    h = max(wall * c, 0.1) if direction == "up" else -max(wall * c, 0.1)
    lip = trimesh.creation.extrude_polygon(ring, height=h)
    lip.apply_translation([0, 0, z if direction == "up" else z - abs(h)])

    # Shear vertices outward to follow the wall angle
    if angle_deg > 0.5:
        verts = lip.vertices.copy()
        z_bottom = z if direction == "up" else z - abs(h)
        frac = np.clip((verts[:, 2] - z_bottom) / abs(h), 0, 1)
        r = np.sqrt(verts[:, 0]**2 + verts[:, 1]**2)
        theta = np.arctan2(verts[:, 1], verts[:, 0])
        dr = wall * s * frac
        verts[:, 0] += dr * np.cos(theta)
        verts[:, 1] += dr * np.sin(theta)
        lip.vertices = verts

    try:
        result = trimesh.boolean.union([segment, lip], engine="manifold", check_volume=False)
    except Exception:
        result = trimesh.util.concatenate([segment, lip])
    if result is not None and not result.is_empty:
        return result
    return segment


def add_axial_flange(segment: trimesh.Trimesh, z: float,
                     thickness: float, ring: float, wall: float,
                     bolt_n: int, bolt_d: float, bolt_phase: float = 0.0,
                     direction: str = "up") -> trimesh.Trimesh:
    """
    Add a bolted flange on the OUTER surface of *segment* at Z=*z*.
    If direction == "up", the cut is at z and the segment goes UP (this is the TOP segment, so flange is at its bottom, occupying [z, z+thickness]).
    If direction == "down", the cut is at z and the segment goes DOWN (this is the BOTTOM segment, so flange is at its top, occupying [z-thickness, z]).
    """
    import flange_generator as _fg
    
    eps = 0.01 * (1.0 if direction == "up" else -1.0)
    outer = _outer_polygon(segment, [0, 0, z + eps], [0, 0, 1])
    if outer is None:
        return segment

    pts = np.array(outer.exterior.coords)
    
    # generate_contour_flange places the top face at `offset` and grows downwards by `thickness`.
    # For direction == "up", the flange needs to sit above Z. So top face is z + thickness.
    # For direction == "down", the flange sits below Z. So top face is z.
    flange_offset = z + thickness if direction == "up" else z
    
    flange = _fg.generate_contour_flange(
        inner_xy=pts,
        thickness=thickness,
        bolt_n=bolt_n,
        bolt_d=bolt_d,
        offset=flange_offset,
        wall=wall,
        ring=ring,
        bite=0.5,
        bolt_phase=bolt_phase
    )
    
    if flange is None or flange.is_empty:
        return segment
        
    try:
        result = trimesh.boolean.union([segment, flange], engine="manifold", check_volume=False)
    except Exception:
        result = trimesh.util.concatenate([segment, flange])
        
    if result is not None and not result.is_empty:
        return result
    return segment


def slice_at_z(mesh: trimesh.Trimesh, z: float, keep: str = "below"
               ) -> trimesh.Trimesh | None:
    """
    Cut *mesh* with a plane at Z=*z*, keep one side.

    Parameters
    ----------
    mesh : trimesh.Trimesh
    z : float
        Z-coordinate of the cutting plane.
    keep : "below" | "above"
        Which side to keep.

    Returns a single watertight Trimesh (capped) or None if empty.
    """
    plane_normal = np.array([0.0, 0.0, 1.0])
    plane_origin = np.array([0.0, 0.0, z])
    if keep == "above":
        plane_normal = -plane_normal
    result = _plane_cut(mesh, plane_origin, plane_normal)
    if result is None or result.is_empty:
        return None
    return result


def _with_joints(segments, cuts, wall, angles=None, flange_params=None):
    """Add joint lips or bolted flanges — each cut gets joining geometry."""
    if (wall <= 0 and flange_params is None) or len(segments) <= 1:
        return segments
    if angles is None:
        angles = {}
    out = []
    for i, seg in enumerate(segments):
        if flange_params is not None:
            # apply flange at the bottom of this segment
            if i > 0:
                z_bottom = cuts[i]
                seg = add_axial_flange(seg, z_bottom, direction="up", **flange_params)
            # apply flange at the top of this segment
            if i < len(segments) - 1:
                z_top = cuts[i + 1]
                seg = add_axial_flange(seg, z_top, direction="down", **flange_params)
        elif wall > 0:
            if i < len(segments) - 1:
                z_cut = cuts[i + 1]
                ang = angles.get(z_cut, 0.0)
                seg = add_axial_lip(seg, z_cut, wall, direction="up", angle_deg=ang)
        out.append(seg)
    return out


def slice_into_segments(mesh: trimesh.Trimesh, n: int,
                        joint_wall: float = 0.0,
                        flange_params: dict | None = None
                        ) -> list[trimesh.Trimesh]:
    """
    Cut *mesh* into *n* axial segments of equal Z-height.

    When *joint_wall* > 0, a joint lip is added to each intermediate cut.
    When *flange_params* is provided, a bolted flange is added to each cut.
    """
    z_min = mesh.bounds[0, 2]
    z_max = mesh.bounds[1, 2]
    dz = (z_max - z_min) / n

    segments: list[trimesh.Trimesh] = []
    lo = z_min
    cuts = [z_min]
    for i in range(n):
        hi = lo + dz
        cuts.append(hi)
        seg = _plane_cut(mesh, [0.0, 0.0, lo], [0.0, 0.0, 1.0])
        if seg is not None and not seg.is_empty:
            seg = _plane_cut(seg, [0.0, 0.0, hi], [0.0, 0.0, -1.0])
            if seg is not None and not seg.is_empty:
                segments.append(seg)
        lo = hi
    angles = _precompute_angles(mesh, cuts) if (joint_wall > 0 and not flange_params) else None
    return _with_joints(segments, cuts, joint_wall, angles, flange_params)


def slice_at_heights(mesh: trimesh.Trimesh, heights: list[float],
                     joint_wall: float = 0.0,
                     flange_params: dict | None = None
                     ) -> list[trimesh.Trimesh]:
    """
    Cut *mesh* at the given Z *heights*. Returns capped slabs.

    When *joint_wall* > 0, a joint lip is added at each cut.
    When *flange_params* is provided, a bolted flange is added.
    """
    z_min = mesh.bounds[0, 2]
    z_max = mesh.bounds[1, 2]
    cuts = sorted([z_min] + [h for h in heights if z_min < h < z_max] + [z_max])

    segments: list[trimesh.Trimesh] = []
    for i in range(len(cuts) - 1):
        lo, hi = cuts[i], cuts[i + 1]
        seg = _plane_cut(mesh, [0.0, 0.0, lo], [0.0, 0.0, 1.0])
        if seg is not None and not seg.is_empty:
            seg = _plane_cut(seg, [0.0, 0.0, hi], [0.0, 0.0, -1.0])
            if seg is not None and not seg.is_empty:
                segments.append(seg)
    angles = _precompute_angles(mesh, cuts) if (joint_wall > 0 and not flange_params) else None
    return _with_joints(segments, cuts, joint_wall, angles, flange_params)


def slice_with_adapter_segment(
    mesh: trimesh.Trimesh,
    adapter_cut_z: float,
    flare_segments: int = 1,
    flare_height: float | None = None,
    joint_wall: float = 0.0,
    flange_params: dict | None = None,
) -> list[trimesh.Trimesh]:
    """
    Cut off the throat adapter as its own bottom axial segment, then slice only
    the flare side above *adapter_cut_z*.

    *adapter_cut_z* is the Z height where the adapter enters the horn throat.
    When *joint_wall* > 0 the adapter→flare cut receives the same axial lip as
    any other intermediate Z cut.
    """
    z_min = float(mesh.bounds[0, 2])
    z_max = float(mesh.bounds[1, 2])
    cut = float(adapter_cut_z)
    cuts: list[float] = []

    if z_min + 1e-6 < cut < z_max - 1e-6:
        cuts.append(cut)
    else:
        return slice_into_segments(mesh, max(1, int(flare_segments)),
                                   joint_wall=joint_wall,
                                   flange_params=flange_params)

    if flare_height is not None and flare_height > 0:
        z = cut + float(flare_height)
        while z < z_max - 1e-6:
            cuts.append(z)
            z += float(flare_height)
    else:
        n = max(1, int(flare_segments))
        if n > 1:
            dz = (z_max - cut) / n
            cuts.extend(cut + dz * k for k in range(1, n))

    return slice_at_heights(mesh, cuts, joint_wall=joint_wall, flange_params=flange_params)


def _axis_intervals(lo: float, hi: float, max_size: float) -> list[tuple[float, float]]:
    """Split [lo, hi] into intervals no larger than *max_size*."""
    lo = float(lo)
    hi = float(hi)
    max_size = float(max_size)
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    if hi <= lo:
        return []
    intervals = []
    cur = lo
    while cur < hi - 1e-6:
        nxt = min(cur + max_size, hi)
        intervals.append((cur, nxt))
        cur = nxt
    return intervals


def _balanced_axis_intervals(lo: float, hi: float, max_size: float) -> list[tuple[float, float]]:
    """Split [lo, hi] into near-equal intervals no larger than *max_size*."""
    lo = float(lo)
    hi = float(hi)
    max_size = float(max_size)
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    if hi <= lo:
        return []
    span = hi - lo
    count = int(np.ceil(span / max_size))
    step = span / count
    return [(lo + step * i, lo + step * (i + 1)) for i in range(count)]


def _centered_axis_intervals(lo: float, hi: float, max_size: float) -> list[tuple[float, float, int]]:
    """Return center-first intervals as (lo, hi, ring), where ring 0 is central."""
    lo = float(lo)
    hi = float(hi)
    max_size = float(max_size)
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    if hi <= lo:
        return []
    span = hi - lo
    if span <= max_size + 1e-6:
        return [(lo, hi, 0)]

    center = (lo + hi) / 2.0
    c0 = max(lo, center - max_size / 2.0)
    c1 = min(hi, c0 + max_size)
    c0 = max(lo, c1 - max_size)
    intervals = [(c0, c1, 0)]

    ring = 1
    left_hi = c0
    right_lo = c1
    while left_hi > lo + 1e-6 or right_lo < hi - 1e-6:
        if left_hi > lo + 1e-6:
            left_lo = max(lo, left_hi - max_size)
            intervals.append((left_lo, left_hi, ring))
            left_hi = left_lo
        if right_lo < hi - 1e-6:
            right_hi = min(hi, right_lo + max_size)
            intervals.append((right_lo, right_hi, ring))
            right_lo = right_hi
        ring += 1
    return intervals


def _clip_to_box(
    mesh: trimesh.Trimesh,
    bounds_min: tuple[float, float, float],
    bounds_max: tuple[float, float, float],
) -> trimesh.Trimesh | None:
    """Clip *mesh* to an axis-aligned box and cap every cut plane."""
    out = mesh
    xmin, ymin, zmin = bounds_min
    xmax, ymax, zmax = bounds_max
    planes = [
        ([xmin, 0.0, 0.0], [1.0, 0.0, 0.0]),
        ([xmax, 0.0, 0.0], [-1.0, 0.0, 0.0]),
        ([0.0, ymin, 0.0], [0.0, 1.0, 0.0]),
        ([0.0, ymax, 0.0], [0.0, -1.0, 0.0]),
        ([0.0, 0.0, zmin], [0.0, 0.0, 1.0]),
        ([0.0, 0.0, zmax], [0.0, 0.0, -1.0]),
    ]
    for origin, normal in planes:
        out = out.slice_plane(origin, normal, cap=True)
        if out is None or out.is_empty:
            return None
    out.merge_vertices()
    out.fix_normals()
    return out


def _split_adaptive_to_limits(
    mesh: trimesh.Trimesh,
    limits: np.ndarray,
) -> list[trimesh.Trimesh]:
    """Recursively split a mesh until every real bounding box fits *limits*."""
    pieces: list[trimesh.Trimesh] = []
    queue = [mesh]
    while queue:
        part = queue.pop(0)
        dims = part.bounds[1] - part.bounds[0]
        excess = dims / limits
        axis = int(np.argmax(excess))
        if excess[axis] <= 1.0 + 1e-6:
            pieces.append(part)
            continue

        cut = float((part.bounds[0, axis] + part.bounds[1, axis]) / 2.0)
        origin = np.zeros(3)
        normal = np.zeros(3)
        origin[axis] = cut
        normal[axis] = 1.0
        below = part.slice_plane(origin, -normal, cap=True)
        above = part.slice_plane(origin, normal, cap=True)
        children = []
        for child in (below, above):
            if child is not None and not child.is_empty and child.volume > 1e-3:
                child.merge_vertices()
                child.fix_normals()
                children.append(child)
        if len(children) <= 1:
            pieces.append(part)
        else:
            queue.extend(children)
    return pieces


def _box_face_polygons(part: trimesh.Trimesh, axis: int, coord: float, normal: np.ndarray):
    """Return significant polygons on an axis-aligned print-volume cut face."""
    origin = np.zeros(3)
    origin[axis] = coord
    polys, to_3D = _seam_face_polygons(part, origin, normal, min_area_frac=0.01)
    if polys:
        return polys, to_3D
    return _seam_face_polygons(part, origin, -normal, min_area_frac=0.01)


def _add_box_tongue(
    part: trimesh.Trimesh,
    axis: int,
    side: int,
    joint_depth: float,
    margin: float,
    clearance: float,
) -> trimesh.Trimesh:
    """Add a tongue protruding from one axis-aligned print-volume face."""
    normal = np.zeros(3)
    normal[axis] = float(side)
    coord = float(part.bounds[1 if side > 0 else 0, axis])
    polys, to_3D = _box_face_polygons(part, axis, coord, normal)
    if not polys or to_3D is None:
        return part

    overlap = min(1.0, max(0.2, joint_depth * 0.5))
    tongues = []
    for poly in polys:
        inner = _joint_profile(poly, to_3D, margin, clearance / 2.0)
        if inner is None or inner.is_empty:
            continue
        tongue = trimesh.creation.extrude_polygon(inner, height=joint_depth + overlap)
        tongue.apply_translation([0.0, 0.0, -overlap])
        transform = to_3D.copy()
        transform[:3, 2] = normal
        tongue.apply_transform(transform)
        tongues.append(tongue)
    if not tongues:
        return part

    try:
        result = trimesh.boolean.union([part, *tongues], engine="manifold",
                                       check_volume=False)
    except Exception:
        result = trimesh.util.concatenate([part, *tongues])
    if result is not None and not result.is_empty:
        return result
    return part


def _add_box_groove(
    part: trimesh.Trimesh,
    axis: int,
    side: int,
    joint_depth: float,
    margin: float,
    clearance: float,
) -> trimesh.Trimesh:
    """Cut a groove into one axis-aligned print-volume face."""
    normal = np.zeros(3)
    normal[axis] = float(side)
    coord = float(part.bounds[1 if side > 0 else 0, axis])
    polys, to_3D = _box_face_polygons(part, axis, coord, normal)
    if not polys or to_3D is None:
        return part

    overlap = min(1.0, max(0.2, joint_depth * 0.5))
    result = part
    for poly in polys:
        inner = _joint_profile(poly, to_3D, margin, -clearance / 2.0)
        if inner is None or inner.is_empty:
            continue
        groove = trimesh.creation.extrude_polygon(inner, height=joint_depth + overlap)
        transform = to_3D.copy()
        transform[:3, 2] = -normal
        transform[:3, 3] += normal * overlap
        groove.apply_transform(transform)
        try:
            cut = trimesh.boolean.difference([result, groove], engine="manifold",
                                             check_volume=False)
        except Exception:
            return part
        if cut is not None and not cut.is_empty:
            result = cut
    return result


def _face_overlap(bounds_a: np.ndarray, bounds_b: np.ndarray, axis: int) -> float:
    """Return overlap area of two bounding boxes on the face orthogonal to *axis*."""
    other = [i for i in range(3) if i != axis]
    area = 1.0
    for ax in other:
        lo = max(float(bounds_a[0, ax]), float(bounds_b[0, ax]))
        hi = min(float(bounds_a[1, ax]), float(bounds_b[1, ax]))
        if hi <= lo + 1e-6:
            return 0.0
        area *= hi - lo
    return area


def _add_print_volume_joints(
    pieces: list[trimesh.Trimesh],
    joint_depth: float,
    joint_margin: float,
    clearance: float,
) -> list[trimesh.Trimesh]:
    """Add tongue/groove joints between neighboring print-volume chunks."""
    if joint_depth <= 0 or len(pieces) <= 1:
        return pieces

    out = list(pieces)
    original_bounds = [p.bounds.copy() for p in pieces]
    ops: list[list[tuple[str, int, int]]] = [[] for _ in pieces]
    touch_tol = max(0.05, clearance * 2.0)
    min_overlap = max((joint_margin * 2.0) ** 2, 4.0)

    for i in range(len(pieces)):
        for j in range(i + 1, len(pieces)):
            bi = original_bounds[i]
            bj = original_bounds[j]
            for axis in range(3):
                if abs(float(bi[1, axis] - bj[0, axis])) <= touch_tol:
                    if _face_overlap(bi, bj, axis) >= min_overlap:
                        ops[i].append(("tongue", axis, 1))
                        ops[j].append(("groove", axis, -1))
                    break
                if abs(float(bj[1, axis] - bi[0, axis])) <= touch_tol:
                    if _face_overlap(bi, bj, axis) >= min_overlap:
                        ops[j].append(("tongue", axis, 1))
                        ops[i].append(("groove", axis, -1))
                    break

    for idx, part_ops in enumerate(ops):
        seen = set()
        part = out[idx]
        for kind, axis, side in part_ops:
            key = (kind, axis, side)
            if key in seen:
                continue
            seen.add(key)
            if kind == "tongue":
                part = _add_box_tongue(part, axis, side, joint_depth,
                                       joint_margin, clearance)
            else:
                part = _add_box_groove(part, axis, side, joint_depth,
                                       joint_margin, clearance)
        part.metadata.update(pieces[idx].metadata)
        out[idx] = part
    return out


def slice_to_print_volume(
    mesh: trimesh.Trimesh,
    max_x: float,
    max_y: float,
    max_z: float,
    keep_z_max: float | None = None,
    strategy: str = "center_up",
    joint_depth: float = 0.0,
    joint_margin: float = 1.0,
    clearance: float = 0.1,
) -> list[trimesh.Trimesh]:
    """
    Slice *mesh* into axis-aligned cuboid chunks constrained by max print volume.

    If *keep_z_max* is set, the throat-side range is kept inside the first
    center-bottom chunk rather than exported as a separate adapter/flange piece.
    That first chunk may exceed the requested build volume so throat hardware
    remains monolithic with the lower horn body.

    strategy="center_up" cuts center-first in X/Y and bottom-up in Z. It yields
    a central stack first, then side wings. strategy="adaptive" recursively
    splits the current largest offending real piece. strategy="grid" uses a
    fixed global X/Y/Z box grid.
    """
    if max_x <= 0 or max_y <= 0 or max_z <= 0:
        raise ValueError("max print dimensions must be positive")

    bmin = mesh.bounds[0].astype(float)
    bmax = mesh.bounds[1].astype(float)
    z_min, z_max = float(bmin[2]), float(bmax[2])
    pieces: list[trimesh.Trimesh] = []

    keep_z = None
    if keep_z_max is not None:
        keep_z = float(np.clip(keep_z_max, z_min, z_max))

    whole = _clip_to_box(mesh, tuple(bmin), tuple(bmax))
    if whole is None or whole.is_empty:
        return _add_print_volume_joints(pieces, joint_depth, joint_margin, clearance)

    protected_z1 = None
    if keep_z is not None:
        protected_z1 = min(z_max, max(z_min + max_z, keep_z))

    if strategy == "adaptive":
        limits = np.array([max_x, max_y, max_z], dtype=float)
        adaptive_start = z_min
        if protected_z1 is not None:
            first = _clip_to_box(mesh, (bmin[0], bmin[1], z_min), (bmax[0], bmax[1], protected_z1))
            if first is not None and not first.is_empty:
                first.metadata["print_volume_ring"] = 0
                first.metadata["print_volume_core"] = True
                first.metadata["print_volume_z"] = (float(z_min), float(protected_z1))
                pieces.append(first)
            adaptive_start = protected_z1
        rest = _clip_to_box(mesh, (bmin[0], bmin[1], adaptive_start), (bmax[0], bmax[1], z_max))
        if rest is not None and not rest.is_empty:
            pieces.extend(_split_adaptive_to_limits(rest, limits))
        return _add_print_volume_joints(pieces, joint_depth, joint_margin, clearance)

    if strategy not in ("center_up", "grid"):
        raise ValueError("strategy must be 'center_up', 'adaptive' or 'grid'")

    if strategy == "center_up":
        limits = np.array([max_x, max_y, max_z], dtype=float)
        cx_intervals = _centered_axis_intervals(bmin[0], bmax[0], max_x)
        cy_intervals = _centered_axis_intervals(bmin[1], bmax[1], max_y)
        cx0, cx1, _ = cx_intervals[0]
        cy0, cy1, _ = cy_intervals[0]

        core_z0 = z_min
        first_z1 = min(z_max, z_min + max_z)
        if protected_z1 is not None:
            first_z1 = protected_z1
            first = _clip_to_box(mesh, (bmin[0], bmin[1], core_z0), (bmax[0], bmax[1], first_z1))
            if first is not None and not first.is_empty:
                first.metadata["print_volume_ring"] = 0
                first.metadata["print_volume_core"] = True
                first.metadata["print_volume_z"] = (float(core_z0), float(first_z1))
                pieces.append(first)
            core_z0 = first_z1

        core_probe = _clip_to_box(mesh, (cx0, cy0, core_z0), (cx1, cy1, z_max))
        core_z1 = z_max
        if core_probe is not None and not core_probe.is_empty:
            core_z1 = float(core_probe.bounds[1, 2])

        for z0, z1 in _balanced_axis_intervals(core_z0, core_z1, max_z):
            core = _clip_to_box(mesh, (cx0, cy0, z0), (cx1, cy1, z1))
            if core is not None and not core.is_empty and core.volume > 1e-3:
                core.metadata["print_volume_ring"] = 0
                core.metadata["print_volume_core"] = True
                core.metadata["print_volume_z"] = (float(z0), float(z1))
                pieces.append(core)

        wing_regions = [
            (bmin[0], cx0, bmin[1], bmax[1]),
            (cx1, bmax[0], bmin[1], bmax[1]),
            (cx0, cx1, bmin[1], cy0),
            (cx0, cx1, cy1, bmax[1]),
        ]
        wing_start = first_z1 if keep_z is not None else z_min
        for x0, x1, y0, y1 in wing_regions:
            if x1 <= x0 + 1e-6 or y1 <= y0 + 1e-6:
                continue
            wing = _clip_to_box(mesh, (x0, y0, wing_start), (x1, y1, z_max))
            if wing is None or wing.is_empty:
                continue
            for part in _split_adaptive_to_limits(wing, limits):
                part.metadata["print_volume_ring"] = 1
                part.metadata["print_volume_core"] = False
                part.metadata["print_volume_z"] = (float(part.bounds[0, 2]), float(part.bounds[1, 2]))
                pieces.append(part)
        return _add_print_volume_joints(pieces, joint_depth, joint_margin, clearance)

    grid_z_min = z_min
    if protected_z1 is not None:
        first = _clip_to_box(mesh, (bmin[0], bmin[1], z_min), (bmax[0], bmax[1], protected_z1))
        if first is not None and not first.is_empty:
            first.metadata["print_volume_ring"] = 0
            first.metadata["print_volume_core"] = True
            first.metadata["print_volume_z"] = (float(z_min), float(protected_z1))
            pieces.append(first)
        grid_z_min = protected_z1

    x_intervals = [(a, b, i) for i, (a, b) in enumerate(_axis_intervals(bmin[0], bmax[0], max_x))]
    y_intervals = [(a, b, i) for i, (a, b) in enumerate(_axis_intervals(bmin[1], bmax[1], max_y))]
    z_intervals = _axis_intervals(grid_z_min, z_max, max_z)

    cells = []
    for yr, (y0, y1, y_ring) in enumerate(y_intervals):
        for xr, (x0, x1, x_ring) in enumerate(x_intervals):
            ring = max(x_ring, y_ring)
            dist = abs((x0 + x1) / 2.0 - (bmin[0] + bmax[0]) / 2.0) + \
                   abs((y0 + y1) / 2.0 - (bmin[1] + bmax[1]) / 2.0)
            cells.append((ring, dist, yr, xr, x0, x1, y0, y1))
    cells.sort(key=lambda c: (c[0], c[1], c[2], c[3]))

    for ring, _dist, _yr, _xr, x0, x1, y0, y1 in cells:
        for z0, z1 in z_intervals:
            part = _clip_to_box(mesh, (x0, y0, z0), (x1, y1, z1))
            if part is not None and not part.is_empty and part.volume > 1e-3:
                part.metadata["print_volume_ring"] = int(ring)
                part.metadata["print_volume_core"] = bool(ring == 0)
                part.metadata["print_volume_z"] = (float(z0), float(z1))
                pieces.append(part)
    return _add_print_volume_joints(pieces, joint_depth, joint_margin, clearance)


def seam_phase_avoiding_holes(n: int, hole_angles, samples: int = 1440) -> float:
    """
    Pick a seam phase (rad) for *n* evenly-spaced radial cuts that keeps every
    seam as far as possible from every bolt-hole angle in *hole_angles* (rad).

    Returns a phase in [0, 2π/n).  The seams stay symmetric (still every 2π/n);
    the whole set is just rotated into the widest gap between holes.  With no
    holes it returns 0.
    """
    holes = np.asarray([h % (2 * np.pi) for h in hole_angles], dtype=float)
    if n < 2 or holes.size == 0:
        return 0.0
    seam0 = np.arange(n) * 2 * np.pi / n
    phases = np.linspace(0.0, 2 * np.pi / n, samples, endpoint=False)
    best_phase, best_gap = 0.0, -1.0
    for phase in phases:
        seams = (seam0[:, None] + phase) % (2 * np.pi)
        d = np.abs(seams - holes[None, :])
        d = np.minimum(d, 2 * np.pi - d)
        gap = float(d.min())
        if gap > best_gap:
            best_gap, best_phase = gap, float(phase)
    return best_phase


def _seam_face_polygons(petal, origin, normal, min_area_frac=0.0):
    """Return all significant closed polygons of a mesh cross-section + its to_3D.

    For n>=3 petals the seam plane meets the wall on a single strip, so this
    returns one polygon.  For n==2 the seam is a diametric plane that crosses the
    axis and meets the wall on TWO strips (one each side), so both are returned.
    Slivers below *min_area_frac* of the largest strip are dropped.
    The threshold is intentionally low so narrow flange strips are kept.
    """
    # Shift origin slightly into the petal to avoid coplanar face degeneracy
    safe_origin = np.asarray(origin, dtype=float) + np.asarray(normal, dtype=float) * 1e-4
    section = petal.section(plane_origin=safe_origin, plane_normal=normal)
    if section is None:
        return [], None
    try:
        planar, to_3D = section.to_2D(normal=normal)
    except Exception:
        return [], None
    polys = [p for p in planar.polygons_closed if p is not None and not p.is_empty]
    if not polys:
        return [], None
    max_area = max(p.area for p in polys)
    polys = [p for p in polys if p.area >= min_area_frac * max_area]
    return polys, to_3D


def _buffer_single(poly, distance):
    """Buffer a shapely polygon, returning a single Polygon (largest part if MultiPolygon)."""
    result = poly.buffer(distance, join_style=shp.BufferJoinStyle.mitre)
    if result is None or result.is_empty:
        return None
    if result.geom_type == "MultiPolygon":
        # Take the largest part (narrow walls can fragment under negative buffer)
        result = max(result.geoms, key=lambda p: p.area)
    return result


def _joint_profile(poly, to_3D, margin, clearance_offset=0.0,
                   outer_margin: float | None = None):
    """Return an inset joint profile biased away from the external skin."""
    inset = max(0.0, margin + clearance_offset)
    profile = _buffer_single(poly, -inset)
    if profile is None or to_3D is None:
        return profile

    if outer_margin is None:
        return profile

    keep_outer = float(outer_margin)
    if keep_outer <= inset + 1e-6:
        return profile

    clipped = _buffer_single(profile, -(keep_outer - inset))
    if clipped is None or clipped.is_empty:
        raise ValueError(
            f"outer_margin={keep_outer:.3f} mm cannot be satisfied by this seam face"
        )
    if clipped.geom_type == "MultiPolygon":
        clipped = max(clipped.geoms, key=lambda p: p.area)
    return clipped


def _filter_polys_by_side(polys, to_3D, axis, side):
    """Keep only the seam strips whose 3D centroid lies on the requested *side*.

    *axis* is an in-plane horizontal direction; *side* is +1 / -1 (or 0 = keep
    all).  Used for n==2, where the diametric seam yields two strips (one each
    side of the axis) and tongue/groove must land on opposite strips.
    """
    if side == 0 or axis is None:
        return polys
    out = []
    for p in polys:
        c = to_3D @ np.array([p.centroid.x, p.centroid.y, 0.0, 1.0])
        d = float(c[:3] @ axis)
        if (d > 0 and side > 0) or (d < 0 and side < 0):
            out.append(p)
    return out


def add_radial_tongue(petal: trimesh.Trimesh, angle: float,
                      joint_depth: float = 2.0,
                      margin: float = 1.0,
                      clearance: float = 0.1,
                      outer_margin: float | None = None,
                      side: int = 0, axis=None) -> trimesh.Trimesh:
    """
    Add a tongue on the RIGHT seam (at *angle*) of a radial petal.

    The tongue is a vertical strip biased toward the inner side of the wall,
    extruded outward along the seam normal by *joint_depth*.

    *clearance* is the total radial gap between tongue and groove when
    mated (split equally: clearance/2 per side).  With the default 0.1 mm
    each face gets 0.05 mm of air.

    When *side* != 0 (n==2 only), the tongue is restricted to the seam strip
    whose centroid sits on that *side* of *axis* (an in-plane direction).
    """
    normal = np.array([-np.sin(angle), np.cos(angle), 0.0])
    polys, to_3D = _seam_face_polygons(petal, [0.0, 0.0, 0.0], normal)
    polys = _filter_polys_by_side(polys, to_3D, axis, side)
    if not polys:
        return petal

    overlap = 1.0
    to_3D_out = to_3D.copy()
    to_3D_out[:3, 2] = -to_3D_out[:3, 2]
    tongues = []
    for poly in polys:
        inner = _joint_profile(poly, to_3D, margin, clearance / 2.0,
                               outer_margin=outer_margin)
        if inner is None:
            continue
        # Start the tongue *inside* the petal (z=-overlap) so it overlaps the body
        # volumetrically — a bare coplanar touch doesn't reliably weld in a union.
        t = trimesh.creation.extrude_polygon(inner, height=joint_depth + overlap)
        t.apply_translation([0.0, 0.0, -overlap])
        t.apply_transform(to_3D_out)
        tongues.append(t)
    if not tongues:
        return petal

    try:
        result = trimesh.boolean.union([petal, *tongues], engine="manifold",
                                       check_volume=False)
    except Exception:
        result = trimesh.util.concatenate([petal, *tongues])
    if result is not None and not result.is_empty:
        if result.body_count > 1:
            bodies = [b for b in result.split() if b.volume > 0]
            if len(bodies) == 1:
                result = bodies[0]
            elif len(bodies) > 1:
                try:
                    result = trimesh.boolean.union(bodies, engine="manifold",
                                                   check_volume=False)
                except Exception:
                    result = trimesh.util.concatenate(bodies)
        return result
    return petal


def add_radial_groove(petal: trimesh.Trimesh, angle: float,
                      joint_depth: float = 2.0,
                      margin: float = 1.0,
                      clearance: float = 0.1,
                      outer_margin: float | None = None,
                      side: int = 0, axis=None) -> trimesh.Trimesh:
    """
    Cut a groove on the LEFT seam (at *angle*) of a radial petal.

    The groove is a vertical slot biased toward the inner side of the wall,
    going INTO the petal by *joint_depth*.

    *clearance* is the total radial gap between tongue and groove when
    mated (split equally: clearance/2 per side).  With the default 0.1 mm
    each face gets 0.05 mm of air.

    When *side* != 0 (n==2 only), the groove is restricted to the seam strip
    whose centroid sits on that *side* of *axis* (an in-plane direction).
    """
    normal = np.array([np.sin(angle), -np.cos(angle), 0.0])
    polys, to_3D = _seam_face_polygons(petal, [0.0, 0.0, 0.0], normal)
    polys = _filter_polys_by_side(polys, to_3D, axis, side)
    if not polys:
        return petal

    overlap = 1.0
    to_3D_off = to_3D.copy()
    to_3D_off[:3, 3] += normal * (-overlap)

    result = petal
    for poly in polys:
        inner = _joint_profile(poly, to_3D, margin, -clearance / 2.0,
                               outer_margin=outer_margin)
        if inner is None:
            continue
        # Add 0.2mm to height to provide clearance at the tip of the tongue
        groove = trimesh.creation.extrude_polygon(inner, height=joint_depth + overlap + 0.2)
        groove.apply_transform(to_3D_off)
        try:
            cut = trimesh.boolean.difference([result, groove], engine="manifold",
                                             check_volume=False)
        except Exception:
            return petal
        if cut is not None and not cut.is_empty and cut.body_count == 1:
            result = cut
    return result


def slice_into_petals(mesh: trimesh.Trimesh, n: int,
                      phase: float = 0.0,
                      joint_depth: float = 0.0,
                      joint_margin: float = 0.5,
                      clearance: float = 0.1,
                      outer_margin: float | None = None,
                      flange_params: dict | None = None,
                      ) -> list[trimesh.Trimesh]:
    """
    Cut *mesh* into *n* radial petals (like an orange).

    Seams sit at angles *phase* + i·2π/n (rotate *phase* to keep them clear of
    flange bolt holes).  When *joint_depth* > 0 and n >= 3, each petal gets a
    tongue on its right seam face and a groove on its left seam face (tongue &
    groove joint).  For n == 2 the two halves share a single diametric seam (two
    wall strips, one each side of the axis); each half gets a tongue on one strip
    and a groove on the other, assigned so the halves mate and come out as
    identical parts.

    If *flange_params* is provided, an external bolted flange is added to the 
    seams instead of the internal tongue & groove joint.

    *clearance* — total radial gap between tongue and groove (default 0.1 mm).
    *outer_margin* — protected external-skin width; when set, tongue/groove
    profiles are clipped away from the outside so the visible wall stays solid.
    """
    petals: list[trimesh.Trimesh] = []
    for i in range(n):
        angle0 = phase + i * 2 * np.pi / n
        angle1 = phase + (i + 1) * 2 * np.pi / n

        normal0 = np.array([np.sin(angle0), -np.cos(angle0), 0.0])
        normal1 = np.array([-np.sin(angle1), np.cos(angle1), 0.0])

        petal = _plane_cut(mesh, [0.0, 0.0, 0.0], normal0)
        if petal is not None and not petal.is_empty and n > 2:
            petal = _plane_cut(petal, [0.0, 0.0, 0.0], normal1)
        if petal is None or petal.is_empty:
            continue
            
        if joint_depth > 0:
            if n == 2:
                axis = np.array([np.cos(phase), np.sin(phase), 0.0])
                tongue_side = 1 if i == 0 else -1
                petal = add_radial_tongue(petal, angle1, joint_depth, joint_margin,
                                          clearance=clearance,
                                          outer_margin=outer_margin,
                                          side=tongue_side, axis=axis)
                petal = add_radial_groove(petal, angle0, joint_depth, joint_margin,
                                          clearance=clearance,
                                          outer_margin=outer_margin,
                                          side=-tongue_side, axis=axis)
            else:
                petal = add_radial_tongue(petal, angle1, joint_depth, joint_margin,
                                          clearance=clearance,
                                          outer_margin=outer_margin)
                petal = add_radial_groove(petal, angle0, joint_depth, joint_margin,
                                          clearance=clearance,
                                          outer_margin=outer_margin)

        if petal is not None and not petal.is_empty:
            petals.append(petal)

    return petals
