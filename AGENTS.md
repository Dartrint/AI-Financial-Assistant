<!-- vnai-bootstrap | auto-generated -->
# Vnstock Vibe Onboarding

You are an AI coding assistant (e.g., Google Antigravity, Cursor, Claude Code). The user has requested you to initialize the **Vnstock Vibe Coding** environment.

**Your Objective:** Automate the entire setup process autonomously. Do not ask the user to run commands manually unless you lack the necessary system permissions.

## Execution Workflow

Execute these steps sequentially. If a step fails, attempt to auto-remediate. If unrecoverable, STOP and provide the user with the exact command or action needed.

### 1. Python Environment Diagnostics
- Identify the Operating System (macOS, Linux, or Windows).
- Verify `python3` (or `python`/`py` on Windows) is in the PATH.
- Verify Python version is **>= 3.10**.
- **Failure Handling:** If Python is missing or outdated, STOP. Instruct the user on how to install it natively. Do not blindly `curl` or `wget` installers.

### 2. Virtual Environment Setup
- **Identify Environment:** Check if the user is running in Google Colab by checking if `"google.colab" in sys.modules` via Python.
- **For Google Colab:** DO NOT create a virtual environment. Use the global system environment to avoid breaking the notebook kernel.
- **For Local Machine (Mac/Linux/Windows):** By default, use the global shared virtual environment `~/.venv` (macOS/Linux) or `$HOME\.venv` (Windows). Only create a project-specific `.venv` if explicitly requested by the user.
  - **Mac/Linux:** `python3 -m venv ~/.venv`
  - **Windows:** `py -m venv $HOME\.venv` or `python -m venv $HOME\.venv`
- **Crucial (Local Only):** You MUST activate this `.venv` (e.g., `source ~/.venv/bin/activate` or `& "$HOME\.venv\Scripts\Activate.ps1"`) before running any `pip` or `python` commands in the subsequent steps.

### 3. Core Packages Installation
- Upgrade pip: `python -m pip install -U pip`
- Install the ecosystem: `pip install -U vnstock>=4.0.5 vnai>=2.5.6`

### 4. Jupyter Notebook Integration (Local Only)
- If the user is running locally (not Google Colab) and mentions Jupyter, Cursor Notebook, or Windsurf Notebook, you must register the `.venv` as an `ipykernel` so the IDE can detect the libraries.
- Execute:
  ```bash
  python -m pip install ipykernel
  python -m ipykernel install --user --name=vnstock-venv --display-name "Python (Vnstock)"
  ```
- Instruct the user to select the **Python (Vnstock)** kernel in their Notebook.

### 5. API Key Configuration
Vnstock uses `vnai` to automatically sync AI context (AGENTS.md) and skills into the `.agents/` directory when authenticated.
- Check if the user provided an API Key in their prompt.
- If provided, configure it silently via Python:
  ```python
  from vnstock.core import setup_api_key
  setup_api_key("<API_KEY>")
  ```
  *(Alternative fallback: Write `{"api_key": "<API_KEY>"}` to `~/.vnstock/api_key.json` or `$HOME\.vnstock\api_key.json`)*
- If NOT provided, ask the user to provide their API Key from `vnstocks.com/settings`.
- **Note:** Do not manually create `AGENTS.md`. It will sync automatically upon successful authentication.

### 6. Verification
- Create a temporary script `test_vnstock.py`:
  ```python
  from vnstock import Reference
  df = Reference().company.info("FPT")
  print("Data fetch successful:", not df.empty)
  ```
- Execute the script using the virtual environment's Python.
- If successful, delete `test_vnstock.py`.

### 7. Skill Discovery & User Guidance
- The user's tier privileges dictate which AI Agent Skills are unlocked. You MUST dynamically discover these skills using the Vnstock Agents API.
- Execute a silent Python script to retrieve the skill catalog:
  ```python
  from vnstock.core.utils.agents import load_skill_catalog
  import json
  catalog = load_skill_catalog()
  print(json.dumps(catalog, indent=2))
  ```
- Based on the returned catalog, identify the user's tier (e.g., **Free** vs **Sponsor**) and which specific skills they have access to.
- Output a customized welcome message in Vietnamese that:
  1. Announces success: *"🎉 **Môi trường Vibe Coding đã thiết lập thành công!** Hệ thống đã sẵn sàng."*
  2. Explicitly lists the Agent Skills they have unlocked as part of their privileges (based on the catalog).
  3. Provides 2-3 example prompts they can copy-paste to start working immediately.
- **CRITICAL REMINDER:** When instructed by the user to use a specific skill later, you MUST always fetch its instructions into your context first by running a python script with `vnstock.core.utils.agents.load_skill('<skill-name>')`.
