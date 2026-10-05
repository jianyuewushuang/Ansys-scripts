import os
"""Voxel union of the interpenetrating shells -> ONE watertight STL.

1.stl is 4 separate, mutually interpenetrating closed shells.  Boolean ops need a
valid solid, so instead we rasterise the UNION on a grid and run marching cubes:

  inside(x,y,z)  <=>  an x-ray from -inf crosses an ODD number of triangles

Odd-parity gives exactly the union of the shells, however they overlap.
"""
import numpy as np, re, os
from skimage import measure

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
SRC = BASE + "/data/1.stl"
OUT = BASE + "/artifacts/geometry/aircraft_solid.stl"
H = float(os.environ.get("VOXEL", 0.05))     # voxel size, m

txt = open(SRC, "r", errors="ignore").read()
V = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = V.reshape(-1, 3, 3)
print(f"input: {len(tri)} facets, spacing h = {H} m")

lo = tri.reshape(-1, 3).min(axis=0) - 3 * H
hi = tri.reshape(-1, 3).max(axis=0) + 3 * H
nx = int(np.ceil((hi[0] - lo[0]) / H))
ny = int(np.ceil((hi[1] - lo[1]) / H))
nz = int(np.ceil((hi[2] - lo[2]) / H))
print(f"grid: {nx} x {ny} x {nz} = {nx*ny*nz/1e6:.1f} M voxels")

# ---------- per-column (y,z) ray casting along +x ----------
Ay, Az, Ax = tri[:, 0, 1], tri[:, 0, 2], tri[:, 0, 0]     # vertex A
e1y = tri[:, 1, 1] - Ay; e1z = tri[:, 1, 2] - Az
e2y = tri[:, 2, 1] - Ay; e2z = tri[:, 2, 2] - Az
e1x = tri[:, 1, 0] - Ax; e2x = tri[:, 2, 0] - Ax
proj_area2 = e1y * e2z - e1z * e2y
good = np.abs(proj_area2) > 1e-14          # skip triangles seen edge-on in (y,z)
print(f"triangles usable for x-ray casting: {good.sum()} / {len(tri)}")

Ay, Az, Ax = Ay[good], Az[good], Ax[good]
e1y, e1z, e1x = e1y[good], e1z[good], e1x[good]
e2y, e2z, e2x = e2y[good], e2z[good], e2x[good]
proj_area2 = proj_area2[good]
nt = len(Ax)

yc = lo[1] + (np.arange(ny) + 0.5) * H
zc = lo[2] + (np.arange(nz) + 0.5) * H
YY, ZZ = np.meshgrid(yc, zc, indexing="ij")      # (ny, nz)
cols = np.stack([YY.ravel(), ZZ.ravel()], axis=1)
ncol = cols.shape[0]
print(f"ray columns: {ncol}")

occ = np.zeros((ny, nz, nx), dtype=bool)         # (y, z, x)

CHUNK = 4000
for c0 in range(0, ncol, CHUNK):
    c1 = min(c0 + CHUNK, ncol)
    P = cols[c0:c1]                              # (m, 2)
    m = P.shape[0]
    py = P[:, 0][:, None] - Ay[None, :]          # (m, nt)
    pz = P[:, 1][:, None] - Az[None, :]
    d00 = e1y * e1y + e1z * e1z
    d01 = e1y * e2y + e1z * e2z
    d11 = e2y * e2y + e2z * e2z
    d20 = py * e1y + pz * e1z
    d21 = py * e2y + pz * e2z
    den = d00 * d11 - d01 * d01
    u = (d11 * d20 - d01 * d21) / den
    v = (d00 * d21 - d01 * d20) / den
    hit = (u >= 0) & (v >= 0) & (u + v <= 1)
    xhit = np.where(hit, Ax[None, :] + u * e1x[None, :] + v * e2x[None, :], np.nan)

    # odd parity => inside the union
    for i in range(m):
        xs = xhit[i][hit[i]]
        if xs.size == 0:
            continue
        xs = np.sort(xs)
        idx = np.searchsorted(xs, lo[0] + (np.arange(nx) + 0.5) * H)
        occ_i = (idx % 2) == 1
        iy, iz = divmod(c0 + i, nz)
        occ[iy, iz, :] = occ_i
    if c0 % 40000 == 0:
        print(f"   cast {c1}/{ncol}")

vol_vox = occ.sum() * H ** 3
print(f"voxelised volume = {vol_vox:.3f} m^3  (sum of shell volumes 175.519)")

# ---------- marching cubes ----------
grid = occ.astype(np.float32)
verts, faces, normals, values = measure.marching_cubes(grid, level=0.5, spacing=(H, H, H))
verts = verts + np.array([lo[1], lo[2], lo[0]])          # (y,z,x) -> world
verts = verts[:, [2, 0, 1]]                              # -> (x,y,z)
print(f"marching cubes: {len(verts)} verts, {len(faces)} faces")

v0 = verts[faces[:, 0]]; v1 = verts[faces[:, 1]]; v2 = verts[faces[:, 2]]
vol = np.einsum('ij,ij->i', np.cross(v1 - v0, v2 - v0), (v0 + v1 + v2) / 3.0).sum() / 6.0
print(f"signed volume = {vol:.3f} m^3")
if vol < 0:
    faces = faces[:, ::-1]
    vol = -vol
    print("   (flipped to outward normals)")

# manifold check
from collections import defaultdict
key = lambda p: (round(float(p[0]), 6), round(float(p[1]), 6), round(float(p[2]), 6))
eu = defaultdict(int)
for f in faces:
    ks = [key(verts[j]) for j in f]
    for j in range(3):
        eu[tuple(sorted((ks[j], ks[(j + 1) % 3])))] += 1
hist = defaultdict(int)
for c in eu.values():
    hist[c] += 1
print("edge usage:", dict(hist), " -> watertight" if set(hist) == {2} else " -> NOT watertight")

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


for f in faces:
    ks = [key(verts[j]) for j in f]
    uni(ks[0], ks[1]); uni(ks[1], ks[2])
comps = defaultdict(list)
for fi, f in enumerate(faces):
    comps[find(key(verts[f[0]]))].append(fi)
sizes = sorted((len(v) for v in comps.values()), reverse=True)
print("component sizes:", sizes[:10], "... total", len(sizes))

# keep only substantial components (drop voxelisation islands)
keep = [fi for v in comps.values() if len(v) >= int(os.environ.get("MINCOMP", "500"))
        for fi in v]
keep = np.array(sorted(keep))
if len(keep) != len(faces):
    print(f"dropping {len(faces)-len(keep)} island facets -> keeping {len(keep)}")
    faces = faces[keep]
    used = np.unique(faces.ravel())
    remap = {old: new for new, old in enumerate(used)}
    verts = verts[used]
    faces = np.vectorize(remap.get)(faces)

v0 = verts[faces[:, 0]]; v1 = verts[faces[:, 1]]; v2 = verts[faces[:, 2]]
vol = np.einsum('ij,ij->i', np.cross(v1 - v0, v2 - v0), (v0 + v1 + v2) / 3.0).sum() / 6.0
print(f"final volume = {abs(vol):.3f} m^3")
print("bbox min", verts.min(axis=0), "max", verts.max(axis=0))

# ---------- write binary STL ----------
def write_binary_stl(path, verts, faces):
    import struct
    nrm = np.cross(verts[faces[:, 1]] - verts[faces[:, 0]],
                   verts[faces[:, 2]] - verts[faces[:, 0]])
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = np.divide(nrm, np.where(ln == 0, 1, ln))
    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(faces)))
        data = np.zeros(len(faces), dtype=np.dtype([
            ("n", "<f4", 3), ("v0", "<f4", 3), ("v1", "<f4", 3),
            ("v2", "<f4", 3), ("attr", "<u2")]))
        data["n"] = nrm.astype("<f4")
        data["v0"] = verts[faces[:, 0]].astype("<f4")
        data["v1"] = verts[faces[:, 1]].astype("<f4")
        data["v2"] = verts[faces[:, 2]].astype("<f4")
        data.tofile(f)


write_binary_stl(OUT, verts, faces)
print(f"\nsaved {OUT}: {len(faces)} facets, {os.path.getsize(OUT)/1e6:.2f} MB")
