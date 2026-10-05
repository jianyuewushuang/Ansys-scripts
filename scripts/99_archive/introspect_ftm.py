"""Start the Fault-Tolerant meshing workflow and dump tasks + arguments."""
import os, json
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

s = launch_fluent(mode="meshing", processor_count=2, precision="double",
                  cwd=rBASE + "/work")
print("=== LAUNCH OK ===", flush=True)

try:
    s.fault_tolerant()
    print("fault_tolerant() started", flush=True)
except Exception as e:
    print("fault_tolerant() fail:", type(e).__name__, e, flush=True)

wf = s.workflow
names = wf.TaskObject.get_object_names()
print("\n=== FTM TASK LIST ===")
for n in names:
    print("  -", n)

for n in names:
    try:
        t = wf.TaskObject[n]
        args = t.Arguments.get_object_names()
        if not args:
            continue
        print(f"\n===== {n} | state={t.State()} =====")
        for a in args:
            try:
                val = t.Arguments[a].get_attr("value")
                typ = t.Arguments[a].get_attr("type")
                opts = None
                if typ in ("string-list", "string"):
                    try:
                        opts = t.Arguments[a].get_attr("allowed-values")
                    except Exception:
                        opts = None
                line = f"   {a:38s} = {val!r}"
                if opts:
                    line += f"   allowed={opts}"
                print(line)
            except Exception as e:
                print(f"   {a:38s} <err {type(e).__name__}>")
    except Exception as e:
        print(f"task {n} fail: {type(e).__name__} {e}")

s.exit()
print("\n=== DONE ===")
