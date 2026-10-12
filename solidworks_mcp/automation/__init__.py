"""
SolidWorks Automation Package
-----------------------------
Complete automation class combining all operations.
"""

from .base import SolidWorksAutomation as _BaseAutomation
from .documents import DocumentOperations
from .sketches import SketchOperations
from .features import FeatureOperations
from .drawings import DrawingOperations
from .modeling import ModelingOperations
from .assembly import AssemblyOperations
from .data_export import DataExportOperations
from .simulation import SimulationOperations


class SolidWorksAutomation(_BaseAutomation, SimulationOperations, DataExportOperations, DocumentOperations, 
                           SketchOperations, FeatureOperations, DrawingOperations,
                           ModelingOperations, AssemblyOperations):
    """
    Complete SolidWorks automation class
    
    Combines all operation mixins:
    - Base: Connection, document access, utilities
    - Documents: Create, open, save, close documents
    - Sketches: Create sketches, draw 2D geometry
    - Features: Extrude, cut, fillet, chamfer
    - Drawings: Sheets, views, sections, annotations, BOM, export
    
    Example:
        sw = SolidWorksAutomation()
        sw.connect()
        sw.create_new_part()
        sw.create_sketch("Front")
        sw.draw_circle(0, 0, 25)
        sw.extrude_sketch(10)
        sw.save_document("C:/Parts/MyPart.sldprt")
    """
    pass


__all__ = [
    "SolidWorksAutomation",
    "DocumentOperations",
    "SketchOperations", 
    "FeatureOperations",
    "DrawingOperations",
    "ModelingOperations",
    "AssemblyOperations",
    "DataExportOperations",
    "SimulationOperations",
]
