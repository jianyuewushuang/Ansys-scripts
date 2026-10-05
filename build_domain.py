"""Build the fluid-domain STL as ONE closed shell (box + airframe cavity).

The outer box facets are subdivided so the initial faceting is well scaled
(avoids the "self-intersecting triangles" failure seen with 12 huge facets).
The airframe facets keep their winding so their normals point INTO the airframe,
i.e. out of the fluid.  The result is one closed genus-1 volume whose interior
is exactly the air around the aircraft.
"""
import numpy as np, re, os

BASE = "C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
OUT = BASE + "/fluid_domain.stl"

XMIN, XMAX = -36.0, 84.0
YMIN, YMAX = -33.0, 33.0
ZMIN, ZMAX = -20.0, 20.0
BOX_TARGET = float(os.environ.get("BOX_TARGET", 6.0))   # m, box facet edge target

print(f"domain x[{XMIN},{XMAX}] y[{YMIN},{YMAX}] z[{ZMIN},{ZMAX}]  "
      f"= {XMAX-XMIN:.0f}x{YMAX-YMIN:.0f}x{ZMAX-ZMIN:.0f} m")

txt = open(BASE + "/1.stl", "r", errors="ignore").read()
V = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = V.reshape(-1, 3, 3)
print(f"aircraft: {len(tri)} facets")


def signed(v0, v1, v2):
    return np.einsum('ij,ij->i', np.cross(v1 - v0, v2 - v0), (v0 + v1 + v2) / 3.0) / 6.0


vol_ac = signed(tri[:, 0], tri[:, 1], tri[:, 2]).sum()
print(f"aircraft volume {vol_ac:.3f} m^3 (positive => normals point out of the airframe)")


def quad_grid(p00, p10, p11, p01, nx, ny):
    """Subdivide a planar quad into 2*nx*ny triangles, preserving orientation."""
    out = []
    for i in range(nx):
        for j in range(ny):
            u0, u1 = i / nx, (i + 1) / nx
            v0, v1 = j / ny, (j + 1) / ny
            def P(u, v):
                return (p00 * (1 - u) * (1 - v) + p10 * u * (1 - v)
                        + p11 * u * v + p01 * (1 - u) * v)
            a, b, c, d = P(u0, v0), P(u1, v0), P(u1, v1), P(u0, v1)
            out.append([a, b, c]); out.append([a, c, d])
    return out


x0, x1, y0, y1, z0, z1 = XMIN, XMAX, YMIN, YMAX, ZMIN, ZMAX
C = np.array([
    [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
    [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)

QUADS = [  # (p00, p10, p11, p01) ordered so the normal points OUT of the box
    (C[4], C[5], C[6], C[7]),   # z = zmax
    (C[1], C[0], C[3], C[2]),   # z = zmin
    (C[0], C[4], C[7], C[3]),   # x = xmin
    (C[5], C[1], C[2], C[6]),   # x = xmax
    (C[0], C[1], C[5], C[4]),   # y = ymin
    (C[3], C[7], C[6], C[2]),   # y = ymax
]
box = []
for p00, p10, p11, p01 in QUADS:
    e1 = np.linalg.norm(p10 - p00)
    e2 = np.linalg.norm(p01 - p00)
    nx = max(1, int(round(e1 / BOX_TARGET)))
    ny = max(1, int(round(e2 / BOX_TARGET)))
    box.extend(quad_grid(p00, p10, p11, p01, nx, ny))
box = np.array(box)
print(f"box: {len(box)} facets (target edge {BOX_TARGET} m)")

# airframe: reverse winding -> normals point INTO the airframe (out of the fluid)
ac = tri[:, ::-1].copy()

merged = np.concatenate([box, ac], axis=0)

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

if os.environ.get("TWO", "0") == "1":
    # two named shells -> Fluent creates two labels ('farfield','aircraft') which
    # makes per-body mesh sizing possible.  Fluent still cannot boolean them.
    with open(OUT, "w") as f:
        write_solid(f, "farfield", box)
        write_solid(f, "aircraft", ac)
    print(f"\nwrote {OUT}: TWO shells (farfield {len(box)} + aircraft {len(ac)})")
else:
    with open(OUT, "w") as f:
        write_solid(f, "fluid_domain", merged)

vt = signed(merged[:, 0], merged[:, 1], merged[:, 2]).sum()
expect = (x1 - x0) * (y1 - y0) * (z1 - z0) - vol_ac
print(f"\nwrote {OUT}: {len(merged)} facets ({len(box)} box + {len(ac)} airframe)")
print(f"  signed volume {vt:.3f} m^3 | expected (box - airframe) {expect:.3f} m^3")
print("  OK - single closed shell, consistent outward normals" if abs(vt - expect) < 1e-3
      else "  MISMATCH - orientation problem")
print(f"  file {os.path.getsize(OUT)/1e6:.2f} MB")
