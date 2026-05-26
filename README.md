# 📯 Acoustic Horn Generator

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
| **Le Cléac'h** | `--throat --fc` | Spherical isophase wavefront expansion with native roll-back |
| **Iwata** | `--throat --fc --length` | Salmon hyperbolic-exponential area expansion (T=0.707) |

## Flange Generator

```bash
python -m src.02_flange_generator
```

Parameters: outer diameter, inner diameter, thickness, bolt circle radius, bolt count, bolt diameter.

## Requirements

- Python 3.10+
- numpy, numpy-stl, trimesh, manifold3d, scipy
- streamlit (for UI)

## Data Flow

```
Parameters → 2D Profile (Z,R) → Normal offset → Revolution → STL
                ↑                        ↑
          tractrix / lecleach / iwata    generate_3d_mesh_from_profile()
```

## Project Structure

```
src/
  01_profile_generator.py    — profile math + 3D mesh engine
  02_flange_generator.py     — parametric circular flange
  main.py                    — CLI orchestrator
ui_app.py                    — Streamlit web UI
```

## License

MIT
