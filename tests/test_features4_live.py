"""
Live test for Lotto MODELLAZIONE 4 (33 tools) against dedicated hidden SolidWorks instance.
"""

import math
import os
import sys
import asyncio
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from live_common import ROOT, OUT, PYTHON, SERVER, sw_pids, Client, cleanup, EXPECTED_TOOLS

PART = OUT / "test_features4_live_part.SLDPRT"

RESULTS = []


def record(name, ok, note=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}"[:180])


async def feats(c):
    ok, _, d = await c.call("list_features", detail=True)
    return d.get("features", []) if ok else []


async def bodies(c):
    ok, _, d = await c.call("list_bodies")
    return d.get("bodies", []) if ok else []


async def vol(c):
    ok, _, d = await c.call("get_mass_properties")
    return float(d.get("volume_mm3", -1.0)) if ok else -1.0


def sketches(fs):
    return [f["name"] for f in fs if f["type"] == "ProfileFeature"]


def near(v, exp, tol_rel=0.001):
    return abs(v - exp) <= tol_rel * abs(exp)


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
                # Setup: Model Part for Features 4
                # =============================================================
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=-60, y1=-40, x2=60, y2=40, unit="mm")
                await c.call("extrude_boss", depth=30, unit="mm")
                await c.call("save_document", filepath=str(PART), overwrite=True)

                # =============================================================
                # Test Suite Features 4 Live (33 tools)
                # =============================================================
                print("\n--- Test Features 4 Tools Live ---")

                # 1. Estrusioni, Rivoluzioni e Tagli Solidi
                ok_nim, text_nim, _ = await c.call("extrude_from_surface", depth=10.0, offset_distance=2.0)
                record("extrude_from_surface: rifiutato perche' non implementato", (not ok_nim) and "non e' implementato" in text_nim, text_nim[:80])

                # intersect: corpo B 40x20x30 dentro il corpo A 120x80x30 -> intersezione = B = 24000 mm3
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=-60, y1=-40, x2=60, y2=40, unit="mm")
                await c.call("extrude_boss", depth=30, unit="mm")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=-20, y1=-10, x2=20, y2=10, unit="mm")
                await c.call("close_sketch")
                sk = sketches(await feats(c))
                await c.call("extrude_boss", sketch=sk[-1], depth=30, merge=False, unit="mm")
                nb0 = len(await bodies(c))
                ok_isf, text_isf, _ = await c.call("intersect_solid_features", body_names=[b["name"] for b in await bodies(c)])
                v_isf, nb_isf = await vol(c), len(await bodies(c))
                record("intersect_solid_features", ok_isf and near(v_isf, 24000.0) and nb_isf == 1,
                       f"corpi {nb0} -> {nb_isf}, volume {v_isf:.1f} contro 24000.0 (40x20x30)")
                await c.call("close_document", discard=True)

                # 2. Loft, Sweep e Boundary Solidi
                ok_nim, text_nim, _ = await c.call("solid_sweep", tool_body_name="SolidBody1", path_sketch="Sketch1")
                record("solid_sweep: rifiutato perche' non implementato", (not ok_nim) and "non e' implementato" in text_nim, text_nim[:80])

                # sweep a sezione (variabile con guide): profilo circolare r=5 lungo una linea di 60 mm -> pi*r^2*60
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_line", x1=0, y1=0, x2=60, y2=0)
                await c.call("close_sketch")
                await c.call("create_sketch", plane="Right")
                await c.call("draw_circle", x=0, y=0, radius=5)
                await c.call("close_sketch")
                sk = sketches(await feats(c))
                ok_vss, text_vss, _ = await c.call("variable_section_sweep", profile_sketch=sk[1], path_sketch=sk[0], scale_factor=1.0)
                v_vss = await vol(c)
                record("variable_section_sweep", ok_vss and near(v_vss, math.pi * 25 * 60),
                       f"volume {v_vss:.2f} contro {math.pi * 25 * 60:.2f} (pi*5^2*60)")
                ok_vss2, text_vss2, _ = await c.call("variable_section_sweep", profile_sketch=sk[1], path_sketch=sk[0], scale_factor=1.2)
                record("variable_section_sweep: scale_factor 1.2 rifiutato", (not ok_vss2) and "non supportato" in text_vss2, text_vss2[:80])
                await c.call("close_document", discard=True)

                # 3. Raccordi, Smussi e Lavorazioni Spigoli
                ok_nim, text_nim, _ = await c.call("setback_fillet", vertex_point=[60, 40, 30], radius=5.0)
                record("setback_fillet: rifiutato perche' non implementato", (not ok_nim) and "non e' implementato" in text_nim, text_nim[:80])

                # 6. Ripetizioni e Simmetrie 3D: corpo asimmetrico (y 10..70, z -40..20) specchiato sul piano Top (z=0)
                #    -> unione con lo specchio (z -40..40): 30 x 60 x 80 = 144000 mm3
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=10, y1=-40, x2=70, y2=20, unit="mm")
                await c.call("extrude_boss", depth=30, unit="mm")
                nbody = [b["name"] for b in await bodies(c)]
                nf0 = len(await feats(c))
                ok_mbm, text_mbm, _ = await c.call("mirror_body_merge", body_names=nbody, mirror_plane="Top", merge_bodies=True)
                v_mbm, nb_mbm, nf_mbm = await vol(c), len(await bodies(c)), len(await feats(c))
                record("mirror_body_merge", ok_mbm and near(v_mbm, 144000.0) and nb_mbm == 1 and nf_mbm > nf0,
                       f"volume {v_mbm:.1f} contro 144000.0, corpi {nb_mbm}, feature {nf0} -> {nf_mbm}")
                await c.call("close_document", discard=True)

                # 7. Gestione Multibody (Booleane e Tagli)
                ok_nim, text_nim, _ = await c.call("body_replace_face", target_face_points=[[0, 0, 30]], surface_name="SurfaceBody1")
                record("body_replace_face: rifiutato perche' non implementato", (not ok_nim) and "non e' implementato" in text_nim, text_nim[:80])

                # 9. Lamiera (Sheet Metal)
                ok_cb, _, _ = await c.call("cross_break", face_point=[0, 0, 30], depth=1.0, break_angle=2.0)
                record("cross_break", ok_cb)

                # conversione in lamiera di un box 120x80x30 (faccia fissa z=40): prova = volume cambiato
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=-60, y1=-40, x2=60, y2=40, unit="mm")
                await c.call("extrude_boss", depth=30, unit="mm")
                v_csm0 = await vol(c)
                ok_csm, text_csm, _ = await c.call("convert_to_sheet_metal", thickness=2.0, bend_radius=2.5, fixed_face_point=[15, 0, 40])
                v_csm1 = await vol(c)
                # con la sola faccia fissa (nessuno spigolo di piega) resta la lamiera della faccia 120x30: 120 x 30 x 2 = 7200 mm3
                record("convert_to_sheet_metal: volume = faccia fissa 120x30 x spessore 2 = 7200 mm3", ok_csm and abs(v_csm1 - 7200.0) < 0.5,
                       f"volume {v_csm0:.1f} -> {v_csm1:.1f}")
                await c.call("close_document", discard=True)

                ok_nim, text_nim, _ = await c.call("loft_bend", profile1_sketch="Sketch1", profile2_sketch="Sketch1", thickness=1.5, bend_count=4)
                record("loft_bend: rifiutato perche' non implementato", (not ok_nim) and "non e' implementato" in text_nim, text_nim[:80])

                # 10. Saldature e Strutture Metalliche
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_rectangle", x1=-60, y1=-40, x2=60, y2=40, unit="mm")
                await c.call("extrude_boss", depth=30, unit="mm")
                ok_nim, text_nim, _ = await c.call("cosmetic_weld_bead", face_from_point=[0, 0, 0], face_to_point=[15, -60, 0], bead_size=4.0)
                record("cosmetic_weld_bead: rifiutato perche' non implementato", (not ok_nim) and "non e' implementato" in text_nim, text_nim[:80])
                await c.call("close_document", discard=True)

                # distinta e sotto-saldatura su un profilato strutturale 200 mm
                await c.call("create_new_part")
                await c.call("create_sketch", plane="Front")
                await c.call("draw_line", x1=0, y1=0, x2=200, y2=0)
                await c.call("close_sketch")
                await c.call("structural_member", standard="iso", profile="square tube", size="40 x 40 x 4")
                await c.call("weldment_cut_list", update=True)
                ok_ucl, text_ucl, _ = await c.call("update_cut_list", force_rebuild=True)
                record("update_cut_list", ok_ucl, text_ucl[:90])
                wb = await bodies(c)
                nf_sw0 = len(await feats(c))
                ok_swf, text_swf, _ = await c.call("subweldment_folder", folder_name="MainFrame", member_names=[wb[0]["name"]])
                record("subweldment_folder", ok_swf and len(await feats(c)) == nf_sw0 + 1,
                       f"feature {nf_sw0} -> {len(await feats(c))}: {text_swf[:60]}")

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
