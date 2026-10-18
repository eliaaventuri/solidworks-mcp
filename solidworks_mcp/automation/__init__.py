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
from .ext_moka import MokaOperations
from .ext_sketch2 import Sketch2Operations
from .ext_features2 import Features2Operations
from .ext_bodies2 import Bodies2Operations
from .ext_curves import CurvesOperations
from .ext_surfaces1 import Surfaces1Operations
from .ext_surfaces2 import Surfaces2Operations
from .ext_manage import ManageOperations
from .ext_sheetmetal import SheetMetalOperations
from .ext_weldments import WeldmentsOperations
from .ext_mold import MoldOperations


class SolidWorksAutomation(_BaseAutomation, SimulationOperations, DataExportOperations, DocumentOperations, 
                           SketchOperations, FeatureOperations, DrawingOperations,
                           ModelingOperations, AssemblyOperations, MokaOperations, Sketch2Operations,
                           Features2Operations, Bodies2Operations, CurvesOperations, Surfaces1Operations, Surfaces2Operations,
                           ManageOperations, SheetMetalOperations, WeldmentsOperations, MoldOperations):
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
