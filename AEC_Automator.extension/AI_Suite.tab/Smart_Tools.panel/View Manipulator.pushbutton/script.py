# -*- coding: utf-8 -*-
import clr
import re
import os
import json

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('System')

import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI
from System.Collections.Generic import List
from System.Net import ServicePointManager, SecurityProtocolType, WebClient, HttpRequestHeader
from System.Text import Encoding

def normalize_text(text):
    if not text: return ""
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', str(text)).lower()

def matches_level(req_level, elem_level_name):
    if not req_level: return True
    if not elem_level_name: return False
    req_clean = req_level.lower().strip()
    elem_clean = elem_level_name.lower().strip()
    if req_clean in elem_clean or elem_clean in req_clean: return True
    req_digits = re.findall(r'\d+', req_clean)
    elem_digits = re.findall(r'\d+', elem_clean)
    if req_digits and elem_digits:
        return any(str(int(d)) in [str(int(e)) for e in elem_digits] for d in req_digits)
    return False

def run_script():
    from pyrevit import revit, output, forms
    doc = revit.doc
    uidoc = revit.uidoc
    active_view = revit.active_view

    # 1. Prompt User
    instructions = (
        "👁️ BIM AI View Manipulator\n\n"
        "How to use (Must be in a 3D View):\n"
        "• To crop: 'Cut a section box around the Tree Guard railing'.\n"
        "• To hide others: 'Isolate exterior structural columns at Level 1'.\n"
        "• Type 'reset' to clear view settings and unhide.\n\n"
        "Tell the AI what to view:"
    )
    user_prompt = forms.ask_for_string(
        prompt=instructions,
        title="BIM AI View Manipulator",
        default="Cut a section box around all exterior walls"
    )
    if not user_prompt: return

    # Check for direct reset command
    if user_prompt.lower().strip() in ["reset", "clear", "unhide", "reset view"]:
        with DB.Transaction(doc, "AI Reset View") as t:
            t.Start()
            if active_view.IsTemporaryHideIsolateActive():
                active_view.DisableTemporaryViewMode(DB.TemporaryViewMode.TemporaryHideIsolate)
            if isinstance(active_view, DB.View3D) and active_view.IsSectionBoxActive:
                active_view.IsSectionBoxActive = False
            t.Commit()
        uidoc.RefreshActiveView()
        return

    # 2. Configure .NET Networking & Secure API Key
    ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
    if not GEMINI_API_KEY:
        GEMINI_API_KEY = "YOUR_SECURE_API_KEY_HERE"
        
    if GEMINI_API_KEY == "YOUR_SECURE_API_KEY_HERE" or not GEMINI_API_KEY:
        UI.TaskDialog.Show("Security Warning", "API Key missing.")
        return

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
    
    system_instruction_text = (
        "You are a Revit API View Controller. Convert natural language into a JSON view manipulation object.\n"
        "Output ONLY raw JSON matching this key structure exactly:\n"
        '{"action": string, "category": string, "keywords": list of strings, "level": string or null}\n\n'
        "Domain Rules:\n"
        "1. ACTION: Must be exactly 'isolate' (to hide other elements) or 'section_box' (to crop the 3D view).\n"
        "2. CATEGORY: Rooms, Walls, Doors, Windows, Columns, Floors, Ceilings, Roofs, Furniture, Casework, Railings, Stairs, Ramps, Specialty Equipment, Generic Models, Site, Planting, Curtain Panels, Curtain Mullions, Structural Columns, Structural Framing, Structural Foundations, Plumbing, Lighting, Mechanical Equipment, Electrical Equipment, Electrical Fixtures, Ducts, Pipes.\n"
        "3. KEYWORDS: CRITICAL - Extract identifying names, family types, or descriptors (e.g., 'Tree Guard', 'Exterior'). DO NOT leave blank if the user names a specific object type.\n"
        "4. LEVEL: Extract any level mentions."
    )

    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction_text}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    # 3. Call Google Gemini API
    client = WebClient()
    client.Headers[HttpRequestHeader.ContentType] = "application/json"
    raw_bytes = Encoding.UTF8.GetBytes(json.dumps(payload))
    try:
        res_json = json.loads(Encoding.UTF8.GetString(client.UploadData(url, "POST", raw_bytes)))
        clean_json_str = res_json['candidates'][0]['content']['parts'][0]['text'].replace("```json", "").replace("```", "").strip()
        parsed_data = json.loads(clean_json_str)
    except Exception as e:
        UI.TaskDialog.Show("API Connection Error", "Failed to connect to the Gemini API.\n\nDetails: " + str(e))
        return

    # Extract Action Data
    action_type = parsed_data.get("action", "isolate")
    cat_str = parsed_data.get("category", "Walls")
    keywords = parsed_data.get("keywords") or []
    level_str = parsed_data.get("level")

    # Verify 3D View for Section Box
    if action_type == "section_box" and not isinstance(active_view, DB.View3D):
        UI.TaskDialog.Show("View Error", "Section boxes can only be created in a 3D View. Please open a 3D view and run the tool again.")
        return

    # 4. Search Revit Document - THE BULLETPROOF DICTIONARY
    cat_map = {
        "Rooms": DB.BuiltInCategory.OST_Rooms, "Room": DB.BuiltInCategory.OST_Rooms,
        "Walls": DB.BuiltInCategory.OST_Walls, "Wall": DB.BuiltInCategory.OST_Walls,
        "Doors": DB.BuiltInCategory.OST_Doors, "Door": DB.BuiltInCategory.OST_Doors,
        "Windows": DB.BuiltInCategory.OST_Windows, "Window": DB.BuiltInCategory.OST_Windows,
        "Columns": DB.BuiltInCategory.OST_Columns, "Column": DB.BuiltInCategory.OST_Columns,
        "Floors": DB.BuiltInCategory.OST_Floors, "Floor": DB.BuiltInCategory.OST_Floors,
        "Ceilings": DB.BuiltInCategory.OST_Ceilings, "Ceiling": DB.BuiltInCategory.OST_Ceilings,
        "Roofs": DB.BuiltInCategory.OST_Roofs, "Roof": DB.BuiltInCategory.OST_Roofs,
        "Casework": DB.BuiltInCategory.OST_Casework, "Cabinet": DB.BuiltInCategory.OST_Casework,
        "Furniture": DB.BuiltInCategory.OST_Furniture,
        "Railings": DB.BuiltInCategory.OST_StairsRailing, "Railing": DB.BuiltInCategory.OST_StairsRailing,
        "Stairs": DB.BuiltInCategory.OST_Stairs, "Stair": DB.BuiltInCategory.OST_Stairs,
        "Ramps": DB.BuiltInCategory.OST_Ramps, "Ramp": DB.BuiltInCategory.OST_Ramps,
        "Specialty Equipment": DB.BuiltInCategory.OST_SpecialityEquipment,
        "Generic Models": DB.BuiltInCategory.OST_GenericModel, "Generic Model": DB.BuiltInCategory.OST_GenericModel,
        "Site": DB.BuiltInCategory.OST_Site, "Planting": DB.BuiltInCategory.OST_Planting, 
        "Curtain Panels": DB.BuiltInCategory.OST_CurtainWallPanels, "Curtain Mullions": DB.BuiltInCategory.OST_CurtainWallMullions,
        "Structural Columns": DB.BuiltInCategory.OST_StructuralColumns, "Structural Framing": DB.BuiltInCategory.OST_StructuralFraming, 
        "Structural Foundations": DB.BuiltInCategory.OST_StructuralFoundation,
        "Plumbing": DB.BuiltInCategory.OST_PlumbingFixtures, "Lighting": DB.BuiltInCategory.OST_LightingFixtures,
        "Mechanical Equipment": DB.BuiltInCategory.OST_MechanicalEquipment, "Electrical Equipment": DB.BuiltInCategory.OST_ElectricalEquipment,
        "Electrical Fixtures": DB.BuiltInCategory.OST_ElectricalFixtures, "Ducts": DB.BuiltInCategory.OST_DuctCurves, 
        "Pipes": DB.BuiltInCategory.OST_PipeCurves, "Spaces": DB.BuiltInCategory.OST_MEPSpaces, "Areas": DB.BuiltInCategory.OST_Areas
    }

    selected_cat = cat_map.get(cat_str)
    if not selected_cat:
        UI.TaskDialog.Show("Mapping Error", "The category '{}' is not supported in the current map.".format(cat_str))
        return
        
    collector = DB.FilteredElementCollector(doc, active_view.Id).OfCategory(selected_cat).WhereElementIsNotElementType()

    matched_elements = []

    for elem in collector:
        elem_type = None
        try: elem_type = doc.GetElement(elem.GetTypeId())
        except: pass

        # Robust Level Scanner
        elem_level_name = "N/A"
        try:
            if hasattr(elem, "Level") and elem.Level: 
                elem_level_name = elem.Level.Name
            else:
                lvl_param = elem.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM) or elem.get_Parameter(DB.BuiltInParameter.ROOM_LEVEL_ID)
                if not lvl_param:
                    for p in elem.Parameters:
                        if "level" in p.Definition.Name.lower() and p.StorageType == DB.StorageType.ElementId:
                            lvl_param = p; break
                if lvl_param and lvl_param.HasValue:
                    lvl_elem = doc.GetElement(lvl_param.AsElementId())
                    if lvl_elem: elem_level_name = lvl_elem.Name
        except: pass
        if level_str and not matches_level(level_str, elem_level_name): continue

        # Strict Keyword Filtering
        elem_name, family_name = "Unknown", ""
        try:
            if elem_type:
                elem_name = elem_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or elem.Name
                family_name = elem_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME).AsString() or ""
            else: elem_name = elem.Name
        except: pass

        if keywords:
            stop_words = set(["isolate", "section", "box", "show", "only", "find", "all", "the", "around", "door", "doors", "wall", "walls", "railing", "railings"])
            filtered_words = []
            for kw in keywords:
                for w in normalize_text(kw).split():
                    if w not in stop_words and len(w) > 1:
                        filtered_words.append(w)
                        
            target_str = normalize_text(family_name) + " " + normalize_text(elem_name)
            
            try:
                for p in elem.Parameters:
                    if p.StorageType == DB.StorageType.String and p.HasValue: target_str += " " + normalize_text(p.AsString())
                if elem_type:
                    for p in elem_type.Parameters:
                        if p.StorageType == DB.StorageType.String and p.HasValue: target_str += " " + normalize_text(p.AsString())
            except: pass

            if filtered_words and not all(word in target_str for word in filtered_words): continue
        
        matched_elements.append(elem)

    if not matched_elements:
        UI.TaskDialog.Show("Search Complete", "No elements matched your criteria in this view.")
        return

    # 5. Execute View Manipulation
    with DB.Transaction(doc, "AI View Manipulation") as t:
        t.Start()
        
        element_ids = List[DB.ElementId]([e.Id for e in matched_elements])
        
        if action_type == "isolate":
            # Temporary Isolate (Works in 2D and 3D)
            active_view.IsolateElementsTemporary(element_ids)
            
        elif action_type == "section_box" and isinstance(active_view, DB.View3D):
            # Calculate collective bounding box for Section Box
            min_x, min_y, min_z = float('inf'), float('inf'), float('inf')
            max_x, max_y, max_z = float('-inf'), float('-inf'), float('-inf')
            
            valid_boxes = 0
            for elem in matched_elements:
                bbox = elem.get_BoundingBox(active_view)
                if bbox:
                    valid_boxes += 1
                    min_x = min(min_x, bbox.Min.X)
                    min_y = min(min_y, bbox.Min.Y) # Fixed coordinate bug here
                    min_z = min(min_z, bbox.Min.Z)
                    max_x = max(max_x, bbox.Max.X)
                    max_y = max(max_y, bbox.Max.Y)
                    max_z = max(max_z, bbox.Max.Z)
            
            if valid_boxes > 0:
                # Add a 3-foot buffer around the elements so they aren't cropped too tightly
                buffer = 3.0 
                new_bbox = DB.BoundingBoxXYZ()
                new_bbox.Min = DB.XYZ(min_x - buffer, min_y - buffer, min_z - buffer)
                new_bbox.Max = DB.XYZ(max_x + buffer, max_y + buffer, max_z + buffer)
                
                active_view.SetSectionBox(new_bbox)
                active_view.IsSectionBoxActive = True
            else:
                UI.TaskDialog.Show("Error", "Could not calculate bounding boxes for the selected elements.")
                t.RollBack()
                return
                
        t.Commit()
        
    uidoc.Selection.SetElementIds(element_ids)
    uidoc.RefreshActiveView()

try: run_script()
except Exception as ex: UI.TaskDialog.Show("Error", str(ex))