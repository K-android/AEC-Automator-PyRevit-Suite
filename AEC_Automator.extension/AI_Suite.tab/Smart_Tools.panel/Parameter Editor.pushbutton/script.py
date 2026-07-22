# -*- coding: utf-8 -*-
import clr
import re
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('System')

import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI
from System.Collections.Generic import List

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

    # 1. Prompt User
    instructions = (
        "✏️ BIM AI Parameter Editor\n\n"
        "How to use:\n"
        "• State elements and target parameter (e.g., 'Set Fire Rating of Level 1 doors to 2-HR').\n"
        "• To wipe data, say 'Clear' or 'Remove' (e.g., 'Clear comments on all walls').\n"
        "• For checkboxes, use Yes/No or True/False.\n\n"
        "Tell the AI what to update:"
    )
    user_prompt = forms.ask_for_string(
        prompt=instructions,
        title="BIM AI Parameter Editor",
        default="Set Fire Rating of all doors to 2-HR"
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
        "You are a Revit API Data Editor. Convert natural language into a JSON edit object.\n"
        "Output ONLY raw JSON matching this key structure exactly:\n"
        '{"category": string, "keywords": list of strings, "level": string or null, "phase": string or null, "workset": string or null, "design_option": string or null, "target_parameter": string, "new_value": string or number}\n\n'
        "Domain Rules:\n"
        "1. CATEGORY: Rooms, Walls, Doors, Windows, Columns, Floors, Ceilings, Roofs, Furniture, Plumbing, Lighting, Mechanical Equipment, Casework, etc.\n"
        "2. KEYWORDS: Words to locate the elements. DO NOT include the parameter name or new value here.\n"
        "3. TARGET_PARAMETER: The exact name of the Revit parameter to change (e.g. 'Fire Rating', 'Comments', 'Is Exterior').\n"
        "4. NEW_VALUE: The exact value to write. \n"
        "   - If the user asks to CLEAR, REMOVE, or WIPE a value, output an empty string \"\".\n"
        "   - If the parameter is a Yes/No checkbox, output 1 for Yes/Check/True and 0 for No/Uncheck/False."
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

    # Extract Action Data
    cat_str = parsed_data.get("category", "Doors")
    keywords = parsed_data.get("keywords") or []
    level_str = parsed_data.get("level")
    target_param_name = parsed_data.get("target_parameter")
    new_value = parsed_data.get("new_value")

    if not target_param_name or new_value is None:
        UI.TaskDialog.Show("AI Error", "The AI could not determine which parameter to change, or what the new value should be. Try rephrasing.")
        return

    # 4. Search Revit Document
    cat_map = {
        "Rooms": DB.BuiltInCategory.OST_Rooms, "Walls": DB.BuiltInCategory.OST_Walls,
        "Doors": DB.BuiltInCategory.OST_Doors, "Windows": DB.BuiltInCategory.OST_Windows,
        "Columns": DB.BuiltInCategory.OST_Columns, "Floors": DB.BuiltInCategory.OST_Floors,
        "Ceilings": DB.BuiltInCategory.OST_Ceilings, "Roofs": DB.BuiltInCategory.OST_Roofs,
        "Furniture": DB.BuiltInCategory.OST_Furniture, "Plumbing": DB.BuiltInCategory.OST_PlumbingFixtures,
        "Lighting": DB.BuiltInCategory.OST_LightingFixtures, "Mechanical Equipment": DB.BuiltInCategory.OST_MechanicalEquipment,
        "Casework": DB.BuiltInCategory.OST_Casework, "Specialty Equipment": DB.BuiltInCategory.OST_SpecialityEquipment
    }

    selected_cat = cat_map.get(cat_str, DB.BuiltInCategory.OST_Doors)
    collector = DB.FilteredElementCollector(doc).OfCategory(selected_cat).WhereElementIsNotElementType()

    matched_elements = []
    processed_type_ids = set()

    for elem in collector:
        elem_type = None
        try: elem_type = doc.GetElement(elem.GetTypeId())
        except: pass

        # Level Filter
        elem_level_name = "N/A"
        try:
            if hasattr(elem, "Level") and elem.Level: elem_level_name = elem.Level.Name
            else:
                lvl_param = elem.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM) or elem.get_Parameter(DB.BuiltInParameter.ROOM_LEVEL_ID)
                if lvl_param:
                    lvl_elem = doc.GetElement(lvl_param.AsElementId())
                    if lvl_elem: elem_level_name = lvl_elem.Name
        except: pass
        if level_str and not matches_level(level_str, elem_level_name): continue

        # Smart Keyword Filtering
        elem_name, family_name = "Unknown", ""
        try:
            if elem_type:
                elem_name = elem_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or elem.Name
                family_name = elem_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME).AsString() or ""
            else: elem_name = elem.Name
        except: pass

        if keywords:
            param_words = normalize_text(target_param_name).split()
            val_words = normalize_text(str(new_value)).split()
            stop_words = set(["find", "all", "show", "me", "get", "the", "set", "change", "update", "clear", "remove", "door", "doors", "wall", "walls", "to", "with", "value"] + param_words + val_words)
            
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
        
        # Robust Parameter Lookup
        param_to_edit = elem.LookupParameter(target_param_name)
        if not param_to_edit and elem_type:
            param_to_edit = elem_type.LookupParameter(target_param_name)
            
        if not param_to_edit:
            if "fire rating" in target_param_name.lower():
                param_to_edit = elem.get_Parameter(DB.BuiltInParameter.FIRE_RATING)
                if not param_to_edit and elem_type: param_to_edit = elem_type.get_Parameter(DB.BuiltInParameter.FIRE_RATING)
            elif "comments" in target_param_name.lower():
                param_to_edit = elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            elif "mark" in target_param_name.lower():
                param_to_edit = elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
            
        if param_to_edit and not param_to_edit.IsReadOnly:
            if elem_type and param_to_edit.Element.Id == elem_type.Id:
                type_id_key = str(elem_type.Id)
                if type_id_key in processed_type_ids:
                    continue
                processed_type_ids.add(type_id_key)
                
            matched_elements.append({
                "element": param_to_edit.Element,
                "param": param_to_edit
            })

    if not matched_elements:
        UI.TaskDialog.Show("Search Complete", "No editable elements matched your criteria, or the parameter '{}' is Read-Only/Missing.".format(target_param_name))
        return

    # 5. The Safety Checkpoint
    dialog = UI.TaskDialog("AI Safety Checkpoint")
    dialog.MainInstruction = "AI is ready to update the Revit model."
    display_val = "CLEAR/EMPTY" if new_value == "" else new_value
    dialog.MainContent = "Target Category: {}\nUnique Elements/Types to Update: {}\n\nParameter: '{}'\nNew Value: '{}'\n\nDo you want to proceed?".format(cat_str, len(matched_elements), target_param_name, display_val)
    dialog.CommonButtons = UI.TaskDialogCommonButtons.Yes | UI.TaskDialogCommonButtons.No
    
    if dialog.Show() == UI.TaskDialogResult.Yes:
        # 6. Execute the Transaction (With Checkbox & Clear Handlers)
        success_count = 0
        with DB.Transaction(doc, "AI Parameter Update") as t:
            t.Start()
            for item in matched_elements:
                param = item["param"]
                try:
                    # Clear Protocol
                    if new_value == "" or str(new_value).lower() in ["clear", "none", "null"]:
                        if param.StorageType == DB.StorageType.String:
                            param.Set("")
                        elif param.StorageType == DB.StorageType.Integer:
                            param.Set(0) # Unchecks boxes, zeroes numbers
                        elif param.StorageType == DB.StorageType.Double:
                            param.Set(0.0)
                        success_count += 1
                    
                    # Standard Write Protocol
                    else:
                        if param.StorageType == DB.StorageType.String:
                            param.Set(str(new_value))
                        elif param.StorageType == DB.StorageType.Double:
                            param.Set(float(new_value))
                        elif param.StorageType == DB.StorageType.Integer:
                            # Yes/No Checkbox Safety Net
                            val_str = str(new_value).lower().strip()
                            if val_str in ["true", "yes", "checked", "on"]:
                                param.Set(1)
                            elif val_str in ["false", "no", "unchecked", "off"]:
                                param.Set(0)
                            else:
                                param.Set(int(float(new_value)))
                        success_count += 1
                except Exception:
                    pass
            t.Commit()
            
        UI.TaskDialog.Show("Update Complete", "Successfully updated {} parameter(s)!".format(success_count))

try: run_script()
except Exception as ex: UI.TaskDialog.Show("Error", str(ex))
