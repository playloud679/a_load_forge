"""
STL slicer — cut a horn mesh lengthwise or into radial petals.

Uses trimesh for plane slicing with capping.
"""

import numpy as np
import trimesh
import shapely as shp


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
    result = mesh.slice_plane(plane_origin, plane_normal, cap=True)
    if result is None or result.is_empty:
        return None
    return result


def _with_joints(segments, cuts, wall, angles=None):
    """Add joint lips — each segment (except top) gets a lip on its TOP face."""
    if wall <= 0 or len(segments) <= 1:
        return segments
    if angles is None:
        angles = {}
    out = []
    for i, seg in enumerate(segments):
        if i < len(segments) - 1:
            z_cut = cuts[i + 1]
            ang = angles.get(z_cut, 0.0)
            seg = add_axial_lip(seg, z_cut, wall, direction="up", angle_deg=ang)
        out.append(seg)
    return out


def slice_into_segments(mesh: trimesh.Trimesh, n: int,
                        joint_wall: float = 0.0
                        ) -> list[trimesh.Trimesh]:
    """
    Cut *mesh* into *n* axial segments of equal Z-height.

    When *joint_wall* > 0, a joint lip is added to each intermediate cut.
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
        seg = mesh.slice_plane([0.0, 0.0, lo], [0.0, 0.0, 1.0], cap=True)
        if seg is not None and not seg.is_empty:
            seg = seg.slice_plane([0.0, 0.0, hi], [0.0, 0.0, -1.0], cap=True)
            if seg is not None and not seg.is_empty:
                segments.append(seg)
        lo = hi
    angles = _precompute_angles(mesh, cuts) if joint_wall > 0 else None
    return _with_joints(segments, cuts, joint_wall, angles)


def slice_at_heights(mesh: trimesh.Trimesh, heights: list[float],
                     joint_wall: float = 0.0
                     ) -> list[trimesh.Trimesh]:
    """
    Cut *mesh* at the given Z *heights*. Returns capped slabs.

    When *joint_wall* > 0, a joint lip is added at each cut.
    """
    z_min = mesh.bounds[0, 2]
    z_max = mesh.bounds[1, 2]
    cuts = sorted([z_min] + [h for h in heights if z_min < h < z_max] + [z_max])

    segments: list[trimesh.Trimesh] = []
    for i in range(len(cuts) - 1):
        lo, hi = cuts[i], cuts[i + 1]
        seg = mesh.slice_plane([0.0, 0.0, lo], [0.0, 0.0, 1.0], cap=True)
        if seg is not None and not seg.is_empty:
            seg = seg.slice_plane([0.0, 0.0, hi], [0.0, 0.0, -1.0], cap=True)
            if seg is not None and not seg.is_empty:
                segments.append(seg)
    angles = _precompute_angles(mesh, cuts) if joint_wall > 0 else None
    return _with_joints(segments, cuts, joint_wall, angles)


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


def _seam_face_polygon(petal, origin, normal):
    """Get the outermost closed polygon of a mesh cross-section at a plane."""
    section = petal.section(plane_origin=origin, plane_normal=normal)
    if section is None:
        return None, None
    try:
        planar, to_3D = section.to_2D(normal=normal)
    except Exception:
        return None, None
    poly_list = [p for p in planar.polygons_closed if p is not None]
    if not poly_list:
        return None, None
    poly = max(poly_list, key=lambda p: p.area)
    return poly, to_3D


def _buffer_single(poly, distance):
    """Buffer a shapely polygon, returning a single Polygon (largest part if MultiPolygon)."""
    result = poly.buffer(distance, join_style=shp.BufferJoinStyle.mitre)
    if result is None or result.is_empty:
        return None
    if result.geom_type == "MultiPolygon":
        # Take the largest part (narrow walls can fragment under negative buffer)
        result = max(result.geoms, key=lambda p: p.area)
    return result


def add_radial_tongue(petal: trimesh.Trimesh, angle: float,
                      joint_depth: float = 2.0,
                      margin: float = 1.0) -> trimesh.Trimesh:
    """
    Add a tongue on the RIGHT seam (at *angle*) of a radial petal.

    The tongue is a vertical strip centred on the wall cross-section,
    extruded outward along the seam normal by *joint_depth*.
    """
    normal = np.array([-np.sin(angle), np.cos(angle), 0.0])
    poly, to_3D = _seam_face_polygon(petal, [0.0, 0.0, 0.0], normal)
    if poly is None:
        return petal

    inner = _buffer_single(poly, -margin)
    if inner is None:
        return petal

    tongue = trimesh.creation.extrude_polygon(inner, height=joint_depth)
    to_3D_out = to_3D.copy()
    to_3D_out[:3, 2] = -to_3D_out[:3, 2]
    tongue.apply_transform(to_3D_out)

    try:
        result = trimesh.boolean.union([petal, tongue], engine="manifold",
                                       check_volume=False)
    except Exception:
        result = trimesh.util.concatenate([petal, tongue])
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
                      margin: float = 1.0) -> trimesh.Trimesh:
    """
    Cut a groove on the LEFT seam (at *angle*) of a radial petal.

    The groove is a vertical slot centred on the wall cross-section,
    going INTO the petal by *joint_depth*.
    """
    normal = np.array([np.sin(angle), -np.cos(angle), 0.0])
    poly, to_3D = _seam_face_polygon(petal, [0.0, 0.0, 0.0], normal)
    if poly is None:
        return petal

    inner = _buffer_single(poly, -margin)
    if inner is None:
        return petal

    overlap = 1.0
    groove = trimesh.creation.extrude_polygon(inner, height=joint_depth + overlap)
    to_3D_off = to_3D.copy()
    to_3D_off[:3, 3] += normal * (-overlap)
    groove.apply_transform(to_3D_off)

    try:
        result = trimesh.boolean.difference([petal, groove], engine="manifold",
                                            check_volume=False)
    except Exception:
        return petal
    if result is not None and not result.is_empty and result.body_count == 1:
        return result
    return petal


def _apply_step_joint(petal, angle, joint_depth, normal_into):
    """Cut a full-face step at the left seam — removes entire face inward."""
    normal = normal_into
    origin_off = np.array([0.0, 0.0, 0.0]) + normal * joint_depth
    result = petal.slice_plane(plane_origin=origin_off, plane_normal=normal, cap=True)
    if result is not None and not result.is_empty and result.body_count == 1:
        return result
    return petal


def slice_into_petals(mesh: trimesh.Trimesh, n: int,
                      phase: float = 0.0,
                      joint_depth: float = 0.0,
                      joint_margin: float = 0.5
                      ) -> list[trimesh.Trimesh]:
    """
    Cut *mesh* into *n* radial petals (like an orange).

    Seams sit at angles *phase* + i·2π/n (rotate *phase* to keep them clear of
    flange bolt holes).  When *joint_depth* > 0, each petal gets a tongue on its
    right seam face and a groove on its left seam face (tongue & groove joint).
    """
    petals: list[trimesh.Trimesh] = []
    for i in range(n):
        angle0 = phase + i * 2 * np.pi / n
        angle1 = phase + (i + 1) * 2 * np.pi / n

        normal0 = np.array([np.sin(angle0), -np.cos(angle0), 0.0])
        normal1 = np.array([-np.sin(angle1), np.cos(angle1), 0.0])

        petal = mesh.slice_plane([0.0, 0.0, 0.0], normal0, cap=True)
        if petal is None or petal.is_empty:
            continue
        petal = petal.slice_plane([0.0, 0.0, 0.0], normal1, cap=True)
        if petal is None or petal.is_empty:
            continue

        if joint_depth > 0:
            if n == 2:
                # Full-face step: very visible recess (female) on left, tongue (male) on right
                petal = _apply_step_joint(petal, angle0, joint_depth, normal0)
                petal = add_radial_tongue(petal, angle1, joint_depth, joint_margin)
            else:
                petal = add_radial_groove(petal, angle0, joint_depth, joint_margin)
                petal = add_radial_tongue(petal, angle1, joint_depth, joint_margin)

        petals.append(petal)

    return petals
