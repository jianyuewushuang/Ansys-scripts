import os
"""Build the HALF-model fluid domain.

Why a half model fixes the problem:
  the full model needs the airframe to be a *floating cavity* inside the box, i.e. a
  genus-1 body, and Fluent cannot boolean a faceted STL shell out of a box.
  In the half model the airframe sits ON the symmetry plane, so the fluid domain is
  topologically a BALL (genus 0) - the trivial case for Fluent.

Boundary of the fluid region:
  * 5 outer box faces      -> farfield   (x = xmin, x = xmax, y = ymax, z = zmin, z = zmax)
  * y = 0 plane with the airframe footprint cut out -> symmetry
  * airframe surface y>=0, winding reversed -> aircraft (wall)

The STL turns out to be exactly symmetric (3132 tris at y>=0, 3132 at y<=0, none
straddling), so no triangle clipping is required - we just pick the y>=0 half and
read the footprint loops off the edges that lie on y=0.
"""
import numpy as np, re, os
import mapbox_earcut as earcut

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
OUT = BASE + "/artifacts/geometry/half_domain.stl"

XMIN, XMAX = -36.0, 84.0
YMIN, YMAX = 0.0, 33.0
ZMIN, ZMAX = -20.0, 20.0
BOX_EDGE = float(os.environ.get("BOX_EDGE", 8.0))    # m, box facet target
MERGE = os.environ.get("MERGE", "0") == "1"          # 1 -> single solid

print(f"half domain x[{XMIN},{XMAX}] y[{YMIN},{YMAX}] z[{ZMIN},{ZMAX}] "
      f"= {XMAX-XMIN:.0f}x{YMAX-YMIN:.0f}x{ZMAX-ZMIN:.0f} m")

# ---------------- read the STL ----------------
txt = open(BASE + "/data/1.stl", "r", errors="ignore").read()
V = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = V.reshape(-1, 3, 3)


def signed(v0, v1, v2):
    return np.einsum('ij,ij->i', np.cross(v1 - v0, v2 - v0), (v0 + v1 + v2) / 3.0) / 6.0


vol_full = signed(tri[:, 0], tri[:, 1], tri[:, 2]).sum()
print(f"aircraft volume (full) = {vol_full:.4f} m^3")

EPS = 1e-9
yhalf = tri[:, :, 1]
keep = yhalf.min(axis=1) >= -EPS
drop = yhalf.max(axis=1) <= EPS
stra = ~(keep | drop)
print(f"facets: y>=0 {keep.sum()} | y<=0 {drop.sum()} | straddling {stra.sum()}")
if stra.sum():
    raise SystemExit("unexpected: triangles straddle y=0 - clipping needed")

half = tri[keep]                       # 3132 facets, outward normals (out of airframe)
# fluid side is outside the airframe -> normals must point INTO the airframe
ac = half[:, ::-1].copy()
vol_half = vol_full / 2.0
print(f"aircraft half used: {len(ac)} facets, half volume ~{vol_half:.4f} m^3")

# ---------------- footprint loops on y = 0 ----------------
key = lambda p: (round(float(p[0]), 7), round(float(p[2]), 7))
edges = []
for t in half:
    for i in range(3):
        a, b = t[i], t[(i + 1) % 3]
        if abs(a[1]) < 1e-9 and abs(b[1]) < 1e-9:
            edges.append((key(a), key(b)))

adj = {}
for a, b in edges:
    adj.setdefault(a, []).append(b)
    adj.setdefault(b, []).append(a)

loops = []
seen = set()
for start in adj:
    if start in seen:
        continue
    if len(adj[start]) != 2:
        continue
    loop = [start]
    seen.add(start)
    cur = start
    while True:
        nxt = [n for n in adj[cur] if n not in seen]
        if not nxt:
            break
        cur = nxt[0]
        seen.add(cur)
        loop.append(cur)
        if cur == start:
            break
    if len(loop) >= 3:
        loops.append(loop)

def area2(poly):
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        s += x1 * z2 - x2 * z1
    return s / 2.0

loops = [l for l in loops if abs(area2(l)) > 1e-8]
areas = [area2(l) for l in loops]
print(f"\nfootprint loops on y=0: {len(loops)}")
for i, (l, a) in enumerate(zip(loops, areas)):
    xs = [p[0] for p in l]; zs = [p[1] for p in l]
    print(f"   loop {i}: {len(l)} pts, |A| = {abs(a):.4f} m^2, "
          f"x[{min(xs):.2f},{max(xs):.2f}] z[{min(zs):.3f},{max(zs):.3f}]")

# ---------------- triangulate the symmetry plane (rectangle - footprint) -------
# The outer ring is subdivided so its boundary vertices land EXACTLY on the box
# edge vertices (see the n1/n2 counts the box faces use).  Otherwise the patches
# only touch at points and Fluent reports "non-manifold point contacts".
def _n(a, b, target):
    return max(1, int(round(abs(b - a) / target)))


NX = _n(XMIN, XMAX, BOX_EDGE)      # divisions along x on the z = const edges
NZ = _n(ZMIN, ZMAX, BOX_EDGE)      # divisions along z on the x = const edges
print(f"seam matching: NX={NX} (x edges), NZ={NZ} (z edges)")

outer = []
for k in range(NX):                # z = ZMIN, x: XMIN -> XMAX
    outer.append((XMIN + (XMAX - XMIN) * k / NX, ZMIN))
for k in range(NZ):                # x = XMAX, z: ZMIN -> ZMAX
    outer.append((XMAX, ZMIN + (ZMAX - ZMIN) * k / NZ))
for k in range(NX):                # z = ZMAX, x: XMAX -> XMIN
    outer.append((XMAX - (XMAX - XMIN) * k / NX, ZMAX))
for k in range(NZ):                # x = XMIN, z: ZMAX -> ZMIN
    outer.append((XMIN, ZMAX - (ZMAX - ZMIN) * k / NZ))
if area2(outer) < 0:
    outer = outer[::-1]
print(f"  outer ring: {len(outer)} pts")
verts2 = list(outer)
rings = [len(verts2)]            # mapbox_earcut wants cumulative END indices
for l in loops:
    ring = l[:]
    if area2(ring) > 0:          # holes must be opposite winding
        ring = ring[::-1]
    verts2.extend(ring)
    rings.append(len(verts2))

va = np.array(verts2, dtype=np.float64)
ri = np.array(rings, dtype=np.uint32)
assert ri[-1] == len(va), (ri[-1], len(va))
idx = earcut.triangulate_float64(va, ri)
sym_tris = va[np.array(idx).reshape(-1, 3)]
sym = np.zeros((len(sym_tris), 3, 3))
sym[:, :, 0] = sym_tris[:, :, 0]      # x
sym[:, :, 1] = YMIN                   # y = 0
sym[:, :, 2] = sym_tris[:, :, 1]      # z
# verify the triangulation really covers rectangle - holes
A = 0.5 * np.abs(np.cross(sym[:, 1] - sym[:, 0], sym[:, 2] - sym[:, 0])[:, 1]).sum()
Aexp = (XMAX - XMIN) * (ZMAX - ZMIN) - sum(abs(a) for a in areas)
print(f"  symmetry plane area {A:.4f} m^2 | expected {Aexp:.4f} m^2"
      + ("  OK" if abs(A - Aexp) < 1e-3 else "  MISMATCH"))
# outward from the fluid at y=0 is -y ; flip if needed
nrm = np.cross(sym[:, 1] - sym[:, 0], sym[:, 2] - sym[:, 0])
if np.median(nrm[:, 1]) > 0:
    sym = sym[:, ::-1].copy()
print(f"\nsymmetry plane: {len(sym)} triangles")

# ---------------- outer box faces (no y = YMIN face) ----------------
x0, x1, y0, y1, z0, z1 = XMIN, XMAX, YMIN, YMAX, ZMIN, ZMAX
C = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
              [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
# (p00, p10, p11, p01) ordered so the normal points OUT of the box
QUADS = [(C[4], C[5], C[6], C[7]),   # z = zmax (+z)
         (C[1], C[0], C[3], C[2]),   # z = zmin (-z)
         (C[0], C[4], C[7], C[3]),   # x = xmin (-x)
         (C[5], C[1], C[2], C[6]),   # x = xmax (+x)
         (C[3], C[7], C[6], C[2])]   # y = ymax (+y)


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


far = np.array([t for q in QUADS for t in quad_grid(*q, BOX_EDGE)])


def subdivide(fac, target, maxiter=7):
    """1-to-4 midpoint splitting until every edge is shorter than `target`."""
    for _ in range(maxiter):
        e = np.stack([np.linalg.norm(fac[:, 1] - fac[:, 0], axis=1),
                      np.linalg.norm(fac[:, 2] - fac[:, 1], axis=1),
                      np.linalg.norm(fac[:, 0] - fac[:, 2], axis=1)], axis=1)
        longest = e.max(axis=1)
        if longest.max() <= target:
            break
        big = fac[longest > target]
        small = fac[longest <= target]
        m01 = 0.5 * (big[:, 0] + big[:, 1])
        m12 = 0.5 * (big[:, 1] + big[:, 2])
        m20 = 0.5 * (big[:, 2] + big[:, 0])
        new = np.concatenate([
            np.stack([big[:, 0], m01, m20], axis=1),
            np.stack([m01, big[:, 1], m12], axis=1),
            np.stack([m20, m12, big[:, 2]], axis=1),
            np.stack([m01, m12, m20], axis=1)], axis=0)
        fac = np.concatenate([small, new], axis=0)
    return fac


# the earcut output on the symmetry plane is a handful of enormous triangles
# (~100 m^2 each); Fluent's surface mesher folds on them -> subdivide first.
SYM_EDGE = float(os.environ.get("SYM_EDGE", 4.0))
sym = subdivide(sym, SYM_EDGE)
print(f"farfield box faces: {len(far)} triangles")
print(f"symmetry plane after subdivision to {SYM_EDGE} m: {len(sym)} triangles")

# ---------------- assemble ----------------
def write_solid(f, name, fac):
    a = fac[:, 1] - fac[:, 0]; b = fac[:, 2] - fac[:, 0]
    nv = np.cross(a, b)
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
    if MERGE:
        write_solid(f, "half_domain", np.concatenate([far, sym, ac], axis=0))
    else:
        write_solid(f, "farfield", far)
        write_solid(f, "symmetry", sym)
        write_solid(f, "aircraft", ac)

allf = np.concatenate([far, sym, ac], axis=0)
vt = signed(allf[:, 0], allf[:, 1], allf[:, 2]).sum()
expect = (x1 - x0) * (y1 - y0) * (z1 - z0) - vol_half
print(f"\nwrote {OUT}")
print(f"   farfield {len(far)} + symmetry {len(sym)} + aircraft {len(ac)} = {len(allf)} facets")
print(f"   signed volume {vt:.3f} m^3 | expected {expect:.3f} m^3")
print("   OK - single closed simply-connected shell" if abs(vt - expect) < 1.0
      else f"   MISMATCH ({vt-expect:+.3f})")
print(f"   file {os.path.getsize(OUT)/1e6:.2f} MB")
