import os
BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
import numpy as np, re

path = BASE + "/data/1.stl"
txt = open(path, "r", errors="ignore").read()
verts = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = verts.reshape(-1, 3, 3)

# --- projected (silhouette) areas ---
a = tri[:, 1] - tri[:, 0]
b = tri[:, 2] - tri[:, 0]
nrm = np.cross(a, b)
signed = nrm / 2.0  # area vector
av = np.abs(signed)
print("--- projected area by projection direction (planform proxies) ---")
print("  sum |A_vec| . x  (projected onto YZ) :", round(av[:, 0].sum(), 3))
print("  sum |A_vec| . y  (projected onto XZ) :", round(av[:, 1].sum(), 3))
print("  sum |A_vec| . z  (projected onto XY) :", round(av[:, 2].sum(), 3))

Lx, Ly, Lz = 24.0367, 23.6443, 3.5811
print("\n--- possible reference areas ---")
print("  bbox X*Y  =", round(Lx * Ly, 3), " (planform box if Z is thickness)")
print("  bbox X*Z  =", round(Lx * Lz, 3))

# --- slicing: how does spanwise extent vary along each candidate axis ---
def slices(axis, n=13):
    lo, hi = verts[:, axis].min(), verts[:, axis].max()
    edges = np.linspace(lo, hi, n + 1)
    print(f"\n--- slices normal to axis {axis} (range {lo:.3f} .. {hi:.3f}) ---")
    print(f"{'center':>9} {'#tri':>7} {'y-extent':>18} {'z-extent':>18}")
    for i in range(n):
        m = (tri[:, :, axis].max(axis=1) >= edges[i]) & (tri[:, :, axis].min(axis=1) <= edges[i + 1])
        if m.sum() == 0:
            continue
        c = tri[m][:, :, :].reshape(-1, 3)
        oth = [j for j in range(3) if j != axis]
        ye = (c[:, oth[0]].max() - c[:, oth[0]].min())
        ze = (c[:, oth[1]].max() - c[:, oth[1]].min())
        print(f"{(edges[i]+edges[i+1])/2:9.3f} {m.sum():7d} {ye:18.4f} {ze:18.4f}")

slices(0)   # along X
slices(2)   # along Z (checks vertical stack / wing within box)

# closed-body check: signed volume via divergence theorem
vol = np.einsum('ij,ij->i', (tri[:, 0] + tri[:, 1] + tri[:, 2]) / 3.0, signed).sum() / 3.0
print("\n--- watertight check ---")
print("signed volume :", round(vol, 4), "-> closed and consistently oriented" if vol > 0 else "-> OPEN or inward normals")
print("note: positive volume means outward normals = usable solid body")
