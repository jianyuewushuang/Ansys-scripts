"""HALF-MODEL domain, v2: two CLOSED solids (fluid box + airframe half).

This is the classic "fluid body with a solid body inside it" case that Fluent's
Watertight workflow understands:

  solid  fluid_box : 5 outer box faces + the full y=0 rectangle   (closed box)
  solid  aircraft  : airframe surface y>=0 + footprint cap at y=0 (closed half-body)

The airframe sits ON the y=0 wall, so share topology only has to cut a solid that
touches the boundary - no floating cavity, and no holes to triangulate.
"""
import numpy as np, re, os
import mapbox_earcut as earcut

BASE = "C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
OUT = BASE + "/half_domain.stl"

XMIN, XMAX = -36.0, 84.0
YMIN, YMAX = 0.0, 33.0
ZMIN, ZMAX = -20.0, 20.0
BOX_EDGE = float(os.environ.get("BOX_EDGE", 8.0))

print(f"half domain x[{XMIN},{XMAX}] y[{YMIN},{YMAX}] z[{ZMIN},{ZMAX}] = "
      f"{XMAX-XMIN:.0f}x{YMAX-YMIN:.0f}x{ZMAX-ZMIN:.0f} m")

txt = open(BASE + "/1.stl", "r", errors="ignore").read()
V = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+", txt), dtype=float)
V = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = V.reshape(-1, 3, 3)


def signed(v0, v1, v2):
    return np.einsum('ij,ij->i', np.cross(v1 - v0, v2 - v0), (v0 + v1 + v2) / 3.0) / 6.0


vol_full = signed(tri[:, 0], tri[:, 1], tri[:, 2]).sum()
EPS = 1e-9
h = tri[:, :, 1]
keep = h.min(axis=1) >= -EPS
print(f"aircraft volume (full) = {vol_full:.4f} m^3 | facets y>=0: {keep.sum()}")
half = tri[keep]                      # outward normals (out of the airframe)

# ---------------- footprint loops on y = 0 ----------------
key = lambda p: (round(float(p[0]), 7), round(float(p[2]), 7))
adj = {}
for t in half:
    for i in range(3):
        a, b = t[i], t[(i + 1) % 3]
        if abs(a[1]) < 1e-9 and abs(b[1]) < 1e-9:
            adj.setdefault(key(a), []).append(key(b))
            adj.setdefault(key(b), []).append(key(a))

loops, seen = [], set()
for start in adj:
    if start in seen or len(adj[start]) != 2:
        continue
    loop, cur, seen_add = [start], start, {start}
    seen |= seen_add
    while True:
        nxt = [n for n in adj[cur] if n not in seen]
        if not nxt:
            break
        cur = nxt[0]; seen.add(cur); loop.append(cur)
        if cur == start:
            break
    if len(loop) >= 3:
        loops.append(loop)


def area2(poly):
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
                     - poly[(i + 1) % len(poly)][0] * poly[i][1]
                     for i in range(len(poly)))


loops = [l for l in loops if abs(area2(l)) > 1e-8]
print(f"footprint loops: {len(loops)}")
for i, l in enumerate(loops):
    xs = [p[0] for p in l]; zs = [p[1] for p in l]
    print(f"   loop {i}: {len(l)} pts |A|={abs(area2(l)):.4f} m^2 "
          f"x[{min(xs):.2f},{max(xs):.2f}] z[{min(zs):.3f},{max(zs):.3f}]")

# ---------------- cap the airframe half at y = 0 ----------------
cap = []
for l in loops:
    ring = np.array(l, dtype=np.float64)
    if area2(l) > 0:
        ring = ring[::-1]                    # CW -> normal -y
    idx = earcut.triangulate_float64(ring, np.array([len(ring)], dtype=np.uint32))
    tt = ring[np.array(idx).reshape(-1, 3)]
    c = np.zeros((len(tt), 3, 3))
    c[:, :, 0] = tt[:, :, 0]
    c[:, :, 1] = YMIN
    c[:, :, 2] = tt[:, :, 1]
    nrm = np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0])
    if np.median(nrm[:, 1]) > 0:
        c = c[:, ::-1].copy()
    cap.append(c)
cap = np.concatenate(cap, axis=0) if cap else np.zeros((0, 3, 3))
print(f"footprint cap: {len(cap)} triangles")

vol_half = abs(signed(half[:, 0], half[:, 1], half[:, 2]).sum()
               + signed(cap[:, 0], cap[:, 1], cap[:, 2]).sum())
print(f"aircraft half-solid volume = {vol_half:.4f} m^3 (half of full = {vol_full/2:.4f})")

# ---------------- box faces (all six) ----------------
x0, x1, y0, y1, z0, z1 = XMIN, XMAX, YMIN, YMAX, ZMIN, ZMAX
C = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
              [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
QUADS = [(C[4], C[5], C[6], C[7]),   # z = zmax
         (C[1], C[0], C[3], C[2]),   # z = zmin
         (C[0], C[4], C[7], C[3]),   # x = xmin
         (C[5], C[1], C[2], C[6]),   # x = xmax
         (C[3], C[7], C[6], C[2]),   # y = ymax
         (C[0], C[1], C[5], C[4])]   # y = ymin  (symmetry plane; outward = -y)


def quad_grid(p00, p10, p11, p01, target):
    n1 = max(1, int(round(np.linalg.norm(p10 - p00) / target)))
    n2 = max(1, int(round(np.linalg.norm(p01 - p00) / target)))
    out = []
    for i in range(n1):
        for j in range(n2):
            u0, u1, v0, v1 = i / n1, (i + 1) / n1, j / n2, (j + 1) / n2
            P = lambda u, v: (p00 * (1 - u) * (1 - v) + p10 * u * (1 - v)
                              + p11 * u * v + p01 * (1 - u) * v)
            a, b, c, d = P(u0, v0), P(u1, v0), P(u1, v1), P(u0, v1)
            out.append([a, b, c]); out.append([a, c, d])
    return out


box = np.array([t for q in QUADS for t in quad_grid(*q, BOX_EDGE)])


def write_solid(f, name, fac):
    nv = np.cross(fac[:, 1] - fac[:, 0], fac[:, 2] - fac[:, 0])
    ln = np.linalg.norm(nv, axis=1, keepdims=True)
    nv = nv / np.where(ln == 0, 1, ln)
    f.write(f"solid {name}\n")
    for i in range(len(fac)):
        f.write(f"  facet normal {nv[i,0]:e} {nv[i,1]:e} {nv[i,2]:e}\n")
        f.write("    outer loop\n")
        for j in range(3):
            f.write(f"      vertex {fac[i,j,0]:e} {fac[i,j,1]:e} {fac[i,j,2]:e}\n")
        f.write("    endloop\n  endfacet\n")
    f.write(f"endsolid {name}\n")


with open(OUT, "w") as f:
    write_solid(f, "fluid_box", box)
    write_solid(f, "aircraft", np.concatenate([half, cap], axis=0))

vb = signed(box[:, 0], box[:, 1], box[:, 2]).sum()
print(f"\nwrote {OUT}")
print(f"   fluid_box {len(box)} facets | signed volume {vb:.3f} m^3 "
      f"(expected {(x1-x0)*(y1-y0)*(z1-z0):.3f})")
print(f"   aircraft  {len(half)+len(cap)} facets | half volume {vol_half:.3f} m^3")
print("   fluid_box closed:" , abs(vb - (x1-x0)*(y1-y0)*(z1-z0)) < 1.0)
print(f"   file {os.path.getsize(OUT)/1e6:.2f} MB")
