"""Lotto STAMPI: schemi dei tool -> automation/ext_mold.py (MoldOperations).

Tool di linea/superficie di divisione, chiusura e divisione maschio/matrice NON esposti: in questa istanza di SolidWorks
le API Mold (InsertMoldPartingLine, InsertMoldShutOffSurface) non creano feature (vedi scripts_tmp/notes_mold.md)."""

from ._common import UNIT

TOOLS = {
    "undercut_analysis": ("undercut_analysis",
        "Undercut analysis for a pull direction: a face is in undercut when the ray leaving it on the side it faces the "
        "pull direction hits the body (ray casting on tessellated samples). Faces parallel to the pull direction are never "
        "undercut. Returns the number of undercut faces, their area (mm2) and centre. "
        "Examples: {\"direction\":\"+Z\"} | {\"direction\":[0,1,0]} | {\"direction\":\"-X\",\"unit\":\"mm\"}.",
        {"direction": (None, "Pull direction: '+X', '-X', '+Y', '-Y', '+Z', '-Z' or a vector [dx,dy,dz] (no unit, normalized; default '+Z')"),
         "unit": UNIT},
        []),
}

DESTRUCTIVE = {
}
