# flare_forge

A parametric STL generator for acoustic horn waveguides. You type in the physics — throat diameter, cutoff frequency, wall thickness — and it hands you a watertight solid ready for the printer.

I built this because every tool I found either required a full CAD package, or produced meshes that weren't actually watertight, or got the math wrong in ways that were hard to notice until you printed the thing. A parametric generator that takes physical parameters and does the geometry for you is surprisingly rare.

## Running it

    make install
    streamlit run ui_app.py

The web interface runs at `localhost:8501`. There is also a CLI:

    python -m src.main --throat 20 --fc 600 --profile lecleach --output horn.stl
    python -m src.main --throat 20 --mouth 100
    python -m src.main --profile iwata --throat 20 --fc 600 --length 80

## Why five profiles

Because the right expansion curve depends on what you're optimizing for, and none of them is obviously better.

**Tractrix** has a nice variational property: the tangent is horizontal at the mouth, which minimizes reflections. It comes out short though, which means poor low-frequency driver loading. Still, it's the one with the cleanest derivation.

**Le Cléac'h** is what you use when you actually want to listen to music. It maintains isophase wavefronts by integrating an ODE with RK45. The curve rolls back about 160° before terminating, giving a larger effective mouth than tractrix for the same throat and cutoff.

**Iwata** (technically Salmon hyperbolic-exponential, T=0.707) is the practical one. You hand it a length and a cutoff frequency and it fits an expansion in the box. Predictable and widely used in compression driver work.

**Exponential** is the textbook formula. Area doubles every fixed axial distance. Fast, simple, valid for many applications.

**Radial 360°** is a disk waveguide for omnidirectional applications. Two pieces — bottom plate and top reflector — with an acoustic gap between them.

## How the mesh is built

The 2D profile functions return `(z, r)` arrays — pure math, no geometry yet. These feed a profile-agnostic 3D engine that computes outward normals via finite differences, offsets the inner profile along those normals by the wall thickness to get the outer surface, revolves both around Z, and caps the annuli at the throat and mouth.

Offsets are computed in normal space, not Euclidean space. The distinction matters at the throat, where the profile curves tightly: a naive Euclidean offset collapses or self-intersects there, while the normal-space approach keeps wall thickness uniform in the direction the wall actually faces.

For rectangular cross-sections, the revolution step is replaced by a rectangular lofting engine. Area is preserved from the circular equivalent — `S_rect = S_circ` — with the throat aspect ratio maintained throughout.

Mounting flanges (throat, mouth, and an optional mid-flange at any axial position) are built with CSG boolean operations via trimesh and manifold3d. Bolt holes are real cutouts, not overlapping geometry.

## STEP export

The STEP files use AP203 CONFIG_CONTROL_DESIGN schema with `FACETED_BREP` and `CLOSED_SHELL`. This is the correct combination for triangulated geometry. The common mistake — which you'll find in a lot of generated STEP files — is `MANIFOLD_SOLID_BREP`, which requires a proper boundary representation, not a triangle soup. FreeCAD, Fusion 360, and SolidWorks all reject that silently or import it as an empty body.

## Tests

    .venv/bin/python tests/test_all.py

18 tests covering all profile and cross-section combinations. All meshes are checked for watertightness.

## Known limitations

For very low cutoff frequencies (below roughly 200 Hz) the Le Cléac'h ODE integrates over an enormous arc length and may not terminate cleanly. In practice a 200 Hz horn is physically impractical to print so this doesn't come up often.

Wall thickness at the throat end of high-curvature profiles will be slightly thinner on the concave face than requested. The error is typically under 0.5 mm for normal throat sizes.

## License

MIT
