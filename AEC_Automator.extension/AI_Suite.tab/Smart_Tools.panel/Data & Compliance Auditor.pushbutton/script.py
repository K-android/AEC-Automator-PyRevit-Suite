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
    if not text: return ""
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', str(text)).lower()

def safe_str(val):
    if val is None: return ""
    try: return unicode(val).encode('utf-8')
    except NameError: return str(val)

def reset_view_overrides(doc, active_view):
    collector = DB.FilteredElementCollector(doc, active_view.Id).WhereElementIsNotElementType()
    empty_ogs = DB.OverrideGraphicSettings()
    with DB.Transaction(doc, "Clear QA Overrides") as t:
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
        "🚨 AI Data & Compliance Auditor (Self-Diagnosing)\n\n"
        "How to use:\n"
        "• Missing Data: 'Find all Tree Guard railings missing a Mark'\n"
        "• Code Thresholds: 'Show walls with thickness less than 150mm'\n"
        "• Quality Control: 'Find rooms missing a name'\n"
        "• Type 'reset' to clear all red error highlights.\n\n"
        "Enter your QA/QC rule:"
    )
    user_prompt = forms.ask_for_string(
        prompt=instructions,
        title="BIM AI Data & Compliance Auditor",
        default="Find all doors missing a Fire Rating"
    )
    if not user_prompt: return
    
    if user_prompt.lower().strip() == "reset":
        reset_view_overrides(doc, active_view)
        UI.TaskDialog.Show("Reset Complete", "All AI error highlights have been cleared.")
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
    
    system_instruction_text = (
        "You are a Revit QA/QC Auditor. Convert natural language rules into a JSON audit object.\n"
        "Output ONLY raw JSON matching this key structure exactly:\n"
        '{"category": string, "keywords": list of strings, "target_parameter": string, "audit_type": string, "operator": string or null, "value": number or null, "unit": string or null}\n\n'
        "Domain Rules:\n"
        "1. CATEGORY: Rooms, Walls, Doors, Windows, Columns, Floors, Ceilings, Roofs, Furniture, Casework, Railings, Stairs, Ramps, Specialty Equipment, Generic Models, Site, Planting, Curtain Panels, Curtain Mullions, Structural Columns, Structural Framing, Structural Foundations, Plumbing, Lighting, Mechanical Equipment, Electrical Equipment, Electrical Fixtures, Ducts, Pipes, Spaces, Areas.\n"
        "2. KEYWORDS: Extract identifying names, family types, or descriptors (e.g., 'Tree Guard', 'Exterior').\n"
        "3. TARGET_PARAMETER: The parameter being audited (e.g. 'Fire Rating', 'Comments', 'Height').\n"
        "4. AUDIT_TYPE: Must be 'missing_data' (if checking for null/empty) or 'threshold' (if checking numerical limits).\n"
        "5. OPERATOR: '<', '>', '==', or null. (Only used if audit_type is 'threshold').\n"
        "6. UNIT: If the user provides a unit (e.g., 'mm', 'cm', 'm', 'ft', 'in'), extract it here. Default to 'mm' for dimensions."
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

    cat_str = parsed_data.get("category", "Doors")
    keywords = parsed_data.get("keywords") or []
    target_param_name = parsed_data.get("target_parameter")
    audit_type = parsed_data.get("audit_type", "missing_data")
    op = parsed_data.get("operator")
    raw_val = parsed_data.get("value")
    target_val = float(raw_val) if raw_val is not None else 0.0
    unit_str = parsed_data.get("unit")
    target_unit = unit_str.lower() if unit_str else "mm"

    if not target_param_name:
        UI.TaskDialog.Show("AI Error", "The AI couldn't figure out which parameter you want to audit.")
        return

    # 4. Search Revit Document - MASSIVE CATEGORY EXPANSION
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
    failed_elements = []
    diagnosed_param_name = target_param_name

    for elem in collector:
        elem_type = None
        try: elem_type = doc.GetElement(elem.GetTypeId())
        except: pass

        elem_name = "Unknown"
        family_name = ""
        try:
            if elem_type:
                elem_name = elem_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or elem.Name
                family_name = elem_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME).AsString() or ""
            else: elem_name = elem.Name
        except: pass

        # Keyword Isolation Filtering
        if keywords:
            stop_words = set(["find", "all", "show", "me", "get", "the", "door", "doors", "wall", "walls", "window", "windows", "railing", "railings", "missing", "less", "than", "greater", "with"])
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
            
            if filtered_words and not all(word in target_str for word in filtered_words): 
                continue

        # --- THE SELF-DIAGNOSING PARAMETER ENGINE ---
        param = None
        target_clean = target_param_name.lower().strip()
        
        for p in elem.Parameters:
            if p.Definition.Name.lower() == target_clean:
                param = p; break
        if not param and elem_type:
            for p in elem_type.Parameters:
                if p.Definition.Name.lower() == target_clean:
                    param = p; break
        
        if not param:
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
            if best_match and highest_score > 0: param = best_match

        if not param:
            if "fire rating" in target_clean:
                param = elem.get_Parameter(DB.BuiltInParameter.FIRE_RATING) or (elem_type.get_Parameter(DB.BuiltInParameter.FIRE_RATING) if elem_type else None)
            elif "comments" in target_clean:
                param = elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            elif "area" in target_clean: 
                param = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED) or elem.get_Parameter(DB.BuiltInParameter.ROOM_AREA)
            elif any(x in target_clean for x in ["width", "thickness"]): 
                param = elem.get_Parameter(DB.BuiltInParameter.WALL_ATTR_WIDTH_PARAM) or elem.get_Parameter(DB.BuiltInParameter.DOOR_WIDTH) or elem.get_Parameter(DB.BuiltInParameter.WINDOW_WIDTH)
            elif "height" in target_clean: 
                param = elem.get_Parameter(DB.BuiltInParameter.DOOR_HEIGHT) or elem.get_Parameter(DB.BuiltInParameter.WINDOW_HEIGHT) or elem.get_Parameter(DB.BuiltInParameter.WALL_USER_HEIGHT_PARAM)

        is_failed = False
        current_val_display = "N/A"

        if param: diagnosed_param_name = param.Definition.Name

        # AUDIT LOGIC: Missing Data
        if audit_type == "missing_data":
            if not param:
                is_failed = True
                current_val_display = "Parameter Not Found"
            elif not param.HasValue:
                is_failed = True
                current_val_display = "<Null/Empty>"
            elif param.StorageType == DB.StorageType.String and str(param.AsString()).strip() == "":
                is_failed = True
                current_val_display = "<Blank String>"
                
        # AUDIT LOGIC: Thresholds & Math Engine
        elif audit_type == "threshold" and param and param.HasValue:
            val = None
            if param.StorageType == DB.StorageType.Double:
                raw_double = param.AsDouble()
                dim_keywords = ["width", "thickness", "height", "length", "offset", "elevation"]
                
                if "area" in target_clean: val = raw_double * 0.092903
                elif "volume" in target_clean: val = raw_double * 0.0283168
                elif any(k in target_clean for k in dim_keywords): 
                    if target_unit in ["mm", "millimeter", "millimeters"]: val = raw_double * 304.8
                    elif target_unit in ["cm", "centimeter", "centimeters"]: val = raw_double * 30.48
                    elif target_unit in ["m", "meter", "meters"]: val = raw_double * 0.3048
                    elif target_unit in ["in", "\"", "inch", "inches"]: val = raw_double * 12.0
                    elif target_unit in ["ft", "'", "foot", "feet"]: val = raw_double * 1.0
                    else: val = raw_double * 304.8
                else: val = raw_double
            elif param.StorageType == DB.StorageType.Integer: val = param.AsInteger()

            if val is not None:
                current_val_display = "{:.2f} {}".format(val, target_unit if any(k in target_clean for k in dim_keywords) else "")
                if op == ">" and not (val > target_val): is_failed = True
                elif op == "<" and not (val < target_val): is_failed = True
                elif op == "==" and not (abs(val - target_val) < 0.01): is_failed = True
            else:
                is_failed = True
                current_val_display = "Not a Number"
        elif audit_type == "threshold" and (not param or not param.HasValue):
            is_failed = True
            current_val_display = "<Missing Data>"

        if is_failed:
            failed_elements.append({"id": elem.Id, "name": elem_name, "error": current_val_display})

    # Diagnostic Check if completely failed
    if not failed_elements and not any(elem for elem in collector):
        UI.TaskDialog.Show("Audit Complete", "No elements matched your keyword criteria to audit.")
        return

    # 5. Output Generation
    out = output.get_output()
    out.close()

    if failed_elements:
        matching_ids = [e["id"] for e in failed_elements]
        
        # Graphic Override: RED for Errors
        ogs = DB.OverrideGraphicSettings()
        ogs.SetProjectionLineColor(DB.Color(255, 0, 0)) # Solid Red
        ogs.SetSurfaceForegroundPatternColor(DB.Color(255, 0, 0))
        
        with DB.Transaction(doc, "AI QA Overrides") as t:
            t.Start()
            for eid in matching_ids: active_view.SetElementOverrides(eid, ogs)
            t.Commit()
        
        id_collection = List[DB.ElementId](matching_ids)
        uidoc.Selection.SetElementIds(id_collection)
        uidoc.RefreshActiveView()

        out.print_md("# 🚨 AI QA/QC Error Report")
        out.print_md("**Audit Rule:** *\"{}\"*".format(user_prompt))
        out.print_md("---")
        out.print_md("### ⚠️ Violations Found: `{}`".format(len(failed_elements)))
        out.print_md("The elements listed below failed the audit and have been highlighted in **RED** in your active view.")

        table_data = []
        for item in failed_elements:
            table_data.append([out.linkify(item["id"]), item["name"], diagnosed_param_name, item["error"]])

        out.print_table(
            table_data=table_data,
            columns=["Element ID", "Type/Name", "Audited Parameter", "Current Value (Error)"]
        )

        try:
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = "BIM_QA_Audit_" + timestamp + ".csv"
            csv_path = os.path.join(temp_dir, csv_filename)

            with open(csv_path, 'w') as csvfile:
                writer = csv.writer(csvfile, lineterminator='\n')
                writer.writerow(["Element ID", "Type / Name", "Audited Parameter", "Error Value"])
                for item in failed_elements:
                    writer.writerow([safe_str(item["id"]), safe_str(item["name"]), safe_str(diagnosed_param_name), safe_str(item["error"])])
            
            out.print_md("---")
            out.print_md("### 💾 Export Audit Log")
            out.print_md("Copy & paste this path into Excel to save the error report:")
            out.print_html("<div style='background:#ffe6e6; border:1px solid #ff9999; padding:8px; border-radius:4px; font-family:monospace; color:#cc0000;'>{}</div>".format(csv_path))
            
        except Exception as e: pass
    else:
        UI.TaskDialog.Show("Audit Passed", "✅ Perfect! No elements violated your QA rule.")

try: run_script()
except Exception as ex: UI.TaskDialog.Show("Error", str(ex))