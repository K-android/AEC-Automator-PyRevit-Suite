# AEC Automator | PyRevit AI Suite

A robust, custom Revit extension built with PyRevit, Python, and the Revit API. This toolset leverages Google Gemini's Large Language Model (LLM) to translate natural language prompts into safe, precise, and predictable BIM workflows. 

Designed for Design Technologists and BIM Coordinators, this suite accelerates day-to-day architectural modeling, enforces data integrity for strict ISO-compliant deliverables, and bridges the gap between conversational AI and hard-coded Revit API transactions.

### 🧠 Core System Upgrades
*   **Self-Diagnosing Parameter Engine:** Employs fuzzy-logic matching to auto-correct slight parameter misspellings (e.g., mapping user input "fire code" to Revit's exact "Fire Rating"). If a parameter genuinely doesn't exist, it generates a diagnostic report of available parameters for the user.
*   **Dynamic Unit Math Engine:** Automatically extracts units (mm, cm, m, in, ft) from prompts and dynamically converts them to Revit's internal Decimal Feet format on the fly, ensuring safe dimensional scaling.
*   **Strict Keyword Isolation:** Prevents accidental bulk-editing by isolating elements via Family Names, Type Names, Marks, and Comments prior to transaction execution.

---

## 🛠️ The Toolkit

The suite consists of four specialized tools, structured for maximum predictability and model safety. **Click on any tool below to view its source code:**

### 1. [AI Finder & Auditor](./AEC_Automator.extension/AI_Suite.tab/Smart_Tools.panel/Finder%20&%20Auditor.pushbutton)
A localized, read-only search engine for your Revit model.
*   **Function:** Searches the model using natural language and highlights elements matching specific parameter queries, targeted names, levels, phases, or worksets. Fully unit-aware for dimensional filtering (e.g., "Find doors with Height > 7ft").
*   **Output:** Visually overrides elements in gold and silently generates temporary CSV reports for external database tracking and schedules.

### 2. [AI Parameter Editor](./AEC_Automator.extension/AI_Suite.tab/Smart_Tools.panel/Parameter%20Editor.pushbutton)
Translates text prompts into direct database edits with built-in unit conversion.
*   **Function:** Securely handles string, double, and integer (Yes/No) modifications across multiple elements or types simultaneously. 
*   **Safety Checkpoint:** Features a mandatory UI confirmation dialogue to verify transaction quantities, target parameters, active metric conversions, and exact values *before* committing changes to the Revit database.

### 3. [AI View Manipulator](./AEC_Automator.extension/AI_Suite.tab/Smart_Tools.panel/View%20Manipulator.pushbutton)
An automated virtual camera operator for 3D views.
*   **Function:** Automates Revit camera and visibility graphics. Instantly calculates collective element bounding boxes to generate precise 3D section boxes around specific target elements, or temporarily isolates specialized categories via text prompt.

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
4. **Security Requirement:** To prevent exposing API credentials in public repositories, this suite securely retrieves your API key from Windows Environment Variables. 
    * Open your Windows Start Menu and search for **"Edit the system environment variables"**.
    * Click **"Environment Variables..."** at the bottom.
    * Under "User variables", click **"New..."**.
    * Set Variable name as `GEMINI_API_KEY` and Variable value as your actual Google Gemini API key. Click OK.
5. Reload PyRevit to initialize the ribbon and authenticate the AI.

---

## ⚖️ License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

*Disclaimer: This tool executes automated transactions within the Revit database. While safety checkpoints are included, users are responsible for verifying model changes. Provided "as is" without warranty.*
