"""SpaceClaim: build the external-flow enclosure (fluid = box - airframe).

Run headless:  SpaceClaim.exe /RunScript="scdm_build.py" /Headless=True
Writes progress + API introspection to scdm_build.log
"""
import os, sys, traceback

BASE = r"C:\Users\jianyuewushuang\document\model\ansys\UAVdesign20261004"
LOG = os.path.join(BASE, "scdm_build.log")
STL = os.path.join(BASE, "1.stl")
OUT = os.path.join(BASE, "fluid_domain.scdoc")

logf = open(LOG, "w", buffering=1)


def p(*a):
    logf.write(" ".join(str(x) for x in a) + "\n")


p("=== SpaceClaim enclosure script ===")
p("python:", sys.version)

try:
    from SpaceClaim.Api.V261 import *
    from SpaceClaim.Api.V261.Scripting import *
    p("imported SpaceClaim.Api.V261 + Scripting")
except Exception as e:
    p("IMPORT FAIL:", e)
    traceback.print_exc(file=logf)
    logf.close()
    raise

ns = dir()
p("\n--- API names ---")
for kw in ("Body", "Block", "Box", "Enclos", "Combin", "Boolean", "Document",
           "Point", "Solid", "Volume", "Split", "Merge", "Plane", "Direction",
           "Import", "Export", "Save", "Window", "Part", "Component", "Helper"):
    p(f"  {kw:11s}: {[x for x in ns if kw.lower() in x.lower()][:16]}")

# ---------- open the STL ----------
p("\n--- open STL ---")
try:
    DocumentOpen.Execute(STL)
    p("DocumentOpen ok")
except Exception as e:
    p("DocumentOpen fail:", e)
    traceback.print_exc(file=logf)

try:
    root = GetRootPart()
    bodies = list(root.GetAllBodies())
    p("bodies:", [str(b.GetName()) for b in bodies])
except Exception as e:
    p("bodies fail:", e)
    traceback.print_exc(file=logf)

p("\n--- done ---")
logf.close()
