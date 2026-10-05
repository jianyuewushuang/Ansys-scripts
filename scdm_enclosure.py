"""SpaceClaim script: build the external-flow enclosure around the aircraft.

Run headless:  SpaceClaim.exe /RunScript="scdm_enclosure.py" /Headless=True
Writes progress/errors to scdm_build.log so we can see what the API offers.
"""
import os, sys, traceback

LOG = r"C:\Users\jianyuewushuang\document\model\ansys\UAVdesign20261004\scdm_build.log"
OUT = r"C:\Users\jianyuewushuang\document\model\ansys\UAVdesign20261004\fluid_domain.scdoc"
STL = r"C:\Users\jianyuewushuang\document\model\ansys\UAVdesign20261004\1.stl"

logf = open(LOG, "w")


def p(*a):
    s = " ".join(str(x) for x in a)
    logf.write(s + "\n")
    logf.flush()


p("=== SpaceClaim enclosure script start ===")
p("python:", sys.version)

try:
    from SpaceClaim.Api.V261 import *
    from SpaceClaim.Api.V261.Scripting import *
    p("imported SpaceClaim.Api.V261 + Scripting")
except Exception as e:
    p("IMPORT FAIL:", e)
    traceback.print_exc(file=logf)
    raise

ns = dir()
p("\n--- interesting API names ---")
for kw in ("Body", "Block", "Box", "Enclos", "Combin", "Boolean", "Document",
           "Point", "Import", "Export", "Solid", "Volume", "Combine", "Subtract",
           "Merge", "Split", "Plane", "Direction"):
    hits = [x for x in ns if kw.lower() in x.lower()]
    p(f"  {kw:12s}: {hits[:14]}")

# ---------- open the STL ----------
p("\n--- opening STL ---")
try:
    DocumentOpen.Execute(STL)
    p("DocumentOpen ok")
except Exception as e:
    p("DocumentOpen fail:", e)
    traceback.print_exc(file=logf)

try:
    root = GetRootPart()
    p("root:", root)
    bodies = [b for b in root.GetAllBodies()]
    p("bodies:", [str(b.GetName()) for b in bodies])
    for b in bodies:
        try:
            p("   body", b.GetName(), "shape:", b.Shape)
        except Exception as e:
            p("   body shape err", e)
except Exception as e:
    p("inspect fail:", e)
    traceback.print_exc(file=logf)

p("\n--- done ---")
logf.close()
