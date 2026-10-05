"""Decimate the repaired airframe so the CFD surface mesh can be coarsened.

aircraft_solid.stl has 262k facets -> Fluent's surface mesher reproduces that
resolution no matter how large MIN_SIZE / CURV are.  Collapsing it first is
what actually frees the cell budget for boundary-layer prisms.
"""
import os
import struct
import numpy as np
import pymeshlab as ml

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
SRC = os.environ.get("SRC", BASE + "/artifacts/geometry/aircraft_solid.stl")
OUT = os.environ.get("OUT", BASE + "/artifacts/geometry/aircraft_solid_dec.stl")
NT = int(os.environ.get("NFACES", 60000))


def read_binary_stl(path):
    with open(path, "rb") as f:
        d = f.read()
    n = struct.unpack("<I", d[80:84])[0]
    dt = np.dtype([("n", "<f4", 3), ("v0", "<f4", 3), ("v1", "<f4", 3),
                   ("v2", "<f4", 3), ("a", "<u2")])
    a = np.frombuffer(d[84:84 + 50 * n], dtype=dt)
    v = np.stack([a["v0"], a["v1"], a["v2"]], axis=1).astype(np.float64)
    nrm = a["n"].astype(np.float64)
    return v, nrm


def signed_volume(tri):
    return float(np.einsum("ij,ij->i",
                           np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]),
                           tri.mean(axis=1)).sum() / 6.0)


tri, nrm = read_binary_stl(SRC)
print("input : %d facets, signed volume %.4f m3" % (len(tri), signed_volume(tri)))

ms = ml.MeshSet()
m = ml.Mesh(vertex_matrix=tri.reshape(-1, 3).astype(np.float64),
            face_matrix=np.arange(len(tri) * 3).reshape(-1, 3))
ms.add_mesh(m, "airframe")
print("loaded into pymeshlab:", ms.current_mesh().vertex_number(), "verts",
      ms.current_mesh().face_number(), "faces")

ms.meshing_merge_close_vertices(threshold=ml.PercentageValue(0.0))
ms.meshing_remove_duplicate_faces()
ms.meshing_remove_unreferenced_vertices()
print("after weld:", ms.current_mesh().face_number(), "faces")

# quadric edge collapse, preserving mesh boundary is irrelevant (closed solid)
ms.meshing_decimation_quadric_edge_collapse(
    targetfacenum=NT, preservenormal=True, preservetopology=False,
    qualitythr=0.3, boundaryweight=1.0, optimalplacement=True,
    planarquadric=True, autoclean=True)
print("after decimation:", ms.current_mesh().face_number(), "faces")

cm = ms.current_mesh()
F = cm.face_matrix()
V = cm.vertex_matrix()
out = V[F].astype(np.float32)
print("output: %d facets, signed volume %.4f m3"
      % (len(out), signed_volume(out.astype(np.float64))))

# recompute facet normals
a = out[:, 1] - out[:, 0]
b = out[:, 2] - out[:, 0]
nv = np.cross(a, b)
L = np.linalg.norm(nv, axis=1)
nv /= np.maximum(L, 1e-20)[:, None]

with open(OUT, "wb") as f:
    f.write(b"\0" * 80)
    f.write(struct.pack("<I", len(out)))
    buf = np.zeros(len(out), dtype=np.dtype([("n", "<f4", 3), ("v0", "<f4", 3),
                                             ("v1", "<f4", 3), ("v2", "<f4", 3),
                                             ("a", "<u2")]))
    buf["n"] = nv
    buf["v0"] = out[:, 0]
    buf["v1"] = out[:, 1]
    buf["v2"] = out[:, 2]
    f.write(buf.tobytes())

print("wrote", OUT, "%.2f MB" % (os.path.getsize(OUT) / 1e6))
