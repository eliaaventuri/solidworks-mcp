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

                ok_gcp, _, data_gcp = await c.call("get_config_custom_property", property_name="PartNumber", configuration="Default")
                letto_gcp = (data_gcp or {}).get("value") or (data_gcp or {}).get("resolved")
                record("get_config_custom_property", ok_gcp and letto_gcp == "SW-1002", f"letto {letto_gcp!r}")

                ok_smd, _, _ = await c.call("set_document_summary_info", title="Staffa Robotica", author="Elia", comments="Release 8.3")
                record("set_document_summary_info", ok_smd)

                # 3. Equazioni
                ok_aeq, _, _ = await c.call("add_equation", equation='"TestVar" = 12')
                ok_eqx, text_eqx, _ = await c.call("export_equations_to_file", filepath=str(EQ_OUT), overwrite=True)
                contenuto_eq = EQ_OUT.read_text(encoding="utf-8") if EQ_OUT.exists() else ""
                record("export_equations_to_file", ok_aeq and ok_eqx and "TestVar" in contenuto_eq, text_eqx[:120])

                # 4. Configurazioni e Tabelle di Progettazione
                ok_idt, text_idt, _ = await c.call("insert_design_table", blank=True)
                record("insert_design_table: rifiutato perche' non implementato", (not ok_idt) and "non e' implementato" in text_idt,
                       text_idt[:80])

                ok_dcf, _, _ = await c.call("create_derived_configuration", name="Config_Machined", parent_configuration="Default")
                record("create_derived_configuration", ok_dcf)

                # 6. Esportazione Modelli 3D e CAD Neutri
                ok_242, text_242, _ = await c.call("export_step_ap242_pmi", filepath=str(STEP_OUT), overwrite=True)
                record("export_step_ap242_pmi: rifiutato perche' non implementato", (not ok_242) and "non e' implementato" in text_242,
                       text_242[:80])

                ok_dxf, _, _ = await c.call("export_dxf_flat_pattern", filepath=str(DXF_OUT), overwrite=True)
                record("export_dxf_flat_pattern", ok_dxf)

                ok_jt, text_jt, _ = await c.call("export_jt", filepath=str(JT_OUT), overwrite=True)
                record("export_jt: rifiutato perche' non implementato", (not ok_jt) and "non e' implementato" in text_jt, text_jt[:80])

                ok_ifc, _, _ = await c.call("export_ifc", filepath=str(IFC_OUT), overwrite=True, schema_version="IFC2X3")
                ifc_head = IFC_OUT.read_bytes()[:65536].decode("latin-1") if IFC_OUT.exists() else ""
                record("export_ifc", ok_ifc and ifc_head.startswith("ISO-10303-21") and "IFC2X3" in ifc_head,
                       f"{IFC_OUT.stat().st_size if IFC_OUT.exists() else 0} byte")

                ok_glb, _, _ = await c.call("export_gltf_glb", filepath=str(GLB_OUT), overwrite=True)
                glb_head = GLB_OUT.read_bytes()[:4] if GLB_OUT.exists() else b""
                record("export_gltf_glb", ok_glb and glb_head == b"glTF", f"{GLB_OUT.stat().st_size if GLB_OUT.exists() else 0} byte")

                ok_3dp, _, data_3dp = await c.call("export_3d_pdf", filepath=str(PDF3D_OUT), overwrite=True)
                pdf_head = PDF3D_OUT.read_bytes()[:5] if PDF3D_OUT.exists() else b""
                has_3d = ((data_3dp or {}).get("verify") or {}).get("has_3d")
                record("export_3d_pdf", ok_3dp and pdf_head == b"%PDF-" and has_3d is True, f"has_3d={has_3d}")

                # 7. Quotatura 3D MBD / DimXpert (PMI)
                ok_nim, text_nim, _ = await c.call("add_dimxpert_dimension", face1_point=[0, 0, 25], dimension_type="size")
                record("add_dimxpert_dimension: rifiutato perche' non implementato", (not ok_nim) and "non e' implementato" in text_nim, text_nim[:80])

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
