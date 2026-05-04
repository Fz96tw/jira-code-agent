We’ll build a minimal but real system:

Jira → Trigger → Agent Runtime → Execute → Report back → Transition issue

on top of Jira Cloud REST API

🧠 Architecture (Simple but real)
1. Jira (control plane)
Issues represent work units
Status changes trigger execution
2. Webhook listener (event ingress)
Receives Jira issue events
3. Agent runtime worker
Pulls issue details
Runs task in sandbox (local container / subprocess / Claude Code agent)
Produces artifacts + logs
4. Jira writer (egress)
Posts:
comments
execution output
status transitions
⚙️ Minimal Working Version (MVP)

We’ll implement:

✔ Flask webhook server
✔ Worker execution loop
✔ Jira update client
✔ “Agent Task” execution trigger

You must register webhook in Jira:

Endpoint:
http://YOUR_SERVER:5005/jira/webhook
Events:
Issue Created
Issue Updated

Filter later by issue type = Agent Task

⚡ HOW IT WORKS
Step 1

You create Jira issue:

Type: Agent Task
Summary: Build API client
Step 2

Jira sends webhook

Step 3

Your server receives:

issue_key = AGENT-12
Step 4

Agent runs:

print("Executing: Build API client")
Step 5

Writes back:

comment: execution started
comment: execution result
(optional) transitions status