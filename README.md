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

**Iwata** is the real thing — the horn from the l'Audiophile plan (for JBL 2440/375), digitized from the drawing. Unlike the others it is *rectangular and asymmetric*: width and height flare at different rates (mouth ≈ 740×320 mm over 572 mm), so the cross-section grows from ~1:1 at the throat to ~2.3:1 at the mouth. The wide-plane mouth is a **circular arc** (radius 692 mm about an apex behind the throat), the height-plane mouth stays flat — built by boolean-trimming the loft with a cylinder. You set throat size and length; the proportions, mouth and ≈210 Hz cutoff follow from the plan. (Selecting Iwata forces a rectangular section; the curved mouth means no mouth flange.)

Most profiles return `(z, r)` and nothing else — just the math, with the cross-section a separate choice. The rectangular ones (including Iwata) return `(z, w, h)` because the section is intrinsic to them.

## Cross-sections

The profile says how the area grows along the axis. The section says what shape that area takes. Any of the four profiles composes with any of the four sections.

**Circular** is the revolution you'd expect: spin the profile around Z.

**Polygonal** makes every Z slice a regular N-gon (3 to 12 sides), area-matched to the equivalent circle, so the acoustics are unchanged but the horn prints flat-faced. The circumradius is `r_eq · √(2π / (N·sin(2π/N)))`.

**Rectangular** loftes a rectangle of constant aspect ratio along the axis; width and height both follow the same area-preserving expansion as the equivalent circle.

**Radial 360°** is a disk waveguide for omnidirectional applications. Two pieces — bottom plate and top reflector — with an acoustic gap between them.

## How the mesh is built

The 2D profile functions return `(z, r)` arrays — pure math, no geometry yet. For a circular section these feed a profile-agnostic 3D engine that computes outward normals via finite differences, offsets the inner profile along those normals by the wall thickness to get the outer surface, revolves both around Z, and caps the throat and mouth.

The offset is a true parallel offset along the meridian normal. For a body of revolution the 3D surface normal lies entirely in the meridian plane, so a 2D normal offset *is* a 3D offset — the wall comes out at a **constant** perpendicular thickness everywhere (no Euclidean/normal-space approximation, no thinning toward the mouth). The trade-off is that the outer throat rim then sits at a different Z than the inner rim, leaving a slanted base; the engine slices that base flat with a plane and re-caps it, so the throat face is planar while the wall stays uniform.

The 2D preview's "+ wall" line draws this same parallel offset, so what you see is what gets printed.

The polygonal section reuses the same `(z, r)` and the same normal-offset idea, but lofts N-gon rings instead of revolving — the per-vertex offset is scaled by `1/cos(π/N)` so the wall thickness stays uniform along the face normal, not the vertex direction. Radial has its own two-piece revolution engine.

## Splitting into petals

A horn that's too big for the print bed can be sliced into `n` radial petals (like an orange) and glued back together. With a non-zero joint depth each seam gets a tongue-and-groove interlock for alignment and glue area.

The UI defaults to one axial segment and two radial petals. That gives a ready-to-print left/right split without accidentally slicing the horn into a stack of axial rings; increase the segment count only when the print height needs it.

When an assembly includes a throat adapter, the slicer can treat the adapter as its own bottom axial segment. The cut is placed at the adapter-to-flare handoff and uses the same axial joint lip when enabled, while Count/Height segmentation applies only to the flare above it.

For `n >= 3` each petal is a wedge under 180°, so its left and right seams are distinct planes: a groove goes on the left, a tongue on the right, and adjacent petals mate tongue-into-groove.

`n = 2` is the awkward case, and worth calling out because it's easy to get wrong. The two cutting planes are coplanar — a single diametric plane through the axis — so a petal's "left" and "right" seams are the *same* face, and that face crosses the axis into **two** wall strips. You can't put both a groove and a tongue on one face. The fix is to make each half hermaphrodite: a tongue on one strip, a groove on the other, with the strip assignment flipped between the two halves so a tongue always faces a groove. The two halves come out as identical parts — one is just the other rotated 180°.

## Flanges

Mounting flanges (throat, mouth, and an optional mid-flange at any axial position) are built with CSG boolean operations via trimesh and manifold3d. Bolt holes are real cutouts, not overlapping geometry. The outer body can be circular or a polygon, independently of the horn's section.

The mouth flange is sized against the horn's actual outer wall, not the acoustic inner profile. Circular, polygonal and rectangular mouths all use the same rule: the hole follows the real outer wall at the mouth and bites inward by 0.5 mm. That small overlap avoids coplanar contact, so the flange unions as a real volumetric weld instead of leaving non-manifold edges or a visible loose ledge. The value shown in the UI is the same value used for ring width, bolt-circle limits and final mesh generation.

One subtlety worth stating, because it's easy to get wrong: on a polygonal outer, "ring width" is the wall thickness at the **flat faces**, not the distance to the corners. The hole is a circle of radius `inner_R`; the polygon's narrowest wall is at its inradius, `flange_R · cos(π/N)`. If you size the polygon by its circumradius (`inner_R + ring`), the flat-face wall shrinks as you add sides and eventually goes negative — the round hole punches straight through the edges and you're left with detached corner triangles. So the circumradius is solved backwards from the wall you actually want: `flange_R = (inner_R + ring) / cos(π/N)`. The wall is then a uniform `ring` everywhere it's thinnest, for any side count.

The throat side can also be an adapter from a round driver interface into the horn throat. Flanged drivers and modeled internal threads are supported for 1", 1¼" and 2" UNF interfaces, on circular, rectangular and polygonal flares. The adapter is not just diameter-matched at the throat: its equivalent-radius curve is Hermite-raccordato to the flare's first derivative, and the outer wall target is computed with the same parallel-offset convention as the horn mesh, so the adapter hands off without an internal or external edge while preserving the expansion law.

## STEP export

The STEP files use AP203 CONFIG_CONTROL_DESIGN schema with `FACETED_BREP` and `CLOSED_SHELL`. This is the correct combination for triangulated geometry. The common mistake — which you'll find in a lot of generated STEP files — is `MANIFOLD_SOLID_BREP`, which requires a proper boundary representation, not a triangle soup. FreeCAD, Fusion 360, and SolidWorks all reject that silently or import it as an empty body.

## Tests

    .venv/bin/python tests/test_all.py
    .venv/bin/python tests/test_geometry.py

`test_all.py` (78 tests) covers the full profile × section matrix, flanges, slicing, the radial petal tongue & groove joint, and the throat adapter raccordo. `test_geometry.py` (33 tests) checks the *shape* of the output the way you would in a slicer — it sections the mesh, isolates the outer contour, and measures `max_r / min_r` (1.0 for a circle, `1/cos(π/N)` for an N-gon). That second file exists because the failures worth catching aren't crashes: they're a flange that came out round when you asked for a square, or a "wall" that isn't actually the thickness you typed.

## Known limitations

For very low cutoff frequencies (below roughly 200 Hz) the Le Cléac'h ODE integrates over an enormous arc length and may not terminate cleanly. In practice a 200 Hz horn is physically impractical to print so this doesn't come up often.

A polygonal flange with few sides and a large hole gets big: holding a uniform flat-face wall on a triangle means the corners reach a long way out. That's geometry, not a bug — switch to more sides or a circular outer if the footprint matters.

## License

MIT
