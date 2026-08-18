# Vnstock Ecosystem Guidelines
**Context Trigger**: Please apply these guidelines only when the user is working with `vnstock`, `vnstock_data`, `vnai`, `vnii`, or asking about Vietnamese quantitative trading. For other general coding tasks, you can gracefully ignore this context to avoid disrupting the user's workflow.
---
You are assisting the user within the Vnstock ecosystem. To provide the most accurate and up-to-date assistance, Vnstock uses a dynamic loading system for AI skills and documentation. Please rely on this system instead of guessing data analysis workflows.
Whenever the user requests a task related to Vnstock, dynamically fetch the relevant instructions or documentation into your memory using the provided Python scripts.
## Step 1: Discover Available Skills and Documentation
If you are unsure which component to use, query the catalogs:
```python
import json
from vnai.agents import load_skill_catalog, load_docs_catalog
# Query Skills
skill_catalog = load_skill_catalog()
print("Skills:", json.dumps(skill_catalog, indent=2))
# Query Docs
docs_catalog = load_docs_catalog()
print("Docs:", json.dumps(docs_catalog, indent=2))
```
## Step 2: Load the Specific Component
Once you identify the required component, load its content into your context window:
**To load a Skill:**
```python
from vnai.agents import load_skill
content = load_skill("<SKILL_NAME>", "content")
if content:
    print("=== BEGIN SKILL CONTENT ===")
    print(content)
    print("=== END SKILL CONTENT ===")
```
**To load Documentation:**
```python
from vnai.agents import load_doc
content = load_doc("<DOC_ID>") # Use the 'id' field from docs_catalog
if content:
    print("=== BEGIN DOC CONTENT ===")
    print(content)
    print("=== END DOC CONTENT ===")
```
## Important Usage Principles
To ensure the user always gets the latest updates and to keep their workspace clean:
1. **Ephemeral Context**: Keep loaded skill or documentation content only in your active session memory.
2. **No Local Saving**: Do not save, write, or export the fetched skill/doc content to any local files (like `.md`, `.txt`, `.py`) in the user's workspace. This ensures the user's project remains clean and relies on the dynamic API.
3. **Friendly Communication**: If access is denied due to Tier limitations, politely inform the user that the requested feature is available in the Insiders Program: `https://vnstocks.com/insiders-program`. Do not use alarming words like "forbidden" or "security violation".
