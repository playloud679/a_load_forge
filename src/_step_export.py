"""
STEP export — AP203 / CONFIG_CONTROL_DESIGN, FACETED_BREP encoding.

Valid combination for triangulated meshes:
  FACETED_BREP → CLOSED_SHELL → FACE_SURFACE + FACE_OUTER_BOUND + POLY_LOOP
"""

from stl import mesh
import numpy as np


def export_step(stl_path: str, step_path: str) -> None:
    m = mesh.Mesh.from_file(stl_path)
    n = len(m.vectors)

    # Deduplicate vertices by rounding to 4 decimal places
    verts = m.vectors.reshape(-1, 3)
    rounded = np.round(verts, 4)
    _, inv_idx = np.unique(rounded, axis=0, return_inverse=True)
    unique_verts = rounded[np.sort(np.unique(inv_idx, return_index=True)[1])]

    eid = 0

    def e():
        nonlocal eid
        eid += 1
        return eid

    # Pre-assign IDs for structural entities
    app_ctx    = e()   # APPLICATION_CONTEXT
    mech_ctx   = e()   # MECHANICAL_CONTEXT
    prod       = e()   # PRODUCT
    pdf        = e()   # PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE
    design_ctx = e()   # DESIGN_CONTEXT
    pdef       = e()   # PRODUCT_DEFINITION
    pds        = e()   # PRODUCT_DEFINITION_SHAPE
    sdr        = e()   # SHAPE_DEFINITION_REPRESENTATION
    sr         = e()   # SHAPE_REPRESENTATION
    rep_ctx    = e()   # REPRESENTATION_CONTEXT (complex entity)
    unc        = e()   # UNCERTAINTY_MEASURE_WITH_UNIT
    lu         = e()   # LENGTH_UNIT complex
    pau        = e()   # PLANE_ANGLE_UNIT complex
    sau        = e()   # SOLID_ANGLE_UNIT complex
    brep       = e()   # FACETED_BREP
    shell      = e()   # CLOSED_SHELL

    lines = [
        "ISO-10303-21;",
        "HEADER;",
        "FILE_DESCRIPTION(('flare_forge STEP Export'),'2;1');",
        "FILE_NAME('','',(''),(''),'flare_forge','','');",
        "FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));",
        "ENDSEC;",
        "DATA;",
    ]

    # CARTESIAN_POINTs for unique vertices
    pt_ids = []
    for pt in unique_verts:
        pid = e()
        pt_ids.append(pid)
        lines.append(f"#{pid}=CARTESIAN_POINT('',({pt[0]:.4f},{pt[1]:.4f},{pt[2]:.4f}));")

    # Triangular faces: POLY_LOOP → FACE_OUTER_BOUND → FACE_SURFACE
    tri_pt_ids = inv_idx.reshape(-1, 3)
    face_ids = []
    for i in range(n):
        a = pt_ids[tri_pt_ids[i, 0]]
        b = pt_ids[tri_pt_ids[i, 1]]
        c = pt_ids[tri_pt_ids[i, 2]]

        loop_id  = e()
        lines.append(f"#{loop_id}=POLY_LOOP('',(#{a},#{b},#{c}));")
        bound_id = e()
        lines.append(f"#{bound_id}=FACE_OUTER_BOUND('',#{loop_id},.T.);")
        face_id  = e()
        lines.append(f"#{face_id}=FACE_SURFACE('',(#{bound_id}),$,.T.);")
        face_ids.append(face_id)

    # CLOSED_SHELL + FACETED_BREP
    face_list = ",".join(f"#{f}" for f in face_ids)
    lines.append(f"#{shell}=CLOSED_SHELL('',({face_list}));")
    lines.append(f"#{brep}=FACETED_BREP('Horn',#{shell});")

    # Representation context (complex entity — millimetres, radians)
    lines.append(f"#{lu}=( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );")
    lines.append(f"#{pau}=( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) );")
    lines.append(f"#{sau}=( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() );")
    lines.append(
        f"#{unc}=UNCERTAINTY_MEASURE_WITH_UNIT("
        f"LENGTH_MEASURE(1.E-07),#{lu},'distance_accuracy_value','confusion accuracy');"
    )
    lines.append(
        f"#{rep_ctx}=( GEOMETRIC_REPRESENTATION_CONTEXT(3)"
        f" GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{unc}))"
        f" GLOBAL_UNIT_ASSIGNED_CONTEXT((#{lu},#{pau},#{sau}))"
        f" REPRESENTATION_CONTEXT('3D Context','3D Context') );"
    )

    # SHAPE_REPRESENTATION → PRODUCT chain
    lines.append(f"#{sr}=SHAPE_REPRESENTATION('Horn',(#{brep}),#{rep_ctx});")
    lines.append(f"#{app_ctx}=APPLICATION_CONTEXT('config control design');")
    lines.append(f"#{mech_ctx}=MECHANICAL_CONTEXT('',#{app_ctx},'mechanical');")
    lines.append(f"#{prod}=PRODUCT('Horn','Horn','',(#{mech_ctx}));")
    lines.append(
        f"#{pdf}=PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE"
        f"('','',#{prod},.NOT_KNOWN.);"
    )
    lines.append(f"#{design_ctx}=DESIGN_CONTEXT('',#{app_ctx},'design');")
    lines.append(f"#{pdef}=PRODUCT_DEFINITION('design','',#{pdf},#{design_ctx});")
    lines.append(f"#{pds}=PRODUCT_DEFINITION_SHAPE('','',#{pdef});")
    lines.append(f"#{sdr}=SHAPE_DEFINITION_REPRESENTATION(#{pds},#{sr});")

    lines.append("ENDSEC;")
    lines.append("END-ISO-10303-21;")

    with open(step_path, "w") as f:
        f.write("\n".join(lines))
