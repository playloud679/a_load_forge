# `src/omni_horn.py` — Omnidirectional Compression-Driver Horn

Generates a **curved** axial→360°-radial waveguide for a compression driver
firing *axially* into the apex. A central **deflector** turns the wavefront 90°
and a curved outer **reflector** opens it to a full 360° radial mouth — the
"omni" tower geometry (central pointed deflector + flaring bell).

This is the curved sibling of `radial_horn.py`. The radial module uses a crude
linear deflector ramp (`z = (R-Rt)·0.3`); here the channel follows a true
*curved meridian* whose flow angle eases smoothly from 90° (axial) at the throat
to `lip_angle` at the mouth.

All dimensions in mm. The meridian revolution uses `numpy-stl`
(`_revolve_polygon`, own engine); part assembly / boolean welds use `trimesh`.

---

## Public API

### `build_omni_parts` (primary)

```python
def build_omni_parts(throat_diam=25.0, mouth_diam=200.0, fc=None, rings=64,
                     profile="Exponential", lip_angle_deg=0.0, bend_scale=1.0,
                     thickness=4.0, n=300, standoffs=None, standoff_width=3.0,
                     ribs_fused=True, vert_cov_deg=0.0,
                     preserve_area_law=True, pillar_count=None,
                     pillars_fused=None, pillar_hole_diam=0.0,
                     pillar_hole_ref_diam=None, pillar_hole_def_diam=None,
                     pillar_hole_pos=0.55, pillar_hole_depth=4.0,
                     pillar_hole_head_diam=0.0,
                     pillar_hole_head_depth=0.0,
                     plan_sides=0, plan_corner_radius=0.0) -> dict
```

Returns `{"deflector": Trimesh, "reflector": Trimesh, "pillars": Trimesh|None}`,
**all in one common assembled frame** (throat at the top, mouth below, parts
positioned relative to each other). The caller exports them assembled (for the
multi-body assembly STL + slicer) or translates each to `Z=0` for printing.

- Canonical names are `pillar_count`, `pillar_width`/`standoff_width`, and
  `pillars_fused`. Legacy `standoffs`, `n_pillars`, and `ribs_fused` are still
  accepted for saved scripts/UI state.
- `pillars_fused=True` (default): the `pillar_count` pillars are welded into the
  deflector; `pillars` is `None`.
- `pillars_fused=False`: the deflector stays smooth and the pillars come back as a
  separate `pillars` body (one multi-body mesh of `pillar_count` pillars).
- Pillar fixing holes can use separate diameters: `pillar_hole_ref_diam` cuts
  the reflector/flare clearance hole, while `pillar_hole_def_diam` cuts the
  deflector/pillar pilot/thread hole. Legacy `pillar_hole_diam` still sets both
  when the split diameters are not provided. Optional head counterbores cut only
  the reflector side.

The Streamlit UI calls this so omni flows through the normal assembly/results/
**slicer** pipeline (the omni branch concatenates the parts into a multi-body
assembly; the throat adapter is welded onto the reflector when *Integrated* or
kept as a separate part when *Separated*).

**Driver adapter = mechanical MOUNT only (throat follows the driver bore).**
When an adapter is included the UI sets the omni **throat to the driver bore**
(`_adapter_controls_throat` is true for omni too), so the channel *starts from
the driver* and the driver→throat transition is absorbed by the flare — it adds
**no acoustic length**. The adapter the UI builds is therefore a *matched*
(identity) transition: `make_adapter_assembly(horn_R_eq = throat_d/2 = driver_R,
adapter_length = max(3, thickness))`, i.e. a short weld neck + the mechanical
socket/flange. Only that mount sits behind the throat plane (≈ socket depth /
flange thickness), instead of the old separate ≈30 mm tube stacked on top that
grew the total depth. There is no "Adapter length" input for omni — the stick-out
is governed by *Socket depth* (threaded) / *Flange thickness* (flanged). See
`_check_omni_driver_mount_matched` in the tests. This is why the omni throat is
**not** taken from the user's throat Ø when an adapter is present; without an
adapter the throat Ø input is used as before.

**Smooth adapter weld.** The UI does not join the Omni mount with the generic
short circular adapter. It samples the reflector's first millimetres with
`omni_adapter_section_stack()` and passes those exact circular `custom_pts` /
`custom_outer_pts` to `throat_adapter.make_adapter_assembly()`. The adapter tail
therefore follows the same inner and outer radii as the reflector through the
overlap (the same method used by the OS-SE/R-OSSE adapter path), and the
integrated mode trims the replaced reflector section before unioning. This
removes the visible cylindrical step at the mount/reflector junction while
keeping the acoustic throat tied to the driver bore.

### `generate_omni_horn` (CLI/test wrapper)

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
    standoffs: int | None = None,
    standoff_width: float = 3.0,
    ribs_fused: bool = True,
    vert_cov_deg: float = 0.0,
    preserve_area_law: bool = True,
    pillar_count: int | None = None,
    pillars_fused: bool | None = None,
    pillar_hole_diam: float = 0.0,
    pillar_hole_ref_diam: float | None = None,
    pillar_hole_def_diam: float | None = None,
    pillar_hole_pos: float = 0.55,
    pillar_hole_depth: float = 4.0,
    pillar_hole_head_diam: float = 0.0,
    pillar_hole_head_depth: float = 0.0,
    plan_sides: int = 0,
    plan_corner_radius: float = 0.0,
) -> tuple[mesh.Mesh, mesh.Mesh]:
```

Thin wrapper over `build_omni_parts`: fuses the pillars by default, drops each part
to `Z=0`, writes `omni_deflector.stl` / `omni_reflector.stl` (+ `omni_pillars.stl`
when `pillars_fused=False` / `ribs_fused=False`). **Returns** `(deflector, reflector)` as `trimesh`
objects. Accepts both canonical pillar names and the legacy `standoffs` /
`ribs_fused` aliases.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `throat_diam` | `float` | `25.0` | Driver throat Ø (circular). Throat area `St = π·(throat/2)²`. Sets the reflector's central hole Ø. |
| `mouth_diam` | `float` | `200.0` | Outer mouth Ø — the channel centerline ends at radius `mouth/2`. |
| `fc` | `float \| None` | `None` | Cutoff (Hz). Defaults to `1000.0` internally. Used by Exponential & Salmon. |
| `rings` | `int` | `64` | Angular segments in the revolution. |
| `output_dir` | `str` | `"io"` | STL output directory. |
| `profile` | `str` | `"Exponential"` | Area law: `"Exponential"`, `"Tractrix"`, `"Salmon"`, `"Oblate spheroidal"`, `"Conical"`. |
| `lip_angle_deg` | `float` | `0.0` | Flow angle (from horizontal) at the mouth. `0` = mouth fires purely radial (clean omni). `<0` = upturned morning-glory bell (advanced — the deflector may overhang the reflector radially with large gaps). |
| `bend_scale` | `float` | `1.0` | Vertical stretch of the bend (deflector height/aspect). `>1` = taller. |
| `thickness` | `float` | `4.0` | Reflector wall thickness; also the deflector base thickness. |
| `n` | `int` | `300` | Meridian sample count. |
| `pillar_count` | `int \| None` | `None` | Canonical number of aerodynamic self-centering pillars across the channel. `0`/`None` = none. Their gap volume is compensated (gap widened to hold `S(s)`). |
| `standoffs` | `int \| None` | `None` | Legacy alias for `pillar_count`. |
| `standoff_width` | `float` | `3.0` | Max tangential width (mm) of each pillar mid-chord (tapers to zero at both ends). |
| `pillars_fused` | `bool \| None` | `None` | Canonical fusion flag. `True`: pillars are welded into the deflector. `False`: return a separate `pillars` body. |
| `ribs_fused` | `bool` | `True` | Legacy alias for `pillars_fused`. |
| `vert_cov_deg` | `float` | `0.0` | Vertical coverage: splays the two mouth lips apart by this angle. `0` = collimated (narrow vertical beam); larger = wider vertical dispersion. |
| `preserve_area_law` | `bool` | `True` | `True`: re-gap after splaying so `S(s)` stays exact (gentle coverage). `False`: CD flare — mouth opens past the law for stronger coverage. |
| `pillar_hole_diam` | `float` | `0.0` | Legacy/common reflector↔pillar screw diameter. Used for both sides when the split diameters below are `None`. |
| `pillar_hole_ref_diam` | `float \| None` | `None` | Reflector/flare clearance-hole diameter. Overrides `pillar_hole_diam` for the reflector side. |
| `pillar_hole_def_diam` | `float \| None` | `None` | Deflector/pillar pilot, thread, or insert-hole diameter. Overrides `pillar_hole_diam` for the pillar side. |
| `pillar_hole_pos` | `float` | `0.55` | Hole station along the pillar band, `0` = throat-side start, `1` = mouth-side end. UI exposes this as percent. |
| `pillar_hole_depth` | `float` | `4.0` | Extra depth drilled into the pillar after the cutter crosses the reflector wall. |
| `pillar_hole_head_diam` | `float` | `0.0` | Optional counterbore diameter on the reflector/flare outside. `0` disables the head pocket. |
| `pillar_hole_head_depth` | `float` | `0.0` | Optional counterbore depth into the reflector/flare wall. |
| `plan_sides` | `int` | `0` | Plan (top-view) shape of the bell: `0` = circular revolution; `≥3` = rounded regular N-gon plan (see *Polygonal plan shape*). |
| `plan_corner_radius` | `float` | `0.0` | Corner fillet (mm) of the plan polygon at the mouth. `0` = sharp corners; `≥ mouth radius` degenerates back to the circle. |

### Polygonal plan shape (`plan_sides ≥ 3`)

Gives the bell a **rounded regular N-gon footprint** (top view) instead of the
circular revolution — an aesthetic option that preserves the acoustics:

- **σ(φ)** (`_plan_sigma_dev_fn`): the plan is a rounded N-gon (vertices at
  `π/2 + k·2π/N`, fillet `plan_corner_radius`, radial function from
  `polygonal_horn.rounded_poly_radius_at_angle`) **perimeter-matched** to the
  circle — unit-perimeter core `Rc₁ = π(1−f₁)/(N·sin(π/N))`, `f₁ =
  corner_radius/Rm` clamped to `[0,1]`. Because `S = perimeter·gap`, the open
  cross-section stays exactly on the area law with the unchanged axisymmetric
  gap `h`. Faces pull in (`σ_min = Rc₁cos(π/N)+f₁ < 1`), corners poke out
  (`σ_max = Rc₁+f₁ > 1`); the UI shows both footprint diameters. At
  `f₁ = 1` the shape IS the circle (graceful degeneration).
- **Blend** (`_plan_blend`): smoothstep weight `w(t)` = 0 for meridian
  `t ≤ _PLAN_BLEND_T0 = 0.25` → the throat, the reflector's central hole and
  the **adapter handoff region stay exactly circular** (the driver-mount
  path and `omni_adapter_section_stack` are untouched); `w = 1` at the mouth.
- **Application**: an **additive centerline shift** per vertex,
  `Δr = ρ_c(station)·w(station)·(σ(φ)−1)` — `get_omni_profile` is unchanged
  (the meridian math never sees the plan). Since inner wall, outer skin and
  pillar band all shift by the same Δ at the same (station, azimuth), the gap,
  the wall thickness in each meridian half-plane, the pillar root overlap and
  tip clearance are all preserved. Implemented in `_revolve_polygon(plan_dev,
  plan_amp)`, `_sector_wedge(plan_dev_fn, plan_amp)` and the fastener cutters
  (position shifted; the cutter axis keeps the meridian normal — the small
  azimuthal wall tilt at the corners is neglected).
- Corners are sampled by the revolve rings: use a higher `rings` (Fine
  preset) for smooth plan corners.

### Vertical coverage (`vert_cov_deg > 0`)

The omni fires 360° in the horizontal plane (fixed), so directivity control is
**vertical**. Two orthogonal knobs:

- `lip_angle_deg` — vertical **aim** (where the beam points up/down).
- `vert_cov_deg` — vertical **coverage / beamwidth**.

`_splay_walls` bends the terminal portion of each wall apart by ±`vert_cov_deg`/2
(reflector lip up, deflector lip down), each rotated progressively (smoothstep,
so no kink) about its own point at `_SPLAY_T0 = 0.55`. The mouth then fans the
radial output over a vertical angle; `0` keeps the lips parallel (collimated).
The reflector's outer face is offset along the *splayed* wall normal
(`_wall_normal`) so its wall stays perpendicular-thick; with no splay this is
exactly the centerline normal, so the geometry is byte-identical to before.

**`preserve_area_law` (the splay ↔ loading trade-off).** Since `S = 2π·ρ·gap`,
opening the lips (growing the gap) fights the area law. Two modes:

- **`True` (default) — keep the area law.** After splaying, `_regap_to_area`
  re-sets the perpendicular gap about the splayed midline so `S(s)` stays exactly
  on the chosen law (throat *and* flare). The lips keep their aim but the mouth
  slot doesn't balloon; the achievable divergence is gentler (e.g. a `90°` input
  yields ≈`27°` real included angle) — usually the right call for an omni, whose
  vertical coverage should stay modest.
- **`False` — CD flare.** The splay opens the gap freely, so the area grows
  faster than `S(s)` over the last ~45% (a standard constant-directivity mouth
  flare — still smooth and strictly monotonic, never random). Gives the full
  divergence (`90°` → ≈`101°`) at the cost of a mouth that expands past the law.

Both modes leave the throat half (`t < 0.55`) exactly on the law, and both stay
watertight.

### Aerodynamic centering pillars (`pillar_count > 0`)

Each rib is a **streamlined pillar** that fills the channel band over `t ∈ [0.35,
0.95]` of the meridian (the throat tip and extreme rim are skipped so the throat
is never blocked). `_pillar_band` also pushes the band **start past the deflector
nose** — a steep / low-`fc` profile (e.g. Oblate at high `fc`) can keep the inner
wall on the axis (`low_r≈0`) well past `t=0.35`, and a pillar rooted there would
collide on the axis or take a negative radius; the start moves to the first
station where `low_r` clears `_STANDOFF_OVERLAP + 1.5 mm`. It spans the full gap
(deflector→reflector), but its
*tangential* width follows a lens taper (`_pillar_halfwidth`, `standoff_width·sin^p(π·u)`).
**Two decoupled profiles** are used on purpose:

- **`w_mm` (`sin`, `power=1`)** drives the pillar *mesh* — a slender lens with a
  sharp, low-diffraction, *printable* tip. (A `sin²` tip is so thin it re-opens
  the mesh on an STL vertex-merge round-trip.)
- **`w_comp` (`sin²`, `power=2`)** drives the axisymmetric *volume compensation*.
  Its **zero-slope onset** is what removes the visible artifact: compensating
  with the sharp `sin` profile starts the gap-widening with slope π and leaves a
  **C¹ kink — an annular step** in the channel wall right at the band edge (every
  part of the wavefront crosses it); `sin²` joins smoothly.

Because the physical pillar (`sin`) is slightly wider than the compensated
profile (`sin²`) near the band edges, a small, **smooth** area deficit remains
(≲1% at the default 3 mm width, ~2% at 4 mm) — negligible next to an annular
wall step. `_sector_wedge` takes the per-station half-angle array and sweeps the
meridian loop over `[φ−half_ang[k], φ+half_ang[k]]`; at the tapered ends the
swept loop collapses, and the resulting zero-area slivers are dropped
(`nondegenerate_faces`).

**Volume compensation.** `get_omni_profile` widens the gap *axisymmetrically* so
the total open cross-section — full annulus minus what the `pillar_count` pillars
block — still equals `S(s)`:

```
open_circ = 2π·ρ_c − pillar_count·w_comp(s)   # w_comp = smooth compensation width
h = S / open_circ                              (clamped so blockage ≤ 80%)
```

Because `w_comp → 0` at the throat/mouth, the gap there is untouched (the
exact-throat invariant still holds) and only bulges a few percent mid-band.

Each pillar's root sinks `_STANDOFF_OVERLAP = 1 mm` into the deflector body
(clean boolean weld) and its tip stops `_STANDOFF_CLEARANCE = 0.2 mm` short of
the reflector wall, so the **separately printed** deflector self-centers against
the reflector without fusing to it. Pillars are unioned onto the deflector with
trimesh's boolean engine (each is `fix_normals()`-ed so it is a valid volume);
on engine failure it falls back to concatenation (the 1 mm overlap still slices
as one part).

**Reflector↔pillar fixing holes.** When either split diameter is positive,
`build_omni_parts()` creates one hole per pillar at the pillar center azimuth.
`pillar_hole_pos` selects the meridian station inside the aerodynamic pillar
band. The cutter axis follows the local reflector normal. The reflector cutter
starts outside the flare and stops in the built-in 0.2 mm air gap before the
    pillar, while the deflector/pillar cutter starts in the same gap just before
the pillar tip and continues into the pillar by `pillar_hole_depth`. Starting in
the air gap is intentional: a pilot cutter that starts fully inside the pillar
creates an internal blind subtraction and can split compact fused pillars into
separate slicer bodies. This lets the reflector use a larger clearance hole and
the pillar/deflector use a smaller pilot/thread/insert hole.
The optional `pillar_hole_head_diam` / `pillar_hole_head_depth` counterbore is
applied only to the reflector. In the Streamlit UI these controls appear under
**Omni → Pillar fixing holes** as **Reflector hole Ø** and
**Deflector/pillar hole Ø**.

### `omni_adapter_section_stack`

```python
def omni_adapter_section_stack(P, thickness, follow_depth, neck_height, rings,
                               section_count=16) -> dict
```

Builds the exact circular section stack used by the Streamlit Omni adapter
branch. `P` is the dict returned by `get_omni_profile`. The returned dict
contains:

| Key | Meaning |
|---|---|
| `custom_pts_z` | Adapter-local Z stations. `neck_height` is the throat plane; `neck_height + follow_depth` is the handoff inside the reflector. |
| `custom_pts` | Inner airway circular sections sampled from `P["up_r"], P["up_z"]`. |
| `custom_outer_pts` | Outer reflector-wall sections sampled from `P["up_r"] + thickness·P["nrho_out"]`. |
| `custom_match_from_z` | Local Z where the adapter starts following the exact stack. |
| `adapter_length` | `neck_height + actual_follow_depth`. |
| `follow_depth` | Actual sampled depth, clamped to available reflector depth. |
| `horn_R_eq` | Area-equivalent radius at the handoff section. |

---

## Profile math — `get_omni_profile`

```python
def get_omni_profile(throat_diam, mouth_diam, fc=None, n=300,
                     profile="Exponential", lip_angle_deg=0.0,
                     bend_scale=1.0, n_pillars=None, pillar_width=0.0,
                     vert_cov_deg=0.0, preserve_area_law=True,
                     pillar_count=None) -> dict:
```

`pillar_count` / `pillar_width` drive the aerodynamic-pillar gap compensation —
see *Aerodynamic centering pillars* above. Legacy `n_pillars` is still accepted.
They widen `h` axisymmetrically so the open area stays on `S(s)`.

Returns a dict of parallel 1-D arrays (length `n`):

| Key | Meaning |
|---|---|
| `rho_c`, `z_c` | channel centerline (meridian radius, axial) |
| `h` | channel gap, **perpendicular to flow**, pillar-volume-compensated |
| `nrho`, `nz` | unit meridian normal (the gap direction) |
| `nrho_out`, `nz_out` | normal for the reflector's outer face (splay-aware; `= nrho,nz` with no splay) |
| `low_r`, `low_z` | inner / deflector-side wall = `M − h/2·N`, lip splayed by `vert_cov_deg` |
| `up_r`, `up_z` | outer / reflector-side wall = `M + h/2·N`, lip splayed by `vert_cov_deg` |
| `w_mm` | physical (`sin`) tangential width (mm) of ONE pillar per station — drives the mesh |
| `w_comp` | smooth (`sin²`) width driving the axisymmetric volume compensation |
| `pillar_count`, `n_pillars` | resolved pillar count; `n_pillars` is retained as a legacy result key |
| `pillar_i0`, `pillar_i1` | meridian index band the pillars occupy (nose-clearing) |
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
- **Conical** — radius grows linearly along the arc (`S ∝ r²`, constant
  expansion angle). The constant-directivity reference: pairs with `vert_cov_deg`
  for a directivity-first design, but loads poorly at low frequency (Kolbrek —
  a conical horn "must open up slowly" for LF loading, which it doesn't).

> Note: `Le Cléac'h` and `R-OSSE` are **not** offered here. The omni consumes
> only the *area law*, and Le Cléac'h's area law is identical to Salmon's while
> R-OSSE's value lives in its (discarded) superellipse mouth geometry — both
> would be redundant once reduced to `S(s)`.

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
- Optional `pillar_count`/`standoffs` pillars self-center the deflector against the reflector;
  with `pillar_count=0` the two parts are not mechanically tied (same as
  `radial_horn`).
- `lip_angle_deg < 0` can make the deflector overhang the reflector radially
  when the mouth gap is large (e.g. high-`fc` Exponential). `0` is the clean
  default.
