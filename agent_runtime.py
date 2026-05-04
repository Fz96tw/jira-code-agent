import os
import json
import requests
import subprocess
from dotenv import load_dotenv

load_dotenv()

JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
EMAIL = os.environ["JIRA_EMAIL"]
API_TOKEN = os.environ["JIRA_API_TOKEN"]

AUTH = (EMAIL, API_TOKEN)

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}


def _get_field_id(name):
    r = requests.get(f"{JIRA_BASE_URL}/rest/api/3/field", headers=HEADERS, auth=AUTH)
    for f in r.json():
        if f["name"] == name:
            return f["id"]
    return None


# Resolved once at import time
AGENT_STATUS_FIELD = _get_field_id("Agent Status")
AGENT_TYPE_FIELD = _get_field_id("Agent Type")
EXECUTION_CONTEXT_FIELD = _get_field_id("Execution Context")
AGENT_OUTPUT_FIELD = _get_field_id("Agent Output")


# =========================
# JIRA CLIENT
# =========================
def jira_get_issue(issue_key):
    r = requests.get(
        f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}",
        headers=HEADERS,
        auth=AUTH
    )
    return r.json()


def jira_get_agent_status(issue_data):
    if not AGENT_STATUS_FIELD:
        return None
    val = issue_data.get("fields", {}).get(AGENT_STATUS_FIELD)
    return val.get("value") if val else None


def jira_get_agent_type(issue_data):
    if not AGENT_TYPE_FIELD:
        return None
    val = issue_data.get("fields", {}).get(AGENT_TYPE_FIELD)
    return val.get("value") if val else None


def jira_get_execution_context(issue_data):
    if not EXECUTION_CONTEXT_FIELD:
        return {}
    adf = issue_data.get("fields", {}).get(EXECUTION_CONTEXT_FIELD)
    if not adf:
        return {}
    try:
        # Extract plain text from ADF paragraph nodes
        text = "".join(
            node.get("text", "")
            for block in adf.get("content", [])
            for node in block.get("content", [])
            if node.get("type") == "text"
        )
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def jira_set_execution_context(issue_key, context_dict):
    if not EXECUTION_CONTEXT_FIELD:
        print(f"  ⚠️  EXECUTION_CONTEXT_FIELD not resolved — skipping set for {issue_key}")
        return
    r = requests.put(
        f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}",
        headers=HEADERS,
        auth=AUTH,
        json={"fields": {EXECUTION_CONTEXT_FIELD: {
            "type": "doc",
            "version": 1,
            "content": [{
                "type": "paragraph",
                "content": [{"type": "text", "text": json.dumps(context_dict)}]
            }]
        }}}
    )
    if r.status_code not in (200, 204):
        print(f"  ❌ jira_set_execution_context failed ({r.status_code}): {r.text}")


def jira_create_issue(project_key, summary, description, issue_type="Agent Task"):
    payload = {
        "fields": {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}]
                }]
            }
        }
    }
    r = requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issue",
        headers=HEADERS,
        auth=AUTH,
        json=payload
    )
    body = r.json()
    if not body.get("key"):
        print(f"  ❌ jira_create_issue failed ({r.status_code}): {body}")
    return body.get("key")


def jira_link_issues(outward_key, inward_key, link_type="Blocks"):
    """Create a link where outward_key blocks inward_key."""
    r = requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issueLink",
        headers=HEADERS,
        auth=AUTH,
        json={
            "type": {"name": link_type},
            "outwardIssue": {"key": outward_key},
            "inwardIssue": {"key": inward_key},
        }
    )
    if r.status_code not in (200, 201):
        print(f"  ❌ jira_link_issues failed ({r.status_code}): {r.text}")


def jira_set_agent_status(issue_key, status):
    if not AGENT_STATUS_FIELD:
        return
    requests.put(
        f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}",
        headers=HEADERS,
        auth=AUTH,
        json={"fields": {AGENT_STATUS_FIELD: {"value": status}}}
    )


def jira_set_agent_output(issue_key, text):
    if not AGENT_OUTPUT_FIELD:
        return
    requests.put(
        f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}",
        headers=HEADERS,
        auth=AUTH,
        json={"fields": {AGENT_OUTPUT_FIELD: {
            "type": "doc",
            "version": 1,
            "content": [{
                "type": "paragraph",
                "content": [{"type": "text", "text": text}]
            }]
        }}}
    )


def jira_comment(issue_key, text):
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{
                "type": "paragraph",
                "content": [{"type": "text", "text": text}]
            }]
        }
    }
    requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment",
        headers=HEADERS,
        auth=AUTH,
        json=payload
    )


def jira_transition(issue_key, transition_id):
    requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/transitions",
        headers=HEADERS,
        auth=AUTH,
        json={"transition": {"id": transition_id}}
    )


def jira_transition_by_name(issue_key, name):
    r = requests.get(
        f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/transitions",
        headers=HEADERS,
        auth=AUTH
    )
    for t in r.json().get("transitions", []):
        if t["name"].lower() == name.lower():
            jira_transition(issue_key, t["id"])
            return True
    print(f"⚠️  No transition named '{name}' found for {issue_key}")
    return False


# =========================
# AGENT EXECUTION CORE
# =========================
def run_agent_task_old(issue_key, summary, description):
    print(f"\n🤖 Running agent task: {issue_key}")

    jira_set_agent_status(issue_key, "Running")
    jira_comment(issue_key, "🚀 Agent started execution")

    try:
        result = subprocess.check_output(
            ["python3", "-c", f'print("Executing: {summary}")'],
            stderr=subprocess.STDOUT,
            timeout=30
        ).decode()

        jira_comment(issue_key, f"✅ Execution complete:\n{result}")
        jira_set_agent_status(issue_key, "Completed")
        return True

    except Exception as e:
        jira_comment(issue_key, f"❌ Execution failed:\n{str(e)}")
        jira_set_agent_status(issue_key, "Failed")
        return False

from agent_planner import plan_task
from agent_executor import execute_plan

def run_agent_task(issue_key, summary, description, workspace=None, design_context=None):
    print(f"\n🤖 Running agent task: {issue_key}")

    jira_set_agent_status(issue_key, "Running")
    jira_transition_by_name(issue_key, "In Progress")
    jira_comment(issue_key, "🧠 Planning task...")

    try:
        plan = plan_task(summary, description, design_context=design_context)
        print(plan)

        jira_comment(issue_key, f"📋 Plan:\n{plan}")

        jira_comment(issue_key, "⚙️ Executing plan...")

        success, output = execute_plan(plan, summary, description, workspace=workspace, issue_key=issue_key)
        print(output)

        jira_set_agent_output(issue_key, output)
        jira_comment(issue_key, f"📝 Execution log:\n{output}")

        if success:
            jira_set_agent_status(issue_key, "Completed")
            jira_transition_by_name(issue_key, "Done")
            jira_comment(issue_key, "✅ Task completed successfully")
        else:
            jira_set_agent_status(issue_key, "Failed")
            jira_comment(issue_key, "❌ Task failed")

        return success

    except Exception as e:
        jira_comment(issue_key, f"💥 Agent crashed:\n{str(e)}")
        jira_set_agent_status(issue_key, "Failed")
        return False