import numpy as np, re

path = "C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004/1.stl"
with open(path, "r", errors="ignore") as f:
    txt = f.read()

solid_name = txt.split("\n")[0].strip()
verts = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
n_tri = len(verts) // 3

print("solid header :", solid_name)
print("vertices     :", len(verts))
print("triangles    :", n_tri)
print("\n--- bounding box (raw units) ---")
mn, mx = verts.min(axis=0), verts.max(axis=0)
print("min :", np.array2string(mn, precision=4))
print("max :", np.array2string(mx, precision=4))
print("size:", np.array2string(mx - mn, precision=4))

# duplicate-vertex count (tells us if shell is watertight-ish)
uniq = np.unique(verts, axis=0)
print("\nunique vertices:", len(uniq), "| duplicate minus non-unique:", len(verts) - len(uniq))

# area per triangle -> wetted area
v = verts.reshape(-1, 3, 3)
a = v[:, 1] - v[:, 0]
b = v[:, 2] - v[:, 0]
cross = np.cross(a, b)
areas = 0.5 * np.linalg.norm(cross, axis=1)
print("\n--- surface metrics (raw units^2) ---")
print("total surface area :", round(areas.sum(), 4))
print("max triangle area  :", round(areas.max(), 6))
print("min triangle area  :", round(areas.min(), 9))
print("avg triangle area  :", round(areas.mean(), 6))

# degenerate check
deg = (areas < 1e-12).sum()
print("degenerate triangles:", deg)
