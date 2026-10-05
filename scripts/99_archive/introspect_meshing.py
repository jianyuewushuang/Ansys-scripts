"""Introspect Fluent Meshing workflows to confirm external-flow / enclosure options."""
import os, sys, traceback
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")

from ansys.fluent.core import launch_fluent

s = launch_fluent(mode="meshing", processor_count=2, precision="double",
                  cwd=rBASE + "/work")
print("=== LAUNCH OK ===", flush=True)

try:
    m = s.meshing
    print("\n=== meshing root children (subset) ===")
    kids = [k for k in dir(m) if not k.startswith("_")]
    print(kids)
except Exception as e:
    print("meshing attr fail", e)

for api in ("workflow", "watertight", "fault_tolerant"):
    try:
        obj = getattr(s, api)
        print(f"\n=== s.{api} type: {type(obj)}")
    except Exception as e:
        print(f"s.{api}: {type(e).__name__} {e}")

# workflow tasks
try:
    wf = s.workflow
    print("\n=== workflow tasks ===")
    for t in wf.TaskObject.get_object_names():
        print("  -", t)
except Exception as e:
    print("workflow list fail:", e)

# FTM describe-geometry-and-flow args
for task in ("DescribeGeometryAndFlow", "DescribeGeometryAndFlow_1", "DescribeGeometry"):
    try:
        t = s.workflow.TaskObject[task]
        print(f"\n=== {task} arguments ===")
        for name in t.Arguments.get_object_names():
            a = t.Arguments[name]
            print(f"  {name}: {a.get_attr('value')!r}  ({a.get_attr('type')})")
    except Exception as e:
        print(f"{task}: {type(e).__name__} {e}")

s.exit()
print("\n=== DONE ===")
