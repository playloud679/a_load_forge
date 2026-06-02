# flare_forge

A parametric STL generator for acoustic horn waveguides. You type in the physics — throat diameter, cutoff frequency, wall thickness — and it hands you a watertight solid ready for the printer.

I built this because every tool I found either required a full CAD package, or produced meshes that weren't actually watertight, or got the math wrong in ways that were hard to notice until you printed the thing. A parametric generator that takes physical parameters and does the geometry for you is surprisingly rare.

## Running it

    make install
    make run            # launches the UI and opens it in Safari

`make run` starts Streamlit headless and opens `localhost:8501` in Safari. Or run it yourself with `streamlit run ui_app.py` (default browser). There is also a CLI:

     python -m src.main --throat 20 --mouth 100
    python -m src.main --profile salmon --throat 20 --fc 600 --length 80

## The expansion profiles

There are three. The right expansion curve depends on what you're optimizing for, and none of them is obviously better.

**Tractrix** has a nice variational property: the tangent is horizontal at the mouth, which minimizes reflections. It comes out short though, which means poor low-frequency driver loading. Still, it's the one with the cleanest derivation.

**Salmon** (hyperbolic-exponential, parametrizzato da `T`). Con `T=0.707` (Hypex) è il profilo più usato nei compression driver. Dai una lunghezza e una frequenza di taglio, e calcola l'espansione. Prevedibile e robusto.

**Exponential** is the textbook formula. Area doubles every fixed axial distance. Fast, simple, valid for many applications.

Each returns `(z, r)` and nothing else — just the math. The cross-section is a separate choice.

## Cross-sections

The profile says how the area grows along the axis. The section says what shape that area takes. Any of the four profiles composes with any of the three sections.

**Circular** is the revolution you'd expect: spin the profile around Z.

**Polygonal** makes every Z slice a regular N-gon (3 to 12 sides), area-matched to the equivalent circle, so the acoustics are unchanged but the horn prints flat-faced. The circumradius is `r_eq · √(2π / (N·sin(2π/N)))`.

**Radial 360°** is a disk waveguide for omnidirectional applications. Two pieces — bottom plate and top reflector — with an acoustic gap between them.

## How the mesh is built

The 2D profile functions return `(z, r)` arrays — pure math, no geometry yet. For a circular section these feed a profile-agnostic 3D engine that computes outward normals via finite differences, offsets the inner profile along those normals by the wall thickness to get the outer surface, revolves both around Z, and caps the throat and mouth.

The offset is a true parallel offset along the meridian normal. For a body of revolution the 3D surface normal lies entirely in the meridian plane, so a 2D normal offset *is* a 3D offset — the wall comes out at a **constant** perpendicular thickness everywhere (no Euclidean/normal-space approximation, no thinning toward the mouth). The trade-off is that the outer throat rim then sits at a different Z than the inner rim, leaving a slanted base; the engine slices that base flat with a plane and re-caps it, so the throat face is planar while the wall stays uniform.

The 2D preview's "+ wall" line draws this same parallel offset, so what you see is what gets printed.

The polygonal section reuses the same `(z, r)` and the same normal-offset idea, but lofts N-gon rings instead of revolving — the per-vertex offset is scaled by `1/cos(π/N)` so the wall thickness stays uniform along the face normal, not the vertex direction. Radial has its own two-piece revolution engine.

## Flanges

Mounting flanges (throat, mouth, and an optional mid-flange at any axial position) are built with CSG boolean operations via trimesh and manifold3d. Bolt holes are real cutouts, not overlapping geometry. The outer body can be circular or a polygon, independently of the horn's section.

One subtlety worth stating, because it's easy to get wrong: on a polygonal outer, "ring width" is the wall thickness at the **flat faces**, not the distance to the corners. The hole is a circle of radius `inner_R`; the polygon's narrowest wall is at its inradius, `flange_R · cos(π/N)`. If you size the polygon by its circumradius (`inner_R + ring`), the flat-face wall shrinks as you add sides and eventually goes negative — the round hole punches straight through the edges and you're left with detached corner triangles. So the circumradius is solved backwards from the wall you actually want: `flange_R = (inner_R + ring) / cos(π/N)`. The wall is then a uniform `ring` everywhere it's thinnest, for any side count.

## STEP export

The STEP files use AP203 CONFIG_CONTROL_DESIGN schema with `FACETED_BREP` and `CLOSED_SHELL`. This is the correct combination for triangulated geometry. The common mistake — which you'll find in a lot of generated STEP files — is `MANIFOLD_SOLID_BREP`, which requires a proper boundary representation, not a triangle soup. FreeCAD, Fusion 360, and SolidWorks all reject that silently or import it as an empty body.

## Tests

    .venv/bin/python tests/test_all.py
    .venv/bin/python tests/test_geometry.py

`test_all.py` (48 tests) covers the full profile × section matrix and asserts the things that actually matter for printing: watertight, single body, positive volume, correct mouth radius. `test_geometry.py` (33 tests) checks the *shape* of the output the way you would in a slicer — it sections the mesh, isolates the outer contour, and measures `max_r / min_r` (1.0 for a circle, `1/cos(π/N)` for an N-gon). That second file exists because the failures worth catching aren't crashes: they're a flange that came out round when you asked for a square, or a "wall" that isn't actually the thickness you typed.

## Known limitations

For very low cutoff frequencies (below roughly 200 Hz) the Le Cléac'h ODE integrates over an enormous arc length and may not terminate cleanly. In practice a 200 Hz horn is physically impractical to print so this doesn't come up often.

A polygonal flange with few sides and a large hole gets big: holding a uniform flat-face wall on a triangle means the corners reach a long way out. That's geometry, not a bug — switch to more sides or a circular outer if the footprint matters.

## License

MIT