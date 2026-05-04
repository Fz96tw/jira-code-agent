from flask import Flask, request
from agent_runtime import run_agent_task, jira_get_issue, jira_get_agent_status

app = Flask(__name__)


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
        run_agent_task(issue_key, summary, description)

    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005)
