import trimesh
import numpy as np
from src._slicer import slice_into_petals

# create a tube mesh
outer = trimesh.creation.cylinder(radius=12.0, height=20.0)
inner = trimesh.creation.cylinder(radius=10.0, height=20.0)
# Make it a tube
mesh = trimesh.boolean.difference([outer, inner], engine="manifold")

petals = slice_into_petals(mesh, 4, joint_depth=2.0)
for i, p in enumerate(petals):
    r = np.sqrt(p.vertices[:, 0]**2 + p.vertices[:, 1]**2)
    min_r = np.min(r)
    print(f"Petal {i} min radius: {min_r:.4f}")
