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
from pyrevit import revit, output, forms

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
    doc = revit.doc
    uidoc = revit.uidoc

    # 1. Prompt User
    instructions = (
        "✏️ BIM AI Parameter Editor (Targeted & Unit-Aware)\n\n"
        "How to use:\n"
        "• State elements, names, and parameter (e.g., 'Change the base offset of the Tree Guard railing at Level 5 to 900mm').\n"
        "• You can use units like mm, cm, m, ft, or in.\n\n"
        "Tell the AI what to update:"
    )
    user_prompt = forms.ask_for_string(
        prompt=instructions,
        title="BIM AI Parameter Editor",
        default="Set all Door Fire Rating to 2-Hr"
    )
    if not user_prompt: return

    # 2. Configure Networking & API Key
    ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12
    
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
    if not GEMINI_API_KEY:
        GEMINI_API_KEY = "YOUR_SECURE_API_KEY_HERE" # Fallback
        
    if GEMINI_API_KEY == "YOUR_SECURE_API_KEY_HERE" or not GEMINI_API_KEY:
        UI.TaskDialog.Show("Security Warning", "API Key missing.")
        return

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
    
    # UPGRADED SYSTEM INSTRUCTIONS: Force strict keywords and unit extraction
    system_instruction_text = (
        "You are a Revit API Data Editor. Convert natural language into a JSON edit object.\n"
        "Output ONLY raw JSON matching this key structure exactly:\n"
        '{"category": string, "keywords": list of strings, "level": string or null, "target_parameter": string, "new_value": string or number, "unit": string or null}\n\n'
        "Domain Rules:\n"
        "1. CATEGORY: Rooms, Walls, Doors, Windows, Columns, Floors, Ceilings, Roofs, Furniture, Casework, Railings, Stairs, Ramps, Specialty Equipment, Generic Models, Site, Planting, Curtain Panels, Curtain Mullions, Structural Columns, Structural Framing, Structural Foundations, Plumbing, Lighting, Mechanical Equipment, Electrical Equipment, Electrical Fixtures, Ducts, Pipes.\n"
        "2. KEYWORDS: CRITICAL - Extract identifying names, family types, or descriptors (e.g., 'Tree Guard', 'Exterior'). DO NOT leave blank if the user names a specific object type.\n"
        "3. TARGET_PARAMETER: The exact name of the Revit parameter to change.\n"
        "4. NEW_VALUE: The exact value to write. ONLY output the numeric value for dimensions.\n"
        "5. UNIT: If the user provides a unit (e.g., 'mm', 'cm', 'm', 'ft', 'in', '\"', '\''), extract it here. If no unit is specified but it is a dimension, assume 'mm'."
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
        response_bytes = client.UploadData(url, "POST", raw_bytes)
        res_json = json.loads(Encoding.UTF8.GetString(response_bytes))
        clean_json_str = res_json['candidates'][0]['content']['parts'][0]['text'].replace("```json", "").replace("```", "").strip()
        parsed_data = json.loads(clean_json_str)
    except Exception as e:
        UI.TaskDialog.Show("API Connection Error", "Failed to connect to the Gemini API.\n\nDetails: " + str(e))
        return

    # Extract Action Data
    cat_str = parsed_data.get("category", "Doors")
    keywords = parsed_data.get("keywords") or []
    level_str = parsed_data.get("level")
    target_param_name = parsed_data.get("target_parameter")
    new_value = parsed_data.get("new_value")
    unit_str = parsed_data.get("unit") # The new unit variable

    if not target_param_name or new_value is None:
        UI.TaskDialog.Show("AI Error", "The AI could not determine which parameter to change.")
        return

    # 4. Search Revit Document
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
        UI.TaskDialog.Show("Mapping Error", "The category '{}' is not supported.".format(cat_str))
        return

    collector = DB.FilteredElementCollector(doc).OfCategory(selected_cat).WhereElementIsNotElementType()
    matched_elements = []
    processed_type_ids = set()

    for elem in collector:
        elem_type = None
        try: elem_type = doc.GetElement(elem.GetTypeId())
        except: pass

        # Level Scanner
        elem_level_name = "N/A"
        try:
            if hasattr(elem, "Level") and elem.Level: 
                elem_level_name = elem.Level.Name
            else:
                lvl_param = elem.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
                if not lvl_param:
                    for p in elem.Parameters:
                        if "level" in p.Definition.Name.lower() and p.StorageType == DB.StorageType.ElementId:
                            lvl_param = p; break
                if lvl_param and lvl_param.HasValue:
                    lvl_elem = doc.GetElement(lvl_param.AsElementId())
                    if lvl_elem: elem_level_name = lvl_elem.Name
        except: pass
        
        if level_str and not matches_level(level_str, elem_level_name): continue

        # --- STRICTER KEYWORD FILTERING ---
        elem_name, family_name = "Unknown", ""
        try:
            if elem_type:
                elem_name = elem_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or elem.Name
                family_name = elem_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME).AsString() or ""
            else: elem_name = elem.Name
        except: pass

        if keywords:
            target_clean = target_param_name.lower().strip()
            stop_words = set(["find", "all", "show", "me", "get", "the", "set", "change", "update", "clear", "remove", "door", "doors", "wall", "walls", "railing", "railings", "to", "with", "value"] + target_clean.split())
            
            # Break down multi-word keywords (like "Tree Guard") into strict individual words to force a perfect match
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

            # If filtered words exist, they MUST ALL be present in the element's metadata to prevent picking up random railings
            if filtered_words and not all(word in target_str for word in filtered_words): 
                continue

        # --- THE SELF-DIAGNOSING PARAMETER ENGINE ---
        param_to_edit = None
        target_clean = target_param_name.lower().strip()
        
        for p in elem.Parameters:
            if p.Definition.Name.lower() == target_clean:
                param_to_edit = p; break
        if not param_to_edit and elem_type:
            for p in elem_type.Parameters:
                if p.Definition.Name.lower() == target_clean:
                    param_to_edit = p; break
        
        if not param_to_edit:
            target_words = target_clean.split()
            best_match, highest_score = None, 0
            def score_param(p):
                return sum(1 for word in target_words if word in p.Definition.Name.lower())

            for p in elem.Parameters:
                if not p.IsReadOnly:
                    score = score_param(p)
                    if score > highest_score: highest_score, best_match = score, p
            if elem_type:
                for p in elem_type.Parameters:
                    if not p.IsReadOnly:
                        score = score_param(p)
                        if score > highest_score: highest_score, best_match = score, p
            if best_match and highest_score > 0: param_to_edit = best_match

        if param_to_edit and not param_to_edit.IsReadOnly:
            target_param_name = param_to_edit.Definition.Name 
            if elem_type and param_to_edit.Element.Id == elem_type.Id:
                type_id_key = str(elem_type.Id)
                if type_id_key in processed_type_ids: continue
                processed_type_ids.add(type_id_key)
                
            matched_elements.append({"element": param_to_edit.Element, "param": param_to_edit})

    if not matched_elements:
        diag_msg = "No editable elements matched your specific criteria.\n\n"
        sample_elem = DB.FilteredElementCollector(doc).OfCategory(selected_cat).WhereElementIsNotElementType().FirstElement()
        if sample_elem:
            available_params = [p.Definition.Name for p in sample_elem.Parameters if not p.IsReadOnly and p.StorageType != DB.StorageType.ElementId]
            if available_params:
                diag_msg += "💡 DIAGNOSTIC REPORT:\nAvailable parameters for '{}' include:\n- {}".format(cat_str, "\n- ".join(sorted(available_params)[:15]))
        UI.TaskDialog.Show("Audit Failed", diag_msg)
        return

    # Dimensional Check
    dim_keywords = ["offset", "height", "width", "length", "thickness", "elevation", "radius"]
    is_dimensional = any(word in target_param_name.lower() for word in dim_keywords)

    # 5. Execute Transaction
    dialog = UI.TaskDialog("AI Safety Checkpoint")
    
    # UI Updated to show dynamic conversion
    metric_warning = ""
    target_unit = unit_str.lower() if unit_str else "mm"
    
    if is_dimensional:
        metric_warning = "\n\n⚠️ UNIT CONVERSION ACTIVE:\nThe value ({}{}) will be dynamically converted to Revit's Decimal Feet format.".format(new_value, target_unit)
        
    dialog.MainContent = "Target Category: {}\nElements to Update: {}\nDiagnosed Parameter: '{}'\nValue to Apply: '{}'{}\n\nProceed?".format(cat_str, len(matched_elements), target_param_name, new_value, metric_warning)
    dialog.CommonButtons = UI.TaskDialogCommonButtons.Yes | UI.TaskDialogCommonButtons.No
    
    if dialog.Show() == UI.TaskDialogResult.Yes:
        success_count = 0
        with DB.Transaction(doc, "AI Parameter Update") as t:
            t.Start()
            for item in matched_elements:
                param = item["param"]
                try:
                    if new_value == "" or str(new_value).lower() in ["clear", "none"]:
                        if param.StorageType == DB.StorageType.String: param.Set("")
                        elif param.StorageType == DB.StorageType.Integer: param.Set(0)
                        elif param.StorageType == DB.StorageType.Double: param.Set(0.0)
                        success_count += 1
                    else:
                        if param.StorageType == DB.StorageType.String:
                            param.Set(str(new_value))
                        elif param.StorageType == DB.StorageType.Double:
                            val_float = float(new_value)
                            
                            # --- DYNAMIC UNIT MATH ENGINE ---
                            if is_dimensional:
                                if target_unit in ["mm", "millimeter", "millimeters"]: conversion = 304.8
                                elif target_unit in ["cm", "centimeter", "centimeters"]: conversion = 30.48
                                elif target_unit in ["m", "meter", "meters"]: conversion = 0.3048
                                elif target_unit in ["in", "\"", "inch", "inches"]: conversion = 12.0
                                elif target_unit in ["ft", "'", "foot", "feet"]: conversion = 1.0
                                else: conversion = 304.8 # Fallback to mm
                                
                                param.Set(val_float / conversion)
                            else:
                                param.Set(val_float)
                                
                        elif param.StorageType == DB.StorageType.Integer:
                            val_str = str(new_value).lower().strip()
                            if val_str in ["true", "yes", "on"]: param.Set(1)
                            elif val_str in ["false", "no", "off"]: param.Set(0)
                            else: param.Set(int(float(new_value)))
                        success_count += 1
                except Exception:
                    pass
            t.Commit()
            
        UI.TaskDialog.Show("Update Complete", "Successfully updated {} parameter(s)!".format(success_count))

try: run_script()
except Exception as ex: UI.TaskDialog.Show("Fatal Error", str(ex))