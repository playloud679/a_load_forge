# `src/omni_horn.py` — Omnidirectional Compression-Driver Horn

Generates a **curved** axial→360°-radial waveguide for a compression driver
firing *axially* into the apex. A central **deflector** turns the wavefront 90°
and a curved outer **reflector** opens it to a full 360° radial mouth — the
"omni" tower geometry (central pointed deflector + flaring bell).

This is the curved sibling of `radial_horn.py`. The radial module uses a crude
linear deflector ramp (`z = (R-Rt)·0.3`); here the channel follows a true
*curved meridian* whose flow angle eases smoothly from 90° (axial) at the throat
to `lip_angle` at the mouth.

All dimensions in mm. Outputs `omni_deflector.stl` and `omni_reflector.stl`.
Uses `numpy-stl` (`from stl import mesh`) — NOT trimesh. Own revolution engine
(`_revolve_polygon`), not the axisymmetric/rect engines.

---

## Public API

### `generate_omni_horn`

```python
def generate_omni_horn(
    throat_diam: float = 25.0,
    mouth_diam: float = 200.0,
    fc: float | None = None,
    rings: int = 64,
    output_dir: str = "io",
    profile: str = "Exponential",
    lip_angle_deg: float = 0.0,
    bend_scale: float = 1.0,
    thickness: float = 4.0,
    n: int = 300,
) -> tuple[mesh.Mesh, mesh.Mesh]:
```

**Returns:** `(deflector, reflector)` — two `stl.mesh.Mesh` objects, also saved
to `output_dir/omni_deflector.stl` and `output_dir/omni_reflector.stl`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `throat_diam` | `float` | `25.0` | Driver throat Ø (circular). Throat area `St = π·(throat/2)²`. Sets the reflector's central hole Ø. |
| `mouth_diam` | `float` | `200.0` | Outer mouth Ø — the channel centerline ends at radius `mouth/2`. |
| `fc` | `float \| None` | `None` | Cutoff (Hz). Defaults to `1000.0` internally. Used by Exponential & Salmon. |
| `rings` | `int` | `64` | Angular segments in the revolution. |
| `output_dir` | `str` | `"io"` | STL output directory. |
| `profile` | `str` | `"Exponential"` | Area law: `"Exponential"`, `"Tractrix"`, `"Salmon"`, `"Oblate spheroidal"`. |
| `lip_angle_deg` | `float` | `0.0` | Flow angle (from horizontal) at the mouth. `0` = mouth fires purely radial (clean omni). `<0` = upturned morning-glory bell (advanced — the deflector may overhang the reflector radially with large gaps). |
| `bend_scale` | `float` | `1.0` | Vertical stretch of the bend (deflector height/aspect). `>1` = taller. |
| `thickness` | `float` | `4.0` | Reflector wall thickness; also the deflector base thickness. |
| `n` | `int` | `300` | Meridian sample count. |
| `standoffs` | `int` | `0` | Number of self-centering ribs welded onto the **deflector** (deflector-only). `0` = none. |
| `standoff_width` | `float` | `3.0` | Tangential width (mm) of each rib. |

### Centering ribs (`standoffs > 0`)

Each rib is a thin radial wedge that fills the channel band over `t ∈ [0.35,
0.95]` of the meridian (the throat tip and extreme rim are skipped so the throat
is never blocked). Its root sinks `_STANDOFF_OVERLAP = 1 mm` into the deflector
body (clean boolean weld) and its tip stops `_STANDOFF_CLEARANCE = 0.2 mm` short
of the reflector wall, so the **separately printed** deflector self-centers
against the reflector without fusing to it. Ribs are unioned onto the deflector
with trimesh's boolean engine (each wedge is `fix_normals()`-ed so it is a valid
volume); on engine failure it falls back to concatenation (the 1 mm overlap
still slices as one part). The result is returned as a single watertight
`stl.mesh.Mesh`.

---

## Profile math — `get_omni_profile`

```python
def get_omni_profile(throat_diam, mouth_diam, fc=None, n=300,
                     profile="Exponential", lip_angle_deg=0.0,
                     bend_scale=1.0) -> dict:
```

Returns a dict of parallel 1-D arrays (length `n`):

| Key | Meaning |
|---|---|
| `rho_c`, `z_c` | channel centerline (meridian radius, axial) |
| `h` | channel gap, measured **perpendicular to the local flow** |
| `nrho`, `nz` | unit meridian normal (the gap direction) |
| `low_r`, `low_z` | inner / deflector-side wall = `M − h/2·N` |
| `up_r`, `up_z` | outer / reflector-side wall = `M + h/2·N` |
| `St`, `Sm` | throat and mouth cross-sectional area |

### Centerline (the bend)

Flow angle from horizontal, cosine-eased (zero slope at both ends):

```
θ(t) = lip + (π/2 − lip)·½(1 + cos(π·t)),   t ∈ [0,1]
```

Unit tangents are integrated (`dρ ∝ cosθ`, `dz ∝ −sinθ`) and the result scaled
so the centerline radius spans `[Rt/2, Rm]`; `z` is multiplied by `bend_scale`.

### Key invariant: exact throat (no fudge)

The centerline **starts at `ρ₀ = Rt/2`**. With `S(throat)=St=π·Rt²`, the throat
gap is `h₀ = St/(2π·ρ₀) = Rt`. Therefore at the throat:

- inner wall `low_r[0] = ρ₀ − h₀/2 = 0` → deflector nose sits on the axis;
- outer wall `up_r[0] = ρ₀ + h₀/2 = Rt` → reflector hole = driver throat Ø.

So the throat is a true circle of radius `Rt` (area exactly `π·Rt²`) that becomes
annular as the deflector nose grows — the disk→annulus transition is built in,
not approximated.

### Area law `S(s)` (along centerline arc length `s`)

- **Exponential** — `S = St·exp(m·s)`, `m = 4π·fc/c`. (Like `radial_horn`, `fc`
  sets expansion rate and `mouth_diam` sets the geometric radial extent
  independently — they are not forced to agree; the UI mouth-adequacy warning
  flags a mismatch.)
- **Tractrix / Salmon / Oblate** — the profile's own area curve `π·r(z)²` is
  re-parameterised onto normalised arc length and clamped to `≥ St`.

Gap: `H = S / (2π·ρ_centerline)`. Walls are offset from the centerline along the
meridian normal `N`, so the wall thickness is perpendicular to flow (true gap),
not vertical — this is the curvature improvement over `radial_horn`.

---

## Solids

`_revolve_polygon(r_poly, z_poly, rings)` revolves a **closed** meridian polygon
(it connects consecutive points only, so the polygon's last point must equal its
first — a band must explicitly repeat the start point to close). Both parts are
aligned to `Z=0` and wound to positive volume via `_utils`.

- **Deflector** — solid central body under the inner wall `low_*`, closed to a
  flat base at `min(z) − thickness` and down the axis (`ρ=ε`).
- **Reflector** — constant-thickness shell: inner face `up_*`, outer face
  `up_* + thickness·N`, closed as a band (`up`, reversed `out`, back to `up[0]`)
  with the central throat hole at `ρ = Rt`.

---

## Standalone

```bash
python -m src.omni_horn          # writes omni_deflector.stl + omni_reflector.stl
```

## Known simplifications

- Geometric / area-law model, **not** an exact isophase (constant-phase
  wavefront) solution — good for loading & dispersion intent, not a substitute
  for a BEM-optimised waveguide.
- Optional `standoffs` ribs self-center the deflector against the reflector;
  with `standoffs=0` the two parts are not mechanically tied (same as
  `radial_horn`).
- `lip_angle_deg < 0` can make the deflector overhang the reflector radially
  when the mouth gap is large (e.g. high-`fc` Exponential). `0` is the clean
  default.
