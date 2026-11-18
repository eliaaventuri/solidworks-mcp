"""
SolidWorks MCP Constants
------------------------
All constants, enums, and error codes for SolidWorks automation.
"""

from enum import IntEnum


# ============================================================================
# Error Codes
# ============================================================================

class SwErrors(IntEnum):
    """SolidWorks MCP error codes"""
    swSuccess = 0
    swFileNotFoundError = 2
    swFileLoadError = 3
    swFileSaveError = 4
    swInvalidFileType = 5
    swConnectionError = 100
    swNoActiveDocument = 101
    swSketchError = 102
    swFeatureError = 103
    swSelectionError = 104
    swSolidWorksNotFound = 105
    swTemplateNotFound = 106
    swInvalidInput = 107
    swSimulationError = 108
    swExportError = 109
    swGenericError = 110
    swNotImplemented = 111
    swFileAlreadyExists = 112
    swUnknownError = 999


# ============================================================================
# Document Types
# ============================================================================

class SwDocumentTypes(IntEnum):
    """SolidWorks document types"""
    swDocNONE = 0
    swDocPART = 1
    swDocASSEMBLY = 2
    swDocDRAWING = 3


# ============================================================================
# Feature End Conditions
# ============================================================================

class SwEndConditions(IntEnum):
    """Extrusion end conditions"""
    swEndCondBlind = 0
    swEndCondThroughAll = 1
    swEndCondThroughAllBoth = 2
    swEndCondThroughNext = 3
    swEndCondUpToVertex = 4
    swEndCondUpToSurface = 5
    swEndCondMidPlane = 6
    swEndCondOffsetFromSurface = 7


# ============================================================================
# Mate Types
# ============================================================================

class SwMateTypes(IntEnum):
    """Assembly mate types"""
    swMateCOINCIDENT = 0
    swMateCONCENTRIC = 1
    swMatePERPENDICULAR = 2
    swMatePARALLEL = 3
    swMateTANGENT = 4
    swMateDISTANCE = 5
    swMateANGLE = 6
    swMateLOCK = 16
    swMateWIDTH = 18


# ============================================================================
# File Extensions
# ============================================================================

class SwFileTypes:
    """SolidWorks file extensions"""
    PART = ".sldprt"
    ASSEMBLY = ".sldasm"
    DRAWING = ".slddrw"
    PART_TEMPLATE = ".prtdot"
    ASSEMBLY_TEMPLATE = ".asmdot"
    DRAWING_TEMPLATE = ".drwdot"
    
    # Export formats
    STEP = ".step"
    STEP_ALT = ".stp"
    STL = ".stl"
    IGES = ".igs"
    PARASOLID = ".x_t"
    DXF = ".dxf"
    DWG = ".dwg"
    PDF = ".pdf"
    
    @classmethod
    def is_valid_part(cls, ext: str) -> bool:
        return ext.lower() == cls.PART
    
    @classmethod
    def is_valid_export(cls, ext: str) -> bool:
        valid = [cls.STEP, cls.STEP_ALT, cls.STL, cls.IGES, cls.PARASOLID, cls.DXF, cls.DWG, cls.PDF]
        return ext.lower() in valid


# ============================================================================
# Selection Types
# ============================================================================

class SwSelectType:
    """Entity selection types for SelectByID2"""
    FACE = "FACE"
    EDGE = "EDGE"
    VERTEX = "VERTEX"
    PLANE = "PLANE"
    AXIS = "AXIS"
    SKETCH = "SKETCH"
    SKETCHSEGMENT = "SKETCHSEGMENT"
    SKETCHPOINT = "SKETCHPOINT"
    BODYFEATURE = "BODYFEATURE"
    COMPONENT = "COMPONENT"
    EXTSKETCHSEGMENT = "EXTSKETCHSEGMENT"


# Cartelle di sistema dell'albero (GetTypeName2, uguali in ogni lingua di SolidWorks): Commenti, Preferiti, Cronologia,
# Impostazioni selezione, Sensori, Design Binder, Annotazioni, Corpi di superficie/solidi, Luci e videocamere,
# Annotazioni (markup), Equazioni, Materiale. Non sono feature di modellazione.
SYSTEM_FOLDER_TYPES = frozenset({
    "CommentsFolder", "FavoriteFolder", "HistoryFolder", "SelectionSetFolder", "SensorFolder", "DocsFolder",
    "DetailCabinet", "SurfaceBodyFolder", "SolidBodyFolder", "EnvFolder", "InkMarkupFolder", "EqnFolder", "MaterialFolder",
})
