"""Introspect the NEW (26R1) meshing workflow API: task names + arguments."""
import os, json
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

s = launch_fluent(mode="meshing", processor_count=2, precision="double",
                  cwd=rBASE + "/work")
print("LAUNCH OK", flush=True)

ftm = s.fault_tolerant()
print("workflow class:", type(ftm).__name__)

names = ftm.task_names()
print("\n=== TASK NAMES (display) ===")
for n in names:
    print("  -", n)

print("\n=== TASKS: python attr -> arguments ===")
for display in names:
    # find the snake_case attribute for this display name
    try:
        wf = ftm._workflow if hasattr(ftm, "_workflow") else None
    except Exception:
        wf = None
    try:
        task_obj = ftm._task_object[display]
    except Exception as e:
        print(f"\n-- {display}: cannot access ({type(e).__name__})")
        continue
    try:
        args = task_obj.arguments
        argdict = args()
        print(f"\n-- {display}   (task_type={task_obj.task_type()})")
        for k, v in argdict.items():
            print(f"     {k:32s} = {v!r}")
    except Exception as e:
        print(f"\n-- {display}: args fail {type(e).__name__} {e}")

# also show what snake_case attrs are available on the workflow
print("\n=== workflow attrs (snake_case) ===")
import re
print([a for a in dir(ftm) if not a.startswith("_")])

s.exit()
print("\nDONE")
