import requests
import json
import sys

# =========================
# CONFIG (EDIT THIS)
# =========================
JIRA_BASE_URL = "https://fz96tw.atlassian.net"
EMAIL = "fz96tw@gmail.com"
API_TOKEN = "ATATT3xFfGF0Ibc8robuteLz-SI90yIVHBOtE8vUGniX68wohQ_EUHdgEO79akY3q5vXtj1XozbZTnvtb_0zvl7E2VCbazp1jAFn-D0BPIT3uOZwZUSPQlQOaUqHKPMyYVsXHv1X2kI_Rv97kTeFEkzyl0xN2PuGV9M2DjJcnWFuo5amTXhFBH0=1472E66D"
PROJECT_LEAD_ACCOUNT_ID = "712020:75fe7e05-edd2-4eb8-9f25-d037985e66b3"

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

    print(f"{method} {url} -> {resp.status_code}")
    if resp.text:
        print(resp.text)

    if resp.status_code >= 400:
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


def get_or_create_field(name):
    print(f"\n🧠 Field: {name}")

    for f in get_fields():
        if f["name"] == name:
            print("✅ Exists")
            return f["id"]

    print("🚀 Creating")

    payload = {
        "name": name,
        "description": f"{name} for agent system",
        "type": "com.atlassian.jira.plugin.system.customfieldtypes:textarea"
    }

    data = request("POST", "/rest/api/3/field", payload)
    return data["id"]


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

    attach_issue_types_to_scheme(scheme_id, issue_type_ids)
    assign_scheme_to_project(scheme_id, project_id)

    # 4. Fields
    get_or_create_field("Execution Context")
    get_or_create_field("Agent Output")

    print("\n🎉 DONE (IDEMPOTENT SETUP COMPLETE)")