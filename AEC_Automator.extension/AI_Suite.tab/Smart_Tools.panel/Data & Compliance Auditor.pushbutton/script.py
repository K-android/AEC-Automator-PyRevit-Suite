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
        "🚨 AI Data & Compliance Auditor\n\n"
        "What this does: Instantly audits model data and code thresholds (Does NOT check geometry clashes).\n\n"
        "How to use:\n"
        "• Missing Data Checks: 'Find all doors missing a Fire Rating'\n"
        "• Code/Size Thresholds: 'Show walls with thickness less than 150'\n"
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

    # 2. Configure .NET Networking
    import json
    from System.Net import ServicePointManager, SecurityProtocolType, WebClient, HttpRequestHeader
    from System.Text import Encoding
    ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12

    # ==========================================================================
    # PASTE YOUR GEMINI API KEY HERE
    # ==========================================================================
    GEMINI_API_KEY = "PUT GEMINI KEY"

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
    
    system_instruction_text = (
        "You are a Revit QA/QC Auditor. Convert natural language rules into a JSON audit object.\n"
        "Output ONLY raw JSON matching this key structure exactly:\n"
        '{"category": string, "target_parameter": string, "audit_type": string, "operator": string or null, "value": number or null}\n\n'
        "Domain Rules:\n"
        "1. CATEGORY: Rooms, Walls, Doors, Windows, Columns, Floors, Ceilings, Roofs, Furniture, Plumbing, Lighting, Mechanical Equipment, Casework, etc.\n"
        "2. TARGET_PARAMETER: The parameter being audited (e.g. 'Fire Rating', 'Comments', 'Height').\n"
        "3. AUDIT_TYPE: Must be 'missing_data' (if asking for missing, empty, or unassigned values) or 'threshold' (if checking numerical limits).\n"
        "4. OPERATOR: '<', '>', '==', or null. (Only used if audit_type is 'threshold')."
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

    cat_str = parsed_data.get("category", "Doors")
    target_param_name = parsed_data.get("target_parameter")
    audit_type = parsed_data.get("audit_type", "missing_data")
    op = parsed_data.get("operator")
    raw_val = parsed_data.get("value")
    target_val = float(raw_val) if raw_val is not None else 0.0

    if not target_param_name:
        UI.TaskDialog.Show("AI Error", "The AI couldn't figure out which parameter you want to audit.")
        return

    # 4. Search Revit Document
    cat_map = {
        "Rooms": DB.BuiltInCategory.OST_Rooms, "Walls": DB.BuiltInCategory.OST_Walls,
        "Doors": DB.BuiltInCategory.OST_Doors, "Windows": DB.BuiltInCategory.OST_Windows,
        "Columns": DB.BuiltInCategory.OST_Columns, "Floors": DB.BuiltInCategory.OST_Floors,
        "Ceilings": DB.BuiltInCategory.OST_Ceilings, "Roofs": DB.BuiltInCategory.OST_Roofs,
        "Furniture": DB.BuiltInCategory.OST_Furniture, "Plumbing": DB.BuiltInCategory.OST_PlumbingFixtures,
        "Lighting": DB.BuiltInCategory.OST_LightingFixtures, "Mechanical Equipment": DB.BuiltInCategory.OST_MechanicalEquipment,
        "Casework": DB.BuiltInCategory.OST_Casework
    }

    selected_cat = cat_map.get(cat_str, DB.BuiltInCategory.OST_Doors)
    collector = DB.FilteredElementCollector(doc).OfCategory(selected_cat).WhereElementIsNotElementType()

    failed_elements = []

    for elem in collector:
        elem_type = None
        try: elem_type = doc.GetElement(elem.GetTypeId())
        except: pass

        # Get Element Info
        elem_name = "Unknown"
        try:
            if elem_type: elem_name = elem_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or elem.Name
            else: elem_name = elem.Name
        except: pass

        # Look for the parameter
        param = elem.LookupParameter(target_param_name)
        if not param and elem_type: param = elem_type.LookupParameter(target_param_name)
        
        # Fallbacks for strict system parameters
        if not param:
            if "fire rating" in target_param_name.lower():
                param = elem.get_Parameter(DB.BuiltInParameter.FIRE_RATING)
                if not param and elem_type: param = elem_type.get_Parameter(DB.BuiltInParameter.FIRE_RATING)
            elif "comments" in target_param_name.lower():
                param = elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            elif target_param_name.lower() in ["width", "height", "thickness"]:
                if target_param_name.lower() == "height": param = elem.get_Parameter(DB.BuiltInParameter.DOOR_HEIGHT) or elem.get_Parameter(DB.BuiltInParameter.WINDOW_HEIGHT) or elem.get_Parameter(DB.BuiltInParameter.WALL_USER_HEIGHT_PARAM)
                if target_param_name.lower() in ["width", "thickness"]: param = elem.get_Parameter(DB.BuiltInParameter.WALL_ATTR_WIDTH_PARAM) or elem.get_Parameter(DB.BuiltInParameter.DOOR_WIDTH) or elem.get_Parameter(DB.BuiltInParameter.WINDOW_WIDTH)

        is_failed = False
        current_val_display = "N/A"

        # AUDIT LOGIC: Check for missing/empty data
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
                
        # AUDIT LOGIC: Check thresholds
        elif audit_type == "threshold" and param and param.HasValue:
            val = None
            if param.StorageType == DB.StorageType.Double:
                raw_double = param.AsDouble()
                # Metric Conversions
                if target_param_name.lower() in ["width", "thickness", "height", "length"]: val = raw_double * 304.8
                else: val = raw_double
            elif param.StorageType == DB.StorageType.Integer: val = param.AsInteger()

            if val is not None:
                current_val_display = "{:.2f}".format(val)
                if op == ">" and not (val > target_val): is_failed = True
                elif op == "<" and not (val < target_val): is_failed = True
                elif op == "==" and not (abs(val - target_val) < 0.01): is_failed = True
            else:
                is_failed = True # Fails if it can't evaluate the threshold
                current_val_display = "Not a Number"
        elif audit_type == "threshold" and (not param or not param.HasValue):
            is_failed = True
            current_val_display = "<Missing Data>"

        if is_failed:
            failed_elements.append({
                "id": elem.Id,
                "name": elem_name,
                "error": current_val_display
            })

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
            table_data.append([out.linkify(item["id"]), item["name"], target_param_name, item["error"]])

        out.print_table(
            table_data=table_data,
            columns=["Element ID", "Type/Name", "Audited Parameter", "Current Value (Error)"]
        )

        # Temp CSV Export
        try:
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = "BIM_QA_Audit_" + timestamp + ".csv"
            csv_path = os.path.join(temp_dir, csv_filename)

            with open(csv_path, 'w') as csvfile:
                writer = csv.writer(csvfile, lineterminator='\n')
                writer.writerow(["Element ID", "Type / Name", "Audited Parameter", "Error Value"])
                for item in failed_elements:
                    writer.writerow([safe_str(item["id"]), safe_str(item["name"]), safe_str(target_param_name), safe_str(item["error"])])
            
            out.print_md("---")
            out.print_md("### 💾 Export Audit Log")
            out.print_md("Copy & paste this path into Excel to save the error report:")
            out.print_html("<div style='background:#ffe6e6; border:1px solid #ff9999; padding:8px; border-radius:4px; font-family:monospace; color:#cc0000;'>{}</div>".format(csv_path))
            
        except Exception as e: pass
    else:
        UI.TaskDialog.Show("Audit Passed", "✅ Perfect! No elements violated your QA rule.")

try: run_script()
except Exception as ex: UI.TaskDialog.Show("Error", str(ex))
