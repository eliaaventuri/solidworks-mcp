"""
SolidWorks Sketch Operations
----------------------------
Create sketches and draw 2D geometry.
"""

import math
import logging
import traceback
from typing import Optional, Dict, List, Tuple

import win32com.client
import pythoncom

from ..constants import SwErrors, SwPlanes

logger = logging.getLogger(__name__)


class SketchOperations:
    """
    Mixin class for sketch operations
    
    Requires parent class to have:
    - get_active_doc(): Document access method
    - _result(): Result factory method
    - _units: UnitConverter instance
    """
    
    # ---- identificativi delle entita' create (usati da add_sketch_dimension / add_sketch_relation) ----
    def _ids_of(self, seg) -> dict:
        """entity_id (+ punti iniziale/finale/centro) di un segmento appena creato"""
        data = {}
        try:
            data["entity_id"] = self._seg_id(seg)
        except Exception:
            return data
        for key, attr in (("start_point_id", "GetStartPoint2"), ("end_point_id", "GetEndPoint2"),
                          ("center_point_id", "GetCenterPoint2")):
            try:
                data[key] = self._pt_id(getattr(seg, attr))
            except Exception:
                pass
        return data

    def _ids_many(self, segs) -> dict:
        try:
            ids = [self._seg_id(s) for s in segs if s is not None]
        except Exception:
            ids = []
        return {"entity_ids": ids} if ids else {}

    def create_sketch(self, plane: str = "Front") -> Dict:
        """
        Create a new sketch on specified plane
        
        Args:
            plane: Plane name - "Front", "Top", or "Right"
        
        Returns:
            Result dictionary
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            
            # Get plane name
            plane_name = SwPlanes.get(plane)
            
            # Create empty variant for callout parameter
            empty_callout = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)
            
            # Select plane
            result = doc.Extension.SelectByID2(
                plane_name, "PLANE", 0, 0, 0, False, 0, empty_callout, 0
            )
            
            if not result:
                # Localized SolidWorks (e.g. "Piano frontale"): select by tree position
                result = self._select_std_plane(doc, plane)

            if not result:
                # piano di riferimento creato dall'utente (es. "Piano1") o nome italiano
                try:
                    feat = doc.FeatureByName(plane)
                    result = bool(feat is not None and feat.Select2(False, 0))
                except Exception:
                    result = False

            if not result:
                return self._result(False, f"Could not select {plane_name}",
                                  SwErrors.swSelectionError)
            
            # Insert sketch
            doc.InsertSketch2(True)
            
            try:
                axes = self._sketch_plane_info(doc)
            except Exception:
                axes = {}
            return self._result(True, f"Sketch created on {plane_name}",
                              SwErrors.swSuccess, {"plane": plane_name, **axes})
            
        except Exception as e:
            logger.error(f"Create sketch error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swSketchError)
    
    def create_sketch_on_face(self, x: float = 0, y: float = 0, z: float = 0,
                              unit: str = None) -> Dict:
        """
        Create a new sketch on a face selected by coordinate.
        ADDED v4.1: Enables cut-extrude on existing body faces (not just ref planes).
        
        Args:
            x, y, z: Coordinates (in user units) of a point ON the target face
            unit: Unit for coordinates (uses default if None)
        
        Returns:
            Result dictionary
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            
            # Convert to meters
            x_m = self._units.to_meters(x, unit)
            y_m = self._units.to_meters(y, unit)
            z_m = self._units.to_meters(z, unit)
            unit_str = unit or self._units.default_unit.value
            
            # Clear any selection
            doc.ClearSelection2(True)
            
            # Select face at the given coordinates (selezione geometrica; fallback su SelectByID2)
            selected = False
            try:
                selected, _info = self._select_point(doc, "face", (x, y, z), unit, False, 0, 0.05)
            except Exception:
                selected = False
            if not selected:
                empty_callout = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)
                selected = doc.Extension.SelectByID2(
                    "", "FACE", x_m, y_m, z_m, False, 0, empty_callout, 0
                )
            
            if not selected:
                return self._result(False,
                    f"No face found at ({x}{unit_str}, {y}{unit_str}, {z}{unit_str}). "
                    f"Coordinates must be on an existing body face.",
                    SwErrors.swSelectionError)
            
            # Insert sketch on the selected face
            doc.InsertSketch2(True)
            
            try:
                axes = self._sketch_plane_info(doc)
            except Exception:
                axes = {}
            return self._result(True,
                f"Sketch created on face at ({x}, {y}, {z}) {unit_str}",
                SwErrors.swSuccess,
                {"face_point": {"x": x, "y": y, "z": z}, "unit": unit_str, **axes})
            
        except Exception as e:
            logger.error(f"Create sketch on face error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swSketchError)
    
    def exit_sketch(self) -> Dict:
        """
        Exit the current sketch
        
        Returns:
            Result dictionary
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            
            doc.InsertSketch2(True)
            
            return self._result(True, "Exited sketch", SwErrors.swSuccess)
            
        except Exception as e:
            return self._result(False, f"Error: {e}", SwErrors.swSketchError)
    
    def draw_line(self, x1: float = 0, y1: float = 0, 
                  x2: float = 100, y2: float = 0, unit: str = None) -> Dict:
        """
        Draw a line in the active sketch
        
        Args:
            x1, y1: Start point coordinates
            x2, y2: End point coordinates
            unit: Unit for coordinates (uses default if None)
        
        Returns:
            Result dictionary
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            
            # Convert to meters
            x1_m = self._units.to_meters(x1, unit)
            y1_m = self._units.to_meters(y1, unit)
            x2_m = self._units.to_meters(x2, unit)
            y2_m = self._units.to_meters(y2, unit)
            
            # Draw line
            line = doc.SketchManager.CreateLine(x1_m, y1_m, 0, x2_m, y2_m, 0)
            
            if line is None:
                return self._result(False, "Failed - ensure sketch is active",
                                  SwErrors.swSketchError)
            
            # Calculate length
            length_m = math.sqrt((x2_m - x1_m)**2 + (y2_m - y1_m)**2)
            length_display = self._units.from_meters(length_m, unit)
            unit_str = unit or self._units.default_unit.value
            
            return self._result(True, f"Line: {length_display:.2f}{unit_str}",
                              SwErrors.swSuccess,
                              {"length": length_display, "unit": unit_str, **self._ids_of(line)})
            
        except Exception as e:
            logger.error(f"Draw line error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swSketchError)
    
    def draw_circle(self, x: float = 0, y: float = 0, 
                    radius: float = 25, unit: str = None) -> Dict:
        """
        Draw a circle in the active sketch
        
        Args:
            x, y: Center point coordinates
            radius: Circle radius
            unit: Unit for dimensions (uses default if None)
        
        Returns:
            Result dictionary
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            
            # Convert to meters
            x_m = self._units.to_meters(x, unit)
            y_m = self._units.to_meters(y, unit)
            radius_m = self._units.to_meters(radius, unit)
            
            # Draw circle (center point and edge point)
            circle = doc.SketchManager.CreateCircle(
                x_m, y_m, 0,              # Center
                x_m + radius_m, y_m, 0    # Edge point
            )
            
            if circle is None:
                return self._result(False, "Failed - ensure sketch is active",
                                  SwErrors.swSketchError)
            
            unit_str = unit or self._units.default_unit.value
            
            return self._result(True, f"Circle: r={radius}{unit_str}",
                              SwErrors.swSuccess,
                              {"radius": radius, "unit": unit_str,
                               "center_x": x, "center_y": y, **self._ids_of(circle)})
            
        except Exception as e:
            logger.error(f"Draw circle error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swSketchError)
    
    def draw_rectangle(self, x1: float = -50, y1: float = -25,
                       x2: float = 50, y2: float = 25, unit: str = None) -> Dict:
        """
        Draw a rectangle in the active sketch
        
        Args:
            x1, y1: First corner coordinates
            x2, y2: Opposite corner coordinates
            unit: Unit for dimensions
        
        Returns:
            Result dictionary
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            
            # Convert to meters
            x1_m = self._units.to_meters(x1, unit)
            y1_m = self._units.to_meters(y1, unit)
            x2_m = self._units.to_meters(x2, unit)
            y2_m = self._units.to_meters(y2, unit)
            
            # Draw rectangle
            rect = doc.SketchManager.CreateCornerRectangle(
                x1_m, y1_m, 0, x2_m, y2_m, 0
            )
            
            if rect is None:
                return self._result(False, "Failed - ensure sketch is active",
                                  SwErrors.swSketchError)
            
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            unit_str = unit or self._units.default_unit.value
            
            return self._result(True, f"Rectangle: {width}x{height}{unit_str}",
                              SwErrors.swSuccess,
                              {"width": width, "height": height, "unit": unit_str,
                               **self._ids_many(rect)})
            
        except Exception as e:
            logger.error(f"Draw rectangle error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swSketchError)
    
    def draw_arc_center(self, cx: float = 0, cy: float = 0, radius: float = 25,
                        start_angle: float = 0, end_angle: float = 90,
                        unit: str = None) -> Dict:
        """
        Draw an arc by center point and angles
        
        Args:
            cx, cy: Center point
            radius: Arc radius
            start_angle: Start angle in degrees
            end_angle: End angle in degrees
            unit: Unit for radius
        
        Returns:
            Result dictionary
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            
            # Convert to meters
            cx_m = self._units.to_meters(cx, unit)
            cy_m = self._units.to_meters(cy, unit)
            radius_m = self._units.to_meters(radius, unit)
            
            # Convert angles to radians
            start_rad = math.radians(start_angle)
            end_rad = math.radians(end_angle)
            
            # Calculate start and end points
            x1 = cx_m + radius_m * math.cos(start_rad)
            y1 = cy_m + radius_m * math.sin(start_rad)
            x2 = cx_m + radius_m * math.cos(end_rad)
            y2 = cy_m + radius_m * math.sin(end_rad)
            
            # Draw arc (center, start, end, direction)
            arc = doc.SketchManager.CreateArc(
                cx_m, cy_m, 0,   # Center
                x1, y1, 0,       # Start
                x2, y2, 0,       # End
                1                # Direction (1 = counter-clockwise)
            )
            
            if arc is None:
                return self._result(False, "Failed - ensure sketch is active",
                                  SwErrors.swSketchError)
            
            unit_str = unit or self._units.default_unit.value
            arc_angle = abs(end_angle - start_angle)
            
            return self._result(True, f"Arc: r={radius}{unit_str}, {arc_angle}°",
                              SwErrors.swSuccess,
                              {"radius": radius, "start_angle": start_angle,
                               "end_angle": end_angle, "unit": unit_str, **self._ids_of(arc)})
            
        except Exception as e:
            logger.error(f"Draw arc error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swSketchError)
    
    def draw_polygon(self, cx: float = 0, cy: float = 0, radius: float = 25,
                     sides: int = 6, unit: str = None) -> Dict:
        """
        Draw a regular polygon
        
        Args:
            cx, cy: Center point
            radius: Circumscribed radius
            sides: Number of sides (3-100)
            unit: Unit for radius
        
        Returns:
            Result dictionary
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            
            if sides < 3 or sides > 100:
                return self._result(False, "Sides must be between 3 and 100",
                                  SwErrors.swInvalidInput)
            
            # Convert to meters
            cx_m = self._units.to_meters(cx, unit)
            cy_m = self._units.to_meters(cy, unit)
            radius_m = self._units.to_meters(radius, unit)
            
            # Draw polygon
            polygon = doc.SketchManager.CreatePolygon(
                cx_m, cy_m, 0,               # Center
                cx_m + radius_m, cy_m, 0,    # Vertex
                sides,                        # Number of sides
                False                         # Inscribed (False = circumscribed)
            )
            
            if polygon is None:
                return self._result(False, "Failed - ensure sketch is active",
                                  SwErrors.swSketchError)
            
            unit_str = unit or self._units.default_unit.value
            
            return self._result(True, f"{sides}-sided polygon: r={radius}{unit_str}",
                              SwErrors.swSuccess,
                              {"sides": sides, "radius": radius, "unit": unit_str,
                               **self._ids_many(polygon if isinstance(polygon, (tuple, list)) else [])})
            
        except Exception as e:
            logger.error(f"Draw polygon error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swSketchError)
    
    def draw_centerline(self, x1: float = 0, y1: float = -50,
                        x2: float = 0, y2: float = 50, unit: str = None) -> Dict:
        """
        Draw a centerline (for revolve axis)
        
        Args:
            x1, y1: Start point
            x2, y2: End point
            unit: Unit for coordinates
        
        Returns:
            Result dictionary
        """
        try:
            doc, err = self.get_active_doc()
            if err:
                return err
            
            # Convert to meters
            x1_m = self._units.to_meters(x1, unit)
            y1_m = self._units.to_meters(y1, unit)
            x2_m = self._units.to_meters(x2, unit)
            y2_m = self._units.to_meters(y2, unit)
            
            # Draw centerline
            line = doc.SketchManager.CreateCenterLine(x1_m, y1_m, 0, x2_m, y2_m, 0)
            
            if line is None:
                return self._result(False, "Failed - ensure sketch is active",
                                  SwErrors.swSketchError)
            
            return self._result(True, "Centerline created",
                              SwErrors.swSuccess, self._ids_of(line))
            
        except Exception as e:
            logger.error(f"Draw centerline error: {e}\n{traceback.format_exc()}")
            return self._result(False, f"Error: {e}", SwErrors.swSketchError)
