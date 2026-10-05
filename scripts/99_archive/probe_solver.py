"""Probe: read the mesh in the solver and list boundary zones + API structure."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
MSH = BASE + "/artifacts/mesh/aircraft_mesh.msh.h5"

s = launch_fluent(mode="solver", processor_count=2, precision="double", cwd=BASE + "/work")
print("LAUNCH OK", flush=True)
s.settings.file.read(file_type="mesh", file_name=MSH)
print("MESH READ OK", flush=True)

print("\n=== top-level attrs ===")
print([a for a in dir(s) if not a.startswith("_")][:80])

print("\n=== mesh size / cell count ===")
try:
    print(s.mesh.get_mesh_size())
except Exception as e:
    print("get_mesh_size fail:", type(e).__name__, e)

print("\n=== boundary zones ===")
try:
    bcs = s.settings.setup.boundary_conditions
    for grp in bcs.get_object_names():
        try:
            holders = getattr(bcs, grp)
            for n in holders.get_object_names():
                print(f"   {grp:24s} :: {n}")
        except Exception as e:
            print(f"   {grp} fail {type(e).__name__} {e}")
except Exception as e:
    print("bc listing fail:", type(e).__name__, e)

print("\n=== cell zones ===")
try:
    cz = s.settings.setup.cell_zone_conditions
    print(cz.get_object_names())
except Exception as e:
    print("cz fail:", type(e).__name__, e)

print("\n=== models / materials available ===")
try:
    print("models:", s.settings.setup.models.get_object_names())
except Exception as e:
    print("models fail:", e)
try:
    print("materials:", s.settings.setup.materials.get_object_names())
except Exception as e:
    print("materials fail:", e)

print("\n=== one velocity-inlet-like zone structure (if any) ===")
try:
    bcs = s.settings.setup.boundary_conditions
    for grp in ("velocity_inlet", "pressure_outlet"):
        h = getattr(bcs, grp)
        names = h.get_object_names()
        print(f"  {grp}: {names}")
except Exception as e:
    print("n/a", e)

s.exit()
print("\nDONE")
