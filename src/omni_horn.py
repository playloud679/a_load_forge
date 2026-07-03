"""
Omnidirectional Compression-Driver Horn (curved axial → 360° radial expansion).

A compression driver fires *axially* into the throat at the apex; a curved
central **deflector** turns the wavefront 90° and the curved outer **reflector**
opens it to a full 360° radial mouth.  Unlike `radial_horn.py` (which uses a
crude linear deflector ramp `z = (R-Rt)·0.3`), the channel here follows a true
*curved meridian*: the flow angle eases smoothly from 90° (axial) at the throat
to `lip_angle` at the mouth, so the wall sweeps like the trumpet-bell in the
reference photo.

Geometry (the clean part):
    The channel centerline starts at radius ρ₀ = Rt/2.  With area law S(Rt)=St,
    the throat gap is h₀ = St/(2π·ρ₀) = Rt, so the *inner* wall starts at ρ=0
    (deflector nose on the axis) and the *outer* wall at ρ=Rt (the circular
    driver throat).  Throat area = π·Rt² exactly — no fudge factor.

Acoustic law (gap follows the chosen expansion profile):
    S(s) along the centerline arc length s; gap H = S / (2π·ρ_centerline)
    measured *perpendicular* to the local flow (not vertically).

Output:  omni_deflector.stl  — solid central body (nose on axis)
         omni_reflector.stl  — outer shell with central throat hole (Ø = throat)
"""

import logging
import sys
from pathlib import Path

import numpy as np
from stl import mesh

_src = str(Path(__file__).resolve().parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

from _constants import SOUND_SPEED
import _utils

logger = logging.getLogger(__name__)

_EPS = 1e-3  # avoids degenerate triangles on the Z axis

# Centering pillars (legacy UI label: standoffs) across the channel.
_STANDOFF_OVERLAP = 1.0    # mm the rib root sinks into the deflector body (clean weld)
_STANDOFF_CLEARANCE = 0.2  # mm air gap between the rib tip and the reflector wall
_STANDOFF_T0, _STANDOFF_T1 = 0.35, 0.95  # rib spans this fraction of the meridian

# Polygonal plan shape: the morph from circular starts at this meridian
# fraction, so the throat, the reflector's central hole and the adapter
# handoff region (all near t=0) stay exactly circular.
_PLAN_BLEND_T0 = 0.25


def _plan_blend(t: np.ndarray) -> np.ndarray:
    """Smoothstep weight of the plan morph along the meridian: 0 (circle) for
    t ≤ _PLAN_BLEND_T0, 1 (full plan polygon) at the mouth."""
    u = np.clip((np.asarray(t, float) - _PLAN_BLEND_T0)
                / (1.0 - _PLAN_BLEND_T0), 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def _plan_sigma_dev_fn(plan_sides: int, plan_corner_radius: float,
                       mouth_R: float):
    """Radial deviation σ(φ)−1 of the plan shape from the unit circle.

    The plan is a rounded regular N-gon (vertices at π/2 + k·2π/N, like
    `polygonal_horn`) **perimeter-matched** to the circle: with the same
    per-station perimeter the open cross-section S = perimeter·gap stays
    exactly on the area law with the unchanged axisymmetric gap `h`. Faces
    pull in (σ<1), corners poke out (σ>1); `plan_corner_radius` is the mouth
    corner fillet in mm — at ≥ mouth_R the shape degenerates back to the
    circle. Returns a callable dev(angles)->σ−1 valid at any azimuth.
    """
    from polygonal_horn import rounded_poly_radius_at_angle
    ns = int(plan_sides)
    f1 = float(np.clip(plan_corner_radius / max(mouth_R, 1e-9), 0.0, 1.0))
    # unit-perimeter core: 2n·Rc·sin(π/n) + 2π·f = 2π
    Rc1 = np.pi * (1.0 - f1) / (ns * np.sin(np.pi / ns))

    def dev(angles):
        return rounded_poly_radius_at_angle(Rc1, f1, ns, angles) - 1.0

    dev.sigma_max = Rc1 + f1                       # across corners
    dev.sigma_min = Rc1 * np.cos(np.pi / ns) + f1  # across flats
    return dev


def _pillar_band(n, low_r=None, r_safe=None):
    """[i0, i1) meridian index range the pillars occupy.

    The base range skips the throat tip and the extreme rim. When `low_r` /
    `r_safe` are given, the start is pushed past the deflector nose so the pillar
    roots stay off the axis (else adjacent pillars collide / take a negative
    radius). If the wall never lifts that far off the axis, the band is empty.
    """
    i0 = max(1, int(_STANDOFF_T0 * n))
    i1 = min(n, int(_STANDOFF_T1 * n))
    if low_r is not None and r_safe is not None:
        safe = np.nonzero(np.asarray(low_r) > r_safe)[0]
        i0 = max(i0, int(safe[0])) if safe.size else i1
    return i0, i1


_SPLAY_T0 = 0.55  # vertical-coverage lip flare starts here (fraction of meridian)


def _splay_walls(low_r, low_z, up_r, up_z, cov_deg: float, t: np.ndarray):
    """Bend the terminal portion of each wall apart by ±`cov_deg`/2 → vertical
    coverage. The reflector lip tilts up, the deflector lip down, each rotated
    (progressively, smoothstep-ramped) about its own point at `_SPLAY_T0`, so the
    mouth fans out vertically without a kink. `cov_deg = 0` is a no-op.
    """
    x = np.clip((t - _SPLAY_T0) / (1.0 - _SPLAY_T0), 0.0, 1.0)
    ramp = x * x * (3.0 - 2.0 * x)          # smoothstep (C¹ at the flare start)
    half = np.radians(cov_deg / 2.0) * ramp
    i0 = int(np.searchsorted(t, _SPLAY_T0))

    def bend(r, z, sign):
        b = sign * half
        cb, sb = np.cos(b), np.sin(b)
        dr, dz = r - r[i0], z - z[i0]
        return r[i0] + cb * dr - sb * dz, z[i0] + sb * dr + cb * dz

    up_r2, up_z2 = bend(up_r, up_z, +1.0)     # reflector lip up
    low_r2, low_z2 = bend(low_r, low_z, -1.0)  # deflector lip down
    return low_r2, low_z2, up_r2, up_z2


def _regap_to_area(low_r, low_z, up_r, up_z, s_target, i_start=0):
    """Re-set the perpendicular gap about the (splayed) midline so the channel's
    total cross-section equals `s_target` (= 2π·ρ_mid·gap) at every station from
    `i_start` on (the flare region — the throat half is left untouched).

    Keeps the splayed lip *aim* (the gap direction/midline) but restores the
    area-law gap magnitude, so a vertical-coverage splay does not balloon the
    mouth off the chosen expansion law. Returns (low_r, low_z, up_r, up_z).
    """
    low_r, low_z, up_r, up_z = (a.copy() for a in (low_r, low_z, up_r, up_z))
    sl = slice(i_start, None)
    mr, mz = 0.5 * (low_r[sl] + up_r[sl]), 0.5 * (low_z[sl] + up_z[sl])
    gr, gz = up_r[sl] - low_r[sl], up_z[sl] - low_z[sl]
    g = np.hypot(gr, gz)
    g[g < 1e-9] = 1.0
    ur, uz = gr / g, gz / g                        # unit gap direction
    ht = s_target[sl] / (2.0 * np.pi * np.maximum(mr, 1e-6))
    low_r[sl], low_z[sl] = mr - 0.5 * ht * ur, mz - 0.5 * ht * uz
    up_r[sl], up_z[sl] = mr + 0.5 * ht * ur, mz + 0.5 * ht * uz
    return low_r, low_z, up_r, up_z


def _wall_normal(r, z, nrho_ref, nz_ref):
    """Unit meridian normal of a wall curve (r, z), oriented to match a reference
    normal — used to give the splayed reflector a perpendicular-thick outer face.
    """
    tr, tz = np.gradient(r), np.gradient(z)
    tn = np.hypot(tr, tz)
    tn[tn < 1e-12] = 1.0
    tr, tz = tr / tn, tz / tn
    nr, nz = -tz, tr                          # rotate tangent +90°
    s = np.sign(nr * nrho_ref + nz * nz_ref)  # keep the outward orientation
    s[s == 0] = 1.0
    return nr * s, nz * s


def _pillar_halfwidth(n, pillar_width, i0=None, i1=None, power=1):
    """Tangential width (mm) of ONE pillar at each meridian station: a lens taper
    ``pillar_width·sin^power(π·u)`` over the band (``[i0, i1)``, default `_pillar_band`).

    Two profiles are derived from this, on purpose (see `get_omni_profile`):

    - `power=1` (``sin``) drives the pillar **mesh** — a slender lens that tapers
      to a sharp, low-diffraction, *printable* tip (a `sin²` tip is so thin it
      re-opens on an STL vertex-merge round-trip).
    - `power=2` (``sin²``) drives the axisymmetric **volume compensation** — its
      zero-slope onset lets the widened gap join the un-widened gap without a C¹
      kink (a `sin` taper starts with slope π and leaves a visible annular step
      in the channel wall). Its integral is the volume the gap widens for.
    """
    w = np.zeros(n)
    if pillar_width <= 0:
        return w
    if i0 is None or i1 is None:
        i0, i1 = _pillar_band(n)
    if i1 - i0 < 3:
        return w
    u = np.linspace(0.0, 1.0, i1 - i0)
    w[i0:i1] = pillar_width * np.sin(np.pi * u) ** power
    return w


def _circle_section(radius: float, count: int) -> np.ndarray:
    th = np.linspace(0.0, 2.0 * np.pi, int(count), endpoint=False)
    return np.column_stack([radius * np.cos(th), radius * np.sin(th)])


def omni_adapter_section_stack(
    P: dict,
    thickness: float,
    follow_depth: float,
    neck_height: float,
    rings: int,
    section_count: int = 16,
) -> dict:
    """Exact circular section stack for an Omni throat adapter weld.

    The generic circular adapter is too crude for Omni because the reflector
    outer wall immediately leaves the throat with a real flare slope. This
    helper samples the reflector inner and outer radii over the first
    ``follow_depth`` mm below the throat so ``throat_adapter.make_adapter`` can
    use the same `custom_pts` / `custom_outer_pts` overlap strategy as the
    OS-SE and R-OSSE branches.

    Returned local Z coordinates are in adapter space: ``neck_height`` is the
    throat plane and ``neck_height + follow_depth`` is the handoff plane inside
    the reflector.
    """
    follow_depth = max(0.5, float(follow_depth))
    neck_height = max(0.5, float(neck_height))
    rings = max(16, int(rings))
    section_count = max(3, int(section_count))

    up_r = np.asarray(P["up_r"], dtype=float)
    up_z = np.asarray(P["up_z"], dtype=float)
    out_r = up_r + float(thickness) * np.asarray(P["nrho_out"], dtype=float)
    out_z = up_z + float(thickness) * np.asarray(P["nz_out"], dtype=float)

    inner_z = up_z - up_z[0]
    # Use the inner-wall Z as the station coordinate for both inner and outer.
    # The reflector outer wall is a normal offset, so sampling it at the same
    # absolute Z plane can put the "outer" radius inside the inner radius on a
    # steep Omni throat. Station sampling matches the mesh engine and guarantees
    # each custom outer section encloses its inner section.
    max_depth = max(0.5, min(follow_depth, -float(np.min(inner_z))))

    def interp_radius(z_arr, r_arr, z_rel):
        order = np.argsort(z_arr)
        return float(np.interp(float(z_rel), z_arr[order], r_arr[order]))

    z_rel = -np.linspace(0.0, max_depth, section_count)
    custom_z = neck_height - z_rel
    inner_stack = np.stack([
        _circle_section(interp_radius(inner_z, up_r, z), rings) for z in z_rel
    ])
    outer_stack = np.stack([
        _circle_section(interp_radius(inner_z, out_r, z), rings) for z in z_rel
    ])

    handoff_inner = inner_stack[-1]
    handoff_area = 0.5 * abs(
        np.dot(handoff_inner[:, 0], np.roll(handoff_inner[:, 1], -1))
        - np.dot(handoff_inner[:, 1], np.roll(handoff_inner[:, 0], -1))
    )
    return {
        "custom_pts_z": custom_z,
        "custom_pts": inner_stack,
        "custom_outer_pts": outer_stack,
        "custom_match_from_z": float(neck_height),
        "adapter_length": float(neck_height + max_depth),
        "follow_depth": float(max_depth),
        "neck_height": float(neck_height),
        "horn_R_eq": float(np.sqrt(handoff_area / np.pi)),
    }


def _resolve_pillar_count(pillar_count, n_pillars=None, standoffs=None) -> int:
    """Resolve the canonical `pillar_count` plus legacy aliases.

    `n_pillars` is the older profile-level name; `standoffs` is the older
    part-generator/UI name. Keep both as aliases so saved scripts keep working,
    but reject contradictory explicit values.
    """
    values = []
    for name, value in (
        ("pillar_count", pillar_count),
        ("n_pillars", n_pillars),
        ("standoffs", standoffs),
    ):
        if value is not None:
            values.append((name, int(value)))
    if not values:
        return 0
    first_name, first_value = values[0]
    for name, value in values[1:]:
        if value != first_value:
            raise ValueError(
                f"Conflicting omni pillar counts: {first_name}={first_value}, "
                f"{name}={value}"
            )
    return max(0, first_value)


def _resolve_pillars_fused(ribs_fused=True, pillars_fused=None) -> bool:
    """Resolve canonical `pillars_fused` plus legacy `ribs_fused`.

    The default legacy value is True, so a supplied canonical value wins unless
    the legacy argument is explicitly False and contradicts it.
    """
    if pillars_fused is None:
        return bool(ribs_fused)
    if ribs_fused is False and pillars_fused is True:
        raise ValueError("Conflicting omni pillar fusion flags: ribs_fused=False, pillars_fused=True")
    return bool(pillars_fused)


# ======================================================================
#  Profile math
# ======================================================================

def _cumtrapz0(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Cumulative trapezoid integral with a leading 0 (no scipy dependency)."""
    out = np.zeros_like(y, dtype=float)
    out[1:] = np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(x))
    return out


def get_omni_profile(
    throat_diam: float,
    mouth_diam: float,
    fc: float | None = None,
    n: int = 300,
    profile: str = "Exponential",
    lip_angle_deg: float = 0.0,
    bend_scale: float = 1.0,
    n_pillars: int | None = None,
    pillar_width: float = 0.0,
    vert_cov_deg: float = 0.0,
    preserve_area_law: bool = True,
    pillar_count: int | None = None,
) -> dict:
    """
    Build the curved omni channel: centerline, gap, and the two channel walls.

    The centerline bends from axial (90° from horizontal) at the throat to
    `lip_angle_deg` at the mouth via a cosine-eased flow angle, then the
    cross-sectional area `S` is laid out along the resulting arc length using
    the chosen expansion profile.

    `vert_cov_deg` sets the **vertical coverage**: the two mouth lips are splayed
    apart by ±`vert_cov_deg`/2 over the terminal flare, so the horn fans the
    360°-radial output out over a vertical angle. `0` keeps the lips parallel
    (collimated, narrow vertical beam); `lip_angle_deg` still aims that fan
    up/down. See `_splay_walls`.

    `preserve_area_law` (default True) controls how the splay interacts with the
    expansion law. True: after splaying, the gap is re-set (`_regap_to_area`) so
    the cross-section stays exactly on `S(s)` — the lips keep their aim but the
    mouth slot doesn't balloon; coverage is gentler. False (CD flare): the splay
    opens the gap freely, so the area grows faster than `S(s)` in the terminal
    flare (standard constant-directivity mouth) for stronger coverage.

    When `pillar_count > 0`, the gap is widened (axisymmetrically) so the TOTAL open
    cross-section — full annulus minus the area the pillars block —
    still equals `S(s)`. The pillars taper to zero width at the throat/mouth
    ends, so the gap there is unchanged and the exact-throat invariant holds.

    Returns a dict of parallel 1-D arrays (all length `n`):
        rho_c, z_c   — centerline (meridian radius, axial)
        h            — channel gap (perpendicular to flow), pillar-compensated
        nrho, nz     — unit meridian normal (gap direction)
        low_r, low_z — inner / deflector-side wall  (M − h/2·N)
        up_r,  up_z  — outer / reflector-side wall   (M + h/2·N)
        w_mm         — tangential width (mm) of ONE pillar per station (0 = none)
        St, Sm       — throat and mouth cross-sectional area
    """
    pillar_count = _resolve_pillar_count(pillar_count, n_pillars=n_pillars)

    Rt = throat_diam / 2.0
    Rm = mouth_diam / 2.0
    St = np.pi * Rt ** 2

    t = np.linspace(0.0, 1.0, n)
    lip = np.radians(lip_angle_deg)

    # Flow angle from horizontal: 90° (axial) → lip, smooth (zero slope at ends).
    theta = lip + (np.pi / 2.0 - lip) * 0.5 * (1.0 + np.cos(np.pi * t))

    # Integrate unit tangents to get the centerline shape, then scale so the
    # meridian radius spans [Rt/2, Rm].  z descends from 0 (mouth below throat).
    cos_th, sin_th = np.cos(theta), np.sin(theta)
    rho_u = _cumtrapz0(cos_th, t)
    z_u = _cumtrapz0(sin_th, t)

    rho_start = Rt / 2.0
    span = rho_u[-1] if rho_u[-1] > 1e-9 else 1.0
    L = (Rm - rho_start) / span
    rho_c = rho_start + L * rho_u
    z_c = -bend_scale * L * z_u

    # True arc length of the (scaled) centerline.
    ds = np.hypot(np.diff(rho_c), np.diff(z_c))
    s = np.concatenate([[0.0], np.cumsum(ds)])

    # ---- area law S(s) -------------------------------------------------------
    if profile == "Exponential":
        m = 4.0 * np.pi * (fc or 1000.0) / SOUND_SPEED
        S = St * np.exp(m * s)
    else:
        from profile_generator import (
            get_tractrix, get_salmon, get_oblate_spheroidal_for_mouth,
        )
        if profile == "Tractrix":
            z_p, r_p = get_tractrix(throat_diam, mouth_diam, n)
        elif profile == "Salmon":
            z_p, r_p = get_salmon(throat_diam, fc or 1000.0, float(Rm - Rt), n)
        elif profile == "Oblate spheroidal":
            z_p, r_p = get_oblate_spheroidal_for_mouth(throat_diam, mouth_diam, 90.0, n)
        elif profile == "Conical":
            # Constant expansion angle → radius grows linearly along the arc
            # (S ∝ r²). The constant-directivity reference; loads poorly at LF
            # (Kolbrek). z_p is unused after the arc-length reparam below.
            z_p = np.linspace(0.0, 1.0, n)
            r_p = np.linspace(Rt, Rm, n)
        else:
            raise ValueError(f"Unknown profile: {profile}")
        S_prof = np.pi * r_p ** 2
        sn = s / s[-1] if s[-1] > 1e-9 else s
        tp = np.linspace(0.0, 1.0, len(z_p))
        S = np.interp(sn, tp, S_prof)
        S = np.maximum(S, St)  # monotone: never narrower than throat

    # ---- meridian normal (gap direction) ------------------------------------
    t_rho = np.gradient(rho_c)
    t_z = np.gradient(z_c)
    tn = np.hypot(t_rho, t_z)
    tn[tn < 1e-12] = 1.0
    t_rho /= tn
    t_z /= tn
    # Rotate tangent so N points to +ρ at the throat (axial flow → radial gap).
    nrho = -t_z
    nz = t_rho

    # ---- pillar band + area compensation ------------------------------------
    # Place the pillar band where the deflector inner wall has lifted off the
    # axis: a steep / low-fc profile can keep low_r≈0 well past t=0.35, and a
    # pillar rooted there would collide on the axis (or take a negative radius).
    # Use the uncompensated gap to locate the band, then widen the gap so the
    # TOTAL open cross-section (annulus − pillar_count·w_comp) still follows S(s).
    circ = 2.0 * np.pi * rho_c
    if pillar_count > 0 and pillar_width > 0:
        low_r0 = rho_c - 0.5 * (S / circ) * nrho     # inner wall, uncompensated
        i0p, i1p = _pillar_band(n, low_r0, _STANDOFF_OVERLAP + 1.5)
        w_mm = _pillar_halfwidth(n, pillar_width, i0p, i1p, power=1)    # mesh (sin)
        w_comp = _pillar_halfwidth(n, pillar_width, i0p, i1p, power=2)  # comp (sin²)
    else:
        i0p, i1p = _pillar_band(n)
        w_mm = w_comp = np.zeros(n)
    # Compensate with the smooth (sin²) profile so the widened gap has no C¹ kink;
    # the physical pillar is the sharper `w_mm`, so a tiny (<1%), smooth area
    # deficit remains near the band edges — negligible vs an annular wall step.
    open_circ = np.maximum(circ - pillar_count * w_comp, 0.2 * circ)  # cap blockage ≤80%
    h = S / open_circ

    low_r = np.maximum(rho_c - 0.5 * h * nrho, _EPS)
    low_z = z_c - 0.5 * h * nz
    up_r = rho_c + 0.5 * h * nrho
    up_z = z_c + 0.5 * h * nz

    # ---- vertical coverage: splay the mouth lips ----------------------------
    # `nrho_out`/`nz_out` is the normal used for the reflector's outer face; with
    # a splay it follows the bent wall (perpendicular-thick), else = centerline N.
    nrho_out, nz_out = nrho, nz
    if abs(vert_cov_deg) > 1e-9:
        low_r, low_z, up_r, up_z = _splay_walls(low_r, low_z, up_r, up_z,
                                                vert_cov_deg, t)
        if preserve_area_law:
            # Restore the area-law gap about the splayed midline (flare region
            # only): keep the lip aim, keep S(s) exact (no mouth balloon).
            i_flare = int(np.searchsorted(t, _SPLAY_T0))
            low_r, low_z, up_r, up_z = _regap_to_area(
                low_r, low_z, up_r, up_z, 2.0 * np.pi * rho_c * h, i_flare)
        low_r = np.maximum(low_r, _EPS)
        nrho_out, nz_out = _wall_normal(up_r, up_z, nrho, nz)

    return {
        "rho_c": rho_c, "z_c": z_c, "h": h, "nrho": nrho, "nz": nz,
        "nrho_out": nrho_out, "nz_out": nz_out,
        "low_r": low_r, "low_z": low_z, "up_r": up_r, "up_z": up_z,
        "w_mm": w_mm, "w_comp": w_comp,
        "pillar_count": int(pillar_count), "n_pillars": int(pillar_count),
        "pillar_i0": int(i0p), "pillar_i1": int(i1p),
        "St": float(St), "Sm": float(S[-1]),
    }


# ======================================================================
#  Solid-of-revolution helper (own engine — closed meridian, no center caps)
# ======================================================================

def _revolve_polygon(r_poly: np.ndarray, z_poly: np.ndarray, rings: int = 64,
                     align: bool = True, plan_dev: np.ndarray | None = None,
                     plan_amp: np.ndarray | None = None) -> mesh.Mesh:
    """Revolve a CLOSED 2-D meridian polygon (r, z) around the Z axis.

    `align=False` keeps the mesh in its input frame (needed when the deflector
    and reflector must stay in one common assembled frame).

    Polygonal plan (`plan_dev`/`plan_amp`, both or none): the vertex radius at
    ring azimuth j becomes ``r_i + plan_amp[i]·plan_dev[j]``. `plan_dev` is the
    per-ring shape deviation σ(φ_j)−1 and `plan_amp` the per-meridian-point
    amplitude ρ_c(station)·w(station) — an **additive centerline shift**, so
    gap and wall thickness measured in each meridian half-plane are unchanged.
    """
    n_pts = len(r_poly)
    theta = np.linspace(0.0, 2.0 * np.pi, rings, endpoint=False)
    ct, st = np.cos(theta), np.sin(theta)
    if plan_dev is None or plan_amp is None:
        dev = np.zeros(rings)
        amp = np.zeros(n_pts)
    else:
        dev = np.asarray(plan_dev, dtype=float)
        amp = np.asarray(plan_amp, dtype=float)

    n_tri = 2 * rings * (n_pts - 1)
    data = np.zeros(n_tri, dtype=mesh.Mesh.dtype)
    tri = 0
    for i in range(n_pts - 1):
        r0, r1 = r_poly[i], r_poly[i + 1]
        z0, z1 = z_poly[i], z_poly[i + 1]
        a0, a1 = amp[i], amp[i + 1]
        for j in range(rings):
            jj = (j + 1) % rings
            r0j, r0jj = r0 + a0 * dev[j], r0 + a0 * dev[jj]
            r1j, r1jj = r1 + a1 * dev[j], r1 + a1 * dev[jj]
            a = [r0j * ct[j], r0j * st[j], z0]
            b = [r1j * ct[j], r1j * st[j], z1]
            c = [r1jj * ct[jj], r1jj * st[jj], z1]
            d = [r0jj * ct[jj], r0jj * st[jj], z0]
            data["vectors"][tri] = [a, d, b]; tri += 1
            data["vectors"][tri] = [b, d, c]; tri += 1
    assert tri == n_tri

    m_obj = mesh.Mesh(data)
    if align:
        _utils.align_z_to_zero(m_obj)
    _utils.ensure_positive_volume(m_obj)
    return m_obj


# ======================================================================
#  Centering pillars (deflector-only when fused)
# ======================================================================

def _sector_wedge(low: np.ndarray, up: np.ndarray,
                  phi_c: float, half_ang: np.ndarray, a_steps: int,
                  plan_dev_fn=None, plan_amp: np.ndarray | None = None):
    """Triangulate one aerodynamic pillar: the channel band (low→up) swept over a
    tangential sector whose half-width VARIES per meridian station.

    `low`/`up` are (K,2) meridian arrays (r, z); `half_ang` is a length-K array of
    tangential half-angles. Where it tapers to 0 (leading/trailing edge) the
    swept loop collapses to a point, giving a streamlined rounded-nose lens
    planform (near-zero diffraction) instead of a bluff slab. The closed band loop is
    swept over [phi_c−half_ang[k], phi_c+half_ang[k]] and capped at both angular
    extremes → a watertight wedge. Returns (verts, faces).

    `plan_dev_fn`/`plan_amp`: polygonal-plan support — each vertex radius gets
    the same additive shift ``plan_amp[k]·(σ(angle)−1)`` applied to the walls,
    so the pillar keeps its root overlap and tip clearance.
    """
    K = len(low)
    loop = np.vstack([low, up[::-1]])          # (2K, 2) closed meridian loop
    L = len(loop)
    # Meridian station index for each loop point (low forward, then up reversed),
    # so each point's tangential half-angle follows the airfoil taper.
    kidx = np.concatenate([np.arange(K), np.arange(K)[::-1]])
    ha_loop = np.asarray(half_ang, dtype=float)[kidx]   # (L,)
    amp_loop = (np.asarray(plan_amp, dtype=float)[kidx]
                if plan_amp is not None else None)
    frac = np.linspace(-1.0, 1.0, a_steps)

    verts = np.empty((a_steps * L, 3), dtype=float)
    for a in range(a_steps):
        ang = phi_c + frac[a] * ha_loop        # (L,) per-station tangential angle
        r_a = loop[:, 0]
        if plan_dev_fn is not None and amp_loop is not None:
            r_a = r_a + amp_loop * plan_dev_fn(ang)
        verts[a * L:(a + 1) * L, 0] = r_a * np.cos(ang)
        verts[a * L:(a + 1) * L, 1] = r_a * np.sin(ang)
        verts[a * L:(a + 1) * L, 2] = loop[:, 1]

    def vid(a, l):
        return a * L + l

    faces = []
    # Lateral sweep of the closed loop.
    for a in range(a_steps - 1):
        for l in range(L):
            l2 = (l + 1) % L
            faces.append((vid(a, l), vid(a, l2), vid(a + 1, l2)))
            faces.append((vid(a, l), vid(a + 1, l2), vid(a + 1, l)))
    # Flat caps at both angular ends (quad strip between low[k] and up[k]).
    for a in (0, a_steps - 1):
        for k in range(K - 1):
            lo0, lo1 = vid(a, k), vid(a, k + 1)
            up0, up1 = vid(a, 2 * K - 1 - k), vid(a, 2 * K - 2 - k)
            faces.append((lo0, lo1, up1))
            faces.append((lo0, up1, up0))
    return verts, np.asarray(faces, dtype=np.int64)


def _mesh_to_trimesh(m: mesh.Mesh):
    import trimesh
    v = np.asarray(m.vectors, dtype=float).reshape(-1, 3)
    f = np.arange(len(v), dtype=np.int64).reshape(-1, 3)
    return trimesh.Trimesh(vertices=v, faces=f, process=True)


def _trimesh_to_mesh(tm) -> mesh.Mesh:
    tri = np.asarray(tm.triangles, dtype=float)
    data = np.zeros(len(tri), dtype=mesh.Mesh.dtype)
    data["vectors"] = tri
    return mesh.Mesh(data)


def _build_wedges(P: dict, count: int, rings: int, plan_dev_fn=None):
    """Build the `count` aerodynamic pillars as a list of watertight trimeshes.

    The tangential half-width follows `P["w_mm"]` (a `sin` taper: zero at the
    band ends → sharp low-diffraction nose/tail, max mid-band), so each pillar is
    a slender streamlined lens rather than a bluff slab. The gap it fills was
    already widened in `get_omni_profile` (via the smoother `w_comp`) to
    compensate its volume.
    Wedges are returned in the profile's design frame (no Z shift), so they sit
    correctly against the deflector/reflector built with `align=False`.
    `plan_dev_fn` applies the polygonal-plan radial shift (see `_sector_wedge`).
    """
    import trimesh

    low_r, low_z = P["low_r"], P["low_z"]
    up_r, up_z = P["up_r"], P["up_z"]
    nrho, nz = P["nrho"], P["nz"]
    rho_c = P["rho_c"]
    w_mm = P["w_mm"]
    i0, i1 = P["pillar_i0"], P["pillar_i1"]
    if i1 - i0 < 3:
        return []
    sl = slice(i0, i1)
    plan_amp_band = None
    if plan_dev_fn is not None:
        n_st = len(rho_c)
        plan_amp_band = (rho_c * _plan_blend(np.linspace(0.0, 1.0, n_st)))[sl]

    # Rib root sinks into the deflector (−N), tip stops short of the reflector.
    low_band = np.column_stack([low_r[sl] - _STANDOFF_OVERLAP * nrho[sl],
                                low_z[sl] - _STANDOFF_OVERLAP * nz[sl]])
    up_band = np.column_stack([up_r[sl] - _STANDOFF_CLEARANCE * nrho[sl],
                               up_z[sl] - _STANDOFF_CLEARANCE * nz[sl]])

    # Per-station tangential half-angle from the (airfoil-tapered) mm width.
    half_ang = 0.5 * w_mm[sl] / np.maximum(rho_c[sl], 1e-6)
    ha_max = float(half_ang.max()) if half_ang.size else 0.0
    if ha_max <= 0.0:
        return []
    a_steps = max(3, int(np.ceil(rings * (2 * ha_max) / (2 * np.pi))) + 1)

    wedges = []
    for k in range(count):
        v, f = _sector_wedge(low_band, up_band, 2.0 * np.pi * k / count,
                             half_ang, a_steps,
                             plan_dev_fn=plan_dev_fn, plan_amp=plan_amp_band)
        w = trimesh.Trimesh(vertices=v, faces=f, process=True)
        w.update_faces(w.nondegenerate_faces())   # drop zero-area knife-tip slivers
        w.remove_unreferenced_vertices()
        w.fix_normals()  # boolean union needs each input to be a coherent volume
        wedges.append(w)
    return wedges


def _union_or_concat(parts):
    import trimesh
    if len(parts) == 1:
        return parts[0]
    try:
        merged = trimesh.boolean.union(parts)
        if isinstance(merged, list):
            merged = trimesh.util.concatenate(merged)
    except Exception as exc:  # pragma: no cover - engine-dependent
        logger.warning("Boolean union failed (%s); concatenating", exc)
        merged = trimesh.util.concatenate(parts)
    # Vertex-merge only if it doesn't DEGRADE the mesh: near the tapered
    # pillar tips (especially with a polygonal plan shift) merging can weld
    # knife-edge triangles into non-manifold pinches on an otherwise
    # watertight boolean result.
    compact = merged.copy()
    compact.merge_vertices()
    if compact.is_watertight or not merged.is_watertight:
        return compact
    return merged


def _axis_cylinder(start: np.ndarray, end: np.ndarray, radius: float, sections: int):
    """Cylinder whose local Z axis runs from ``start`` to ``end``."""
    import trimesh

    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    axis = end - start
    height = float(np.linalg.norm(axis))
    if height <= 1e-9 or radius <= 0.0:
        return None
    direction = axis / height
    z_axis = np.array([0.0, 0.0, 1.0])
    cross = np.cross(z_axis, direction)
    dot = float(np.clip(np.dot(z_axis, direction), -1.0, 1.0))
    if np.linalg.norm(cross) < 1e-12:
        rot = np.eye(4)
        if dot < 0.0:
            rot[:3, :3] = np.diag([1.0, -1.0, -1.0])
    else:
        skew = np.array([
            [0.0, -cross[2], cross[1]],
            [cross[2], 0.0, -cross[0]],
            [-cross[1], cross[0], 0.0],
        ])
        rot3 = (
            np.eye(3) + skew
            + skew @ skew * ((1.0 - dot) / max(np.dot(cross, cross), 1e-12))
        )
        rot = np.eye(4)
        rot[:3, :3] = rot3
    rot[:3, 3] = 0.5 * (start + end)
    return trimesh.creation.cylinder(
        radius=float(radius), height=height, sections=max(12, int(sections)),
        transform=rot)


def _pillar_fastener_cutters(
    P: dict,
    count: int,
    thickness: float,
    reflector_hole_diam: float,
    deflector_hole_diam: float,
    hole_pos: float,
    hole_depth: float,
    head_diam: float = 0.0,
    head_depth: float = 0.0,
    sections: int = 32,
    plan_dev_fn=None,
):
    """Return ``(reflector_cutters, deflector_cutters, head_cutters)``.

    Cutters are placed at each pillar centreline azimuth and at one meridian
    station inside the pillar band. Their axes follow the local reflector normal
    (with a polygonal plan the position gets the plan radial shift; the axis
    keeps the meridian normal — the small azimuthal wall tilt is neglected).
    Reflector and deflector/pillar cutters are split so the outer flare can have
    a screw-clearance hole while the pillar/deflector has a smaller pilot or
    heat-set insert hole. The optional head cutter counterbores only the
    reflector outer skin.
    """
    count = max(0, int(count))
    reflector_hole_diam = max(0.0, float(reflector_hole_diam))
    deflector_hole_diam = max(0.0, float(deflector_hole_diam))
    if count <= 0 or max(reflector_hole_diam, deflector_hole_diam) <= 0.0:
        return [], [], []

    i0, i1 = int(P["pillar_i0"]), int(P["pillar_i1"])
    if i1 - i0 < 3:
        return [], []
    u = float(np.clip(hole_pos, 0.0, 1.0))
    idx = int(np.clip(round(i0 + u * (i1 - i0 - 1)), i0 + 1, i1 - 2))

    up_r = np.asarray(P["up_r"], dtype=float)
    up_z = np.asarray(P["up_z"], dtype=float)
    nrho = np.asarray(P["nrho_out"], dtype=float)
    nz = np.asarray(P["nz_out"], dtype=float)
    depth = max(0.5, float(hole_depth))
    ref_r = 0.5 * reflector_hole_diam
    def_r = 0.5 * deflector_hole_diam
    head_r = 0.5 * float(head_diam)
    head_depth = max(0.0, min(float(head_depth), float(thickness) + 0.5))
    reflector = []
    deflector = []
    heads = []

    rho_c = np.asarray(P["rho_c"], dtype=float)
    w_blend = _plan_blend(np.linspace(0.0, 1.0, len(rho_c)))
    for k in range(count):
        phi = 2.0 * np.pi * k / count
        cp, sp = np.cos(phi), np.sin(phi)
        r_hole = up_r[idx]
        if plan_dev_fn is not None:
            r_hole = r_hole + rho_c[idx] * w_blend[idx] * float(plan_dev_fn(phi))
        p_inner = np.array([r_hole * cp, r_hole * sp, up_z[idx]])
        normal = np.array([nrho[idx] * cp, nrho[idx] * sp, nz[idx]])
        normal /= max(float(np.linalg.norm(normal)), 1e-12)

        start = p_inner + normal * (float(thickness) + 1.0)
        # Stop the reflector cutter inside the air gap, before it reaches the
        # pillar tip. The deflector/pillar cutter starts just beyond that tip.
        ref_end = p_inner - normal * (0.5 * _STANDOFF_CLEARANCE)
        def_start = p_inner - normal * max(_STANDOFF_CLEARANCE - 0.05, 0.0)
        def_end = p_inner - normal * (_STANDOFF_CLEARANCE + depth)
        if ref_r > 0.0:
            cyl = _axis_cylinder(start, ref_end, ref_r, sections)
            if cyl is not None:
                reflector.append(cyl)
        if def_r > 0.0:
            cyl = _axis_cylinder(def_start, def_end, def_r, sections)
            if cyl is not None:
                deflector.append(cyl)

        if head_r > max(ref_r, 1e-9) and head_depth > 0.0:
            h_end = p_inner + normal * max(float(thickness) - head_depth, 0.0)
            hcyl = _axis_cylinder(start, h_end, head_r, sections)
            if hcyl is not None:
                heads.append(hcyl)
    return reflector, deflector, heads


def _difference_or_original(body, cutters, label: str):
    import trimesh

    cutters = [c for c in cutters if c is not None and not c.is_empty]
    if not cutters:
        return body
    try:
        out = trimesh.boolean.difference([body] + cutters, engine="manifold")
        if isinstance(out, list):
            out = trimesh.util.concatenate(out)
        if out is not None and not out.is_empty:
            out.remove_unreferenced_vertices()
            out.fix_normals()
            if float(out.volume) > float(body.volume) + 1e-3:
                logger.warning(
                    "Boolean difference on %s increased volume; leaving part uncut",
                    label)
                return body
            return out
    except Exception as exc:  # pragma: no cover - engine-dependent
        logger.warning("Omni pillar fastener cut failed on %s (%s); leaving part uncut",
                       label, exc)
    return body


# ======================================================================
#  Public API
# ======================================================================

def build_omni_parts(
    throat_diam: float = 25.0,
    mouth_diam: float = 200.0,
    fc: float | None = None,
    rings: int = 64,
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
) -> dict:
    """Build the omni parts as trimeshes in ONE common (assembled) frame.

    Returns ``{"deflector": tm, "reflector": tm, "pillars": tm|None}``.  When
    ``pillars_fused`` the pillars are welded into the deflector and ``pillars``
    is ``None``; otherwise the deflector is left smooth and the pillars come back as a
    separate ``pillars`` body. All meshes share the same Z frame, so the caller
    can export them assembled or translate each to ``z=0`` for printing.
    ``vert_cov_deg`` splays the mouth lips apart for vertical coverage.
    ``pillar_hole_diam > 0`` drills one adjustable reflector↔pillar fixing hole
    per pillar; ``pillar_hole_ref_diam`` and ``pillar_hole_def_diam`` override
    that legacy/common diameter independently.

    ``plan_sides ≥ 3`` gives the bell a **polygonal plan shape** (rounded
    regular N-gon seen from above, corner fillet ``plan_corner_radius`` in mm)
    instead of the circular revolution. The morph blends from an exactly
    circular throat (``t ≤ _PLAN_BLEND_T0`` — driver bore, reflector hole and
    adapter handoff untouched) to the full plan polygon at the mouth. The plan
    is perimeter-matched per station, so the open cross-section stays on the
    area law with the unchanged gap; the shift is applied to the local
    centerline only, so gap and wall thickness in each meridian half-plane are
    preserved. ``plan_corner_radius ≥ mouth radius`` degenerates back to the
    circle; ``0`` = sharp corners.
    """
    pillar_count = _resolve_pillar_count(pillar_count, standoffs=standoffs)
    pillars_fused = _resolve_pillars_fused(ribs_fused, pillars_fused)
    P = get_omni_profile(
        throat_diam=throat_diam, mouth_diam=mouth_diam, fc=fc, n=n,
        profile=profile, lip_angle_deg=lip_angle_deg, bend_scale=bend_scale,
        pillar_count=pillar_count, pillar_width=standoff_width,
        vert_cov_deg=vert_cov_deg, preserve_area_law=preserve_area_law)
    low_r, low_z = P["low_r"], P["low_z"]
    up_r, up_z = P["up_r"], P["up_z"]
    nrho_out, nz_out = P["nrho_out"], P["nz_out"]

    # ---- polygonal plan shape (optional) ------------------------------------
    plan_dev_fn = None
    ring_dev = None
    amp = None
    if int(plan_sides) >= 3:
        plan_dev_fn = _plan_sigma_dev_fn(
            plan_sides, plan_corner_radius, float(P["rho_c"][-1]))
        ring_dev = plan_dev_fn(
            np.linspace(0.0, 2.0 * np.pi, rings, endpoint=False))
        amp = P["rho_c"] * _plan_blend(np.linspace(0.0, 1.0, n))

    logger.info("Omni parts:  throat=%.0f  mouth=%.0f  fc=%s  profile=%s  "
                "pillars=%d  pillars_fused=%s  plan=%s", throat_diam,
                mouth_diam, fc, profile, pillar_count, pillars_fused,
                f"{plan_sides}-gon r={plan_corner_radius:g}"
                if plan_dev_fn is not None else "circular")

    # ---- Deflector (solid central body under the inner wall) — common frame -
    z_base = float(min(low_z.min(), up_z.min())) - thickness
    r_def = np.concatenate([low_r, [low_r[-1], _EPS, _EPS]])
    z_def = np.concatenate([low_z, [z_base, z_base, low_z[0]]])
    # Base rim follows the mouth plan; axis/closure points carry no amplitude.
    amp_def = (np.concatenate([amp, [amp[-1], 0.0, 0.0]])
               if amp is not None else None)
    deflector = _mesh_to_trimesh(_revolve_polygon(
        r_def, z_def, rings, align=False, plan_dev=ring_dev, plan_amp=amp_def))
    deflector.fix_normals()

    # ---- Reflector (outer shell, central throat hole) — common frame --------
    # Outer face offset along the wall normal (splay-aware; = centerline N when
    # there is no vertical-coverage splay).
    out_r = up_r + thickness * nrho_out
    out_z = up_z + thickness * nz_out
    r_ref = np.concatenate([up_r, out_r[::-1], [up_r[0]]])
    z_ref = np.concatenate([up_z, out_z[::-1], [up_z[0]]])
    # Inner and outer skin share the station amplitude → constant wall thickness.
    amp_ref = (np.concatenate([amp, amp[::-1], [amp[0]]])
               if amp is not None else None)
    reflector = _mesh_to_trimesh(_revolve_polygon(
        r_ref, z_ref, rings, align=False, plan_dev=ring_dev, plan_amp=amp_ref))
    reflector.fix_normals()

    pillars = None
    if pillar_count > 0:
        wedges = _build_wedges(P, pillar_count, rings, plan_dev_fn=plan_dev_fn)
        if wedges and pillars_fused:
            deflector = _union_or_concat([deflector] + wedges)
        elif wedges:
            pillars = _union_or_concat(wedges)
        ref_hole_d = (float(pillar_hole_diam) if pillar_hole_ref_diam is None
                      else float(pillar_hole_ref_diam))
        def_hole_d = (float(pillar_hole_diam) if pillar_hole_def_diam is None
                      else float(pillar_hole_def_diam))
        if wedges and max(ref_hole_d, def_hole_d) > 0.0:
            ref_cuts, def_cuts, heads = _pillar_fastener_cutters(
                P, pillar_count, thickness, ref_hole_d, def_hole_d,
                pillar_hole_pos, pillar_hole_depth,
                head_diam=pillar_hole_head_diam,
                head_depth=pillar_hole_head_depth,
                sections=max(24, rings // 2),
                plan_dev_fn=plan_dev_fn)
            reflector = _difference_or_original(reflector, ref_cuts + heads, "reflector")
            if pillars_fused:
                deflector = _difference_or_original(deflector, def_cuts, "deflector/pillars")
            elif pillars is not None:
                pillars = _difference_or_original(pillars, def_cuts, "pillars")

    return {"deflector": deflector, "reflector": reflector, "pillars": pillars}


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
):
    """Generate the deflector + reflector STLs, each Z-aligned for printing.

    Thin CLI/test wrapper over `build_omni_parts`: fuses the pillars by default,
    drops each part to Z=0, and writes `omni_deflector.stl` /
    `omni_reflector.stl` (+ `omni_pillars.stl` when pillars are separate).
    """
    parts = build_omni_parts(
        throat_diam=throat_diam, mouth_diam=mouth_diam, fc=fc, rings=rings,
        profile=profile, lip_angle_deg=lip_angle_deg, bend_scale=bend_scale,
        thickness=thickness, n=n, standoffs=standoffs,
        standoff_width=standoff_width, ribs_fused=ribs_fused,
        vert_cov_deg=vert_cov_deg, preserve_area_law=preserve_area_law,
        pillar_count=pillar_count, pillars_fused=pillars_fused,
        pillar_hole_diam=pillar_hole_diam,
        pillar_hole_ref_diam=pillar_hole_ref_diam,
        pillar_hole_def_diam=pillar_hole_def_diam,
        pillar_hole_pos=pillar_hole_pos,
        pillar_hole_depth=pillar_hole_depth,
        pillar_hole_head_diam=pillar_hole_head_diam,
        pillar_hole_head_depth=pillar_hole_head_depth,
        plan_sides=plan_sides,
        plan_corner_radius=plan_corner_radius)
    out = {}
    for name, tm in parts.items():
        if tm is None:
            continue
        tm = tm.copy()
        tm.apply_translation([0.0, 0.0, -float(tm.bounds[0, 2])])
        tm.export(f"{output_dir}/omni_{name}.stl")
        out[name] = tm
        logger.info("  %-9s watertight=%s  bodies=%d  tris=%d", name,
                    tm.is_watertight, tm.body_count, len(tm.faces))
    return out["deflector"], out["reflector"]


def _wt(m):
    try:
        return str(m.is_closed(exact=True))
    except Exception:
        return "?"


# ======================================================================
#  Standalone
# ======================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_omni_horn(throat_diam=25, mouth_diam=200, fc=600, lip_angle_deg=-10)
