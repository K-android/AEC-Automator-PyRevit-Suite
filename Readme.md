# AEC Automator | PyRevit AI Suite

A robust, custom Revit extension built with PyRevit, Python, and the Revit API. This toolset leverages Google Gemini's Large Language Model (LLM) to translate natural language prompts into safe, precise, and predictable BIM workflows. 

Designed for Design Technologists and BIM Coordinators, this suite accelerates day-to-day architectural modeling, enforces data integrity for strict ISO-compliant deliverables, and bridges the gap between conversational AI and hard-coded Revit API transactions.

---

## 🛠️ The Toolkit

The suite consists of four specialized tools, structured for maximum predictability and model safety. **Click on any tool below to view its source code:**

### 1. [AI Finder & Auditor](./AEC_Automator.extension/AI_Suite.tab/Smart_Tools.panel/Finder%20&%20Auditor.pushbutton)
A localized, read-only search engine for your Revit model.
*   **Function:** Searches the model using natural language and highlights elements matching specific parameter queries, levels, phases, or worksets.
*   **Output:** Visually overrides elements in gold and silently generates temporary CSV reports for external database tracking and schedules.

### 2. [AI Parameter Editor](./AEC_Automator.extension/AI_Suite.tab/Smart_Tools.panel/Parameter%20Editor.pushbutton)
Translates text prompts into direct database edits.
*   **Function:** Securely handles string, double, and integer (Yes/No) modifications across multiple elements or types simultaneously. 
*   **Safety Checkpoint:** Features a mandatory UI confirmation dialogue to verify transaction quantities, target parameters, and exact values *before* committing changes to the Revit database.

### 3. [AI View Manipulator](./AEC_Automator.extension/AI_Suite.tab/Smart_Tools.panel/View%20Manipulator.pushbutton)
An automated virtual camera operator for 3D views.
*   **Function:** Automates Revit camera and visibility graphics. Instantly calculates element bounding boxes to generate precise 3D section boxes around target elements, or temporarily isolates specific categories via text prompt.

### 4. [AI Data & Compliance Auditor](./AEC_Automator.extension/AI_Suite.tab/Smart_Tools.panel/Data%20&%20Compliance%20Auditor.pushbutton)
A targeted QA/QC tool for validating architectural intent and schedule readiness.
*   **Function:** Instantly flags missing model data (e.g., blank fire ratings) and dimensional code violations (e.g., minimum egress widths).
*   **Output:** Overrides offending geometry in bright red for immediate visual feedback, replacing tedious manual schedule reviews.

---

## 🚀 Technical Stack
*   **Environment:** Revit, PyRevit
*   **Languages:** Python, C# (.NET Framework)
*   **API Integration:** Autodesk Revit API, Google Gemini 2.5 Flash REST API

---

## ⚙️ Installation & Setup
1. Install [PyRevit](https://github.com/eirannejad/pyRevit) on your machine.
2. Clone or download this repository.
3. Open PyRevit settings in Revit, navigate to the **Custom Extension Folders** tab, and add the directory containing the `AEC_Automator.extension` folder.
4. **Security Requirement:** To run these scripts, you must generate your own Google Gemini API key. Open the `script.py` file within each `.pushbutton` folder and paste your key into the `GEMINI_API_KEY` variable.
5. Reload PyRevit to initialize the ribbon.

---

## ⚖️ License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

*Disclaimer: This tool executes automated transactions within the Revit database. While safety checkpoints are included, users are responsible for verifying model changes. Provided "as is" without warranty.*