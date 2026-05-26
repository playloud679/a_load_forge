"""
Boolean Operations (Blender Headless).

Stage 3 of the Acoustic Horn pipeline.
Input is a perfectly solid, watertight horn .stl from Stage 1.
Blender only attaches a mounting flange at the throat and ensures Z=0.

Usage:
    blender -b -P blender_scripts/03_boolean_operations.py -- \
        --input io/horn_base.stl --output io/horn.stl --throat 10
"""

import argparse
import sys


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    p = argparse.ArgumentParser()
    p.add_argument("--input", type=str, required=True)
    p.add_argument("--output", type=str, required=True)
    p.add_argument("--throat", type=float, required=True)
    return p.parse_args(argv)


def run(input_path: str, output_path: str, throat: float) -> None:
    import bpy
    from mathutils import Vector

    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Import solid horn
    bpy.ops.import_mesh.stl(filepath=input_path)
    horn = bpy.context.selected_objects[0]
    horn.name = "Horn"
    bbox = [horn.matrix_world @ Vector(c) for c in horn.bound_box]
    throat_z = min(v.z for v in bbox)

    # Mounting flange — solid cylinder at throat
    flange_r = throat * 0.85
    flange_d = 10.0
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=64,
        radius=flange_r,
        depth=flange_d,
        location=(0.0, 0.0, throat_z - flange_d / 2),
    )
    flange = bpy.context.active_object
    flange.name = "Flange"

    bpy.context.view_layer.objects.active = horn
    mod = horn.modifiers.new(name="AttachFlange", type="BOOLEAN")
    mod.operation = "UNION"
    mod.object = flange
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(flange, do_unlink=True)

    # Seat on Z=0
    bbox = [horn.matrix_world @ Vector(c) for c in horn.bound_box]
    min_z = min(v.z for v in bbox)
    if abs(min_z) > 1e-6:
        horn.location.z -= min_z
        bpy.context.view_layer.update()
        print(f"[03] Translated Z by {min_z:.3f} → bottom at Z=0")

    bpy.ops.export_mesh.stl(filepath=output_path, use_selection=True)
    print(f"[03] Exported: {output_path}")


def main() -> None:
    args = parse_args()
    print(f"[03] Input: {args.input}")
    print(f"[03] Throat: {args.throat} mm")
    try:
        run(args.input, args.output, args.throat)
    except ImportError:
        print("ERROR: Must run inside Blender (blender -b -P).")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
