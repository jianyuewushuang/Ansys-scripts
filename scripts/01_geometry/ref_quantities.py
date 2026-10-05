import os
BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
"""Accurate planform + side outline of the UAV, with correct reference areas."""
import numpy as np, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

path = BASE + "/data/1.stl"
txt = open(path, "r", errors="ignore").read()
V = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = V.reshape(-1, 3, 3)

a = tri[:, 1] - tri[:, 0]
b = tri[:, 2] - tri[:, 0]
n2 = np.cross(a, b)                      # = 2 * area-vector
# projected area of a triangle onto a plane = 0.5 * |n2 . normal|
proj = lambda k: 0.5 * np.abs(n2[:, k]).sum()

print("========== REFERENCE QUANTITIES (raw STL units) ==========")
print(f"length  L          = {V[:,0].max()-V[:,0].min():9.4f}  (X)")
print(f"span    b          = {V[:,1].max()-V[:,1].min():9.4f}  (Y)")
print(f"height  h          = {V[:,2].max()-V[:,2].min():9.4f}  (Z)")
A_xy = proj(2); A_yz = proj(0); A_xz = proj(1)
print(f"\nsum of triangle projects onto XY (top view)    = {A_xy:9.4f}")
print(f"sum of triangle projects onto XZ (side view)   = {A_xz:9.4f}")
print(f"sum of triangle projects onto YZ (front view)  = {A_yz:9.4f}")
print(f"\n--> one-side planform footprint  S  = {A_xy/2:9.4f}")
print(f"--> one-side side profile       A_s = {A_xz/2:9.4f}")
print(f"--> one-side frontal area       A_f = {A_yz/2:9.4f}")
print(f"\naspect ratio (full span)^2/S     = {(V[:,1].max()-V[:,1].min())**2/(A_xy/2):9.4f}")

# ---------- spanwise outline ----------
NB = 40
ymax = V[:, 1].max()
ye = np.linspace(0, ymax, NB + 1)
LE, TE, THK = [], [], []
yc = []
for i in range(NB):
    lo, hi = ye[i], ye[i + 1]
    m = (np.abs(tri[:, :, 1]).max(axis=1) >= lo) & (np.abs(tri[:, :, 1]).min(axis=1) <= hi)
    if m.sum() < 2:
        LE.append(np.nan); TE.append(np.nan); THK.append(np.nan); yc.append(np.nan); continue
    c = tri[m].reshape(-1, 3)
    LE.append(c[:, 0].min()); TE.append(c[:, 0].max())
    THK.append(c[:, 2].max() - c[:, 2].min()); yc.append((lo + hi) / 2)
LE, TE, THK, yc = map(np.array, (LE, TE, THK, yc))

fig, ax = plt.subplots(2, 1, figsize=(13, 9))
# planform (mirrored)
for s in (1, -1):
    ax[0].plot(LE, s * yc, 'b-', lw=2, label='Leading edge' if s == 1 else None)
    ax[0].plot(TE, s * yc, 'r-', lw=2, label='Trailing edge' if s == 1 else None)
ax[0].set_title("PLANFORM (top view)   X = flight direction (nose at x=0)")
ax[0].set_xlabel("X"); ax[0].set_ylabel("Y  (span)")
ax[0].grid(True, alpha=0.4); ax[0].legend(); ax[0].set_aspect('equal')

# side profile envelope
xs = np.linspace(0, V[:, 0].max(), 60)
zup, zlo, xc = [], [], []
for i in range(len(xs) - 1):
    m = (tri[:, :, 0].max(axis=1) >= xs[i]) & (tri[:, :, 0].min(axis=1) <= xs[i + 1])
    if m.sum() < 2:
        zup.append(np.nan); zlo.append(np.nan); xc.append(np.nan); continue
    c = tri[m].reshape(-1, 3)
    zup.append(c[:, 2].max()); zlo.append(c[:, 2].min()); xc.append((xs[i] + xs[i + 1]) / 2)
ax[1].fill_between(xc, zlo, zup, color='0.75', ec='k', lw=0.8)
ax[1].axhline(0, color='g', lw=0.8, ls='--')
ax[1].set_title("SIDE PROFILE (looking -Y)")
ax[1].set_xlabel("X"); ax[1].set_ylabel("Z")
ax[1].grid(True, alpha=0.4); ax[1].set_aspect('equal')
plt.tight_layout()
plt.savefig(BASE + "/results/geometry_annotated.png", dpi=110)
print("\nsaved geometry_annotated.png")

# summary table of the wing region
print("\n========== SPANWISE OUTLINE ==========")
print(f"{'|y|':>8} {'x_LE':>9} {'x_TE':>9} {'chord':>9} {'thick':>8}")
for i in range(0, NB, 3):
    if np.isnan(yc[i]):
        continue
    print(f"{yc[i]:8.3f} {LE[i]:9.3f} {TE[i]:9.3f} {TE[i]-LE[i]:9.3f} {THK[i]:8.3f}")
