# 📯 flare_forge

Parametric STL generator for acoustic horns — Tractrix, Le Cléac'h, Iwata.

Generate watertight, 3D-printable horn STLs from acoustical parameters (throat diameter, cutoff frequency, mouth diameter). Includes a parametric mounting flange generator and a Web UI.

## Quick Start

```bash
# Install
make install

# Launch web UI
streamlit run ui_app.py

# Or use CLI
python -m src.main --throat 20 --mouth 100
python -m src.main --throat 20 --fc 800
python -m src.main --profile iwata --throat 20 --fc 600 --length 80
```

## Profiles

| Profile | Parameters | Description |
|---------|-----------|-------------|
| **Tractrix** | `--throat --mouth` | Constant tangent length; terminates at 90° |
| **Le Cléac'h** | `--throat --fc` | Euler integration (m=4π·fc/c) with 160° roll-back |
| **Iwata** | `--throat --fc --length` | Salmon hyperbolic-exponential (T=0.707) |
| **Rectangular** | `--throat_w --throat_h --mouth_w --fc` | Area-preserving W(z)×H(z), manual lofting |
| **Radial 360°** | `--throat --mouth --fc` | Omnidirectional reflector, dual-piece, flipped top |

## Flange Generators

```bash
# Circular flange (circular hole)
python -m src.flange_generator

# Rectangular-hole flange (circular outer, rectangular inner)
python -m src.rectangular_flange
```

## Testing

```bash
.venv/bin/python tests/test_all.py
```

18 tests covering all profiles, mesh engines, and watertightness.

## Requirements

- Python 3.10+
- numpy, numpy-stl, trimesh, manifold3d, scipy
- streamlit (for UI)

## Data Flow

```
Parameters → 2D Profile (Z,R) → Normal offset → Revolution → STL
                ↑                        ↑
         tractrix / lecleach / iwata    generate_3d_mesh_from_profile()

Rectangular:  (z, w, h) → generate_rectangular_3d_mesh() → STL
Radial:       (R, Zb, Zt) → _revolve_polygon() → radial_bottom + radial_top
```

## Project Structure

```
src/  profile_generator.py       — axisymmetric profiles + 3D engine
     flange_generator.py        — parametric circular flange
     rectangular_horn.py        — rectangular horn lofting engine
     radial_horn.py             — 360° radial horn (dual-piece)
     rectangular_flange.py      — rectangular-hole flange
     _step_export.py            — STEP AP242 export utility
     _constants.py              — shared constants
     _utils.py                  — shared utilities (normals, volume, Z-align)
     main.py                    — CLI orchestrator
ui_app.py                       — Streamlit web UI
tests/test_all.py               — comprehensive test suite (18 tests)
```

## License

MIT
