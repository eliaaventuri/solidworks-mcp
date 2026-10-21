"""
Live test for Lotto DATI ED EXPORT 2 (24 tools) against dedicated hidden SolidWorks instance.
"""

import os
import sys
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

PART = OUT / "test_data2_live_part.SLDPRT"
EQ_OUT = OUT / "test_equations_live.txt"
DT_OUT = OUT / "test_design_table_live.csv"
STEP_OUT = OUT / "test_ap242_live.step"
DXF_OUT = OUT / "test_flat_pattern_live.dxf"
JT_OUT = OUT / "test_model_live.jt"
IFC_OUT = OUT / "test_model_live.ifc"
GLB_OUT = OUT / "test_model_live.glb"
PDF3D_OUT = OUT / "test_model_3d_live.pdf"

RESULTS = []


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:180])


async def run():
    elia_pids = sw_pids()
    print(f"Istanze SolidWorks pre-esistenti: {sorted(elia_pids)}")
    env = dict(os.environ)
    env["SW_MCP_INSTANCE"] = "dedicated"
    env["SW_MCP_ALLOW_PYTHON"] = "1"
    params = StdioServerParameters(command=str(PYTHON), args=[str(SERVER)], env=env, cwd=str(ROOT))
    my_pid = None
    try:
        async with stdio_client(params) as (rd, wr):
            async with ClientSession(rd, wr, read_timeout_seconds=timedelta(seconds=600)) as session:
                await session.initialize()
                c = Client(session)
                tools = [t.name for t in (await session.list_tools()).tools]
                record("tools count", len(tools) == EXPECTED_TOOLS, f"{len(tools)} tools (expected {EXPECTED_TOOLS})")

                ok, text, data = await c.call("connect_solidworks")
                my_pid = data.get("pid")
                print(f"Connesso a istanza SolidWorks dedicata: PID {my_pid}")
                record("connect_solidworks", ok)

                # =============================================================
                # Setup: Model Part for Data 2
                # =============================================================
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=-50, y1=-30, x2=50, y2=30, unit="mm")
                await c.call("extrude_sketch", depth=25, unit="mm")
                await c.call("save_document", filepath=str(PART), overwrite=True)

                # =============================================================
                # Test Suite Data 2 Live (24 tools)
                # =============================================================
                print("\n--- Test Data 2 Tools Live ---")

                # 1. Proprietà Personalizzate e Metadati
                ok_scp, _, _ = await c.call("set_config_custom_property", property_name="PartNumber", value="SW-1002", configuration="Default")
                record("set_config_custom_property", ok_scp)

                ok_gcp, _, _ = await c.call("get_config_custom_property", property_name="PartNumber", configuration="Default")
                record("get_config_custom_property", ok_gcp)

                ok_smd, _, _ = await c.call("set_document_summary_info", title="Staffa Robotica", author="Elia", comments="Release 8.3")
                record("set_document_summary_info", ok_smd)

                # 2. Materiali
                ok_cmat, _, _ = await c.call("create_custom_material", material_name="Titanium_Alloy_Ti6Al4V", density=4430.0, elastic_modulus=114000.0)
                record("create_custom_material", ok_cmat)

                # 3. Equazioni
                ok_eqx, text_eqx, _ = await c.call("export_equations_to_file", filepath=str(EQ_OUT), overwrite=True)
                record("export_equations_to_file", ok_eqx, text_eqx[:120])

                # 4. Configurazioni e Tabelle di Progettazione
                ok_idt, _, _ = await c.call("insert_design_table", blank=True)
                record("insert_design_table", ok_idt)

                ok_edt, _, _ = await c.call("edit_design_table", row_index=1, column_name="D1@Sketch1", value="120")
                record("edit_design_table", ok_edt)

                ok_xdt, _, _ = await c.call("export_design_table", filepath=str(DT_OUT), overwrite=True)
                record("export_design_table", ok_xdt)

                ok_dcf, _, _ = await c.call("create_derived_configuration", name="Config_Machined", parent_configuration="Default")
                record("create_derived_configuration", ok_dcf)

                # 5. Misure Geometriche e Massa
                ok_pja, _, _ = await c.call("get_projected_area", direction=[0, 0, 1])
                record("get_projected_area", ok_pja)

                ok_cle, _, _ = await c.call("calculate_clearance_envelope", clearance_offset=8.0)
                record("calculate_clearance_envelope", ok_cle)

                # 6. Esportazione Modelli 3D e CAD Neutri
                ok_242, _, _ = await c.call("export_step_ap242_pmi", filepath=str(STEP_OUT), overwrite=True)
                record("export_step_ap242_pmi", ok_242)

                ok_dxf, _, _ = await c.call("export_dxf_flat_pattern", filepath=str(DXF_OUT), overwrite=True)
                record("export_dxf_flat_pattern", ok_dxf)

                ok_jt, _, _ = await c.call("export_jt", filepath=str(JT_OUT), overwrite=True)
                record("export_jt", ok_jt)

                ok_ifc, _, _ = await c.call("export_ifc", filepath=str(IFC_OUT), overwrite=True)
                record("export_ifc", ok_ifc)

                ok_glb, _, _ = await c.call("export_gltf_glb", filepath=str(GLB_OUT), overwrite=True)
                record("export_gltf_glb", ok_glb)

                ok_3dp, _, _ = await c.call("export_3d_pdf", filepath=str(PDF3D_OUT), overwrite=True)
                record("export_3d_pdf", ok_3dp)

                # 7. Quotatura 3D MBD / DimXpert (PMI)
                ok_ddm, _, _ = await c.call("add_dimxpert_dimension", face1_point=[0, 0, 25], dimension_type="size")
                record("add_dimxpert_dimension", ok_ddm)

                ok_ddt, _, _ = await c.call("add_dimxpert_datum", face_point=[0, 0, 25], datum_label="A")
                record("add_dimxpert_datum", ok_ddt)

                ok_dgt, _, _ = await c.call("add_dimxpert_geometric_tolerance", face_point=[0, 0, 25], tolerance_type="flatness", tolerance_value=0.03, datum_reference="A")
                record("add_dimxpert_geometric_tolerance", ok_dgt)

                ok_ads, _, _ = await c.call("auto_dimension_scheme_dimxpert", part_type="prismatic", tolerance_type="geometric")
                record("auto_dimension_scheme_dimxpert", ok_ads)

                ok_lda, _, _ = await c.call("list_dimxpert_annotations")
                record("list_dimxpert_annotations", ok_lda)

                # 8. Rendering e Aspetti
                ok_svb, _, _ = await c.call("set_view_background", background_type="studio")
                record("set_view_background", ok_svb)

                ok_app, _, _ = await c.call("apply_appearance", appearance_name="polished_chrome", color_rgb=[230, 230, 230])
                record("apply_appearance", ok_app)

                # Chiudi documento
                await c.call("close_document", discard=True)

    finally:
        print("\nCleanup istanza dedicata...")
        cleanup(my_pid, elia_pids)

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
