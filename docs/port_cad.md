# `src.port_cad` — Parametric Port CAD & 3D STL Generator

The `port_cad` module provides in-scale 2D CAD cross-section rendering (SVG) and watertight 3D binary STL generation for loudspeaker acoustic ports (Hourglass continuous flare, double flared Aeroport, single flared and cylindrical vents).

### Aeroport circular terminations

The double-flared Aeroport profile uses mirrored quarter-circle terminations.
Each rounding is tangent to the cylindrical throat at its inner junction and
expands monotonically toward the corresponding mouth.  With normalized axial
coordinate $t\in[0,1]$ from throat junction to mouth, the radial profile is:

$$r(t)=r_{\text{throat}}+(r_{\text{mouth}}-r_{\text{throat}})
\left(1-\sqrt{1-t^2}\right)$$

The left termination uses the same equation with a signed coordinate
$t\in[-1,0]$, so its square produces the exact mirror image.  The single-flare
variant applies the same outward-oriented rounding only at the right mouth.
The flare value is radial and applies on both sides of the circular section,
so $D_{\text{mouth}}=D_{\text{throat}}+2R$ (for example, 130 mm + 2 × 25 mm
= 180 mm).  The SVG title displays this equation explicitly.

## Physical & Mathematical Model

### Hourglass Dynamic Analytical Curvature
The Hourglass meridian $r(z)$ uses a $C^2$ continuous polynomial spline whose boundary curvatures are derived analytically from the physical dimensions:

- **Throat Osculating Curvature Radius**:
  $$R_{\text{throat}} = \frac{(L/2)^2 + (r_{\text{mouth}} - r_{\text{throat}})^2}{2\,(r_{\text{mouth}} - r_{\text{throat}})}$$
- **Mouth Curvature Radius**:
  $$R_{\text{mouth}} = r_{\text{flare}}$$

The $C^2$ quintic polynomial:
$$t = \frac{|z|}{L/2} \in [0, 1]$$
$$r(t) = r_{\text{throat}} + a_2 t^2 + a_3 t^3 + a_4 t^4 + a_5 t^5$$

satisfies $r'(0)=0$, $r''(0)=1/R_{\text{throat}}$, $r(1)=r_{\text{mouth}}$, and $r''(1)=1/R_{\text{mouth}}$, guaranteeing a continuous smooth transition without sharp transitions or airflow boundary detachment.

## Functions

- `calculate_dynamic_hourglass_radii(d_throat_mm, d_mouth_mm, length_mm, flare_radius_mm)`: Computes $(R_{\text{throat}}, R_{\text{mouth}})$ in mm.
- `generate_port_profile_2d(d_throat_mm, d_mouth_mm, length_mm, flare_style, flare_radius_mm, wall_thickness_mm, n_pts=80)`: Computes $(z, r_{\text{inner}}, r_{\text{outer}})$ in mm. Aeroport profiles are monotonic from throat to mouth and share the same geometry in SVG and STL output.
- `generate_port_svg_cad(...)`: Generates a strictly proportional 1:1 in-scale 2D CAD SVG cross-section blueprint.
- `generate_parametric_port_stl(...)`: Exports binary STL bytes for 3D printing and CNC milling with support for full 1-piece, 2-piece symmetric halves ($L/2$), and flange-only adapter modes.
- `write_binary_stl(triangles_nx3x3, header_str)`: High-speed pure-NumPy binary STL serializer.

STL flange holes are real through-holes, not drawing annotations.  Before the
Manifold boolean subtraction, the revolved tube is normalized to an
edge-sharing watertight mesh and an outward-oriented positive volume.  A requested hole pattern now either returns
a drilled watertight mesh or raises a clear generation error; it never silently
returns an undrilled flange.  Runtime installations therefore include both
`trimesh` and the `manifold3d` boolean backend.

Manufacturing length annotations use one common rounded millimeter total and
derive the center-split half length from that displayed total.  Thus an odd
total such as 139 mm is shown as exactly `2 × 69.5 mm`; total and half labels
cannot disagree because of independent decimal rounding.
