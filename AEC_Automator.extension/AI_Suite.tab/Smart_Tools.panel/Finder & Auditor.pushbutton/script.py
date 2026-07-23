# -*- coding: utf-8 -*-
import clr
import re
import csv
import os
import datetime
import tempfile
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
    if not text:
        return ""
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', str(text)).lower()

def safe_str(val):
    if val is None: return ""
    try: return unicode(val).encode('utf-8')
    except NameError: return str(val)

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

def reset_view_overrides(doc, active_view):
    collector = DB.FilteredElementCollector(doc, active_view.Id).WhereElementIsNotElementType()
    empty_ogs = DB.OverrideGraphicSettings()
    with DB.Transaction(doc, "Clear AI Overrides") as t:
        t.Start()
        for elem in collector: active_view.SetElementOverrides(elem.Id, empty_ogs)
        t.Commit()

def run_script():
    from pyrevit import revit, output, forms
    doc = revit.doc
    uidoc = revit.uidoc
    active_view = revit.active_view

    # 1. Prompt User
    instructions = (
        "🤖 BIM AI Finder & Auditor (Targeted & Unit-Aware)\n\n"
        "How to use:\n"
        "• Search by specific names (e.g., 'Find the Tree Guard railing').\n"
        "• Search by parameters & units (e.g., 'Find doors with Height > 7ft').\n"
        "• Type 'reset' to clear all gold highlights.\n\n"
        "Enter your query:"
    )
    user_prompt = forms.ask_for_string(
        prompt=instructions,
        title="BIM AI Finder & Auditor",
        default="Find the Tree Guard railing at Level 5"
    )
    if not user_prompt: return
    
    if user_prompt.lower().strip() == "reset":
        reset_view_overrides(doc, active_view)
        UI.TaskDialog.Show("Reset Complete", "All AI highlights have been cleared.")
        return

    # 2. Configure .NET Networking & Secure API
    ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        GEMINI_API_KEY = "YOUR_SECURE_API_KEY_HERE"
        
    if GEMINI_API_KEY == "YOUR_SECURE_API_KEY_HERE" or not GEMINI_API_KEY:
        UI.TaskDialog.Show("Security Warning", "API Key missing.")
        return

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
    
    # UPGRADED SYSTEM INSTRUCTIONS
    system_instruction_text = (
        "You are an expert BIM Data Architect. Convert natural language requests into a structured JSON query object.\n"
        "Output ONLY raw JSON matching this key structure exactly:\n"
        '{"category": string, "keywords": list of strings, "parameter": string or null, "operator": string or null, "value": number or null, "unit": string or null, "level": string or null, "phase": string or null, "workset": string or null, "design_option": string or null}\n\n'
        "Domain Rules:\n"
        "1. CATEGORY: Rooms, Walls, Doors, Windows, Columns, Floors, Ceilings, Roofs, Furniture, Casework, Railings, Stairs, Ramps, Specialty Equipment, Generic Models, Site, Planting, Curtain Panels, Curtain Mullions, Structural Columns, Structural Framing, Structural Foundations, Plumbing, Lighting, Mechanical Equipment, Electrical Equipment, Electrical Fixtures, Ducts, Pipes, Spaces, Areas.\n"
        "2. KEYWORDS: CRITICAL - Extract identifying names, family types, descriptors, or marks (e.g., 'Tree Guard', 'Exterior'). DO NOT leave blank if the user names a specific object type.\n"
        "3. PARAMETERS: Area, Volume, Width, Height, Thickness, Length, Mark, Fire Rating, Cost, or any custom parameter mentioned.\n"
        "4. UNIT: If the user provides a unit (e.g., 'mm', 'cm', 'm', 'ft', 'in'), extract it here. Default to 'mm' for dimensions.\n"
        "5. WORKSET/PHASE/DESIGN OPTION: Extract context filters."
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
        UI.TaskDialog.Show("API Error", "Connection failed: " + str(e))
        return

    # Extract Action Data
    cat_str = parsed_data.get("category", "Doors")
    keywords = parsed_data.get("keywords") or []
    param_str = parsed_data.get("parameter")
    op = parsed_data.get("operator")
    raw_val = parsed_data.get("value")
    target_val = float(raw_val) if raw_val is not None else 0.0
    unit_str = parsed_data.get("unit") # NEW UNIT DATA
    level_str = parsed_data.get("level")
    phase_str = parsed_data.get("phase")
    workset_str = parsed_data.get("workset")
    do_str = parsed_data.get("design_option")
    
    target_unit = unit_str.lower() if unit_str else "mm"

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
    total_val_sum = 0.0
    diagnosed_param_name = param_str 

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
                lvl_param = elem.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM) or elem.get_Parameter(DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM) or elem.get_Parameter(DB.BuiltInParameter.ROOM_LEVEL_ID)
                if not lvl_param:
                    for p in elem.Parameters:
                        if "level" in p.Definition.Name.lower() and p.StorageType == DB.StorageType.ElementId:
                            lvl_param = p; break
                if lvl_param and lvl_param.HasValue:
                    lvl_elem = doc.GetElement(lvl_param.AsElementId())
                    if lvl_elem: elem_level_name = lvl_elem.Name
        except: pass
        if level_str and not matches_level(level_str, elem_level_name): continue

        # Context Filters
        elem_phase_name = "N/A"
        phase_param = elem.get_Parameter(DB.BuiltInParameter.PHASE_CREATED)
        if phase_param and phase_param.AsElementId() != DB.ElementId.InvalidElementId:
            phase_elem = doc.GetElement(phase_param.AsElementId())
            if phase_elem: elem_phase_name = phase_elem.Name
        if phase_str and phase_str.lower().strip() not in elem_phase_name.lower().strip(): continue

        elem_ws_name = "N/A"
        if doc.IsWorkshared and elem.WorksetId != DB.WorksetId.InvalidWorksetId:
            ws = doc.GetWorksetTable().GetWorkset(elem.WorksetId)
            if ws: elem_ws_name = ws.Name
        if workset_str and workset_str.lower().strip() not in elem_ws_name.lower().strip(): continue

        elem_do_name = "Main Model"
        if elem.DesignOption: elem_do_name = elem.DesignOption.Name
        if do_str and do_str.lower().strip() not in elem_do_name.lower().strip(): continue

        # --- STRICTER KEYWORD FILTERING ---
        elem_name, family_name = "Unknown", ""
        try:
            if elem_type:
                elem_name = elem_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or elem.Name
                family_name = elem_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME).AsString() or ""
            else: elem_name = elem.Name
        except: pass

        if keywords:
            stop_words = set(["find", "all", "show", "me", "get", "the", "door", "doors", "wall", "walls", "window", "windows", "railing", "railings"])
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
            
            # Require all keywords to match to prevent bulk selections
            if filtered_words and not all(word in target_str for word in filtered_words): 
                continue

        # --- PARAMETER EVALUATION WITH DYNAMIC MATH ---
        param_val_display = "N/A"
        if param_str:
            target_clean = param_str.lower().strip()
            param_to_eval = None
            
            for p in elem.Parameters:
                if p.Definition.Name.lower() == target_clean:
                    param_to_eval = p; break
            if not param_to_eval and elem_type:
                for p in elem_type.Parameters:
                    if p.Definition.Name.lower() == target_clean:
                        param_to_eval = p; break
            
            if not param_to_eval:
                target_words = target_clean.split()
                best_match, highest_score = None, 0
                def score_param(p):
                    return sum(1 for word in target_words if word in p.Definition.Name.lower())
                for p in elem.Parameters:
                    score = score_param(p)
                    if score > highest_score: highest_score, best_match = score, p
                if elem_type:
                    for p in elem_type.Parameters:
                        score = score_param(p)
                        if score > highest_score: highest_score, best_match = score, p
                if best_match and highest_score > 0: param_to_eval = best_match
            
            if not param_to_eval:
                if "area" in target_clean: param_to_eval = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED) or elem.get_Parameter(DB.BuiltInParameter.ROOM_AREA)
                elif "volume" in target_clean: param_to_eval = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)
                elif any(x in target_clean for x in ["width", "thickness"]): param_to_eval = elem.get_Parameter(DB.BuiltInParameter.WALL_ATTR_WIDTH_PARAM) or elem.get_Parameter(DB.BuiltInParameter.DOOR_WIDTH) or elem.get_Parameter(DB.BuiltInParameter.WINDOW_WIDTH)
                elif "height" in target_clean: param_to_eval = elem.get_Parameter(DB.BuiltInParameter.DOOR_HEIGHT) or elem.get_Parameter(DB.BuiltInParameter.WINDOW_HEIGHT) or elem.get_Parameter(DB.BuiltInParameter.WALL_USER_HEIGHT_PARAM)

            if param_to_eval and param_to_eval.HasValue:
                diagnosed_param_name = param_to_eval.Definition.Name
                val = None
                
                if param_to_eval.StorageType == DB.StorageType.Double:
                    raw_double = param_to_eval.AsDouble()
                    dim_keywords = ["width", "thickness", "height", "length", "offset", "elevation"]
                    
                    if "area" in target_clean: 
                        val = raw_double * 0.092903 # Sq Ft to Sq M
                    elif "volume" in target_clean: 
                        val = raw_double * 0.0283168 # Cu Ft to Cu M
                    elif any(k in target_clean for k in dim_keywords): 
                        # --- DYNAMIC UNIT CONVERSION FOR COMPARISON ---
                        if target_unit in ["mm", "millimeter", "millimeters"]: val = raw_double * 304.8
                        elif target_unit in ["cm", "centimeter", "centimeters"]: val = raw_double * 30.48
                        elif target_unit in ["m", "meter", "meters"]: val = raw_double * 0.3048
                        elif target_unit in ["in", "\"", "inch", "inches"]: val = raw_double * 12.0
                        elif target_unit in ["ft", "'", "foot", "feet"]: val = raw_double * 1.0
                        else: val = raw_double * 304.8 # Fallback metric
                    else: 
                        val = raw_double
                        
                elif param_to_eval.StorageType == DB.StorageType.Integer: val = param_to_eval.AsInteger()
                elif param_to_eval.StorageType == DB.StorageType.String: val = param_to_eval.AsString()

                if val is not None:
                    if op == ">" and isinstance(val, (int, float)) and val > target_val: pass
                    elif op == "<" and isinstance(val, (int, float)) and val < target_val: pass
                    elif op == "==" and isinstance(val, (int, float)) and abs(val - target_val) < 0.01: pass
                    elif op == "==" and isinstance(val, str) and str(target_val).lower() in val.lower(): pass
                    else: continue
                    
                    if isinstance(val, (int, float)):
                        total_val_sum += float(val)
                        param_val_display = "{:.2f} {}".format(val, target_unit if any(k in target_clean for k in dim_keywords) else "")
                    else: param_val_display = str(val)
            else: continue

        matched_elements.append({
            "id": elem.Id, "name": elem_name, "level": elem_level_name, 
            "phase": elem_phase_name, "workset": elem_ws_name, "design_option": elem_do_name,
            "param_val": param_val_display
        })

    # --- Phase 3: The Diagnostic Error Report ---
    if not matched_elements:
        diag_msg = "No elements matched your criteria.\n\n"
        if param_str:
            sample_elem = DB.FilteredElementCollector(doc).OfCategory(selected_cat).WhereElementIsNotElementType().FirstElement()
            if sample_elem:
                available_params = [p.Definition.Name for p in sample_elem.Parameters if p.StorageType != DB.StorageType.ElementId]
                if available_params:
                    diag_msg += "💡 DIAGNOSTIC REPORT:\nCould not evaluate '{}'. Available parameters for '{}' include:\n- {}".format(
                        param_str, cat_str, "\n- ".join(sorted(set(available_params))[:15])
                    )
        UI.TaskDialog.Show("Audit Complete", diag_msg)
        return

    # 5. Output Generation & Visual Override
    out = output.get_output()
    out.close()

    matching_ids = [e["id"] for e in matched_elements]
    ogs = DB.OverrideGraphicSettings()
    ogs.SetProjectionLineColor(DB.Color(212, 175, 55)) 
    
    with DB.Transaction(doc, "AI Model Search") as t:
        t.Start()
        for eid in matching_ids: active_view.SetElementOverrides(eid, ogs)
        t.Commit()
    
    id_collection = List[DB.ElementId](matching_ids)
    uidoc.Selection.SetElementIds(id_collection)
    uidoc.RefreshActiveView()

    out.print_md("# 🤖 Smart BIM AI Report")
    out.print_md("**Query:** *\"{}\"*".format(user_prompt))
    out.print_md("---")
    
    out.print_md("### 📊 Metrics Summary")
    out.print_md("* **Matches Found:** `{}`".format(len(matched_elements)))
    if phase_str: out.print_md("* **Phase Filter:** `{}`".format(phase_str))
    if workset_str: out.print_md("* **Workset Filter:** `{}`".format(workset_str))
    if do_str: out.print_md("* **Design Option Filter:** `{}`".format(do_str))
    if param_str and total_val_sum > 0: out.print_md("* **Sum ({}):** `{:.2f} {}`".format(diagnosed_param_name, total_val_sum, target_unit))

    out.print_md("---")
    table_data = []
    for item in matched_elements:
        table_data.append([
            out.linkify(item["id"]), item["name"], item["level"], 
            item["phase"], item["workset"], item["design_option"], item["param_val"]
        ])

    out.print_table(
        table_data=table_data,
        columns=["ID", "Type/Name", "Level", "Phase", "Workset", "Design Option", diagnosed_param_name if param_str else "Value"]
    )

    try:
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = "BIM_AI_Report_" + timestamp + ".csv"
        csv_path = os.path.join(temp_dir, csv_filename)

        with open(csv_path, 'w') as csvfile:
            writer = csv.writer(csvfile, lineterminator='\n')
            writer.writerow(["Element ID", "Type / Name", "Level", "Phase", "Workset", "Design Option", diagnosed_param_name if param_str else "Value"])
            for item in matched_elements:
                writer.writerow([
                    safe_str(item["id"]), safe_str(item["name"]), safe_str(item["level"]), 
                    safe_str(item["phase"]), safe_str(item["workset"]), safe_str(item["design_option"]), safe_str(item["param_val"])
                ])
        
        out.print_md("---")
        out.print_md("### 💾 Export Data")
        out.print_md("A CSV file was generated in your temporary folder to avoid cluttering your Desktop.")
        out.print_md("**Copy & paste this path into Excel or File Explorer:**")
        out.print_html("<div style='background:#f4f4f4; border:1px solid #ddd; padding:8px; border-radius:4px; font-family:monospace;'>{}</div>".format(csv_path))
        
    except Exception as e:
        out.print_md("⚠️ **Error saving CSV:** " + str(e))

try: run_script()
except Exception as ex: UI.TaskDialog.Show("Error", str(ex))