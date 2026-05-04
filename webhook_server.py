import os
from flask import Flask, request
from agent_runtime import (
    run_agent_task,
    jira_get_issue,
    jira_get_agent_status,
    jira_get_agent_type,
    jira_get_execution_context,
)
from agent_architect import run_architect_task

app = Flask(__name__)

AGENT_HANDLERS = {
    "ARCHITECT": run_architect_task,
}


@app.route("/jira/webhook", methods=["POST"])
def jira_webhook():
    data = request.get_json(force=True, silent=True) or {}

    print("\n📩 Incoming event")

    issue = data.get("issue", {})
    issue_key = issue.get("key")

    if not issue_key:
        return "no issue", 400

    issue_data = jira_get_issue(issue_key)

    fields = issue_data.get("fields", {})
    issue_type = fields.get("issuetype", {}).get("name")
    summary = fields.get("summary", "")
    description = str(fields.get("description", ""))
    print(f"Issue: {issue_key} Type: {issue_type}")
    print(f"Summary: {summary}")
    print(f"Description: {description[:200]}...")

    if issue_type == "Agent Task":
        status = jira_get_agent_status(issue_data)
        if status in ("Running", "Completed", "Failed"):
            print(f"  Skipping — Agent Status is '{status}'")
            return "skipped", 200

        agent_type = jira_get_agent_type(issue_data)
        print(f"  Agent Type: {agent_type or '(default)'}")

        if agent_type and agent_type.upper() in AGENT_HANDLERS:
            AGENT_HANDLERS[agent_type.upper()](issue_key, summary, description)
        else:
            # Read execution context — populated by architect for child tasks,
            # empty for standalone tasks (falls back to /tmp/agent-workspace)
            ctx = jira_get_execution_context(issue_data)
            workspace = ctx.get("workspace")
            design_context = None
            if workspace:
                design_path = os.path.join(workspace, "DESIGN.md")
                if os.path.isfile(design_path):
                    with open(design_path) as f:
                        design_context = f.read()
                print(f"  Workspace: {workspace}")
            run_agent_task(issue_key, summary, description,
                           workspace=workspace, design_context=design_context)

    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005)
