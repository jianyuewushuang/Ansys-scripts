"""Probe 7: minimal FTM path; does the tunnel get surface-meshed? Compare extraction methods."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"


def variant(extraction, add_size_control=False, do_identify=False):
    print(f"\n############ VARIANT extraction={extraction} "
          f"size_control={add_size_control} identify={do_identify} ############", flush=True)
    s = launch_fluent(mode="meshing", processor_count=2, precision="double",
                      cwd=BASE + "/mesh_work")
    ftm = s.fault_tolerant()
    WFO = ftm._workflow.task_object

    def T(p, i=0):
        h = getattr(WFO, p)
        return h[h.get_object_names()[i]]

    T("import_cad_and_part_management").arguments.set_state(
        {"fmd_file_name": BASE + "/1.stl", "length_unit": "m",
         "create_object_per": "One per part", "route": "Native"})
    T("import_cad_and_part_management").execute()

    T("describe_geometry_and_flow").arguments.set_state(
        {"flow_type": "External flow around object", "add_enclosure": True})
    T("describe_geometry_and_flow").execute()

    T("create_external_flow_boundaries").arguments.set_state({
        "creation_method": "Create new boundary", "selection_type": "object",
        "object_selection_list": ["object1"], "extraction_method": extraction,
        "external_boundaries_name": "tunnel",
        "bounding_box_object": {"size_relative_length": "Ratio relative to geometry size",
                                "xmin_ratio": 1.5, "xmax_ratio": 2.5,
                                "ymin_ratio": 1.0, "ymax_ratio": 1.0,
                                "zmin_ratio": 6.0, "zmax_ratio": 6.0}})
    T("create_external_flow_boundaries").execute()
    print("tunnel created", flush=True)

    if do_identify:
        T("identify_regions").arguments.set_state(
            {"new_region_type": "fluid", "selection_type": "object",
             "mpt_method_type": "Offset Method", "object_selection_list": ["tunnel"],
             "offset_x": 15.0, "offset_y": 0.0, "offset_z": 5.0})
        T("identify_regions").execute()
        print("identify done", flush=True)

    if add_size_control:
        T("setup_size_controls").arguments.set_state({
            "object_selection_list": ["object1", "tunnel"],
            "local_size_control_parameters": {
                "sizing_type": "curvature", "curvature_normal_angle": 18.0,
                "min_size": 0.15, "max_size": 2.0, "growth_rate": 1.2,
                "scope_proximity_to": "faces-and-edges",
                "initial_size_control": False, "target_size_control": False}})
        T("setup_size_controls").execute()

    T("generate_surface_mesh").execute()
    print("surface mesh done", flush=True)

    for n in ("compute_regions", "update_boundaries"):
        try:
            T(n).execute()
        except Exception as e:
            print(n, "fail", e)

    T("create_volume_mesh_ftm").arguments.set_state(
        {"fill_with_size_field": True, "quality_method": "Orthogonal"})
    T("create_volume_mesh_ftm").execute()
    print("volume mesh done", flush=True)
    s.exit()


variant("surface mesh")
variant("wrap")
variant("surface mesh", add_size_control=True, do_identify=True)
print("\nALL VARIANTS DONE")
