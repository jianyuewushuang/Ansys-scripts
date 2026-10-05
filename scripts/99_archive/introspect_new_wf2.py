"""Introspect NEW workflow tasks via children()."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

s = launch_fluent(mode="meshing", processor_count=2, precision="double",
                  cwd=rBASE + "/work")
print("LAUNCH OK", flush=True)
ftm = s.fault_tolerant()

kinds = getattr(ftm, "_cache", {})
print("cache:", kinds)

for t in ftm.children():
    name = getattr(t, "_name", "?")
    try:
        to = t._task_object
        tt = to.task_type()
        args = to.arguments()
        print(f"\n===== {name}   [type={tt}]")
        if not args:
            print("      (no arguments populated yet)")
        for k, v in args.items():
            print(f"      {k:30s} = {v!r}")
    except Exception as e:
        print(f"\n===== {name}: {type(e).__name__} {e}")

s.exit()
print("\nDONE")
