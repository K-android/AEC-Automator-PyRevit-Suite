# -*- coding: utf-8 -*-
import clr
import re
import csv
import os
import datetime
import tempfile
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('System')

import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI
from System.Collections.Generic import List

def normalize_text(text):
    if not text:
        return ""
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', str(text)).lower()

def safe_str(val):
    """Ensures text exports cleanly to CSV without Unicode errors in IronPython."""
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
        "🤖 BIM AI Finder & Auditor\n\n"
        "How to use:\n"
        "• Search by category and parameters (e.g., 'Find all doors with Height > 2000').\n"
        "• Filter by Level, Phase, or Workset.\n"
        "• Type 'reset' to clear all gold highlights.\n\n"
        "Enter your query:"
    )
    user_prompt = forms.ask_for_string(
        prompt=instructions,
        title="BIM AI Finder & Auditor",
        default="Find doors with Fire Rating > 1"
    )
    if not user_prompt: return

    # 2. Configure .NET Networking
    import json
    from System.Net import ServicePointManager, SecurityProtocolType, WebClient, HttpRequestHeader
    from System.Text import Encoding
    ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12

    # ==========================================================================
    # PASTE YOUR GEMINI API KEY HERE
    # ==========================================================================
    GEMINI_API_KEY = "AIzaSyAUcLwGerdXf51UT4H7GXZkcR5IlA-MeO0"

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
    
    system_instruction_text = (
        "You are an expert BIM Data Architect. Convert natural language requests into a structured JSON query object.\n"
        "Output ONLY raw JSON matching this key structure exactly:\n"
        '{"category": string, "keywords": list of strings, "parameter": string or null, "operator": string or null, "value": number or null, "level": string or null, "phase": string or null, "workset": string or null, "design_option": string or null}\n\n'
        "Domain Rules:\n"
        "1. CATEGORY: Rooms, Walls, Doors, Windows, Columns, Floors, Ceilings, Roofs, Furniture, Beams, Plumbing, Lighting, Electrical Equipment, Mechanical Equipment, Ducts, Pipes, Curtain Panels, Casework, Specialty Equipment, Generic Models, Stairs, Railings.\n"
        "2. KEYWORDS: Extract descriptive style, material, manufacturer, or function words (e.g. ['exterior', 'glass', 'kohler', 'wood']).\n"
        "3. PARAMETERS: Area, Volume, Width, Height, Thickness, Length, Mark, Fire Rating, Cost, or any custom parameter mentioned.\n"
        "4. WORKSET/DESIGN OPTION/PHASE: Extract references to worksets, phases, or design options."
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
    res_json = json.loads(Encoding.UTF8.GetString(client.UploadData(url, "POST", raw_bytes)))
    clean_json_str = res_json['candidates'][0]['content']['parts'][0]['text'].replace("```json", "").replace("```", "").strip()
    parsed_data = json.loads(clean_json_str)

    # 4. Search Revit Document
    cat_map = {
        "Rooms": DB.BuiltInCategory.OST_Rooms, "Walls": DB.BuiltInCategory.OST_Walls,
        "Doors": DB.BuiltInCategory.OST_Doors, "Windows": DB.BuiltInCategory.OST_Windows,
        "Columns": DB.BuiltInCategory.OST_Columns, "Structural Columns": DB.BuiltInCategory.OST_StructuralColumns,
        "Floors": DB.BuiltInCategory.OST_Floors, "Ceilings": DB.BuiltInCategory.OST_Ceilings,
        "Roofs": DB.BuiltInCategory.OST_Roofs, "Furniture": DB.BuiltInCategory.OST_Furniture,
        "Beams": DB.BuiltInCategory.OST_StructuralFraming, "Plumbing": DB.BuiltInCategory.OST_PlumbingFixtures,
        "Lighting": DB.BuiltInCategory.OST_LightingFixtures, "Electrical Equipment": DB.BuiltInCategory.OST_ElectricalEquipment,
        "Mechanical": DB.BuiltInCategory.OST_MechanicalEquipment, "Mechanical Equipment": DB.BuiltInCategory.OST_MechanicalEquipment,
        "Ducts": DB.BuiltInCategory.OST_DuctCurves, "Pipes": DB.BuiltInCategory.OST_PipeCurves,
        "Curtain Panels": DB.BuiltInCategory.OST_CurtainWallPanels, "Casework": DB.BuiltInCategory.OST_Casework,
        "Specialty Equipment": DB.BuiltInCategory.OST_SpecialityEquipment, "Generic Models": DB.BuiltInCategory.OST_GenericModel,
        "Structural Foundations": DB.BuiltInCategory.OST_StructuralFoundation, "Stairs": DB.BuiltInCategory.OST_Stairs,
        "Railings": DB.BuiltInCategory.OST_StairsRailing
    }

    cat_str = parsed_data.get("category", "Doors")
    keywords = parsed_data.get("keywords") or []
    param_str = parsed_data.get("parameter")
    op = parsed_data.get("operator")
    raw_val = parsed_data.get("value")
    target_val = float(raw_val) if raw_val is not None else 0.0
    level_str = parsed_data.get("level")
    phase_str = parsed_data.get("phase")
    workset_str = parsed_data.get("workset")
    do_str = parsed_data.get("design_option")

    selected_cat = cat_map.get(cat_str, DB.BuiltInCategory.OST_Doors)
    collector = DB.FilteredElementCollector(doc).OfCategory(selected_cat).WhereElementIsNotElementType()

    matched_elements = []
    total_val_sum = 0.0

    for elem in collector:
        elem_type = None
        try: elem_type = doc.GetElement(elem.GetTypeId())
        except: pass

        # Filters
        elem_level_name = "N/A"
        try:
            if hasattr(elem, "Level") and elem.Level: elem_level_name = elem.Level.Name
            else:
                lvl_param = elem.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM) or elem.get_Parameter(DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM) or elem.get_Parameter(DB.BuiltInParameter.ROOM_LEVEL_ID)
                if lvl_param:
                    lvl_elem = doc.GetElement(lvl_param.AsElementId())
                    if lvl_elem: elem_level_name = lvl_elem.Name
        except: pass
        if level_str and not matches_level(level_str, elem_level_name): continue

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

        # Keyword Extraction
        elem_name, family_name, type_mark, instance_mark = "Unknown", "", "", ""
        try:
            if elem_type:
                elem_name = elem_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or elem.Name
                family_name = elem_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME).AsString() or ""
            else: elem_name = elem.Name
        except: pass

        if keywords:
            stop_words = set(["find", "all", "show", "me", "get", "the", "door", "doors", "wall", "walls", "window", "windows"])
            filtered_words = [normalize_text(w) for w in keywords if normalize_text(w) not in stop_words and len(w) > 1]
            target_str = normalize_text(family_name) + " " + normalize_text(elem_name)
            
            try:
                for p in elem.Parameters:
                    if p.StorageType == DB.StorageType.String and p.HasValue: target_str += " " + normalize_text(p.AsString())
                if elem_type:
                    for p in elem_type.Parameters:
                        if p.StorageType == DB.StorageType.String and p.HasValue: target_str += " " + normalize_text(p.AsString())
            except: pass

            if filtered_words and not all(word in target_str for word in filtered_words): continue

        # Parameter Evaluation
        param_val_display = "N/A"
        if param_str:
            param = elem.LookupParameter(param_str)
            if not param and elem_type: param = elem_type.LookupParameter(param_str)
                
            if not param:
                if param_str == "Area": param = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED) or elem.get_Parameter(DB.BuiltInParameter.ROOM_AREA)
                elif param_str == "Volume": param = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)
                elif param_str in ["Width", "Thickness"]: param = elem.get_Parameter(DB.BuiltInParameter.WALL_ATTR_WIDTH_PARAM) or elem.get_Parameter(DB.BuiltInParameter.DOOR_WIDTH) or elem.get_Parameter(DB.BuiltInParameter.WINDOW_WIDTH)
                elif param_str == "Height": param = elem.get_Parameter(DB.BuiltInParameter.DOOR_HEIGHT) or elem.get_Parameter(DB.BuiltInParameter.WINDOW_HEIGHT) or elem.get_Parameter(DB.BuiltInParameter.WALL_USER_HEIGHT_PARAM)

            if param and param.HasValue:
                val = None
                if param.StorageType == DB.StorageType.Double:
                    raw_double = param.AsDouble()
                    if param_str == "Area": val = raw_double * 0.092903
                    elif param_str == "Volume": val = raw_double * 0.0283168
                    elif param_str in ["Width", "Thickness", "Height", "Length"]: val = raw_double * 304.8
                    else: val = raw_double
                elif param.StorageType == DB.StorageType.Integer: val = param.AsInteger()
                elif param.StorageType == DB.StorageType.String: val = param.AsString()

                if val is not None:
                    if op == ">" and val > target_val: pass
                    elif op == "<" and val < target_val: pass
                    elif op == "==" and abs(val - target_val) < 0.01: pass
                    else: continue
                    
                    if isinstance(val, (int, float)):
                        total_val_sum += float(val)
                        param_val_display = "{:.2f}".format(val)
                    else: param_val_display = str(val)
            else: continue

        matched_elements.append({
            "id": elem.Id, "name": elem_name, "level": elem_level_name, 
            "phase": elem_phase_name, "workset": elem_ws_name, "design_option": elem_do_name,
            "param_val": param_val_display
        })

    # 5. Output Generation & Clickable Temp CSV Export
    out = output.get_output()
    out.close()

    if matched_elements:
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
        out.print_md("* **Matches:** `{}`".format(len(matched_elements)))
        if phase_str: out.print_md("* **Phase Filter:** `{}`".format(phase_str))
        if workset_str: out.print_md("* **Workset Filter:** `{}`".format(workset_str))
        if do_str: out.print_md("* **Design Option Filter:** `{}`".format(do_str))
        if param_str and total_val_sum > 0: out.print_md("* **Sum ({}):** `{:.2f}`".format(param_str, total_val_sum))

        out.print_md("---")
        table_data = []
        for item in matched_elements:
            table_data.append([
                out.linkify(item["id"]), item["name"], item["level"], 
                item["phase"], item["workset"], item["design_option"], item["param_val"]
            ])

        out.print_table(
            table_data=table_data,
            columns=["ID", "Type/Name", "Level", "Phase", "Workset", "Design Option", param_str if param_str else "Value"]
        )

        # ==========================================
        # TEMP CSV EXPORT
        # ==========================================
        try:
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = "BIM_AI_Report_" + timestamp + ".csv"
            csv_path = os.path.join(temp_dir, csv_filename)

            with open(csv_path, 'w') as csvfile:
                writer = csv.writer(csvfile, lineterminator='\n')
                writer.writerow(["Element ID", "Type / Name", "Level", "Phase", "Workset", "Design Option", param_str if param_str else "Value"])
                for item in matched_elements:
                    writer.writerow([
                        safe_str(item["id"]), safe_str(item["name"]), safe_str(item["level"]), 
                        safe_str(item["phase"]), safe_str(item["workset"]), safe_str(item["design_option"]), safe_str(item["param_val"])
                    ])
            
            out.print_md("---")
            out.print_md("### 💾 Export Data")
            out.print_md("A CSV file was generated in your temporary folder to avoid cluttering your Desktop.")
            out.print_md("**Copy & paste this path into Excel or File Explorer:**")
            
            # Prints the path in a clean, easily copyable text box!
            out.print_html("<div style='background:#f4f4f4; border:1px solid #ddd; padding:8px; border-radius:4px; font-family:monospace;'>{}</div>".format(csv_path))
            
        except Exception as e:
            out.print_md("⚠️ **Error saving CSV:** " + str(e))

    else:
        UI.TaskDialog.Show("Search Complete", "No elements matched criteria.")

try: run_script()
except Exception as ex: UI.TaskDialog.Show("Error", str(ex))