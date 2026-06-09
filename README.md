# flare_forge

A parametric STL generator for acoustic horn waveguides. You type in the physics — throat diameter, cutoff frequency, wall thickness — and it hands you a watertight solid ready for the printer.

I built this because every tool I found either required a full CAD package, or produced meshes that weren't actually watertight, or got the math wrong in ways that were hard to notice until you printed the thing. A parametric generator that takes physical parameters and does the geometry for you is surprisingly rare.

## Running it

    make install
    make run            # launches the UI and opens it in Safari

`make run` starts Streamlit headless and opens `localhost:8501` in Safari. Or run it yourself with `streamlit run ui_app.py` (default browser). There is also a CLI:

    python -m src.main --profile tractrix --throat 20 --mouth 100 --output io/horn.stl
    python -m src.main --profile salmon --throat 20 --fc 600 --length 80 --output io/horn.stl
    python -m src.main --profile oblate --throat 20 --coverage 90 --length 120 --output io/horn.stl

## The expansion profiles

The right expansion curve depends on what you're optimizing for, and none of them is obviously better.

**Tractrix** has a nice variational property: the tangent is horizontal at the mouth, which minimizes reflections. It comes out short though, which means poor low-frequency driver loading. Still, it's the one with the cleanest derivation.

**Salmon** (hyperbolic-exponential, parametrizzato da `T`). Con `T=0.707` (Hypex) è il profilo più usato nei compression driver. Dai una lunghezza e una frequenza di taglio, e calcola l'espansione. Prevedibile e robusto.

**Exponential** is the textbook formula. Area doubles every fixed axial distance. Fast, simple, valid for many applications.

**Le Cléac'h** integrates an isophase wavefront profile from a Salmon/Hypex area law. It can roll the mouth back, which is useful acoustically but means some simple mouth-flange assumptions stop applying.

**Oblate spheroidal** is a constant-directivity-oriented profile:
`r(x) = sqrt(r0² + (x·tan(coverage/2))²)`. The throat starts parallel to the axis, then tends toward a conical asymptote. Rectangular oblate horns solve horizontal and vertical coverage independently, so 90° × 45° waveguides are first-class.
The requested angles are nominal/asymptotic: actual polar response depends on frequency, driver and higher-order modes.

**Iwata** is the real thing — the horn from the l'Audiophile plan (for JBL 2440/375), digitized from the drawing. Unlike the others it is *rectangular and asymmetric*: width and height flare at different rates (mouth ≈ 740×320 mm over 572 mm), so the cross-section grows from ~1:1 at the throat to ~2.3:1 at the mouth. The wide-plane mouth is a **circular arc** (radius 692 mm about an apex behind the throat), the height-plane mouth stays flat — built by boolean-trimming the loft with a cylinder. You set throat size and length; the proportions, mouth and an approximate loading frequency follow from the plan. (Selecting Iwata forces a rectangular section; the curved mouth means no mouth flange.)

**OS-SE (ATH)** is the full waveguide from Marcel Batík's OS-SE formula (at-horns.eu): a *round throat → superelliptical mouth* device whose coverage varies with azimuth, so the diagonals get pushed out to the corners in the second half of the length — those bulges are the characteristic **diagonal ridges**. You set throat, length and horizontal/vertical coverage; the mouth W×H and ridges follow. Like radial/Iwata it is non-axisymmetric with its own `r(z,φ)` loft engine and ignores the section selector. It now supports all three mounting flanges: a round throat flange, and superelliptical mouth/mid flanges that follow the **real contour** (ridges included), not an inscribed ellipse.

Most profiles return `(z, r)` and nothing else — just the math, with the cross-section a separate choice. The rectangular ones (including Iwata) return `(z, w, h)` because the section is intrinsic to them.

## Cross-sections

The profile says how the area grows along the axis. The section says what shape that area takes. Most axisymmetric profiles compose with the circular, polygonal and rectangular engines; Iwata is intrinsically rectangular.

**Circular** is the revolution you'd expect: spin the profile around Z.

**Polygonal** makes every Z slice a regular N-gon (3 to 12 sides), area-matched to the equivalent circle, so the fundamental one-dimensional area law is preserved while the horn prints flat-faced. Higher-order modes and directivity can differ from the circular version. The circumradius is `r_eq · √(2π / (N·sin(2π/N)))`.

**Rectangular** loftes a rectangle of constant aspect ratio along the axis; width and height both follow the same area-preserving expansion as the equivalent circle.

## How the mesh is built

The 2D profile functions return `(z, r)` arrays — pure math, no geometry yet. For a circular section these feed a profile-agnostic 3D engine that computes outward normals via finite differences, offsets the inner profile along those normals by the wall thickness to get the outer surface, revolves both around Z, and caps the throat and mouth.

The offset is a true parallel offset along the meridian normal. For a body of revolution the 3D surface normal lies entirely in the meridian plane, so a 2D normal offset *is* a 3D offset — the wall comes out at a **constant** perpendicular thickness everywhere (no Euclidean/normal-space approximation, no thinning toward the mouth). The trade-off is that the outer throat rim then sits at a different Z than the inner rim, leaving a slanted base; the engine slices that base flat with a plane and re-caps it, so the throat face is planar while the wall stays uniform.

The 2D preview's "+ wall" line draws this same parallel offset, so what you see is what gets printed.

The polygonal section reuses the same `(z, r)` and the same normal-offset idea, but lofts N-gon rings instead of revolving — the per-vertex offset is scaled by `1/cos(π/N)` so the wall thickness stays uniform along the face normal, not the vertex direction. Radial has its own two-piece revolution engine.

## Slicing for printing

A horn that's too big for the print bed can be sliced into `n` radial petals (like an orange) and glued back together. With a non-zero joint depth each seam gets a tongue-and-groove interlock for alignment and glue area.

The UI defaults to one axial segment and two radial petals. That gives a ready-to-print left/right split without accidentally slicing the horn into a stack of axial rings; increase the segment count only when the print height needs it.

When an assembly includes a throat adapter, the slicer can treat the adapter as its own bottom axial segment. The cut is placed at the adapter-to-flare handoff and uses the same axial joint lip when enabled, while Count/Height segmentation applies only to the flare above it.

For box-style printer limits, the slicer can cut the assembly into print-volume chunks. The default strategy starts from the center-bottom core, climbs upward, then fills side wings with larger adaptive chunks instead of a global grid of slivers. Throat adapters and throat flanges can be kept monolithic inside the first center-bottom chunk, even if that first chunk exceeds the requested build volume. Box chunks can also receive tongue-and-groove alignment joints on shared cut faces.

For `n >= 3` each petal is a wedge under 180°, so its left and right seams are distinct planes: a groove goes on the left, a tongue on the right, and adjacent petals mate tongue-into-groove.

The radial tongue-and-groove joint protects the outside skin before placing the interlock. By default the outer 1.5 mm strip of the seam is kept solid, so the visible external wall remains consistent and the tongue/groove geometry is biased toward the inside of the wall.

`n = 2` is the awkward case, and worth calling out because it's easy to get wrong. The two cutting planes are coplanar — a single diametric plane through the axis — so a petal's "left" and "right" seams are the *same* face, and that face crosses the axis into **two** wall strips. You can't put both a groove and a tongue on one face. The fix is to make each half hermaphrodite: a tongue on one strip, a groove on the other, with the strip assignment flipped between the two halves so a tongue always faces a groove. The two halves come out as identical parts — one is just the other rotated 180°.

## Flanges

Mounting flanges (throat, mouth, and an optional mid-flange at any axial position) are built with CSG boolean operations via trimesh and manifold3d. Bolt holes are real cutouts, not overlapping geometry. The outer body can be circular or a polygon, independently of the horn's section.

The mouth flange is sized against the horn's actual outer wall, not the acoustic inner profile. Circular, polygonal and rectangular mouths all use the same rule: the hole follows the real outer wall at the mouth and bites inward by 0.5 mm. The OS-SE waveguide goes one step further: because its section is superelliptical, the mouth and mid flanges are built around the **real sampled contour** (`generate_contour_flange`), so they follow the ridges out to the corners instead of an inscribed ellipse that would fall ~30 mm short on the diagonal and clip the airway. That small overlap avoids coplanar contact, so the flange unions as a real volumetric weld instead of leaving non-manifold edges or a visible loose ledge. The value shown in the UI is the same value used for ring width, bolt-circle limits and final mesh generation.

An inward roll-back mouth flange is supported by full load-bearing pillars between the flange and flare. Each pillar is built first and then boolean-clipped against the real curved flare surface, so it reaches the screw bearing face without protruding outside. The visible flare opening remains a round shaft-diameter hole. Optional screw-head seats are axial and concentric with the vertical screw holes, and all seats terminate on one shared coplanar floor set by `Head depth`.

One subtlety worth stating, because it's easy to get wrong: on a polygonal outer, "ring width" is the wall thickness at the **flat faces**, not the distance to the corners. The hole is a circle of radius `inner_R`; the polygon's narrowest wall is at its inradius, `flange_R · cos(π/N)`. If you size the polygon by its circumradius (`inner_R + ring`), the flat-face wall shrinks as you add sides and eventually goes negative — the round hole punches straight through the edges and you're left with detached corner triangles. So the circumradius is solved backwards from the wall you actually want: `flange_R = (inner_R + ring) / cos(π/N)`. The wall is then a uniform `ring` everywhere it's thinnest, for any side count.

The throat side can also be an adapter from a round driver interface into the horn throat. It supports a custom flange, standard commercial bolt-on patterns (1" 2-hole, 1" 3-hole, 1.4" 4-hole, and 2" 4-hole), and a modeled 1⅜"-18 female thread with a separate 25 mm acoustic bore. Bolt-on presets fix the outer diameter, M6 clearance holes, PCD, and angular pattern while allowing configurable throat clearance. The adapter is not just diameter-matched at the throat: its equivalent-radius curve is Hermite-raccordato to the flare's first derivative, and the outer wall target is computed with the same parallel-offset convention as the horn mesh, so the adapter hands off without an internal or external edge while preserving the expansion law.

## STEP export

The STEP files use AP203 CONFIG_CONTROL_DESIGN schema with `FACETED_BREP` and `CLOSED_SHELL`. This is the correct combination for triangulated geometry. The common mistake — which you'll find in a lot of generated STEP files — is `MANIFOLD_SOLID_BREP`, which requires a proper boundary representation, not a triangle soup. FreeCAD, Fusion 360, and SolidWorks all reject that silently or import it as an empty body.

## DXF drilling templates

Each mounting flange (throat, mouth, mid) can also be downloaded as a flat 2-D **DXF** template — a drill/cut drawing with the bolt holes, the throat bore, and the plate outline on separate layers (`HOLES`, `BORE`, `OUTLINE`, `CENTERS`). It's written by hand as plain AutoCAD R12 (AC1009) ASCII in millimetres, so there's no extra dependency and it opens in LibreCAD/QCAD/Fusion/Illustrator and every CAM tool. Templates are taken straight from the generated flange *mesh* by cutting a cross-section through the plate; the section finder also detects thin flange plates on tall throat adapters. Inward mouth flanges export the shaft holes drilled into the assembled horn. Bolt holes come back as exact nominal circles; a hexagonal or rectangular bore keeps its real shape as a polyline.

## Tests

    .venv/bin/python tests/test_all.py
    .venv/bin/python tests/test_geometry.py

`test_all.py` (197 tests) covers the profile × section matrix, requested-dimension regressions, standard driver bolt-on presets, flanges, DXF drilling templates, inward-flange pillars and screw seats across roll-back section shapes, slicing, radial and box tongue-and-groove joints, print-volume chunks, and the throat adapter C1/C2 raccordo. `test_geometry.py` (33 tests) checks the *shape* of the output the way you would in a slicer — it sections the mesh, isolates the outer contour, and measures `max_r / min_r` (1.0 for a circle, `1/cos(π/N)` for an N-gon). That second file exists because the failures worth catching aren't crashes: they're a flange that came out round when you asked for a square, or a "wall" that isn't actually the thickness you typed.

## Known limitations

For very low cutoff frequencies (below roughly 200 Hz) the Le Cléac'h ODE integrates over an enormous arc length and may not terminate cleanly. In practice a 200 Hz horn is physically impractical to print so this doesn't come up often.

A polygonal flange with few sides and a large hole gets big: holding a uniform flat-face wall on a triangle means the corners reach a long way out. That's geometry, not a bug — switch to more sides or a circular outer if the footprint matters.

## License

MIT
