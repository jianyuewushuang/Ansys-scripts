"""Quick offscreen render of the STL in 4 views to identify aircraft orientation."""
import numpy as np, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

path = "C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004/1.stl"
txt = open(path, "r", errors="ignore").read()
verts = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = verts.reshape(-1, 3, 3)
N = len(tri)

# lighting
a = tri[:, 1] - tri[:, 0]
b = tri[:, 2] - tri[:, 0]
n = np.cross(a, b)
mag = np.linalg.norm(n, axis=1, keepdims=True)
mag[mag == 0] = 1e-12
n = n / mag
L = np.array([0.5, -0.6, 0.62]); L /= np.linalg.norm(L)

# keep only triangles whose outward normal points toward camera (backface cull)
def render(ax, view, title, aspect=None):
    # view maps world -> (u,v,depth)
    if view == "top":     M = np.array([[1,0,0],[0,1,0],[0,0,1]]);  u, v, d = 0, 1, 2; flipv = False
    elif view == "side":  M = np.array([[1,0,0],[0,0,-1],[0,1,0]]); u, v, d = 0, 1, 2; flipv = False
    elif view == "front": M = np.array([[0,-1,0],[0,0,1],[1,0,0]]); u, v, d = 0, 1, 2; flipv = False
    else:
        # iso
        th = np.deg2rad(35); ph = np.deg2rad(-58)
        eu = np.array([-np.sin(ph), np.cos(ph), 0])
        ev = np.array([-np.cos(ph)*np.sin(th), -np.sin(ph)*np.sin(th), np.cos(th)])
        ed = np.array([np.cos(th)*np.cos(ph), np.cos(th)*np.sin(ph), np.sin(th)])
        P = np.vstack([eu, ev, ed]); M = None
        proj = tri.reshape(-1, 3) @ np.vstack([eu, ev]).T
        u_, v_ = proj.reshape(N, 3, 2)[:, :, 0], proj.reshape(N, 3, 2)[:, :, 1]
        dep = (tri.reshape(-1, 3) @ ed).reshape(N, 3)
        nn = n @ ed
        keep = nn >= 0
        shade = np.abs(np.dot(n, L)) * 0.75 + 0.25
        order = np.argsort(dep.mean(axis=1))
        for i in order:
            if not keep[i]: continue
            g = max(0.05, min(0.85, shade[i]))
            ax.fill(u_[i], v_[i], color=(g, g, g), lw=0)
        ax.set_aspect("equal"); ax.axis("off"); ax.set_title(title, fontsize=10)
        return

    proj = tri.reshape(-1, 3) @ M.T
    P = proj.reshape(N, 3, 3)
    u_, v_ = P[:, :, u], P[:, :, v]
    dep = P[:, :, d]
    nn = np.einsum('ij,j->i', n, M[d])
    keep = nn >= 0
    shade = np.abs(np.dot(n, L)) * 0.75 + 0.25
    order = np.argsort(dep.mean(axis=1))
    for i in order:
        if not keep[i]: continue
        g = max(0.05, min(0.85, shade[i]))
        ax.fill(u_[i], v_[i], color=(g, g, g), lw=0)
    ax.set_aspect("equal"); ax.axis("off"); ax.set_title(title, fontsize=10)

fig, axes = plt.subplots(2, 2, figsize=(13, 9))
render(axes[0, 0], "top",   "TOP  (looking -Z, planform)  X->right, Y->up")
render(axes[0, 1], "side",  "SIDE (looking -Y)  X->right, Z->up")
render(axes[1, 0], "front", "FRONT (looking -X)  Y->right, Z->up")
render(axes[1, 1], "iso",   "ISO")
plt.tight_layout()
plt.savefig("C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004/geometry_views.png", dpi=110)
print("saved geometry_views.png")
