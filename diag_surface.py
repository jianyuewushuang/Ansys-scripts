"""Diagnose leaks / non-manifold edges / point contacts in half_domain.stl."""
import numpy as np, re
from collections import defaultdict

BASE = "C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
txt = open(BASE + "/half_domain.stl", "r", errors="ignore").read()

blocks = re.split(r"\bsolid\b", txt)[1:]
patches = {}
for b in blocks:
    name = b.split("\n")[0].strip()
    v = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", b), dtype=float)
    patches[name] = v.reshape(-1, 3, 3)
for k, v in patches.items():
    print(f"patch {k:12s}: {len(v)} facets")

key = lambda p: (round(float(p[0]), 6), round(float(p[1]), 6), round(float(p[2]), 6))

allt = np.concatenate(list(patches.values()), axis=0)
patch_of = np.concatenate([[n] * len(v) for n, v in patches.items()])

# edge usage
eu = defaultdict(list)
for i, t in enumerate(allt):
    ks = [key(t[j]) for j in range(3)]
    if ks[0] == ks[1] or ks[1] == ks[2] or ks[0] == ks[2]:
        print(f"  degenerate facet {i} in {patch_of[i]}: {t.tolist()}")
    for j in range(3):
        e = tuple(sorted((ks[j], ks[(j + 1) % 3])))
        eu[e].append(i)

one = [e for e, v in eu.items() if len(v) == 1]
many = [e for e, v in eu.items() if len(v) >= 3]
print(f"\nedges used once (open boundary) : {len(one)}")
print(f"edges used >=3 (non-manifold)   : {len(many)}")

# which patches participate in the bad edges
def report(bad, label):
    if not bad:
        return
    print(f"\n--- {label} (first 25) ---")
    cnt = defaultdict(int)
    for e in bad:
        ps = tuple(sorted({patch_of[i] for i in eu[e]}))
        cnt[ps] += 1
    for ps, c in sorted(cnt.items(), key=lambda x: -x[1]):
        print(f"   {ps}: {c}")
    for e in bad[:25]:
        a, b = e
        ps = sorted({patch_of[i] for i in eu[e]})
        print(f"   {a} -- {b}   patches={ps}")

report(one, "open edges")
report(many, "non-manifold edges")

# vertex-based: vertices shared by several patches
vu = defaultdict(list)
for i, t in enumerate(allt):
    for j in range(3):
        vu[key(t[j])].append(i)

cross = []
for vk, tris in vu.items():
    ps = {patch_of[i] for i in tris}
    if len(ps) > 1:
        # is there at least one edge shared BETWEEN two different patches?
        edges_here = set()
        for i in tris:
            ks = [key(allt[i][j]) for j in range(3)]
            for j in range(3):
                edges_here.add(tuple(sorted((ks[j], ks[(j + 1) % 3]))))
        inter = False
        for e in edges_here:
            p = {patch_of[i] for i in eu[e]}
            if len(p) > 1 and len(eu[e]) == 2:
                inter = True
                break
        if not inter:
            cross.append((vk, sorted(ps)))
print(f"\nvertices shared by >1 patch WITHOUT a shared edge (point contacts): {len(cross)}")
for vk, ps in cross[:25]:
    print(f"   {vk}  patches={ps}")
