"""Probe 9: identify_regions is a Compound task - create/configure its child properly."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/mesh_work")
print("LAUNCH OK", flush=True)
ftm = s.fault_tolerant()
WFO = ftm._workflow.task_object


def Holder(p):
    return getattr(WFO, p)


def T(p, i=0):
    h = Holder(p)
    return h[h.get_object_names()[i]]


def children(p):
    try:
        return Holder(p).get_object_names()
    except Exception as e:
        return f"<{type(e).__name__} {e}>"


def ex(p, i=0):
    try:
        T(p, i).execute()
        print(f"  >> {p} executed")
    except Exception as e:
        print(f"  !! {p} {type(e).__name__} {e}")


T("import_cad_and_part_management").arguments.set_state(
    {"fmd_file_name": BASE + "/1.stl", "length_unit": "m",
     "create_object_per": "One per part", "route": "Native"})
ex("import_cad_and_part_management")

T("describe_geometry_and_flow").arguments.set_state(
    {"flow_type": "External flow around object", "add_enclosure": True})
ex("describe_geometry_and_flow")

T("create_external_flow_boundaries").arguments.set_state({
    "creation_method": "Create new boundary", "selection_type": "object",
    "object_selection_list": ["object1"], "extraction_method": "surface mesh",
    "external_boundaries_name": "tunnel",
    "bounding_box_object": {"size_relative_length": "Ratio relative to geometry size",
                            "xmin_ratio": 1.5, "xmax_ratio": 2.5,
                            "ymin_ratio": 1.0, "ymax_ratio": 1.0,
                            "zmin_ratio": 6.0, "zmax_ratio": 6.0}})
ex("create_external_flow_boundaries")

print("\nidentify_regions children BEFORE:", children("identify_regions"))
ir = T("identify_regions")
ir.arguments.set_state({"new_region_type": "fluid", "selection_type": "object",
                        "mpt_method_type": "Offset Method",
                        "object_selection_list": ["tunnel"],
                        "offset_x": 15.0, "offset_y": 0.0, "offset_z": 5.0,
                        "add_child": True})
ex("identify_regions")
print("identify_regions children AFTER :", children("identify_regions"))

# if a child was created, dump + execute it
ch = children("identify_regions")
if isinstance(ch, list) and len(ch) > 1:
    for i in range(1, len(ch)):
        print(f"\n--- child[{i}] = {ch[i]} ---")
        try:
            cT = Holder("identify_regions")[ch[i]]
            for k, v in cT.arguments().items():
                print(f"    {k:32s} = {v!r}")
        except Exception as e:
            print("    dump fail", e)
        ex("identify_regions", i)
        print("    children now:", children("identify_regions"))
else:
    print("no compound child was created")

ex("generate_surface_mesh")
ex("compute_regions")

t = T("update_region_settings")
print("\n--- update_region_settings AFTER ---")
for k, v in t.arguments().items():
    print(f"    {k:34s} = {v!r}")

s.exit()
print("\nDONE")
