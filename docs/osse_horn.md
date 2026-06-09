# `osse_horn.py` — Full OS-SE Waveguide (ATH-style, non-axisymmetric)

**Path:** `src/osse_horn.py`

Faithful implementation of Marcel Batík's **OS-SE Waveguide** formula
(at-horns.eu, Oct 2020). Unlike the axisymmetric `get_rosse` in
`profile_generator.py`, this builds the real **round-throat → superelliptical
(rectangular) mouth** waveguide whose coverage angle **varies with azimuth** —
which is what produces the characteristic **diagonal ridges** (the
"protrusions") running from the throat to the four corners.

---

## The math (Batík eq. 5), single azimuth

```
r(z) = √(k²r₀² + 2kr₀z·tanα₀ + z²·tan²α) + r₀(1−k)      (generalized OS, a hyperbola)
       + (sL/q)·[1 − (1 − (qz/L)ⁿ)^(1/n)]               (super-ellipse termination)
```

| Symbol | Meaning |
|---|---|
| `r₀` | throat radius |
| `α`  | nominal coverage **half**-angle (half the beamwidth) |
| `α₀` | throat opening **half**-angle (0 = flat wavefront) |
| `k`  | throat expansion factor (`1` = pure OS hyperbola, `0` = straight cone) |
| `L`  | length |
| `s`  | termination flare amount (0 = no mouth flare) |
| `n`  | super-ellipse exponent (higher = profile preserved longer, sharper end) |
| `q`  | truncation coefficient (≈ 0.998; drops the last useless straight bit) |

Properties: `r(0)=r₀` for any `α/α₀/k`; `k=0` ⟹ `r₀ + z·tanα`; the SE term is 0 at the throat.

---

## Azimuthal variation → the ridges

The OS-SE parameters may differ around the device. Here **only `α` varies**, on
an **elliptical cone** between the horizontal half-angle `α_h` (φ=0) and the
vertical half-angle `α_v` (φ=π/2):

```
tan α(φ) = 1 / √( (cosφ/tanα_h)² + (sinφ/tanα_v)² )
```

so the un-morphed mouth is ~elliptical. The mouth is then **morphed** (Batík
sec. 5) onto a **superellipse** of exponent `mouth_exp` whose half-axes equal the
natural H/V mouth (`a = r(L,0)`, `b = r(L,π/2)`):

```
r_M(φ) = ( (|cosφ|/a)^p + (|sinφ|/b)^p )^(−1/p)          p = mouth_exp  (2=ellipse, ∞=rectangle)
r_m(z,φ) = r(z,φ) + clip((z−z_f)/(L−z_f), 0,1)^γ · (r_M(φ) − r(L,φ))
```

Because the superellipse passes through the natural H/V mouth points, the morph
is a **no-op on the H and V axes** but pushes the **diagonals out to the
corners** in the second half of the length — that bulge **is** the ridge.
`z_f = morph_start·L` keeps the throat region intact; `γ = morph_rate` sets how
gradual the push is.

---

## API

### Math layer (no side effects)

| Function | Returns |
|---|---|
| `osse_profile(z, r0, alpha, alpha0=0, k=1, L=120, s=0.8, n=5, q=0.998)` | `r(z)` array, eq. 5 (angles in radians) |
| `coverage_alpha(phi, alpha_h, alpha_v)` | `α(φ)` elliptical-cone coverage |
| `superellipse_radius(phi, a, b, p)` | `r_M(φ)` polar radius of a superellipse |
| `osse_surface(r0, L, alpha_h, alpha_v, alpha0=0, k=1, s=0.8, n=5, q=0.998, mouth_exp=4, morph_start=0, morph_rate=2, nz=120, nphi=160)` | `(z[nz], phi[nphi], R[nz,nphi])` morphed inner radius field |

### Mesh engine

```python
generate_osse_3d_mesh(throat, length, coverage_h, coverage_v,
    throat_angle=0.0, k=1.0, s=0.8, n=5.0, q=0.998,
    mouth_exp=4.0, morph_start=0.0, morph_rate=2.0,
    thickness=4.0, nz=120, nphi=160, output_path=None) -> trimesh.Trimesh
```

- `throat` = throat **diameter** (mm); `coverage_h/v` = full beamwidths (degrees);
  `throat_angle` = full included angle (degrees). Internally halved.
- Builds inner vertices on the `r(z,φ)` grid, computes **true per-vertex normals**
  from the grid tangents (`t_φ × t_z`, oriented outward), offsets by `thickness`
  to the outer shell, and triangulates inner+outer walls + throat/mouth rims.
- The throat (z=0) and mouth (z=L) faces are **pinned flat** (outer z clipped to
  `[0, L]`, end rings forced to the plane), like the rectangular/polygonal
  engines, so the round throat mates with a driver/adapter and the mouth sits in
  a baffle.
- Returns a watertight single-body `trimesh.Trimesh`; keeps the largest body if
  the offset ever splits.

---

## Notes / limits

- This is the **flat-baffle** OS-SE (no free-standing mouth roll-back). For a
  rolled-back free-standing mouth, Batík extends with a clothoid (numerical) —
  not implemented here; the axisymmetric roll-back lives in `get_rosse`.
- The constant-thickness offset can self-intersect at extreme curvature/`mouth_exp`;
  defaults (`mouth_exp ≤ ~10`, `thickness ≤ ~6`) stay clean.
- `get_rosse` (axisymmetric R-OSSE) remains the round-mouth roll-back profile;
  `osse_horn` is the rectangular ATH device with ridges.

## UI mounting flanges

`ui_app.py` wires all three flanges for OS-SE (dedicated branches, no adapter
machinery):

- **Throat** — round, so a flat circular `generate_flange` welds to the throat
  outer wall (`throat_R + thickness`), exactly like the axisymmetric profiles.
- **Mouth / Mid** — the cross-section is superelliptical, so the flange follows
  the **real contour** (ridges included) via `generate_contour_flange`, *not* an
  inscribed ellipse (which would fall ~30 mm short at the diagonals and block the
  airway). The contour is sampled from the `r(z,φ)` field (`_osse_contour_xy`):
  mouth at `z=L`, mid at the chosen station. Hole = contour bitten inward; outer
  = contour + wall + ring.

All three weld into a single watertight body with the horn (test:
`OS-SE throat/mouth/mid flanges weld to horn`).
