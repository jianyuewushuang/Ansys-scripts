"""Quick sanity check of the AoA=0 solution field."""
import os
import numpy as np

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent
from ansys.fluent.core.fields.field_data_interfaces import (
    ScalarFieldDataRequest, SurfaceDataType, SurfaceFieldDataRequest)

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"

s = launch_fluent(mode="solver", precision="double", processor_count=2,
                  cwd=BASE + "/mesh_work")
st = s.settings
st.file.read(file_type="case-data", file_name=BASE + "/final_aoa0.cas.h5")
fd = getattr(s, "field_data", None) or s.fields.field_data

print("operating pressure:", s.execute_tui(
    "define/operating-conditions/operating-pressure"), flush=True)
print("reference values:", st.setup.reference_values.get_state(), flush=True)

s.execute_tui("/surface/plane-surface sym_y0 point-and-normal 0 0 0 0 1 0")
s.execute_tui("/surface/plane-surface far_x point-and-normal -30 0 0 1 0 0")


def sc(surf, field):
    try:
        r = fd.get_field_data(ScalarFieldDataRequest(
            surfaces=[surf], field_name=field, node_value=True,
            boundary_value=True))
        return np.asarray(r[surf]).ravel()
    except Exception as e:
        print("  !", surf, field, str(e)[:90], flush=True)
        return None


for surf in ("aircraft-fluid_box", "fluid_box:1", "sym_y0", "far_x"):
    print("\n---", surf, flush=True)
    for fld in ("pressure", "velocity-magnitude", "density", "temperature",
                "mach-number"):
        v = sc(surf, fld)
        if v is None:
            continue
        v = v[np.isfinite(v)]
        if not len(v):
            continue
        print("   %-20s min %12.3f  mean %12.3f  max %12.3f"
              % (fld, v.min(), v.mean(), v.max()), flush=True)

s.exit()
print("CHECK DONE", flush=True)
