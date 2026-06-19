"""
Horn Generator — pure 2-D profile math  +  shared 3-D mesh engine.

Profiles (return z_array, r_array only):
  tractrix  — z(r) = a·arcosh(a/r) − √(a²−r²);  stops at 90°
  salmon    — axisymmetric Salmon hyperbolic-exponential → radius
  lecleach  — isophase wavefront (Salmon area law + parallel wavefronts)
  oblate    — CD oblate spheroidal profile with conical asymptote
  rosse     — parametric rollback OSSE waveguide

Mesh engine (profile-agnostic):
  generate_3d_mesh_from_profile(z, r, thickness)
    → calculates normals, offsets by thickness, revolves, caps, exports STL

Usage:
    python -m src.profile_generator --throat 10 --mouth 50 --output h.stl
     python -m src.profile_generator --throat 10 --mouth 50 --fc 800 --output h.stl
    python -m src.profile_generator --throat 20 --mouth 100 --length 80 \
        --profile salmon --output h.stl
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import trimesh
from stl import mesh

_src = str(Path(__file__).resolve().parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

from _constants import SOUND_SPEED
import _utils

logger = logging.getLogger(__name__)


# ======================================================================
#  CLI
# ======================================================================

def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Horn .stl generator")
    p.add_argument("--throat", type=float, required=True)
    p.add_argument("--mouth", type=float, default=None,
                   help="Mouth diameter (tractrix / exponential / rosse)")
    p.add_argument("--fc", type=float, default=None,
                   help="Cutoff frequency in Hz (exponential / salmon)")
    p.add_argument("--length", type=float, default=None,
                   help="Axial length in mm (salmon / oblate)")
    p.add_argument("--coverage", type=float, default=90.0,
                   help="Total coverage angle in degrees (oblate / conical / rosse)")
    p.add_argument("--T", type=float, default=0.707,
                   help="Salmon flare parameter T (0=catenoidal, <1=cosh, 1=exponential, >1=sinh)")
    p.add_argument("--max-angle", type=float, default=160.0,
                   help="Termination angle in degrees (lecleach only, 90-180, default 160)")
    p.add_argument("--complete-rollback", action="store_true",
                   help="Extend lecleach/rosse lips with an inward return curl")
    p.add_argument("--rollback-angle", type=float, default=330.0,
                   help="Final tangent angle for --complete-rollback (degrees from +Z)")
    p.add_argument("--profile",
                   choices=["auto", "tractrix", "salmon", "iwata", "lecleach", "oblate", "conical", "rosse"],
                   default="auto")
    p.add_argument("--thickness", type=float, default=4.0)
    p.add_argument("--segments", type=int, default=300)
    p.add_argument("--rings", type=int, default=64)
    p.add_argument("--output", type=str, required=True)
    return p.parse_args(args)


# ======================================================================
#  2-D profile mathematics  —  return (z_array, r_array) only
# ======================================================================

# ---- Tractrix (FROZEN — do not modify) --------------------------------

def get_tractrix(throat: float, mouth: float, n: int
                 ) -> tuple[np.ndarray, np.ndarray]:
    """
    Pure tractrix curve  (Z, R) from throat (z=0) to mouth.

        z(r) = a·arcosh(a/r) − √(a²−r²)

    The curve stops exactly when the tangent is horizontal (90° from Z-axis).
    """
    rt = throat / 2.0
    a  = mouth / 2.0
    r  = np.linspace(rt, a, n)
    raw = a * np.arccosh(a / np.maximum(r, 1e-12)) - np.sqrt(
        np.maximum(a * a - r * r, 0.0)
    )
    z = raw[0] - raw
    return z, r


# ---- Exponential -------------------------------------------------------

def get_exponential(throat: float, mouth: float, fc: float, n: int
                    ) -> tuple[np.ndarray, np.ndarray]:
    """
    Pure exponential horn.

        S(z) = S_t · exp(m · z),   m = 4π·fc / c
        R(z) = (throat/2) · exp(m/2 · z)

    Length is derived so that R(L) = mouth/2.
    Returns (z, r) — same interface as get_tractrix.
    """
    m = 4.0 * np.pi * fc / SOUND_SPEED
    L = 2.0 / m * np.log(mouth / throat)
    z = np.linspace(0.0, L, n)
    r = (throat / 2.0) * np.exp(m / 2.0 * z)
    return z, r


# ---- Oblate spheroidal --------------------------------------------------

def get_oblate_spheroidal(
    throat: float,
    coverage_angle: float,
    length: float,
    n: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Constant-directivity oblate spheroidal waveguide profile.

    The wall follows the hyperbolic/oblate law

        r(x) = sqrt(r0^2 + (x * tan(theta))^2)

    where r0 is the throat radius and theta is half of the requested total
    coverage angle. The derivative is zero at x=0, so the throat starts parallel
    to the acoustic axis, and the far-field slope tends to tan(theta), giving a
    conical asymptote for constant-directivity loading.
    """
    rt = throat / 2.0

    if throat <= 0 or length <= 0:
        raise ValueError("throat and length must be positive")
    if not 0.0 < coverage_angle < 180.0:
        raise ValueError("coverage_angle must be between 0 and 180 degrees")

    theta = np.radians(coverage_angle / 2.0)
    z = np.linspace(0.0, length, n)
    r = np.sqrt(rt * rt + (z * np.tan(theta)) ** 2)
    return z, r


def get_oblate_spheroidal_for_mouth(
    throat: float,
    mouth: float,
    coverage_angle: float,
    n: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Constant-directivity oblate profile solved to hit a target mouth diameter.

    This is a convenience wrapper around get_oblate_spheroidal(): length is
    solved from mouth radius and half-coverage angle.
    """
    rt = throat / 2.0
    rm = mouth / 2.0
    if mouth <= throat:
        raise ValueError("mouth must be greater than throat")
    if not 0.0 < coverage_angle < 180.0:
        raise ValueError("coverage_angle must be between 0 and 180 degrees")

    theta = np.radians(coverage_angle / 2.0)
    length = np.sqrt(max(0.0, rm * rm - rt * rt)) / np.tan(theta)
    return get_oblate_spheroidal(throat, coverage_angle, length, n)


def get_oblate_spheroidal_asymmetric(
    throat_w: float,
    throat_h: float,
    coverage_h: float,
    coverage_v: float,
    length: float,
    n: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Asymmetric constant-directivity oblate profile.

    Horizontal and vertical axes are evaluated independently with the same
    oblate CD law, producing diameters (w, h) that can loft to an elliptical or
    rectangular waveguide section:

        w(x) = 2 * sqrt((throat_w/2)^2 + (x*tan(coverage_h/2))^2)
        h(x) = 2 * sqrt((throat_h/2)^2 + (x*tan(coverage_v/2))^2)
    """
    if throat_w <= 0 or throat_h <= 0 or length <= 0:
        raise ValueError("throat_w, throat_h and length must be positive")
    if not 0.0 < coverage_h < 180.0 or not 0.0 < coverage_v < 180.0:
        raise ValueError("coverage angles must be between 0 and 180 degrees")

    z = np.linspace(0.0, length, n)
    th = np.radians(coverage_h / 2.0)
    tv = np.radians(coverage_v / 2.0)
    w = 2.0 * np.sqrt((throat_w / 2.0) ** 2 + (z * np.tan(th)) ** 2)
    h = 2.0 * np.sqrt((throat_h / 2.0) ** 2 + (z * np.tan(tv)) ** 2)
    return z, w, h


# ---- Conical (constant-directivity baseline) -----------------------------

def get_conical(
    throat: float,
    coverage_angle: float,
    length: float,
    n: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Conical horn — the constant-directivity reference shape.

        r(x) = r0 + x * tan(theta),   theta = coverage_angle / 2

    A straight wall from the throat at the half-coverage angle. Unlike the oblate
    profile the throat slope is non-zero (a sharp cone), so directivity is set
    purely by the wall angle. Same (throat, coverage, length) interface as
    get_oblate_spheroidal, so it drops into the same dispatch. Returns (z, r).
    """
    if throat <= 0 or length <= 0:
        raise ValueError("throat and length must be positive")
    if not 0.0 < coverage_angle < 180.0:
        raise ValueError("coverage_angle must be between 0 and 180 degrees")
    rt = throat / 2.0
    theta = np.radians(coverage_angle / 2.0)
    z = np.linspace(0.0, length, n)
    r = rt + z * np.tan(theta)
    return z, r


# ---- R-OSSE (rollback OSSE waveguide, Marcel Batík) ----------------------

def _resample_profile_by_arclength(
    z: np.ndarray,
    r: np.ndarray,
    n: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Resample a possibly non-monotonic meridian by chord length."""
    z = np.asarray(z, float)
    r = np.asarray(r, float)
    if n <= 2 or len(z) <= 2:
        return z, r
    ds = np.hypot(np.diff(z), np.diff(r))
    s = np.concatenate([[0.0], np.cumsum(ds)])
    if s[-1] <= 1e-12:
        return np.full(n, z[0]), np.full(n, r[0])
    s_new = np.linspace(0.0, s[-1], n)
    return np.interp(s_new, s, z), np.interp(s_new, s, r)


def complete_rollback_profile(
    z: np.ndarray,
    r: np.ndarray,
    n: int | None = None,
    target_angle: float = 330.0,
    curl_scale: float = 0.30,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Extend a rolled-back meridian with an inward return curl.

    The base Le Cléac'h and R-OSSE formulae stop at the acoustic rollback lip:
    axial ``z`` has already turned back, but radius is still at (or near) its
    largest value. This helper appends a smooth circular-arc continuation whose
    tangent starts at the profile's last tangent and ends at ``target_angle``.
    The default produces a complete-looking lip while leaving the airway profile
    unchanged up to the original endpoint.
    """
    z = np.asarray(z, float)
    r = np.asarray(r, float)
    if z.ndim != 1 or r.ndim != 1 or len(z) != len(r) or len(z) < 3:
        raise ValueError("z and r must be same-length 1-D arrays with at least 3 points")
    if curl_scale <= 0.0:
        raise ValueError("curl_scale must be positive")

    out_n = int(n or len(z))
    dz = float(z[-1] - z[-3])
    dr = float(r[-1] - r[-3])
    theta0 = float(np.arctan2(dr, dz))
    while theta0 < 0.0:
        theta0 += 2.0 * np.pi

    # Ordinary profiles are not rolled back enough to define a return curl.
    if theta0 < np.pi / 2.0:
        return _resample_profile_by_arclength(z, r, out_n)

    theta1 = np.radians(target_angle)
    while theta1 <= theta0 + np.radians(5.0):
        theta1 += 2.0 * np.pi

    extra_n = max(24, out_n // 4)
    theta = np.linspace(theta0, theta1, extra_n + 1)[1:]

    r_min = max(float(r[0]) * 1.15, 0.5)
    denom = np.cos(theta1) - np.cos(theta0)
    if denom > 1e-9:
        max_curl_r = 0.90 * max(float(r[-1]) - r_min, 1e-6) / denom
    else:
        max_curl_r = float(r[-1])
    curl_radius = min(float(r[-1]) * curl_scale, max_curl_r)

    # Keep the added return curl above the throat plane.  Le Cléac'h profiles
    # can have a high rollback lip; a large target angle such as 330 degrees
    # otherwise drives part of the appended arc below z[0].  The mesh engine
    # flattens the throat at z[0], so allowing that under-run creates a large
    # crushed cap in the generated solid.
    min_sin = min(float(np.sin(theta0)), float(np.sin(theta1)))
    k = np.ceil((theta0 - 1.5 * np.pi) / (2.0 * np.pi))
    theta_min_sin = 1.5 * np.pi + 2.0 * np.pi * k
    if theta0 <= theta_min_sin <= theta1:
        min_sin = -1.0
    min_z_delta = min_sin - float(np.sin(theta0))
    if min_z_delta < -1e-9:
        z_room = max(float(z[-1] - z[0]), 0.0)
        curl_radius = min(curl_radius, z_room / -min_z_delta)

    if curl_radius <= 1e-9:
        return _resample_profile_by_arclength(z, r, out_n)

    z_ext = z[-1] + curl_radius * (np.sin(theta) - np.sin(theta0))
    r_ext = r[-1] + curl_radius * (np.cos(theta0) - np.cos(theta))
    z_full = np.concatenate([z, z_ext])
    r_full = np.concatenate([r, r_ext])
    return _resample_profile_by_arclength(z_full, r_full, out_n)

def get_rosse(
    throat: float,
    mouth: float,
    coverage_angle: float,
    n: int,
    throat_angle: float = 15.0,
    k: float = 1.8,
    r: float = 0.3,
    m: float = 0.8,
    b: float = 0.3,
    q: float = 3.7,
    complete_rollback: bool = False,
    rollback_angle: float = 330.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    R-OSSE waveguide — rollback Oblate-Spheroidal-Superellipse (Marcel Batík).

    Faithful implementation of the published R-OSSE parametric formulae
    (at-horns.eu, "R-OSSE Waveguide" rev.7). A modern constant-directivity
    waveguide whose mouth rolls back smoothly into free space (so the meridian
    folds: z is NOT monotone near the mouth — like the Le Cléac'h roll-back).

        c1 = (k·r0)²,  c2 = 2·k·r0·tan(a0),  c3 = tan²(a)
        L  = [√(c2² − 4·c3·(c1 − (R + r0(k−1))²)) − c2] / (2·c3)
        x(t) = L[√(r²+m²) − √(r²+(t−m)²)] + bL[√(r²+(1−m)²) − √(r²+m²)]·t²
        y(t) = (1−t^q)[√(c1 + c2·L·t + c3·L²·t²) + r0(1−k)]
               + t^q[R + L(1 − √(1 + c3·(t−1)²))]

    where r0 = throat/2 (so y(0)=r0, x(0)=0), R = mouth/2 (outer radius), and the
    half-angles a = coverage_angle/2, a0 = throat_angle/2 enter as documented
    ("nominal ×0.5"). Shape factors k/r/m/b/q default to Batík's ST260 sample.
    Returns (z, r).
    """
    if throat <= 0 or mouth <= 0:
        raise ValueError("throat and mouth must be positive")
    if mouth <= throat:
        raise ValueError("mouth must be greater than throat")
    if not 0.0 < coverage_angle < 180.0:
        raise ValueError("coverage_angle must be between 0 and 180 degrees")
    if not 0.0 <= throat_angle < 180.0:
        raise ValueError("throat_angle must be between 0 and 180 degrees")
    if n < 2:
        raise ValueError("n must be at least 2")
    if k <= 0.0 or r <= 0.0 or q <= 0.0:
        raise ValueError("k, r and q must be positive")
    if not 0.0 <= m <= 1.0:
        raise ValueError("m must be between 0 and 1")

    r0 = throat / 2.0
    R = mouth / 2.0
    a = np.radians(coverage_angle / 2.0)
    a0 = np.radians(throat_angle / 2.0)

    c1 = (k * r0) ** 2
    c2 = 2.0 * k * r0 * np.tan(a0)
    c3 = np.tan(a) ** 2

    disc = c2 ** 2 - 4.0 * c3 * (c1 - (R + r0 * (k - 1.0)) ** 2)
    if disc < 0:
        raise ValueError("R-OSSE: no real length solution (check mouth/coverage/k)")
    L = (np.sqrt(disc) - c2) / (2.0 * c3)

    t = np.linspace(0.0, 1.0, n)
    x = (L * (np.sqrt(r ** 2 + m ** 2) - np.sqrt(r ** 2 + (t - m) ** 2))
         + b * L * (np.sqrt(r ** 2 + (1.0 - m) ** 2) - np.sqrt(r ** 2 + m ** 2)) * t ** 2)
    y = ((1.0 - t ** q) * (np.sqrt(c1 + c2 * L * t + c3 * L ** 2 * t ** 2) + r0 * (1.0 - k))
         + t ** q * (R + L * (1.0 - np.sqrt(1.0 + c3 * (t - 1.0) ** 2))))
    if complete_rollback:
        return complete_rollback_profile(x, y, n, target_angle=rollback_angle)
    return x, y


# ---- Salmon (axisymmetric) -----------------------------------------------

def get_salmon(throat: float, fc: float, length: float, n: int,
               T: float = 0.707) -> tuple[np.ndarray, np.ndarray]:
    """
    Axisymmetric Salmon / Hyperbolic-Exponential horn.

        S(x) = S_t · (cosh(x/x₀) + T · sinh(x/x₀))²
        R(x) = √(S(x)/π)
        x₀   = c / (2π·fc)

    T: Hornresp-compatible flare parameter.
       0 = catenoidal (cosh²),  <1 = cosh-dominant,
       1 = exponential (e^{2x/x₀}),  >1 = sinh-dominant.
    Default T=0.707 is the classical Hypex alignment (used by Iwata and Hornresp "Le Cléac'h").
    """
    rt = throat / 2.0
    x0 = SOUND_SPEED / (2.0 * np.pi * fc)

    x = np.linspace(0, length, n)
    ch = np.cosh(x / x0)
    sh = np.sinh(x / x0)
    s = np.pi * rt * rt * (ch + T * sh) ** 2
    r = np.sqrt(s / np.pi)
    return x, r


# ---- Iwata preset (Salmon T=0.707) ---------------------------------------

def get_iwata(throat: float, fc: float, length: float, n: int,
              ) -> tuple[np.ndarray, np.ndarray]:
    """Iwata horn: Salmon hyperbolic-exponential with T=0.707 (classic Hypex)."""
    return get_salmon(throat, fc, length, n, T=0.707)


# ---- Le Cléac'h (isophase wavefront) ------------------------------------

from scipy.integrate import solve_ivp


def get_lecleach(throat: float, fc: float, n: int,
                 T: float = 0.707,
                 max_angle: float = 160.0,
                 complete_rollback: bool = False,
                 rollback_angle: float = 330.0) -> tuple[np.ndarray, np.ndarray]:
    """
    Le Cléac'h isophase wavefront horn — Salmon area law + parallel wavefronts.

    Uses the Salmon/Hypex expansion law and integrates the isophase wavefront
    ODE to produce a profile with rolled-back mouth (parallel wavefronts).

        S(s) = S_t · (cosh(s/x₀) + T · sinh(s/x₀))²    (area law)
        cosα = 2πr² / S(s) − 1                           (wavefront curvature)
        dr/ds = sinα ,  dz/ds = cosα                     (wall follows normal)

    Terminates when the wall tangent angle reaches *max_angle* (default 160°).
    Practical range: 90° (gentle roll-back) to 180° (full roll-back, mouth
    curls back toward throat). J.M. Le Cléac'h recommends 160°-180°.
    """
    rt = throat / 2.0
    x0 = SOUND_SPEED / (2.0 * np.pi * fc)
    S_t = np.pi * rt ** 2

    def _area(s):
        ch = np.cosh(s / x0)
        sh = np.sinh(s / x0)
        return S_t * (ch + T * sh) ** 2

    def _ode(s, y):
        r, z = y
        S = _area(s)
        ca = 2.0 * np.pi * r**2 / S - 1.0
        ca = max(-1.0, min(1.0, ca))
        sa = np.sqrt(max(0.0, 1.0 - ca**2))
        return [sa, ca]

    target_cos = np.cos(np.radians(max_angle))

    def _event(s, y):
        r, z = y
        S = _area(s)
        ca = 2.0 * np.pi * r**2 / S - 1.0
        ca = max(-1.0, min(1.0, ca))
        return ca - target_cos
    _event.terminal = True
    _event.direction = -1

    # The termination angle, not an arbitrary axial length, defines the mouth.
    sol = solve_ivp(_ode, (0, 50000.0), [rt, 0.0],
                    method='RK45', events=_event, max_step=0.5,
                    rtol=1e-9, atol=1e-9)

    s_arr = sol.t
    r_arr, z_arr = sol.y

    if len(s_arr) > 1:
        s_new = np.linspace(0, s_arr[-1], n)
        r = np.interp(s_new, s_arr, r_arr)
        z = np.interp(s_new, s_arr, z_arr)
    else:
        r = np.full(n, rt)
        z = np.zeros(n)

    if complete_rollback:
        return complete_rollback_profile(z, r, n, target_angle=rollback_angle)
    return z, r


# ======================================================================
#  3-D mesh engine  —  universal, profile-agnostic
# ======================================================================

def generate_3d_mesh_from_profile(
    z_i: np.ndarray,
    r_i: np.ndarray,
    thickness: float = 4.0,
    rings: int = 64,
    output_path: str | None = None,
) -> mesh.Mesh:
    """
    Take ANY valid 2-D profile (z_i, r_i) and produce a watertight STL
    with uniform *thickness* wall applied along the mathematical normal.

    Steps:
      1. Compute unit normals via finite-difference gradient.
      2. Offset inner profile by *thickness* along the normal → outer profile
         (true parallel offset = constant perpendicular wall thickness).
      3. Revolve both profiles about Z; cap top and bottom annuli.
      4. Slice the throat base flat (constant thickness ⇒ slanted raw base).
      5. Save to *output_path* and return the Mesh.
    """
    n_pts = len(z_i)

    # ---- 1. Normals -------------------------------------------------------
    nml = _utils.compute_profile_normals(z_i, r_i)

    # ---- 2. Outer profile -------------------------------------------------
    # True parallel offset along the meridian normal. For a body of revolution
    # the 3-D surface normal lies in the meridian plane, so this gives a wall of
    # *constant* perpendicular thickness everywhere (a real 3-D offset). The
    # throat base is flattened later by a planar cut rather than by shifting the
    # whole outer surface (which would taper the wall toward the mouth).
    z_o = z_i + nml[:, 0] * thickness
    r_o = r_i + nml[:, 1] * thickness
    theta = np.linspace(0, 2 * np.pi, rings, endpoint=False)
    ct, st = np.cos(theta), np.sin(theta)

    V_o = np.zeros((n_pts, rings, 3))
    V_o[:, :, 0] = r_o[:, np.newaxis] * ct[np.newaxis, :]
    V_o[:, :, 1] = r_o[:, np.newaxis] * st[np.newaxis, :]
    V_o[:, :, 2] = z_o[:, np.newaxis]

    V_i = np.zeros((n_pts, rings, 3))
    V_i[:, :, 0] = r_i[:, np.newaxis] * ct[np.newaxis, :]
    V_i[:, :, 1] = r_i[:, np.newaxis] * st[np.newaxis, :]
    V_i[:, :, 2] = z_i[:, np.newaxis]

    I = np.arange(n_pts - 1)[:, np.newaxis]
    J = np.arange(rings)[np.newaxis, :]
    JJ = (J + 1) % rings

    # Outer wall
    a_o = V_o[I, J]
    b_o = V_o[I + 1, J]
    c_o = V_o[I + 1, JJ]
    d_o = V_o[I, JJ]

    tri_o_1 = np.stack([a_o, d_o, b_o], axis=-2).reshape(-1, 3, 3)
    tri_o_2 = np.stack([b_o, d_o, c_o], axis=-2).reshape(-1, 3, 3)

    # Inner wall
    a_i = V_i[I, J]
    b_i = V_i[I + 1, J]
    c_i = V_i[I + 1, JJ]
    d_i = V_i[I, JJ]

    tri_i_1 = np.stack([a_i, b_i, d_i], axis=-2).reshape(-1, 3, 3)
    tri_i_2 = np.stack([b_i, c_i, d_i], axis=-2).reshape(-1, 3, 3)

    # Bottom annulus
    a_b = V_i[0, J]
    b_b = V_o[0, J]
    c_b = V_o[0, JJ]
    d_b = V_i[0, JJ]

    tri_b_1 = np.stack([a_b, d_b, c_b], axis=-2).reshape(-1, 3, 3)
    tri_b_2 = np.stack([a_b, c_b, b_b], axis=-2).reshape(-1, 3, 3)

    # Top annulus
    a_t = V_i[-1, J]
    b_t = V_o[-1, J]
    c_t = V_o[-1, JJ]
    d_t = V_i[-1, JJ]

    tri_t_1 = np.stack([a_t, b_t, c_t], axis=-2).reshape(-1, 3, 3)
    tri_t_2 = np.stack([a_t, c_t, d_t], axis=-2).reshape(-1, 3, 3)

    # Concatenate all triangles
    all_vectors = np.concatenate([
        tri_o_1, tri_o_2,
        tri_i_1, tri_i_2,
        tri_b_1, tri_b_2,
        tri_t_1, tri_t_2
    ], axis=0)

    # ---- 3. Watertight solid via trimesh ---------------------------------
    tri_pts = all_vectors.reshape(-1, 3)
    faces = np.arange(len(tri_pts)).reshape(-1, 3)
    tm = trimesh.Trimesh(vertices=tri_pts, faces=faces, process=True)
    tm.merge_vertices()

    # ---- 4. Flatten the throat base ---------------------------------------
    # The constant-thickness offset leaves the outer throat rim at a different Z
    # than the inner rim, so the raw base is slanted. Slice it flat at the higher
    # of the two rims and cap → a planar throat face, while the wall stays uniform
    # thickness everywhere else.
    base_z = max(float(z_i[0]), float(z_o[0]))
    sliced = tm.slice_plane([0.0, 0.0, base_z], [0.0, 0.0, 1.0], cap=True)
    if sliced is not None and not sliced.is_empty:
        tm = sliced
    tm.fix_normals()

    # ---- 5. Save / return -------------------------------------------------
    if output_path:
        tm.export(output_path)
        logger.info("Exported: %s  (%d triangles)", output_path, len(tm.faces))

    data = np.zeros(len(tm.faces), dtype=mesh.Mesh.dtype)
    data["vectors"] = tm.triangles
    return mesh.Mesh(data)


def _elliptical_parallel_offset_vertices(
    z_i: np.ndarray,
    rx_i: np.ndarray,
    ry_i: np.ndarray,
    thickness: float,
    rings: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return inner and true parallel-offset outer elliptical loft vertices.

    The offset follows the full 3-D surface normal, including its axial
    component. This preserves wall thickness through roll-back regions where
    a radial-only ``rx + thickness, ry + thickness`` offset collapses.
    """
    theta = np.linspace(0.0, 2.0 * np.pi, rings, endpoint=False)
    ct, st = np.cos(theta), np.sin(theta)

    V_i = np.zeros((len(z_i), rings, 3))
    V_i[:, :, 0] = rx_i[:, np.newaxis] * ct[np.newaxis, :]
    V_i[:, :, 1] = ry_i[:, np.newaxis] * st[np.newaxis, :]
    V_i[:, :, 2] = z_i[:, np.newaxis]

    dz = np.gradient(z_i)
    drx = np.gradient(rx_i)
    dry = np.gradient(ry_i)

    # dS/dtheta × dS/du. At the throat its XY components point outward;
    # through a roll-back they rotate continuously with the wall.
    normals = np.empty_like(V_i)
    normals[:, :, 0] = ry_i[:, None] * ct[None, :] * dz[:, None]
    normals[:, :, 1] = rx_i[:, None] * st[None, :] * dz[:, None]
    normals[:, :, 2] = -(
        rx_i[:, None] * dry[:, None] * st[None, :] ** 2
        + ry_i[:, None] * drx[:, None] * ct[None, :] ** 2
    )
    norm = np.linalg.norm(normals, axis=2, keepdims=True)
    norm[norm < 1e-12] = 1.0
    normals /= norm

    return V_i, V_i + thickness * normals


def generate_elliptical_3d_mesh_from_profiles(
    z_i: np.ndarray,
    rx_i: np.ndarray,
    ry_i: np.ndarray,
    thickness: float = 4.0,
    rings: int = 96,
    output_path: str | None = None,
) -> mesh.Mesh:
    """
    Build a watertight elliptical-section horn from independent X/Y radii.

    This supports asymmetric oblate CD waveguides whose horizontal and vertical
    coverages differ. Each slice is an ellipse:

        x = rx(z) * cos(phi),  y = ry(z) * sin(phi)

    The outer wall is offset by *thickness* along the full 3-D surface normal,
    preserving constant wall thickness through steep and roll-back regions.
    This is intentionally a geometric elliptical loft, distinct from the
    rectangular W/H loft used by rectangular_horn.py.
    """
    z_i = np.asarray(z_i, dtype=float)
    rx_i = np.asarray(rx_i, dtype=float)
    ry_i = np.asarray(ry_i, dtype=float)

    if not (len(z_i) == len(rx_i) == len(ry_i) > 1):
        raise ValueError("z_i, rx_i and ry_i must have the same length > 1")
    if np.any(rx_i <= 0) or np.any(ry_i <= 0):
        raise ValueError("ellipse radii must be positive")

    n_pts = len(z_i)
    V_i, V_o = _elliptical_parallel_offset_vertices(
        z_i, rx_i, ry_i, thickness, rings)

    I = np.arange(n_pts - 1)[:, np.newaxis]
    J = np.arange(rings)[np.newaxis, :]
    JJ = (J + 1) % rings

    a_o = V_o[I, J]
    b_o = V_o[I + 1, J]
    c_o = V_o[I + 1, JJ]
    d_o = V_o[I, JJ]
    tri_o_1 = np.stack([a_o, d_o, b_o], axis=-2).reshape(-1, 3, 3)
    tri_o_2 = np.stack([b_o, d_o, c_o], axis=-2).reshape(-1, 3, 3)

    a_i = V_i[I, J]
    b_i = V_i[I + 1, J]
    c_i = V_i[I + 1, JJ]
    d_i = V_i[I, JJ]
    tri_i_1 = np.stack([a_i, b_i, d_i], axis=-2).reshape(-1, 3, 3)
    tri_i_2 = np.stack([b_i, c_i, d_i], axis=-2).reshape(-1, 3, 3)

    a_b = V_i[0, J]
    b_b = V_o[0, J]
    c_b = V_o[0, JJ]
    d_b = V_i[0, JJ]
    tri_b_1 = np.stack([a_b, d_b, c_b], axis=-2).reshape(-1, 3, 3)
    tri_b_2 = np.stack([a_b, c_b, b_b], axis=-2).reshape(-1, 3, 3)

    a_t = V_i[-1, J]
    b_t = V_o[-1, J]
    c_t = V_o[-1, JJ]
    d_t = V_i[-1, JJ]
    tri_t_1 = np.stack([a_t, b_t, c_t], axis=-2).reshape(-1, 3, 3)
    tri_t_2 = np.stack([a_t, c_t, d_t], axis=-2).reshape(-1, 3, 3)

    all_vectors = np.concatenate([
        tri_o_1, tri_o_2,
        tri_i_1, tri_i_2,
        tri_b_1, tri_b_2,
        tri_t_1, tri_t_2,
    ], axis=0)

    tri_pts = all_vectors.reshape(-1, 3)
    faces = np.arange(len(tri_pts)).reshape(-1, 3)
    tm = trimesh.Trimesh(vertices=tri_pts, faces=faces, process=True)
    tm.merge_vertices()

    # Flatten the throat base (same invariant as the axisymmetric engine):
    # the 3-D normal offset pushes the outer throat rim below z_i[0] wherever
    # the throat expands, so the raw base ring is slanted and mesh z_min sits
    # under the profile origin. Anything anchored to mesh z_min (embedded
    # throat adapter, flange Z offsets) then lands below the profile station
    # it was computed for — a visible step at the adapter↔flare junction.
    base_z = max(float(z_i[0]), float(np.max(V_o[0, :, 2])))
    sliced = tm.slice_plane([0.0, 0.0, base_z], [0.0, 0.0, 1.0], cap=True)
    if sliced is not None and not sliced.is_empty:
        tm = sliced
    tm.fix_normals()

    if output_path:
        tm.export(output_path)
        logger.info("Exported: %s  (%d triangles)", output_path, len(tm.faces))

    data = np.zeros(len(tm.faces), dtype=mesh.Mesh.dtype)
    data["vectors"] = tm.triangles
    return mesh.Mesh(data)


# ======================================================================
#  Dispatch
# ======================================================================

def resolve_profile(args: argparse.Namespace) -> str:
    if args.profile != "auto":
        return args.profile
    if args.length is not None and args.profile == "oblate":
        return "oblate"
    if args.length is not None and args.fc is not None:
        return "salmon"
    if args.fc is not None:
        return "exponential"
    if args.mouth is not None:
        return "tractrix"
    raise ValueError("Specify --mouth, --fc, or --length")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    try:
        name = resolve_profile(args)

        # --- 2-D profile ---------------------------------------------------
        if name == "tractrix":
            if args.mouth is None:
                raise ValueError("--mouth required for tractrix")
            logger.info("Tractrix: throat=%s  mouth=%s", args.throat, args.mouth)
            z, r = get_tractrix(args.throat, args.mouth, args.segments)
            fc = SOUND_SPEED / (np.pi * args.mouth)
            logger.info("Length: %.1f mm  Fc: %.0f Hz  (tangent horizontal)", z[-1], fc)

        elif name == "exponential":
            if args.fc is None:
                raise ValueError("--fc required for exponential")
            logger.info("Exponential: throat=%s  Fc=%s Hz", args.throat, args.fc)
            z, r = get_exponential(args.throat, args.mouth or args.throat*2, args.fc, args.segments)
            logger.info("Mouth ø: %.1f mm  Length: %.1f mm", r.max() * 2, z[-1])

        elif name == "salmon":
            if args.fc is None or args.length is None:
                raise ValueError("--fc and --length required for salmon")
            logger.info("Salmon: throat=%s  Fc=%s  length=%s  T=%s",
                        args.throat, args.fc, args.length, args.T)
            z, r = get_salmon(args.throat, args.fc, args.length, args.segments, T=args.T)
            logger.info("Mouth ø: %.1f mm  (T=%.3f, x₀=c/2π·fc=%.0fmm)",
                        r.max() * 2, args.T, SOUND_SPEED / (2.0 * np.pi * args.fc))

        elif name == "iwata":
            if args.fc is None or args.length is None:
                raise ValueError("--fc and --length required for iwata")
            logger.info("Iwata: throat=%s  Fc=%s  length=%s", args.throat, args.fc, args.length)
            z, r = get_iwata(args.throat, args.fc, args.length, args.segments)
            logger.info("Mouth ø: %.1f mm  (T=0.707, Hypex/Iwata preset)",
                        r.max() * 2)

        elif name == "lecleach":
            if args.fc is None:
                raise ValueError("--fc required for lecleach")
            logger.info("Le Cléac'h: throat=%s  Fc=%s  T=%s  max_angle=%s",
                        args.throat, args.fc, args.T, args.max_angle)
            z, r = get_lecleach(args.throat, args.fc, args.segments,
                                T=args.T, max_angle=args.max_angle,
                                complete_rollback=args.complete_rollback,
                                rollback_angle=args.rollback_angle)
            logger.info("Mouth ø: %.1f mm  Length: %.1f mm  (roll-back %.0f°)",
                        r.max() * 2, z.max(), args.max_angle)

        elif name == "oblate":
            if args.length is None:
                raise ValueError("--length required for oblate")
            logger.info("Oblate spheroidal CD: throat=%s  coverage=%s  length=%s",
                        args.throat, args.coverage, args.length)
            z, r = get_oblate_spheroidal(args.throat, args.coverage, args.length, args.segments)
            fc = 0.2 * SOUND_SPEED * np.sin(np.radians(args.coverage / 2.0)) / (
                np.pi * (args.throat / 2.0))
            logger.info("Mouth ø: %.1f mm  Length: %.1f mm  OS loading estimate≈%.0f Hz",
                        r[-1] * 2, z[-1], fc)

        elif name == "conical":
            if args.length is None:
                raise ValueError("--length required for conical")
            logger.info("Conical CD: throat=%s  coverage=%s  length=%s",
                        args.throat, args.coverage, args.length)
            z, r = get_conical(args.throat, args.coverage, args.length, args.segments)
            fc = SOUND_SPEED / (np.pi * r[-1] * 2.0)
            logger.info("Mouth ø: %.1f mm  Length: %.1f mm  mouth-loading estimate≈%.0f Hz",
                        r[-1] * 2, z[-1], fc)

        elif name == "rosse":
            if args.mouth is None:
                raise ValueError("--mouth required for rosse (waveguide outer Ø)")
            logger.info("R-OSSE: throat=%s  mouth=%s  coverage=%s",
                        args.throat, args.mouth, args.coverage)
            z, r = get_rosse(
                args.throat, args.mouth, args.coverage, args.segments,
                complete_rollback=args.complete_rollback,
                rollback_angle=args.rollback_angle)
            fc = SOUND_SPEED / (np.pi * args.mouth)
            logger.info("Mouth ø: %.1f mm  Length: %.1f mm  mouth-loading estimate≈%.0f Hz (rollback)",
                        args.mouth, z.max(), fc)

        else:
            raise ValueError(f"Unknown profile: {name}")

        # --- 3-D mesh (shared engine) --------------------------------------
        generate_3d_mesh_from_profile(
            z, r,
            thickness=args.thickness,
            rings=args.rings,
            output_path=args.output,
        )

    except Exception as exc:
        logger.exception("Generation failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
