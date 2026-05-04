import os
import requests
import json
import sys
from dotenv import load_dotenv

load_dotenv()

# =========================
# CONFIG
# =========================
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
EMAIL = os.environ["JIRA_EMAIL"]
API_TOKEN = os.environ["JIRA_API_TOKEN"]
PROJECT_LEAD_ACCOUNT_ID = os.environ["PROJECT_LEAD_ACCOUNT_ID"]

PROJECT_KEY = "AGENT"
PROJECT_NAME = "Agent Control Plane"

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

AUTH = (EMAIL, API_TOKEN)


# =========================
# HELPERS
# =========================
def request(method, url, payload=None):
    resp = requests.request(
        method,
        f"{JIRA_BASE_URL}{url}",
        headers=HEADERS,
        auth=AUTH,
        json=payload
    )

    if resp.status_code >= 400:
        print(f"{method} {url} -> {resp.status_code}")
        print(resp.text)
        raise Exception(resp.text)

    return resp.json() if resp.text else {}


# =========================
# PROJECT (IDEMPOTENT)
# =========================
def get_project():
    r = requests.get(
        f"{JIRA_BASE_URL}/rest/api/3/project/{PROJECT_KEY}",
        headers=HEADERS,
        auth=AUTH
    )
    return r.json() if r.status_code == 200 else None


def create_or_get_project():
    print("\n🚀 Checking project...")

    existing = get_project()
    if existing:
        print("✅ Reusing existing project")
        return existing["id"]

    print("🚀 Creating project...")

    payload = {
        "key": PROJECT_KEY,
        "name": PROJECT_NAME,
        "projectTypeKey": "software",
        "projectTemplateKey": "com.pyxis.greenhopper.jira:gh-scrum-template",
        "leadAccountId": PROJECT_LEAD_ACCOUNT_ID
    }

    data = request("POST", "/rest/api/3/project", payload)
    return data.get("id")


# =========================
# ISSUE TYPES (IDEMPOTENT)
# =========================
def get_issue_types():
    return request("GET", "/rest/api/3/issuetype")


def get_or_create_issue_type(name, type_="standard"):
    print(f"\n🧩 Issue type: {name}")

    for it in get_issue_types():
        if it["name"] == name:
            print("✅ Exists")
            return it["id"]

    print("🚀 Creating")

    payload = {
        "name": name,
        "type": type_,
        "description": f"{name} for agent system"
    }

    data = request("POST", "/rest/api/3/issuetype", payload)
    return data["id"]


# =========================
# ISSUE TYPE SCHEME (FIXED + IDEMPOTENT)
# =========================
def get_scheme_by_name(name):
    data = request("GET", "/rest/api/3/issuetypescheme")
    for s in data.get("values", []):
        if s["name"] == name:
            return s
    return None


def create_or_get_scheme(issue_type_ids):
    print("\n🔧 Checking issue type scheme...")

    scheme_name = "Agent Issue Type Scheme"
    existing = get_scheme_by_name(scheme_name)

    if existing:
        print(f"✅ Reusing scheme: {existing['id']}")
        return existing["id"]

    print("🚀 Creating scheme...")

    payload = {
        "name": scheme_name,
        "description": "Agent system issue types",
        "issueTypeIds": issue_type_ids   # 🔥 REQUIRED FIX
    }

    r = requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issuetypescheme",
        headers=HEADERS,
        auth=AUTH,
        json=payload
    )

    print(r.status_code)
    print(r.text)

    if r.status_code >= 400:
        raise Exception(r.text)

    # Jira does NOT reliably return ID → re-fetch
    data = request("GET", "/rest/api/3/issuetypescheme")

    for s in data.get("values", []):
        if s["name"] == scheme_name:
            return s["id"]

    raise Exception("Scheme created but not found")


def attach_issue_types_to_scheme(scheme_id, issue_type_ids):
    print("\n🔗 Attaching issue types...")

    payload = {"issueTypeIds": issue_type_ids}

    request(
        "PUT",
        f"/rest/api/3/issuetypescheme/{scheme_id}/issuetype",
        payload
    )


def assign_scheme_to_project(scheme_id, project_id):
    print("\n📌 Assigning scheme to project...")

    payload = {
        "issueTypeSchemeId": scheme_id,
        "projectId": project_id
    }

    request(
        "PUT",
        "/rest/api/3/issuetypescheme/project",
        payload
    )


# =========================
# FIELDS (IDEMPOTENT)
# =========================
def get_fields():
    return request("GET", "/rest/api/3/field")


def get_or_create_field(name, description, field_type):
    print(f"\n🧠 Field: {name}")

    for f in get_fields():
        if f["name"] == name:
            print("✅ Exists")
            return f["id"]

    print("🚀 Creating")

    data = request("POST", "/rest/api/3/field", {
        "name": name,
        "description": description,
        "type": field_type,
    })
    return data["id"]


def get_or_create_select_field(name, description, options):
    field_id = get_or_create_field(name, description, "com.atlassian.jira.plugin.system.customfieldtypes:select")

    # Get the default context so we can add options to it
    ctx_data = request("GET", f"/rest/api/3/field/{field_id}/context")
    contexts = ctx_data.get("values", [])
    if not contexts:
        print(f"  ⚠️  No context found for {name}, skipping options")
        return field_id
    context_id = contexts[0]["id"]

    # Check existing options
    opt_data = request("GET", f"/rest/api/3/field/{field_id}/context/{context_id}/option")
    existing = {o["value"] for o in opt_data.get("values", [])}

    missing = [o for o in options if o not in existing]
    if missing:
        request("POST", f"/rest/api/3/field/{field_id}/context/{context_id}/option", {
            "options": [{"value": o} for o in missing]
        })
        print(f"  ✅ Added options: {missing}")
    else:
        print("  ✅ Options already exist")

    return field_id


def get_screen_ids_for_project(project_key):
    """Find screens whose name starts with the project key (Jira names them 'KEY: ...')."""
    data = request("GET", "/rest/api/3/screens")
    screen_ids = []
    for screen in data.get("values", []):
        name = screen.get("name", "")
        if name.upper().startswith(project_key.upper()):
            print(f"  Found screen: {name} (id={screen['id']})")
            screen_ids.append(screen["id"])
    return screen_ids


def add_field_to_screen(screen_id, field_id):
    tabs = request("GET", f"/rest/api/3/screens/{screen_id}/tabs")
    if not tabs:
        return
    tab_id = tabs[0]["id"]

    existing = request("GET", f"/rest/api/3/screens/{screen_id}/tabs/{tab_id}/fields")
    if any(f["id"] == field_id for f in existing):
        return

    request("POST", f"/rest/api/3/screens/{screen_id}/tabs/{tab_id}/fields", {"fieldId": field_id})
    print(f"  ✅ Added {field_id} to screen {screen_id}")


def add_fields_to_project_screens(project_key, field_ids):
    print("\n📋 Adding fields to project screens...")
    screen_ids = get_screen_ids_for_project(project_key)
    if not screen_ids:
        print("⚠️  No screens found — add fields manually in Jira screen config")
        return
    for screen_id in screen_ids:
        for field_id in field_ids:
            add_field_to_screen(screen_id, field_id)


# =========================
# MAIN
# =========================
if __name__ == "__main__":

    print("===================================")
    print("Jira Agent Control Plane (STABLE)")
    print("===================================")

    # 1. Project
    project_id = create_or_get_project()
    print("\n📦 Project:", project_id)

    # 2. Issue Types
    initiative = get_or_create_issue_type("Initiative")
    feature = get_or_create_issue_type("Feature")
    agent_task = get_or_create_issue_type("Agent Task")
    agent_subtask = get_or_create_issue_type("Agent Subtask", "subtask")

    # ⚠️ IMPORTANT: DO NOT include subtasks in scheme
    issue_type_ids = [initiative, feature, agent_task]

    # 3. Scheme
    scheme_id = create_or_get_scheme(issue_type_ids)

    assign_scheme_to_project(scheme_id, project_id)

    # 4. Fields
    exec_ctx_id = get_or_create_field(
        "Execution Context", "JSON payload for agent input",
        "com.atlassian.jira.plugin.system.customfieldtypes:textarea"
    )
    agent_out_id = get_or_create_field(
        "Agent Output", "Agent result",
        "com.atlassian.jira.plugin.system.customfieldtypes:textarea"
    )
    agent_status_id = get_or_create_select_field(
        "Agent Status", "Execution state of the agent",
        ["Idle", "Running", "Blocked", "Completed", "Failed"]
    )
    agent_type_id = get_or_create_select_field(
        "Agent Type", "Type of agent",
        ["Architect", "Coder", "Reviewer", "Tester", "Deployer"]
    )

    # 5. Add fields to project screens so they appear on issues
    add_fields_to_project_screens(PROJECT_KEY, [exec_ctx_id, agent_out_id, agent_status_id, agent_type_id])

    print("\n🎉 DONE (IDEMPOTENT SETUP COMPLETE)")