# `src/radial_horn.py` — 360° Radial Horn (Omnidirectional Reflector)

Generates two interlocking solid-of-revolution parts that form a radial
waveguide: a **bottom deflector** and a **top reflector**. The top part is
exported upside-down for supportless FDM printing.

All dimensions in mm. Outputs `radial_bottom.stl` and `radial_top.stl`.

Uses `numpy-stl` (`from stl import mesh`) — NOT trimesh.

---

## Public API

### `generate_radial_horn`

```python
def generate_radial_horn(
    throat_diam: float = 25.0,
    mouth_diam: float = 200.0,
    fc: float | None = None,
    rings: int = 64,
    output_dir: str = "io",
    profile: str = "Exponential",
) -> tuple[mesh.Mesh, mesh.Mesh]:
```

**Returns:** `(bottom_mesh, top_mesh)` — two `stl.mesh.Mesh` objects. Files
are also saved to `output_dir/radial_bottom.stl` and
`output_dir/radial_top.stl`.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `throat_diam` | `float` | `25.0` | Diameter at the inner (throat) end. |
| `mouth_diam` | `float` | `200.0` | Diameter at the outer (mouth) end. |
| `fc` | `float \| None` | `None` | Cutoff frequency (Hz). Defaults to `1000.0` internally. Used for Exponential and Salmon profiles. |
| `rings` | `int` | `64` | Number of angular segments in the revolution. |
| `output_dir` | `str` | `"io"` | Directory for STL output files. |
| `profile` | `str` | `"Exponential"` | Aerodynamic expansion profile. Must be `"Exponential"`, `"Tractrix"`, `"Salmon"`, or `"Oblate spheroidal"`. |

---

## Profiles — `get_radial_profiles`

```python
def get_radial_profiles(
    throat_diam: float,
    mouth_diam: float,
    fc: float | None = None,
    n: int = 300,
    profile: str = "Exponential",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
```

**Returns:** `(R, Z_bottom, Z_top)` — three 1-D arrays of length `n`, where:
- `R` — radius values from `Rt` to `Rm` (mm)
- `Z_bottom` — Z-height of the deflector bottom surface
- `Z_top` — Z-height of the reflector top surface

**Gap (channel height):** `H(R) = Z_top - Z_bottom = S(R) / (2πR)`.

**Z_bottom ramp:** `Z_bottom = (R − Rt) × 0.3` — a gentle linear slope that
gives the bottom deflector a slight upward tilt as it expands.

### Area law `S(R)`

The cross-sectional area `S(R)` follows the chosen aerodynamic profile,
re-parameterised so the profile's axial coordinate spans `[Rt, Rm]`:

#### Exponential

```
St = π × Rt²
m = 4π × fc / SOUND_SPEED
S(R) = St × exp(m × (R − Rt))
```

Straight logarithmic expansion. `fc` is required (defaults to 1000 Hz).

#### Tractrix

- Calls `profile_generator.get_tractrix(throat_diam, mouth_diam, n)` to
  obtain `(z_p, r_p)`.
- Area: `S_prof = π × r_p²`.
- Re-parameterises via linear interpolation on normalised `t ∈ [0, 1]`:
  `S = interp(linspace(0, 1, n), t, S_prof)`.
- Clamped: `S = max(S, St)` to ensure monotonic expansion (never narrower
  than throat).

#### Salmon

- Calls `profile_generator.get_salmon(throat_diam, fc, Rm − Rt, n)`.
- Same re-parameterisation and clamping as Tractrix.

#### Oblate spheroidal

- Calls `profile_generator.get_oblate_spheroidal_for_mouth(throat_diam, mouth_diam, 90.0, n)`.
- Same re-parameterisation and clamping as Tractrix.
- `fc` is ignored because the oblate radial profile is driven by throat, mouth, and a default 90° total coverage.

`fc` is ignored for Tractrix (the profile itself has no frequency parameter);
for Salmon it is used in the underlying `get_salmon` call (defaults to 1000).

---

## Internal — `_revolve_polygon`

```python
def _revolve_polygon(
    r_poly: np.ndarray,
    z_poly: np.ndarray,
    rings: int = 64,
) -> mesh.Mesh:
```

Revolves a **closed** 2-D polygon `(r_poly[i], z_poly[i])` around the Z axis.
Does NOT generate centre caps (top/bottom lids are explicit in the caller's
polygon definition). Does NOT compute gradient normals — uses flat facets.

**Loop:** For each segment `i ∈ [0, n_pts-2]` and angular ring `j ∈ [0, rings-1]`:
- Wraps ring index: `jj = (j + 1) % rings`
- Emits 2 triangles (quad a→d→b, b→d→c):
  ```
  a = (r[i  ]·cos(j ),  r[i  ]·sin(j ),  z[i  ])
  b = (r[i+1]·cos(j ),  r[i+1]·sin(j ),  z[i+1])
  c = (r[i+1]·cos(jj),  r[i+1]·sin(jj),  z[i+1])
  d = (r[i  ]·cos(jj),  r[i  ]·sin(jj),  z[i  ])
  ```
**Triangle count:** `2 × rings × (n_pts − 1)`.

After revolution, calls `_utils.align_z_to_zero(m_obj)` and
`_utils.ensure_positive_volume(m_obj)`.

The `_wt()` logging helper reports `mesh.is_closed(exact=True)` directly, so
radial generation logs whether each exported STL is closed without calling
`numpy-stl.get_mass_properties()` and triggering open-mesh mass-property
warnings.

---

## Bottom Deflector polygon

Closed loop `(r_bot, z_bot)` concatenated as:
```
r_bot = [R..., Rm, Rt]
z_bot = [Zb..., 0,  0 ]
```

Vertices (in order):
1. Top curve: traces `(R[i], Zb[i])` for all i, starting at `(Rt, 0)`.
2. Outer vertical edge: `(Rm, Zb[-1])` → `(Rm, 0)`.
3. Bottom flat: `(Rm, 0)` → `(Rt, 0)` (closes the loop, forms solid base at
   Z=0)

This produces a solid with a flat bottom at Z=0 and a curved upper surface
that follows the bottom profile. The centre throat hole is implicit (no
material inside `r < Rt` — the revolution starts at `Rt`).

The loop intentionally does **not** prepend an extra `(Rt, 0)` point before
`R[0]`: `Zb[0]` is already zero, so that duplicate would create a degenerate
radial strip and make `numpy-stl`'s exact closed-mesh check report the bottom
piece as open.

---

## Top Reflector polygon

Closed loop `(r_top, z_top)` concatenated as:
```
r_top = [eps, R..., Rm, eps, eps]
z_top = [Zt[0], Zt..., Z_flat, Z_flat, Zt[0]]
```

where `wall_T = 4.0` (mm, hardcoded) and `Z_flat = Zt[-1] + wall_T`.

Vertices (in order):
1. `(eps, Zt[0])` — tiny radius `eps = 0.01` near the axis to **avoid
   degenerate triangles** at `r = 0`. The central area `r < eps` is closed
   by the last vertical segment.
2. Bottom curve: traces `(R[i], Zt[i])` for all i
3. Outer vertical: `(Rm, Zt[-1])` → `(Rm, Z_flat)`
4. Top flat: `(Rm, Z_flat)` → `(eps, Z_flat)`
5. Inner vertical: `(eps, Z_flat)` → `(eps, Zt[0])` (closes the loop back to
   the start)

The top reflector is then flipped for printing:
```
zf_flipped = zf.max() − zf
axes_swapped = vectors[:, [0, 2, 1]]
```

This **inverts Z** (so the flat top sits at Z=0 on the print bed) and **swaps
the Y and Z axes** so the part is printed face-up with the curved side on
top — the part is effectively printed upside-down for supportless FDM:
- Original flat top becomes the first layer on the bed (Z=0)
- Original curved bottom faces upward and requires no supports

---

## Standalone usage

```bash
python src/radial_horn.py
```

Runs with defaults: `throat_diam=25`, `mouth_diam=200`, `fc=600`.
