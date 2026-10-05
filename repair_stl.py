"""Repair 1.stl into ONE watertight solid.

1.stl is several SEPARATE, INTERPENETRATING closed shells (main body, 2 booms,
tail).  That is not a solid, so every Fluent boolean (share-topology Intersect)
fails.  Two strategies are tried here:
   A) boolean union of the connected components
   B) screened-Poisson surface reconstruction from a sampled point cloud
      (always yields a single closed watertight surface)
"""
import os
import numpy as np
import pymeshlab as pml

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
SRC = os.path.join(BASE, "1.stl")
OUT = os.path.join(BASE, "aircraft_solid.stl")


def stats(ms, i):
    m = ms.mesh(i)
    return m.vertex_number(), m.face_number()


def signed_volume(verts, faces):
    v0 = verts[faces[:, 0]]; v1 = verts[faces[:, 1]]; v2 = verts[faces[:, 2]]
    return np.einsum('ij,ij->i', np.cross(v1 - v0, v2 - v0),
                     (v0 + v1 + v2) / 3.0).sum() / 6.0


def edge_hist(verts, faces):
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
    return dict(hist)


def n_components(verts, faces):
    from collections import defaultdict
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

    for f in faces:
        ks = [key(verts[j]) for j in f]
        uni(ks[0], ks[1]); uni(ks[1], ks[2])
    return len({find(key(verts[f[0]])) for f in faces})


# ------------------------- strategy A : boolean union -------------------------
print("=== strategy A: boolean union ===")
try:
    ms = pml.MeshSet()
    ms.load_new_mesh(SRC)
    ms.generate_splitting_by_connected_components()
    n = ms.mesh_number()
    print("layers:", n, [stats(ms, i) for i in range(n)])
    # drop layer 0 (the unsplit original) if it is the whole mesh
    if stats(ms, 0)[1] == 6264 and n > 1:
        ms.set_current_mesh(0)
        ms.delete_current_mesh()
        n = ms.mesh_number()
        print("after deleting original:", n, [stats(ms, i) for i in range(n)])
    guard = 0
    while ms.mesh_number() > 1 and guard < 20:
        guard += 1
        ms.generate_boolean_union(first_mesh=0, second_mesh=1)
    m = ms.current_mesh()
    V, F = m.vertex_matrix(), m.face_matrix()
    print("union OK:", m.vertex_number(), "v", m.face_number(), "f",
          "| vol", round(signed_volume(V, F), 4), "| comps", n_components(V, F),
          "|", edge_hist(V, F))
    okA = n_components(V, F) == 1 and set(edge_hist(V, F).keys()) == {2}
except Exception as e:
    print("strategy A failed:", e)
    okA = False

# ------------------------- strategy B : poisson -------------------------
print("\n=== strategy B: screened poisson reconstruction ===")
okB = False
for depth in (10, 9, 11):
    try:
        ms = pml.MeshSet()
        ms.load_new_mesh(SRC)
        ms.generate_sampling_poisson_disk(samplenum=200000, subsample=True)
        ms.generate_surface_reconstruction_screened_poisson(depth=depth, scale=1.1)
        m = ms.current_mesh()
        V, F = m.vertex_matrix(), m.face_matrix()
        vol = signed_volume(V, F)
        eh = edge_hist(V, F)
        nc = n_components(V, F)
        print(f"  depth={depth}: {m.vertex_number()} v {m.face_number()} f | "
              f"vol {vol:.3f} | comps {nc} | edges {eh}")
        if nc == 1 and set(eh.keys()) == {2} and vol > 0:
            # crop to the aircraft bounding box (poisson can add distant sheets)
            ms.save_current_mesh(OUT)
            print(f"  -> accepted, saved {OUT}")
            okB = True
            break
    except Exception as e:
        print(f"  depth={depth} failed: {e}")

print("\nA ok:", okA, " B ok:", okB)
if okB or okA:
    print("saved:", OUT, os.path.getsize(OUT) / 1e6, "MB")
