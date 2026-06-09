"""
OS-SE waveguide — full non-axisymmetric (ATH-style) engine.

Faithful implementation of Marcel Batík's *OS-SE Waveguide* formula (at-horns.eu,
Oct 2020). Unlike the axisymmetric ``get_rosse`` in ``profile_generator.py``,
this module builds the real round-throat → rectangular/superelliptical-mouth
waveguide whose coverage angle varies with azimuth — which is exactly what
produces the characteristic **diagonal ridges** (the "protrusions") running from
the throat to the four corners.

Two-layer design (mirrors the rest of the project):

  1. Math layer (no side effects):
       osse_profile(z, r0, alpha, …)      single-azimuth profile  r(z)   (eq. 5)
       coverage_alpha(phi, a_h, a_v)       elliptical-cone coverage α(φ)
       superellipse_radius(phi, a, b, p)   target mouth outline  r_M(φ)
       osse_surface(...)                   the morphed field      r(z,φ)

  2. Mesh engine:
       generate_osse_3d_mesh(...)          thick watertight shell from r(z,φ)

The OS-SE profile (Batík eq. 5), for one azimuth:

    r(z) = √(k²r₀² + 2kr₀z·tanα₀ + z²·tan²α) + r₀(1−k)              (generalized OS)
           + (sL/q)·[1 − (1 − (qz/L)ⁿ)^(1/n)]                       (super-ellipse term)

  r₀  throat radius           α   nominal coverage half-angle
  α₀  throat opening half-angle    k   throat expansion factor (1=pure OS, 0=conical)
  L   length                  s   termination flare amount   n   SE exponent
  q   truncation coefficient (≈0.998)

Azimuthal variation: α (and only α, by default) follows an elliptical cone
between the horizontal half-angle ``alpha_h`` (φ=0) and the vertical half-angle
``alpha_v`` (φ=π/2). The un-morphed mouth is therefore ~elliptical; the mouth is
then **morphed** (Batík sec. 5) onto a superellipse of exponent ``mouth_exp``
(2 = ellipse, large = rectangle), pushing the diagonals out to the corners and
raising the ridges.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys

import numpy as np
import trimesh

_src = str(Path(__file__).resolve().parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

logger = logging.getLogger(__name__)


# ======================================================================
#  Math layer
# ======================================================================

def osse_profile(
    z: np.ndarray,
    r0: float,
    alpha: float,
    alpha0: float = 0.0,
    k: float = 1.0,
    L: float = 120.0,
    s: float = 0.8,
    n: float = 5.0,
    q: float = 0.998,
) -> np.ndarray:
    """Single-azimuth OS-SE profile r(z) — Batík eq. (5). Angles in radians.

    ``z`` is an array in ``[0, L]``. Returns r(z) of the same shape.

    Properties: ``r(0) = r0`` for any α/α₀/k; ``k=0`` collapses the OS term to a
    cone ``r0 + z·tanα``; the SE term is 0 at z=0 and adds the mouth flare.
    """
    z = np.asarray(z, dtype=float)
    ta, ta0 = np.tan(alpha), np.tan(alpha0)
    gos = np.sqrt(np.maximum(
        k * k * r0 * r0 + 2.0 * k * r0 * z * ta0 + z * z * ta * ta, 0.0)) + r0 * (1.0 - k)
    if L <= 0.0 or s == 0.0:
        return gos
    # Super-ellipse termination term; clamp the base so (·)^(1/n) stays real.
    base = np.clip(1.0 - (q * z / L) ** n, 0.0, 1.0)
    term = (s * L / q) * (1.0 - base ** (1.0 / n))
    return gos + term


def coverage_alpha(phi: np.ndarray, alpha_h: float, alpha_v: float) -> np.ndarray:
    """Coverage half-angle α(φ) interpolated on an **elliptical cone** between
    the horizontal half-angle ``alpha_h`` (φ=0, π) and the vertical half-angle
    ``alpha_v`` (φ=±π/2). Angles in radians.

    The asymptotic cone cross-section is an ellipse with horizontal/vertical
    half-angles α_h/α_v, so along direction φ:

        tan α(φ) = 1 / √( (cosφ/tanα_h)² + (sinφ/tanα_v)² )
    """
    th, tv = np.tan(alpha_h), np.tan(alpha_v)
    c, snt = np.cos(phi), np.sin(phi)
    inv = np.sqrt((c / th) ** 2 + (snt / tv) ** 2)
    return np.arctan(1.0 / np.maximum(inv, 1e-12))


def superellipse_radius(phi: np.ndarray, a: float, b: float, p: float) -> np.ndarray:
    """Polar radius of a superellipse with half-axes ``a`` (x) and ``b`` (y) and
    exponent ``p``: ``(x/a)^p + (y/b)^p = 1``.

    p=2 → ellipse; p→∞ → rectangle 2a×2b. Returns r_M(φ).
    """
    c, snt = np.abs(np.cos(phi)), np.abs(np.sin(phi))
    denom = (c / a) ** p + (snt / b) ** p
    return denom ** (-1.0 / p)


def osse_surface(
    r0: float,
    L: float,
    alpha_h: float,
    alpha_v: float,
    alpha0: float = 0.0,
    k: float = 1.0,
    s: float = 0.8,
    n: float = 5.0,
    q: float = 0.998,
    mouth_exp: float = 4.0,
    morph_start: float = 0.0,
    morph_rate: float = 2.0,
    nz: int = 120,
    nphi: int = 160,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build the morphed OS-SE radius field r(z, φ).

    Returns ``(z[nz], phi[nphi], R[nz, nphi])`` where ``R[i, j]`` is the inner
    surface radius at height ``z[i]`` and azimuth ``phi[j]``.

    Parameters
    ----------
    alpha_h, alpha_v : horizontal / vertical coverage half-angles (radians).
    mouth_exp : superellipse exponent of the morphed mouth outline (2=ellipse,
        large=rectangle). Drives how far the diagonal ridges push out.
    morph_start : fraction of L (0..1) below which the natural OS-SE surface is
        kept intact (``z_f = morph_start·L``).
    morph_rate : morph exponent γ ≥ 1 (1=abrupt at z_f, higher=more gradual).
    """
    z = np.linspace(0.0, L, nz)
    phi = np.linspace(0.0, 2.0 * np.pi, nphi, endpoint=False)

    # Base (un-morphed) OS-SE surface with elliptical-cone coverage.
    alpha_phi = coverage_alpha(phi, alpha_h, alpha_v)            # (nphi,)
    R = np.empty((nz, nphi), dtype=float)
    for j in range(nphi):
        R[:, j] = osse_profile(z, r0, alpha_phi[j], alpha0, k, L, s, n, q)

    # Mouth morph (Batík sec. 5): pull the natural mouth outline onto a
    # superellipse whose half-axes equal the natural horizontal/vertical mouth.
    r_mouth_nat = R[-1, :]                                        # natural r(L,φ)
    a = float(osse_profile(np.array([L]), r0, alpha_h, alpha0, k, L, s, n, q)[0])
    b = float(osse_profile(np.array([L]), r0, alpha_v, alpha0, k, L, s, n, q)[0])
    r_target = superellipse_radius(phi, a, b, mouth_exp)         # r_M(φ)

    z_f = morph_start * L
    if z_f < L:
        w = np.clip((z - z_f) / (L - z_f), 0.0, 1.0) ** morph_rate   # (nz,)
        R = R + np.outer(w, (r_target - r_mouth_nat))
    return z, phi, R


# ======================================================================
#  Mesh engine — thick watertight shell from r(z, φ)
# ======================================================================

def _vertex_normals(V: np.ndarray) -> np.ndarray:
    """Outward unit normals for a structured (nz × nphi) surface grid of points.

    Tangents are central differences along z (rows) and φ (columns, wrapped).
    The normal is ``t_phi × t_z``, flipped to point away from the Z axis.
    """
    nz, nphi, _ = V.shape
    # φ tangent (wrap-around in columns)
    t_phi = np.roll(V, -1, axis=1) - np.roll(V, 1, axis=1)
    # z tangent (one-sided at the two ends)
    t_z = np.empty_like(V)
    t_z[1:-1] = V[2:] - V[:-2]
    t_z[0] = V[1] - V[0]
    t_z[-1] = V[-1] - V[-2]
    nrm = np.cross(t_phi, t_z)
    ln = np.linalg.norm(nrm, axis=2, keepdims=True)
    nrm = nrm / np.maximum(ln, 1e-12)
    # Orient outward: positive radial (x,y) component.
    radial = V.copy(); radial[:, :, 2] = 0.0
    rl = np.linalg.norm(radial, axis=2, keepdims=True)
    radial = radial / np.maximum(rl, 1e-12)
    dot = np.sum(nrm * radial, axis=2, keepdims=True)
    nrm = np.where(dot < 0.0, -nrm, nrm)
    return nrm


def generate_osse_3d_mesh(
    throat: float,
    length: float,
    coverage_h: float,
    coverage_v: float,
    throat_angle: float = 0.0,
    k: float = 1.0,
    s: float = 0.8,
    n: float = 5.0,
    q: float = 0.998,
    mouth_exp: float = 4.0,
    morph_start: float = 0.0,
    morph_rate: float = 2.0,
    thickness: float = 4.0,
    nz: int = 120,
    nphi: int = 160,
    output_path: str | None = None,
) -> trimesh.Trimesh:
    """Build a watertight OS-SE waveguide shell (round throat → superelliptical
    mouth, with azimuth-dependent coverage → diagonal ridges).

    ``throat`` and the coverage angles (``coverage_h``/``coverage_v``, full
    beamwidths in degrees) match the UI convention; internally half-angles are
    used. ``throat_angle`` is the full throat included angle (degrees).

    Returns a ``trimesh.Trimesh`` and optionally writes an STL.
    """
    r0 = throat / 2.0
    a_h = np.radians(coverage_h / 2.0)
    a_v = np.radians(coverage_v / 2.0)
    a0 = np.radians(throat_angle / 2.0)

    z, phi, R = osse_surface(
        r0, length, a_h, a_v, a0, k, s, n, q,
        mouth_exp, morph_start, morph_rate, nz, nphi)

    ct, st = np.cos(phi), np.sin(phi)
    V_in = np.empty((nz, nphi, 3))
    V_in[:, :, 0] = R * ct[None, :]
    V_in[:, :, 1] = R * st[None, :]
    V_in[:, :, 2] = z[:, None]

    nrm = _vertex_normals(V_in)
    V_out = V_in + thickness * nrm
    # Keep the throat (z=0) and mouth (z=L) faces flat for mounting — the inner
    # rings are already planar; clip the offset outer z into range and pin the
    # two end rings (same trick as the rectangular/polygonal engines).
    V_out[:, :, 2] = np.clip(V_out[:, :, 2], 0.0, length)
    V_out[0, :, 2] = 0.0
    V_out[-1, :, 2] = length

    # Flatten: inner block then outer block.
    verts = np.concatenate([V_in.reshape(-1, 3), V_out.reshape(-1, 3)], axis=0)
    base_out = nz * nphi

    def idx_in(i, j):  return i * nphi + (j % nphi)
    def idx_out(i, j): return base_out + i * nphi + (j % nphi)

    faces = []
    # Inner wall — winding so the normal faces the airway (toward axis).
    for i in range(nz - 1):
        for j in range(nphi):
            a = idx_in(i, j); b = idx_in(i + 1, j)
            c = idx_in(i + 1, j + 1); d = idx_in(i, j + 1)
            faces.append([a, c, b]); faces.append([a, d, c])
    # Outer wall — reversed winding (normal outward).
    for i in range(nz - 1):
        for j in range(nphi):
            a = idx_out(i, j); b = idx_out(i + 1, j)
            c = idx_out(i + 1, j + 1); d = idx_out(i, j + 1)
            faces.append([a, b, c]); faces.append([a, c, d])
    # Throat rim (i=0): annulus between inner and outer rings.
    for j in range(nphi):
        a = idx_in(0, j); b = idx_in(0, j + 1)
        c = idx_out(0, j + 1); d = idx_out(0, j)
        faces.append([a, b, c]); faces.append([a, c, d])
    # Mouth rim (i=nz-1): annulus between inner and outer rings (reversed).
    for j in range(nphi):
        a = idx_in(nz - 1, j); b = idx_in(nz - 1, j + 1)
        c = idx_out(nz - 1, j + 1); d = idx_out(nz - 1, j)
        faces.append([a, c, b]); faces.append([a, d, c])

    tm = trimesh.Trimesh(vertices=verts, faces=np.asarray(faces), process=True)
    tm.merge_vertices()
    tm.fix_normals()
    if tm.body_count > 1:
        bodies = [bdy for bdy in tm.split() if bdy.volume > 0]
        if bodies:
            tm = max(bodies, key=lambda bdy: bdy.volume)

    if output_path:
        tm.export(output_path)
        logger.info("Exported OS-SE waveguide: %s  (%d tris, watertight=%s)",
                    output_path, len(tm.faces), tm.is_watertight)
    return tm
