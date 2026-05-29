"""
STEP export — AP242 faceted B-Rep (ISO 10303-21).
Deduplicates vertices for a valid STEP file.
"""

from stl import mesh
import numpy as np


def export_step(stl_path: str, step_path: str) -> None:
    m = mesh.Mesh.from_file(stl_path)
    n = len(m.vectors)

    # Deduplicate vertices by rounding to 4 decimal places
    verts = m.vectors.reshape(-1, 3)
    rounded = np.round(verts, 4)
    # Find unique vertices
    _, inv_idx = np.unique(rounded, axis=0, return_inverse=True)
    unique_verts = rounded[np.sort(np.unique(inv_idx, return_index=True)[1])]

    nv = len(unique_verts)
    eid = 0

    def e(cnt=1):
        nonlocal eid
        r = list(range(eid + 1, eid + cnt + 1))
        eid += cnt
        return r if cnt > 1 else r[0]

    lines = [
        "ISO-10303-21;",
        "HEADER;",
        "FILE_DESCRIPTION((''),'2;1');",
        "FILE_NAME('','',(''),(''),'Horn Generator','',(''));",
        "FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));",
        "ENDSEC;",
        "DATA;",
    ]

    # CARTESIAN_POINT for unique vertices
    pt_ids = []
    for pt in unique_verts:
        pid = e()
        pt_ids.append(pid)
        lines.append(f"#{pid}=CARTESIAN_POINT('',({pt[0]:.4f},{pt[1]:.4f},{pt[2]:.4f}));")

    # Map each triangle to its 3 vertex IDs via inv_idx
    # inv_idx maps each original vertex to its unique index
    tri_pt_ids = inv_idx.reshape(-1, 3)

    face_ids = []
    for i in range(n):
        a = pt_ids[tri_pt_ids[i, 0]]
        b = pt_ids[tri_pt_ids[i, 1]]
        c = pt_ids[tri_pt_ids[i, 2]]

        v0, v1, v2 = m.vectors[i]
        ex = v1 - v0
        ey = v2 - v0
        ez = m.normals[i]

        nx, ny, nz = ez / np.linalg.norm(ez)
        exn = ex / np.linalg.norm(ex)

        zdir = e()
        lines.append(f"#{zdir}=DIRECTION('',({nx:.6f},{ny:.6f},{nz:.6f}));")
        xdir = e()
        lines.append(f"#{xdir}=DIRECTION('',({exn[0]:.6f},{exn[1]:.6f},{exn[2]:.6f}));")

        axis = e()
        lines.append(f"#{axis}=AXIS2_PLACEMENT_3D('',#{a},#{zdir},#{xdir});")
        plane = e()
        lines.append(f"#{plane}=PLANE('',#{axis});")

        loop = e()
        lines.append(f"#{loop}=POLY_LOOP('',(#{a},#{b},#{c}));")
        fb = e()
        lines.append(f"#{fb}=FACE_BOUND('',#{loop},.T.);")

        af = e()
        lines.append(f"#{af}=ADVANCED_FACE('',(#{fb}),#{plane},.T.);")
        face_ids.append(af)

    # CLOSED_SHELL
    sh = e()
    lines.append(
        f"#{sh}=CLOSED_SHELL('',({','.join(f'#{f}' for f in face_ids)}));"
    )

    # MANIFOLD_SOLID_BREP
    ms = e()
    lines.append(f"#{ms}=MANIFOLD_SOLID_BREP('Horn',#{sh});")

    # SHAPE_REPRESENTATION
    sr = e()
    rc = e()
    lines.append(f"#{sr}=SHAPE_REPRESENTATION('',(#{ms}),#{rc});")
    lines.append(f"#{rc}=REPRESENTATION_CONTEXT('',(#{e()}),'');")

    # PRODUCT chain
    prod = e()
    pdf = e()
    pc = e()
    lines.append(f"#{prod}=PRODUCT('Horn','',(#{pc}));")
    lines.append(f"#{pc}=PRODUCT_CONTEXT('',(#{e()}),'mechanical');")
    lines.append(f"#{pdf}=PRODUCT_DEFINITION_FORMATION('',(#{prod}),'');")

    pdef = e()
    pdc = e()
    lines.append(f"#{pdef}=PRODUCT_DEFINITION('design',(#{pdc}),#{pdf});")
    lines.append(f"#{pdc}=PRODUCT_DEFINITION_CONTEXT('',(#{e()}),'design');")

    sdr = e()
    lines.append(f"#{sdr}=SHAPE_DEFINITION_REPRESENTATION('',(#{sr}),#{pdef});")

    lines.append(f"#{e()}=PRODUCT_DEFINITION_SHAPE('',(#{sdr}),#{pdef});")

    lines.append("ENDSEC;")
    lines.append("END-ISO-10303-21;")

    with open(step_path, "w") as f:
        f.write("\n".join(lines))
