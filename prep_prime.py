"""Identify and remove the airframe-interior cell zone from the Prime mesh."""
import os
import numpy as np

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
MESH = os.environ.get("MSH", BASE + "/aircraft_mesh_prime.msh.h5")

s = launch_fluent(mode="solver", precision="double", processor_count=2,
                  cwd=BASE + "/mesh_work")
st = s.settings
st.file.read(file_type="mesh", file_name=MESH)
print("=== zones ===", flush=True)
print(s.execute_tui("define/boundary-conditions/list-zones"), flush=True)

names = []
for g in ("fluid", "solid"):
    o = getattr(st.setup.cell_zone_conditions, g, None)
    if o is None:
        continue
    try:
        names += [(g, n) for n in (o().keys() if callable(o) else [])]
    except Exception as e:
        print(g, str(e)[:80], flush=True)
print("cell zones:", names, flush=True)

fd = getattr(s, "field_data", None) or s.fields.field_data
from ansys.fluent.core.fields.field_data_interfaces import ScalarFieldDataRequest

bcs = st.setup.boundary_conditions
walls = list(bcs.wall().keys()) if callable(bcs.wall) else []
print("walls:", walls, flush=True)

# bbox of each cell zone via the extreme coordinates of its cells
for grp, nm in names:
    try:
        r = fd.get_field_data(ScalarFieldDataRequest(
            surfaces=[nm], field_name="x-coordinate", node_value=False,
            boundary_value=False))
        v = np.asarray(r[nm]).ravel()
        print("   %-16s n=%d  x[%.2f, %.2f]" % (nm, v.size, v.min(), v.max()),
              flush=True)
    except Exception as e:
        print("   %s err %s" % (nm, str(e)[:90]), flush=True)

s.exit()
print("PREP DONE", flush=True)
