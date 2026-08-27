"""Parametric 3D CAD and STL Generator for Acoustic Ports.

Provides in-scale CAD cross-section rendering (SVG) and watertight 3D binary STL
mesh generation for 3D printing and CNC manufacturing.

Supports:
- Hourglass continuous progressive flare with dynamic analytical curvature
  (R_throat = (L/2)^2 / (2*dr) dynamically computed -> R_mouth = flare_radius)
- Double flared (Aeroport) and single flared terminations
- Cylindrical straight ducts
- Configurable wall thickness, mounting flange, and screw hole patterns
- Split modes: 1-piece full, 2-piece symmetric halves (L/2), and flange-only coupling
"""

from __future__ import annotations

import io
import struct
from typing import Any

import numpy as np

try:
    import trimesh
    _HAS_TRIMESH = True
except ImportError:
    _HAS_TRIMESH = False


def write_binary_stl(triangles_nx3x3: np.ndarray, header_str: str = "Load Forge Parametric Port STL") -> bytes:
    """Serialize an (N, 3, 3) triangle array into binary STL format using pure NumPy."""
    v = np.asarray(triangles_nx3x3, dtype=np.float32)
    n_triangles = len(v)
    if n_triangles == 0:
        return b""

    e1 = v[:, 1, :] - v[:, 0, :]
    e2 = v[:, 2, :] - v[:, 0, :]
    normals = np.cross(e1, e2)
    norm_len = np.linalg.norm(normals, axis=1, keepdims=True)
    norm_len[norm_len < 1e-9] = 1.0
    normals = normals / norm_len

    hdr = header_str.encode("ascii")[:80].ljust(80, b"\x00")

    dt = np.dtype([
        ("normal", ("<f4", 3)),
        ("v0", ("<f4", 3)),
        ("v1", ("<f4", 3)),
        ("v2", ("<f4", 3)),
        ("attr", "<u2"),
    ])

    records = np.empty(n_triangles, dtype=dt)
    records["normal"] = normals
    records["v0"] = v[:, 0, :]
    records["v1"] = v[:, 1, :]
    records["v2"] = v[:, 2, :]
    records["attr"] = 0

    out = io.BytesIO()
    out.write(hdr)
    out.write(struct.pack("<I", n_triangles))
    out.write(records.tobytes())
    return out.getvalue()


def calculate_dynamic_hourglass_radii(
    d_throat_mm: float,
    d_mouth_mm: float,
    length_mm: float,
    flare_radius_mm: float = 25.0,
) -> tuple[float, float]:
    """Analytically compute dynamic osculating curvature radii at throat and mouth.

    R_throat is the osculating circle radius: (L/2)^2 / (2 * dr)
    R_mouth is the nominal flare radius at the outer bellmouth lip.
    """
    r_t = max(1.0, float(d_throat_mm) / 2.0)
    r_m = max(r_t, float(d_mouth_mm) / 2.0)
    L_h = max(1.0, float(length_mm) / 2.0)
    dr = max(0.1, r_m - r_t)

    r_throat_calc = float((L_h**2 + dr**2) / (2.0 * dr))
    r_mouth_calc = float(max(5.0, flare_radius_mm))
    return r_throat_calc, r_mouth_calc


def generate_port_profile_2d(
    d_throat_mm: float,
    d_mouth_mm: float,
    length_mm: float,
    flare_style: str = "hourglass",
    flare_radius_mm: float = 25.0,
    wall_thickness_mm: float = 4.0,
    n_pts: int = 80,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calculate 2D meridian arrays (z, r_inner, r_outer) in millimeters.

    For Hourglass, uses a dynamic analytical C2 quintic polynomial blend
    transitioning from R_throat = (L/2)^2 / (2*dr) to R_mouth = flare_radius_mm.
    """
    r_t = max(1.0, float(d_throat_mm) / 2.0)
    r_m = max(r_t, float(d_mouth_mm) / 2.0)
    L = max(1.0, float(length_mm))
    L_h = L / 2.0
    f_rad = max(0.0, float(flare_radius_mm))
    dr = max(0.1, r_m - r_t)

    z_full = np.linspace(-L_h, L_h, n_pts)

    if flare_style == "hourglass":
        # Solve C2 quintic spline
        r_throat_calc, r_mouth_calc = calculate_dynamic_hourglass_radii(
            d_throat_mm, d_mouth_mm, length_mm, flare_radius_mm
        )
        theta_mouth = min(np.pi / 4.0, dr / r_mouth_calc)
        m_mouth = np.tan(theta_mouth)

        a2 = dr
        rhs2 = L_h * m_mouth
        rhs3 = (L_h**2) / r_mouth_calc - 2.0 * a2

        a3 = -4.0 * rhs2 + 0.5 * rhs3
        a4 = 7.0 * rhs2 - 1.0 * rhs3
        a5 = -3.0 * rhs2 + 0.5 * rhs3

        t = np.abs(z_full) / L_h
        r_inner = r_t + a2 * (t**2) + a3 * (t**3) + a4 * (t**4) + a5 * (t**5)
        r_inner = np.maximum(r_t, r_inner)
        r_inner[0] = r_m
        r_inner[-1] = r_m
        r_inner[len(z_full) // 2] = r_t
    elif flare_style == "both":
        r_inner = np.full_like(z_full, r_t)
        f_len = min(f_rad, L_h)
        if f_len > 0:
            for i, zv in enumerate(z_full):
                if zv < -L_h + f_len:
                    zl = (zv - (-L_h + f_len)) / f_len
                    r_inner[i] = r_t + (r_m - r_t) * (1.0 - np.sqrt(max(0.0, 1.0 - (zl + 1.0) ** 2)))
                elif zv > L_h - f_len:
                    zr = (zv - (L_h - f_len)) / f_len
                    r_inner[i] = r_t + (r_m - r_t) * (1.0 - np.sqrt(max(0.0, 1.0 - (1.0 - zr) ** 2)))
    elif flare_style in {"one", "one_end"}:
        r_inner = np.full_like(z_full, r_t)
        f_len = min(f_rad, L)
        if f_len > 0:
            for i, zv in enumerate(z_full):
                if zv > L_h - f_len:
                    zr = (zv - (L_h - f_len)) / f_len
                    r_inner[i] = r_t + (r_m - r_t) * (1.0 - np.sqrt(max(0.0, 1.0 - (1.0 - zr) ** 2)))
    else:  # none
        r_inner = np.full_like(z_full, r_t)

    r_outer = r_inner + max(0.5, float(wall_thickness_mm))
    return z_full, r_inner, r_outer


def generate_port_svg_cad(
    d_throat_mm: float,
    d_mouth_mm: float,
    length_mm: float,
    flare_style: str = "hourglass",
    flare_radius_mm: float = 25.0,
    wall_thickness_mm: float = 4.0,
    has_flange: bool = True,
    flange_diameter_mm: float | None = None,
    flange_thickness_mm: float = 6.0,
    bolt_count: int = 4,
    bolt_diameter_mm: float = 4.0,
    bolt_pcd_mm: float | None = None,
    svg_width: int = 680,
    svg_height: int = 240,
) -> str:
    """Generate a strictly proportional, in-scale 2D CAD cross-section blueprint in SVG format."""
    r_t = max(1.0, float(d_throat_mm) / 2.0)
    r_m = max(r_t, float(d_mouth_mm) / 2.0)
    L = max(1.0, float(length_mm))
    
    if flange_diameter_mm is None or flange_diameter_mm <= d_mouth_mm:
        flange_diameter_mm = d_mouth_mm + 26.0
    r_flange = flange_diameter_mm / 2.0
    
    if bolt_pcd_mm is None or bolt_pcd_mm <= 0:
        bolt_pcd_mm = (d_mouth_mm + flange_diameter_mm) / 2.0
    r_pcd = bolt_pcd_mm / 2.0

    z_full, r_inner, r_outer = generate_port_profile_2d(
        d_throat_mm=d_throat_mm,
        d_mouth_mm=d_mouth_mm,
        length_mm=length_mm,
        flare_style=flare_style,
        flare_radius_mm=flare_radius_mm,
        wall_thickness_mm=wall_thickness_mm,
        n_pts=60,
    )

    r_th_calc, r_mo_calc = calculate_dynamic_hourglass_radii(
        d_throat_mm, d_mouth_mm, length_mm, flare_radius_mm
    )

    max_r = r_flange if has_flange else float(r_outer.max())
    margin_x = 95.0
    margin_y = 48.0
    
    avail_w = svg_width - 2 * margin_x
    avail_h = svg_height - 2 * margin_y
    
    scale = min(avail_w / max(1.0, L), avail_h / max(1.0, 2.0 * max_r))
    
    cx = svg_width / 2.0
    cy = svg_height / 2.0
    
    def map_pt(z_mm: float, r_mm: float) -> tuple[float, float]:
        px = cx + z_mm * scale
        py = cy - r_mm * scale
        return px, py

    top_pts: list[tuple[float, float]] = []
    for z_v, r_v in zip(z_full, r_inner):
        top_pts.append(map_pt(float(z_v), float(r_v)))
        
    z_end = float(z_full[-1])
    if has_flange:
        top_pts.append(map_pt(z_end, r_flange))
        top_pts.append(map_pt(z_end - flange_thickness_mm, r_flange))
        top_pts.append(map_pt(z_end - flange_thickness_mm, float(r_outer[-1])))
    else:
        top_pts.append(map_pt(z_end, float(r_outer[-1])))
        
    for z_v, r_v in zip(reversed(z_full[:-1]), reversed(r_outer[:-1])):
        top_pts.append(map_pt(float(z_v), float(r_v)))
        
    top_path_d = f"M {top_pts[0][0]:.1f},{top_pts[0][1]:.1f} " + " ".join(f"L {p[0]:.1f},{p[1]:.1f}" for p in top_pts[1:]) + " Z"

    bot_pts: list[tuple[float, float]] = []
    for z_v, r_v in zip(z_full, -r_inner):
        bot_pts.append(map_pt(float(z_v), float(r_v)))
    if has_flange:
        bot_pts.append(map_pt(z_end, -r_flange))
        bot_pts.append(map_pt(z_end - flange_thickness_mm, -r_flange))
        bot_pts.append(map_pt(z_end - flange_thickness_mm, float(-r_outer[-1])))
    else:
        bot_pts.append(map_pt(z_end, float(-r_outer[-1])))
    for z_v, r_v in zip(reversed(z_full[:-1]), reversed(-r_outer[:-1])):
        bot_pts.append(map_pt(float(z_v), float(r_v)))
    bot_path_d = f"M {bot_pts[0][0]:.1f},{bot_pts[0][1]:.1f} " + " ".join(f"L {p[0]:.1f},{p[1]:.1f}" for p in bot_pts[1:]) + " Z"

    core_pts: list[tuple[float, float]] = []
    for z_v, r_v in zip(z_full, r_inner):
        core_pts.append(map_pt(float(z_v), float(r_v)))
    for z_v, r_v in zip(reversed(z_full), reversed(-r_inner)):
        core_pts.append(map_pt(float(z_v), float(r_v)))
    core_path_d = f"M {core_pts[0][0]:.1f},{core_pts[0][1]:.1f} " + " ".join(f"L {p[0]:.1f},{p[1]:.1f}" for p in core_pts[1:]) + " Z"

    x_left, _ = map_pt(-L/2, 0)
    x_right, _ = map_pt(L/2, 0)
    x_center, _ = map_pt(0, 0)
    
    holes_svg = ""
    if has_flange and bolt_count > 0:
        hx_c = z_end - flange_thickness_mm / 2.0
        px_h, py_ht = map_pt(hx_c, r_pcd)
        _, py_hb = map_pt(hx_c, -r_pcd)
        hr_px = (bolt_diameter_mm / 2.0) * scale
        h_w = flange_thickness_mm * scale
        holes_svg = f"""
        <!-- Bolt Hole Top Cutout -->
        <rect x="{px_h - h_w/2:.1f}" y="{py_ht - hr_px:.1f}" width="{h_w:.1f}" height="{hr_px*2:.1f}" rx="1" fill="#0f172a" stroke="#f59e0b" stroke-width="1"/>
        <!-- Bolt Hole Bottom Cutout -->
        <rect x="{px_h - h_w/2:.1f}" y="{py_hb - hr_px:.1f}" width="{h_w:.1f}" height="{hr_px*2:.1f}" rx="1" fill="#0f172a" stroke="#f59e0b" stroke-width="1"/>
        <!-- PCD Centerline -->
        <line x1="{px_h:.1f}" y1="{py_ht - hr_px - 4:.1f}" x2="{px_h:.1f}" y2="{py_ht + hr_px + 4:.1f}" stroke="#f59e0b" stroke-width="1" stroke-dasharray="2,2"/>
        <line x1="{px_h:.1f}" y1="{py_hb - hr_px - 4:.1f}" x2="{px_h:.1f}" y2="{py_hb + hr_px + 4:.1f}" stroke="#f59e0b" stroke-width="1" stroke-dasharray="2,2"/>
        """

    curve_label = f"R_throat: {r_th_calc:.0f} mm → R_mouth: {r_mo_calc:.0f} mm" if flare_style == "hourglass" else f"Flare R: {flare_radius_mm:.1f} mm"

    svg = f"""<svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="cadAirGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#10b981" stop-opacity="0.45"/>
      <stop offset="50%" stop-color="#059669" stop-opacity="0.1"/>
      <stop offset="100%" stop-color="#10b981" stop-opacity="0.45"/>
    </linearGradient>
  </defs>

  <!-- Air Core -->
  <path d="{core_path_d}" fill="url(#cadAirGrad)" stroke="#10b981" stroke-width="0.8" stroke-dasharray="3,3" />

  <!-- Solid Top & Bottom Walls -->
  <path d="{top_path_d}" fill="#10b981" fill-opacity="0.9" stroke="#34d399" stroke-width="1.2" />
  <path d="{bot_path_d}" fill="#10b981" fill-opacity="0.9" stroke="#34d399" stroke-width="1.2" />

  {holes_svg}

  <!-- Centerline (Axis of Revolution) -->
  <line x1="{x_left - 25:.1f}" y1="{cy:.1f}" x2="{x_right + 25:.1f}" y2="{cy:.1f}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="6,3,1,3" />

  <!-- Symmetry Division Line -->
  <line x1="{x_center:.1f}" y1="{cy - max_r*scale - 12:.1f}" x2="{x_center:.1f}" y2="{cy + max_r*scale + 12:.1f}" stroke="#f59e0b" stroke-width="1.2" stroke-dasharray="3,2" />

  <!-- Overall Length Dimension (Bottom) -->
  <line x1="{x_left:.1f}" y1="{svg_height - 18:.1f}" x2="{x_right:.1f}" y2="{svg_height - 18:.1f}" stroke="#7cc7ff" stroke-width="1.2" stroke-dasharray="4,2" />
  <line x1="{x_left:.1f}" y1="{svg_height - 24:.1f}" x2="{x_left:.1f}" y2="{svg_height - 12:.1f}" stroke="#7cc7ff" stroke-width="1.2" />
  <line x1="{x_right:.1f}" y1="{svg_height - 24:.1f}" x2="{x_right:.1f}" y2="{svg_height - 12:.1f}" stroke="#7cc7ff" stroke-width="1.2" />
  <text x="{x_center:.1f}" y="{svg_height - 6:.1f}" fill="#7cc7ff" font-size="10.5" text-anchor="middle" font-family="monospace">
    L_tot: {length_mm/10.0:.1f} cm ({length_mm:.0f} mm) · 2x Halves L/2: {length_mm/20.0:.1f} cm
  </text>

  <!-- Center Throat Annotation -->
  <text x="{x_center:.1f}" y="{cy - 4:.1f}" fill="#ffffff" font-size="10" font-weight="bold" text-anchor="middle" font-family="sans-serif">
    Throat Ø {d_throat_mm:.1f} mm
  </text>
  <text x="{x_center:.1f}" y="{cy + 12:.1f}" fill="#a7f3d0" font-size="9" text-anchor="middle" font-family="sans-serif">
    {curve_label}
  </text>

  <!-- Flange & Mouth Dimensions (Right) -->
  <text x="{x_right + 12:.1f}" y="{cy - r_flange*scale:.1f}" fill="#f59e0b" font-size="10" font-weight="bold" text-anchor="start" font-family="sans-serif">
    Flange Ø {flange_diameter_mm:.1f} mm
  </text>
  <text x="{x_right + 12:.1f}" y="{cy - r_m*scale:.1f}" fill="#38bdf8" font-size="9.5" text-anchor="start" font-family="sans-serif">
    Mouth Ø {d_mouth_mm:.1f} mm
  </text>
  {f'<text x="{x_right + 12:.1f}" y="{cy + 14:.1f}" fill="#fbbf24" font-size="9" text-anchor="start" font-family="sans-serif">{bolt_count}x Ø{bolt_diameter_mm:.1f} on PCD Ø{bolt_pcd_mm:.1f}</text>' if has_flange and bolt_count > 0 else ''}

  <!-- Inner Mouth (Left) -->
  <text x="{x_left - 12:.1f}" y="{cy - r_m*scale:.1f}" fill="#38bdf8" font-size="9.5" text-anchor="end" font-family="sans-serif">
    Inner Mouth Ø {d_mouth_mm:.1f} mm
  </text>
  <text x="{x_left - 12:.1f}" y="{cy + 14:.1f}" fill="#94a3b8" font-size="9" text-anchor="end" font-family="sans-serif">
    Wall e: {wall_thickness_mm:.1f} mm
  </text>
</svg>"""
    return svg


def generate_parametric_port_stl(
    d_throat_mm: float,
    d_mouth_mm: float,
    length_mm: float,
    flare_style: str = "hourglass",
    flare_radius_mm: float = 25.0,
    wall_thickness_mm: float = 4.0,
    has_flange: bool = True,
    flange_diameter_mm: float | None = None,
    flange_thickness_mm: float = 6.0,
    bolt_count: int = 4,
    bolt_diameter_mm: float = 4.0,
    bolt_pcd_mm: float | None = None,
    split_mode: str = "full",  # 'full', 'half', 'flange_only'
    rings: int = 72,
    n_pts: int = 100,
) -> bytes:
    """Generate a watertight 3D binary STL file for 3D printing or CNC machining."""
    r_t = max(1.0, float(d_throat_mm) / 2.0)
    r_m = max(r_t, float(d_mouth_mm) / 2.0)
    L = max(1.0, float(length_mm))
    
    if flange_diameter_mm is None or flange_diameter_mm <= d_mouth_mm:
        flange_diameter_mm = d_mouth_mm + 26.0
    r_flange = flange_diameter_mm / 2.0
    
    if bolt_pcd_mm is None or bolt_pcd_mm <= 0:
        bolt_pcd_mm = (d_mouth_mm + flange_diameter_mm) / 2.0

    z_full, r_inner_full, r_outer_full = generate_port_profile_2d(
        d_throat_mm=d_throat_mm,
        d_mouth_mm=d_mouth_mm,
        length_mm=length_mm,
        flare_style=flare_style,
        flare_radius_mm=flare_radius_mm,
        wall_thickness_mm=wall_thickness_mm,
        n_pts=n_pts,
    )

    if split_mode == "half":
        mask = z_full >= -1e-6
        z = z_full[mask]
        r_inner = r_inner_full[mask]
        r_outer = r_outer_full[mask]
    elif split_mode == "flange_only":
        f_len = min(flare_radius_mm * 1.5, L / 2.0)
        mask = z_full >= (L / 2.0 - f_len)
        z = z_full[mask]
        r_inner = r_inner_full[mask]
        r_outer = r_outer_full[mask]
    else:
        z = z_full
        r_inner = r_inner_full
        r_outer = r_outer_full

    poly_r: list[float] = []
    poly_z: list[float] = []
    
    for zi, ri in zip(z, r_inner):
        poly_r.append(float(ri))
        poly_z.append(float(zi))
        
    z_end = float(z[-1])
    if has_flange:
        flange_back_z = z_end - float(flange_thickness_mm)
        poly_r.append(r_flange)
        poly_z.append(z_end)
        poly_r.append(r_flange)
        poly_z.append(flange_back_z)
        poly_r.append(float(r_outer[-1]))
        poly_z.append(flange_back_z)
    else:
        poly_r.append(float(r_outer[-1]))
        poly_z.append(z_end)
        
    for zi, ro in zip(reversed(z[:-1]), reversed(r_outer[:-1])):
        poly_r.append(float(ro))
        poly_z.append(float(zi))
        
    poly_r.append(float(r_inner[0]))
    poly_z.append(float(z[0]))
    
    r_arr = np.array(poly_r, dtype=np.float32)
    z_arr = np.array(poly_z, dtype=np.float32)
    
    theta = np.linspace(0.0, 2.0 * np.pi, rings, endpoint=False).astype(np.float32)
    ct = np.cos(theta)
    st = np.sin(theta)
    
    n_pts_poly = len(r_arr)
    n_triangles = 2 * rings * (n_pts_poly - 1)
    
    triangles = np.zeros((n_triangles, 3, 3), dtype=np.float32)
    tri = 0
    for i in range(n_pts_poly - 1):
        r0, r1 = r_arr[i], r_arr[i + 1]
        z0, z1 = z_arr[i], z_arr[i + 1]
        for j in range(rings):
            jj = (j + 1) % rings
            p0 = [r0 * ct[j],  r0 * st[j],  z0]
            p1 = [r1 * ct[j],  r1 * st[j],  z1]
            p2 = [r1 * ct[jj], r1 * st[jj], z1]
            p3 = [r0 * ct[jj], r0 * st[jj], z0]
            
            triangles[tri] = [p0, p3, p1]; tri += 1
            triangles[tri] = [p1, p3, p2]; tri += 1
            
    if _HAS_TRIMESH and has_flange and bolt_count > 0 and bolt_diameter_mm > 0:
        try:
            tm_base = trimesh.Trimesh(
                vertices=triangles.reshape(-1, 3),
                faces=np.arange(n_triangles * 3).reshape(-1, 3),
                process=False,
            )
            hole_r = bolt_diameter_mm / 2.0
            hole_cylinders = []
            angles = np.linspace(0.0, 2.0 * np.pi, bolt_count, endpoint=False)
            pcd_r = bolt_pcd_mm / 2.0
            flange_h = flange_thickness_mm + 4.0
            z_center = z_end - flange_thickness_mm / 2.0
            
            for ang in angles:
                hx = pcd_r * np.cos(ang)
                hy = pcd_r * np.sin(ang)
                cyl = trimesh.creation.cylinder(
                    radius=hole_r,
                    height=flange_h,
                    sections=20,
                    transform=trimesh.transformations.translation_matrix([hx, hy, z_center]),
                )
                hole_cylinders.append(cyl)
                
            cutout = tm_base.difference(hole_cylinders, engine="manifold")
            if cutout is not None and not cutout.is_empty and len(cutout.faces) > 0:
                triangles = cutout.triangles.astype(np.float32)
        except Exception:
            pass
            
    return write_binary_stl(triangles)
