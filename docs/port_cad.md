# `src.port_cad` — Parametric Port CAD & 3D STL Generator

The `port_cad` module provides in-scale 2D CAD cross-section rendering (SVG) and watertight 3D binary STL generation for loudspeaker acoustic ports (Hourglass continuous flare, double flared Aeroport, single flared and cylindrical vents).

## Physical & Mathematical Model

### Hourglass Continuous Flare
The Hourglass meridian $r(z)$ uses a $C^2$ continuous polynomial power blend transitioning from very low curvature at the center throat ($R_{\text{throat}} \approx 600\text{ mm}$, $z=0$) to high bellmouth flare curvature at the outer mouths ($R_{\text{mouth}} \approx 20\text{ mm}$, $z=\pm L/2$):

$$u = \frac{2|z|}{L} \in [0, 1]$$
$$r(u) = r_{\text{throat}} + (r_{\text{mouth}} - r_{\text{throat}}) \cdot \left[ 0.35\, u^2 + 0.65\, u^{3.5} \right]$$

This avoids edge detachment, eliminates sharp corners, and maximizes linear acoustic volume velocity before chuffing ($\approx 34\text{ m/s}$).

### 3D Watertight Solid of Revolution
The 2D closed polygon $(r, z)$ containing the inner airway, solid wall thickness $e_{\text{wall}}$, and optional mounting flange ($D_{\text{flange}}, e_{\text{flange}}$) is revolved about the $Z$ axis into an $N \times 3 \times 3$ triangle mesh.

When bolt holes are enabled, cylindrical tool cutouts on the bolt circle diameter (PCD) are subtracted from the flange.

## Functions

- `generate_port_profile_2d(d_throat_mm, d_mouth_mm, length_mm, flare_style, flare_radius_mm, wall_thickness_mm, n_pts=80)`: Computes $(z, r_{\text{inner}}, r_{\text{outer}})$ in mm.
- `generate_port_svg_cad(...)`: Generates a strictly proportional 1:1 in-scale 2D CAD SVG cross-section blueprint.
- `generate_parametric_port_stl(...)`: Exports binary STL bytes for 3D printing and CNC milling with support for full 1-piece, 2-piece symmetric halves ($L/2$), and flange-only adapter modes.
- `write_binary_stl(triangles_nx3x3, header_str)`: High-speed pure-NumPy binary STL serializer.
