"""Build the FULL external-flow domain from the repaired watertight airframe.

Two closed solids -> the classic "fluid body with a solid body inside" case:
    fluid_box : 6 box faces (outward normals)
    aircraft  : the repaired single watertight airframe solid (outward normals)
Fluent's watertight workflow + share topology can now boolean these, because
aircraft_solid.stl is a single valid solid (1.stl was 4 interpenetrating shells).
"""
import numpy as np, struct, os

BASE = "C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
SRC = os.environ.get("SRC", BASE + "/aircraft_solid.stl")
OUT = BASE + "/fluid_domain.stl"

XMIN, XMAX = -36.0, 84.0
YMIN, YMAX = -33.0, 33.0
ZMIN, ZMAX = -20.0, 20.0
BOX_EDGE = float(os.environ.get("BOX_EDGE", 8.0))


def read_binary_stl(path):
    d = open(path, "rb").read()
    n = struct.unpack("<I", d[80:84])[0]
    dt = np.dtype([("n", "<f4", 3), ("v0", "<f4", 3), ("v1", "<f4", 3),
                   ("v2", "<f4", 3), ("a", "<u2")])
    arr = np.frombuffer(d[84:84 + 50 * n], dtype=dt)
    V = np.concatenate([arr["v0"], arr["v1"], arr["v2"]], axis=0).astype(np.float64)
    F = np.stack([np.arange(n), np.arange(n) + n, np.arange(n) + 2 * n], axis=1)
    return V, F


V, F = read_binary_stl(SRC)
ac = V[F]
print(f"aircraft solid: {len(ac)} facets | bbox min {ac.reshape(-1,3).min(axis=0)} "
      f"max {ac.reshape(-1,3).max(axis=0)}")


def signed(v0, v1, v2):
    return np.einsum('ij,ij->i', np.cross(v1 - v0, v2 - v0), (v0 + v1 + v2) / 3.0) / 6.0


vol_ac = signed(ac[:, 0], ac[:, 1], ac[:, 2]).sum()
print(f"aircraft signed volume = {vol_ac:.4f} m^3 (positive => outward normals)")

x0, x1, y0, y1, z0, z1 = XMIN, XMAX, YMIN, YMAX, ZMIN, ZMAX
C = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
              [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
QUADS = [(C[4], C[5], C[6], C[7]),   # z = zmax  (+z)
         (C[1], C[0], C[3], C[2]),   # z = zmin  (-z)
         (C[0], C[4], C[7], C[3]),   # x = xmin  (-x)
         (C[5], C[1], C[2], C[6]),   # x = xmax  (+x)
         (C[3], C[7], C[6], C[2]),   # y = ymax  (+y)
         (C[0], C[1], C[5], C[4])]   # y = ymin  (-y)


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
vol_box = signed(box[:, 0], box[:, 1], box[:, 2]).sum()
print(f"box: {len(box)} facets | signed volume {vol_box:.3f} "
      f"(expected {(x1-x0)*(y1-y0)*(z1-z0):.3f})")


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
    write_solid(f, "aircraft", ac)

print(f"\nwrote {OUT}")
print(f"   fluid_box {len(box)} | aircraft {len(ac)}")
print("   both closed:", abs(vol_box - (x1-x0)*(y1-y0)*(z1-z0)) < 1.0)
print(f"   file {os.path.getsize(OUT)/1e6:.2f} MB")
