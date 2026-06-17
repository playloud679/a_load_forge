import numpy as np
import trimesh
from src._slicer import slice_into_petals

# create a simple cylinder mesh
mesh = trimesh.creation.cylinder(radius=10.0, height=20.0)
mesh.apply_translation([0, 0, 10])

# slice into 4 petals
petals = slice_into_petals(mesh, 4, joint_depth=2.0)
print(f"Number of petals: {len(petals)}")
for i, p in enumerate(petals):
    print(f"Petal {i}: volume = {p.volume:.2f}, parts = {p.body_count}")

for i, p in enumerate(petals):
    p.export(f"petal_{i}.stl")
