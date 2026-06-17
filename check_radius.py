import trimesh
import numpy as np

for i in range(4):
    p = trimesh.load(f"petal_{i}.stl")
    r = np.sqrt(p.vertices[:, 0]**2 + p.vertices[:, 1]**2)
    min_r = np.min(r)
    print(f"Petal {i} min radius: {min_r:.4f}")
    if min_r < 9.9:
        print(f"  WARNING: Petal {i} protrudes into hole! (radius {min_r:.4f} < 10)")
