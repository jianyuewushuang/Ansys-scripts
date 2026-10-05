"""Check whether a mesh keeps the aircraft wall as a real boundary."""
import os, sys
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
MSH = sys.argv[1] if len(sys.argv) > 1 else BASE + "/artifacts/mesh/aircraft_mesh.msh.h5"

s = launch_fluent(mode="solver", processor_count=2, precision="double", cwd=BASE + "/work")
out = str(s.execute_tui(f'file/read-case "{MSH}"'))
print("=== read-case output (key lines) ===")
for line in out.splitlines():
    if any(k in line for k in ("cells,", "cell zone", "faces,", "nodes,", "Skipping",
                               "Removing", "zone id", "Error", "warning")):
        print("   ", line.strip())
print("\naircraft kept:", "not referenced by grid" not in out)
print("\n=== zones ===")
print(str(s.execute_tui("define/boundary-conditions/list-zones")))
s.exit()
