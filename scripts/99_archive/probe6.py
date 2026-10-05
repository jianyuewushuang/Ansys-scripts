"""Probe 6: find the coordinate input for the fluid material point."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/work")
print("LAUNCH OK", flush=True)
ftm = s.fault_tolerant()
WFO = ftm._workflow.task_object


def T(pyname, idx=0):
    holder = getattr(WFO, pyname)
    names = holder.get_object_names()
    return holder[names[idx]]


def dump(pyname, tag=""):
    t = T(pyname)
    print(f"\n--- {pyname} {tag} ---")
    try:
        for k, v in t.arguments().items():
            av = ""
            try:
                sub = getattr(t.arguments, k)
                if hasattr(sub, "allowed_values"):
                    a = sub.allowed_values()
                    if a:
                        av = f"  ALLOWED={a}"
            except Exception:
                pass
            print(f"    {k:30s} = {v!r}{av}")
    except Exception as e:
        print("    fail", e)


T("import_cad_and_part_management").arguments.set_state(
    {"fmd_file_name": BASE + "/data/1.stl", "length_unit": "m",
     "create_object_per": "One per part", "route": "Native"})
T("import_cad_and_part_management").execute()
print("imported", flush=True)

T("describe_geometry_and_flow").arguments.set_state(
    {"flow_type": "External flow around object", "add_enclosure": True})
T("describe_geometry_and_flow").execute()

T("create_external_flow_boundaries").arguments.set_state({
    "creation_method": "Create new boundary", "selection_type": "object",
    "object_selection_list": ["object1"], "extraction_method": "surface mesh",
    "external_boundaries_name": "tunnel",
    "bounding_box_object": {"size_relative_length": "Ratio relative to geometry size",
                            "xmin_ratio": 1.5, "xmax_ratio": 3.5,
                            "ymin_ratio": 1.0, "ymax_ratio": 1.0,
                            "zmin_ratio": 6.0, "zmax_ratio": 6.0}})
T("create_external_flow_boundaries").execute()
print("tunnel created", flush=True)

ir = T("identify_regions")
dump("identify_regions", "[default]")

for mode in ("Numerical Inputs", "Offset Method"):
    try:
        ir.arguments.set_state({"mpt_method_type": mode})
        dump("identify_regions", f"[{mode}]")
    except Exception as e:
        print(mode, "fail", e)

# now try enabling show_coordinates
try:
    ir.arguments.set_state({"show_coordinates": True})
    dump("identify_regions", "[show_coordinates=True]")
except Exception as e:
    print("show_coordinates fail", e)

s.exit()
print("\nDONE")
