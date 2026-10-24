"""Tool registrati ma NON implementati: il metodo non chiama SolidWorks (o restituisce valori fissi) e prima rispondeva
SUCCESS lo stesso. Revisione del 2026-10-23 (REVISIONE_2026-10-23.md): finche' non vengono riscritti e misurati dal vivo
restano nascosti da list_tools e una chiamata diretta riceve un errore esplicito. Togliere un nome da qui solo insieme a
un'implementazione vera e a un test live che rilegge il risultato da SolidWorks."""

_WHY_NO_COM = "il metodo non chiama SolidWorks: rispondeva SUCCESS senza fare nulla"
_WHY_FIXED = "il metodo restituisce valori fissi, non misurati da SolidWorks"

NOT_IMPLEMENTED = {
    # disegni 2
    "add_relative_view": _WHY_NO_COM,
    "add_predefined_view": _WHY_NO_COM,
    "add_aligned_section_view": _WHY_NO_COM,
    "add_half_section_view": _WHY_NO_COM,
    "add_unfolded_view": _WHY_NO_COM,
    "add_alternate_position_view": _WHY_NO_COM,
    "add_ordinate_dimension": _WHY_NO_COM,
    "add_chamfer_dimension": _WHY_NO_COM,
    "hide_show_dimension": _WHY_NO_COM,
    "add_weld_symbol": _WHY_NO_COM,
    "add_edge_chamfer_symbol": _WHY_NO_COM,
    "add_weldment_cut_list_table": _WHY_NO_COM,
    "set_entity_layer": _WHY_NO_COM,
    "align_drawing_views": "AlignHorz/AlignVert non spostano le viste: coordinate rilette identiche prima e dopo (2 prove dal vivo)",
    "add_centerlines": "InsertCenterLine2 restituisce None e nessuna linea d'asse si rilegge dalle viste (conteggio 0 -> 0, provato dal vivo)",
    "insert_drawing_block": "nessun file .sldblk creabile con i tool attivi per provarlo; la chiamata InsertBlock aveva gli argomenti sbagliati",
    # assiemi 3
    "create_smart_component": _WHY_NO_COM,
    "promote_subassembly_component": _WHY_NO_COM,
    "demote_subassembly_component": _WHY_NO_COM,
    "insert_new_virtual_part": "InsertNewVirtualPart risponde 6 senza componente creato (2 prove dal vivo, con e senza piano)",
    "save_virtual_component_external": "IComponent2.SaveVirtualComponent da' 'Errore interno dell'applicazione' (61704) dal vivo",
    "set_envelope_component": "IComponent2 espone solo IsEnvelope in sola lettura: nessun modo di impostare la busta",
    "lock_mate_rotation": "IMate2 non ha un metodo per bloccare la rotazione (provato dal vivo)",
    "flip_mate_alignment": "nessuna inversione riuscita dal vivo (CanBeFlipped=False sul caso provato, Alignment in sola lettura)",
    "add_cam_mate": "AddMate5 di tipo camma fa chiudere SolidWorks (RPC non disponibile) dal vivo",
    "add_rack_pinion_mate": "AddMate5 di tipo pignone-cremagliera restituisce None senza codice d'errore dal vivo",
    "add_slot_mate": "AddMate5 di tipo asola restituisce None dal vivo; manca una prova su una vera asola",
    # assiemi 2
    "insert_smart_fasteners": _WHY_NO_COM,
    "insert_toolbox_component": _WHY_NO_COM,
    "mate_controller": _WHY_NO_COM,
    "belt_and_chain_feature": _WHY_NO_COM,
    "chain_component_pattern": _WHY_NO_COM,
    "check_hole_alignment": "allineamento sempre True, nessuna misura",
    "pattern_driven_component_pattern": "doppione incompleto di component_derived_pattern (manca il pezzo con la ripetizione)",
    # feature 4
    "thread_lead_in": _WHY_NO_COM,
    "chain_pattern": _WHY_NO_COM,
    "core_cavity_split": _WHY_NO_COM,
    "freeform_surface": _WHY_NO_COM,
    "flatten_surface": _WHY_NO_COM,
    "radiate_surface": _WHY_NO_COM,
    "curved_edge_flange": _WHY_NO_COM,
    "insert_parting_line": _WHY_NO_COM,
    "insert_shut_off_surfaces": _WHY_NO_COM,
    "insert_parting_surface": _WHY_NO_COM,
    "insert_tooling_split": _WHY_NO_COM,
    "insert_lip_and_groove": _WHY_NO_COM,
    "insert_snap_hook": _WHY_NO_COM,
    "insert_mounting_boss": _WHY_NO_COM,
    "mesh_brep_converter": _WHY_NO_COM,
    "surface_deviation_analysis": _WHY_FIXED,
    "extrude_from_surface": "doppione non provato di extrude_boss con start_from=surface (strada gia' misurata)",
    "solid_sweep": "InsertSweep non esiste nella type library: lo sweep con utensile solido non e' raggiungibile cosi'",
    "body_replace_face": "InsertReplaceFaceFeature non esiste; la sostituzione con InsertFeatureReplaceFace non e' ancora provata dal vivo",
    "loft_bend": "InsertLoftedBend non esiste; InsertSheetMetalLoftedBend non provato (manca l'enumerazione dello spessore)",
    "cosmetic_weld_bead": "InsertCosmeticWeldBead non crea nessuna feature dal vivo (2 firme provate)",
    "create_reference_curve_from_equation": "le equazioni non venivano usate",
    "stud_wizard": "chiamava la creazione guidata senza passare nessun parametro (diametro, lunghezza, filetto)",
    "vent_feature": "chiamava la feature senza passare nessun parametro (costole, longheroni)",
    "setback_fillet": "faceva un raccordo semplice, senza arretramento (gia' disponibile come fillet_edges)",
    "curvature_continuous_fillet": "faceva un raccordo semplice, senza continuita' G2 (gia' disponibile come fillet_edges)",
    # feature 3
    "advanced_hole": _WHY_NO_COM,
    "variable_pattern": _WHY_NO_COM,
    "save_bodies_as_parts": "elencava file mai scritti",
    "freeform_feature": "non crea nessuna feature",
    "heal_edges": "non crea nessuna feature",
    # dati 2
    "add_dimxpert_dimension": _WHY_NO_COM,
    "add_dimxpert_datum": _WHY_NO_COM,
    "add_dimxpert_geometric_tolerance": _WHY_NO_COM,
    "auto_dimension_scheme_dimxpert": _WHY_NO_COM,
    "list_dimxpert_annotations": _WHY_FIXED,
    "set_view_background": _WHY_NO_COM,
    "apply_appearance": _WHY_NO_COM,
    "edit_design_table": _WHY_NO_COM,
    "create_custom_material": _WHY_NO_COM,
    "get_projected_area": _WHY_FIXED + " (area sempre 100x100 mm)",
    "calculate_clearance_envelope": _WHY_FIXED,
    "export_design_table": "scriveva una tabella inventata quando la lettura falliva",
    "insert_design_table": "InsertDesignTable/InsertDesignTable2 non esistono nella type library di SolidWorks 2026 (Excel assente)",
    "export_step_ap242_pmi": "SolidWorks 2026 Student scrive AP203 anche con la preferenza AP242 (schema riletto dal file)",
    "export_jt": "SaveAs in JT restituisce False con errore 256 e nessun file (2 prove dal vivo)",
    # schizzo
    "edit_spline_handles": _WHY_NO_COM,
    "get_spline_curvature_analysis": _WHY_FIXED + " (raggio minimo 50 mm, flessi 0)",
    "diagnose_sketch_relations": _WHY_FIXED + " (conflitti sempre 0)",
    "save_sketch_block_to_file": "scriveva un file segnaposto al posto del blocco",
    "insert_intersection_curve": "InsertIntersectionCurve non esiste nella type library di SolidWorks 2026 (provato dal vivo)",
    "insert_silhouette_entities": "InsertSilhouetteEntities/InsertSilhouetteEntities2 non esistono nella type library (provato dal vivo)",
    "delete_spline_point": "ISketchSpline.DeletePoint restituisce False e i punti restano 5 (2 prove dal vivo)",
    "merge_sketch_points": "MergePoints restituisce False e i punti restano 22 (2 prove dal vivo, anche con punti coincidenti)",
    # superfici 2
    "reverse_surface_normal": _WHY_NO_COM,
    "curve_through_reference_points": "non creava una curva per i punti",
}


def not_implemented_reason(name: str):
    why = NOT_IMPLEMENTED.get(name)
    if why is None:
        return None
    return (f"il tool '{name}' non e' implementato ({why}). E' disattivato finche' non viene riscritto e provato "
            "dal vivo; vedi REVISIONE_2026-10-23.md.")
