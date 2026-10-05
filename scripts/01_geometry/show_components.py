import os
"""Show why Fluent cannot cut the airframe out: it is FOUR separate,
mutually interpenetrating closed shells, not one solid."""
import numpy as np, re
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
txt = open(BASE + "/data/1.stl", "r", errors="ignore").read()
V = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = V.reshape(-1, 3, 3)

key = lambda p: (round(float(p[0]), 6), round(float(p[1]), 6), round(float(p[2]), 6))
par = {}


def find(a):
    par.setdefault(a, a)
    while par[a] != a:
        par[a] = par[par[a]]; a = par[a]
    return a


def uni(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        par[ra] = rb


for t in tri:
    ks = [key(t[j]) for j in range(3)]
    uni(ks[0], ks[1]); uni(ks[1], ks[2])

comp = defaultdict(list)
for t in tri:
    comp[find(key(t[0]))].append(t)

groups = []
for r, ts in comp.items():
    a = np.array(ts)
    mn = a.reshape(-1, 3).min(axis=0); mx = a.reshape(-1, 3).max(axis=0)
    vol = np.einsum('ij,ij->i', np.cross(a[:, 1] - a[:, 0], a[:, 2] - a[:, 0]),
                    a.mean(axis=1)).sum() / 6.0
    groups.append((len(ts), mn, mx, abs(vol), a))
groups.sort(key=lambda g: -g[0])
names = ["main wing/body", "right tail boom", "left tail boom", "horizontal tail"]
colors = ["#4C78C8", "#E45756", "#F58518", "#54A24B"]

fig = plt.figure(figsize=(15, 9))
views = [("TOP  (planform)", (0, 1)), ("SIDE  (x-z)", (0, 2)), ("FRONT  (y-z)", (1, 2))]
for vi, (title, (ua, va)) in enumerate(views):
    ax = fig.add_subplot(2, 2, vi + 1)
    for gi, (n, mn, mx, vol, a) in enumerate(groups):
        P = a.reshape(-1, 3)
        u, v = P[:, ua], P[:, va]
        U = u.reshape(-1, 3); Vv = v.reshape(-1, 3)
        depth = a[:, :, 0].mean(axis=1)
        order = np.argsort(depth)
        ax.tripcolor(U[order].ravel(), Vv[order].ravel(),
                     np.repeat(np.arange(len(order)), 3),
                     color=colors[gi % 4], alpha=0.9, lw=0)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel(["x", "x", "y"][vi]); ax.set_ylabel(["y", "z", "z"][vi])
    ax.grid(alpha=0.3); ax.set_aspect("equal")

ax = fig.add_subplot(2, 2, 4); ax.axis("off")
rows = [["shell", "facets", "volume m^3", "x-range", "y-range", "z-range"]]
for gi, (n, mn, mx, vol, a) in enumerate(groups):
    rows.append([names[gi] if gi < 4 else f"comp {gi}", str(n), f"{vol:.3f}",
                 f"{mn[0]:.1f}..{mx[0]:.1f}", f"{mn[1]:.1f}..{mx[1]:.1f}",
                 f"{mn[2]:.2f}..{mx[2]:.2f}"])
tbl = ax.table(cellText=rows, cellLoc="center", loc="center", colWidths=[0.24] * 6)
tbl.auto_set_font_size(False); tbl.set_fontsize(8); tbl.scale(1, 1.8)
ax.set_title(f"1.stl = {len(groups)} SEPARATE closed shells (they interpenetrate)",
             fontsize=11, color="#c0392b")

plt.tight_layout()
plt.savefig(BASE + "/results/stl_components.png", dpi=110)
print("saved stl_components.png")
for gi, (n, mn, mx, vol, a) in enumerate(groups):
    print(f"  {names[gi] if gi<4 else gi:18s}: {n:5d} facets  vol {vol:8.3f} m^3  "
          f"x[{mn[0]:.2f},{mx[0]:.2f}] y[{mn[1]:.2f},{mx[1]:.2f}] z[{mn[2]:.2f},{mx[2]:.2f}]")
