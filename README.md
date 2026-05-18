# jira-code-agent

A system that turns Jira into an AI agent control plane. You create issues; agents plan, write code, commit it, and report back — all through Jira.

---

## Goals

- Use Jira as the single source of truth for agent work (no separate dashboard needed)
- Let an Architect agent decompose high-level tasks into child issues automatically
- Have Coder agents implement those tasks as real code in a git workspace
- Keep humans in the loop through Jira comments, status fields, and transitions

---

## Key Design Decisions

**Jira as the control plane** — No custom UI. Issues are the task queue; fields carry agent state; comments are the execution log.

**Idempotent setup** — `setup_jira.py` checks before creating every resource. Re-running it on an existing project is safe.

**Persistent git workspace per initiative** — The Architect creates `~/agent-projects/<issue-key>/` and all child tasks write into the same repo, so they share context and build on each other's work.

**Two-model pipeline** — GPT-4o for high-context design (Architect), GPT-4o-mini for the tighter plan/execute loop (lower cost, lower latency).

**No interactive commands** — The executor skips `cd`, direct script runs, and anything requiring stdin. Only static validation (`bash -n`, `ls`) is allowed in shell actions.


---

## How It Works

```
You create a Jira issue
        |
        v
Jira fires a webhook
        |
        v
webhook_server.py receives the event
        |
        +--[Agent Type = Architect]--> agent_architect.py
        |                                   |
        |                          GPT-4o designs system
        |                          Creates child Agent Tasks in Jira
        |                          Runs each child task in sequence
        |
        +--[Agent Type = (default)]--> agent_runtime.py
                                            |
                                   agent_planner.py (GPT-4o-mini)
                                   Breaks task into steps
                                            |
                                   agent_executor.py (GPT-4o-mini)
                                   Converts steps to write_file / shell actions
                                            |
                                   Commits code to git workspace
                                   Pushes to GitHub
                                   Writes results back to Jira
```

---

## Architecture

### Components

```
jira-code-agent/
├── setup_jira.py       # One-time Jira project bootstrap
├── webhook_server.py   # Flask server — receives Jira events
├── agent_runtime.py    # Jira API client + task orchestration
├── agent_architect.py  # Architect agent (GPT-4o design + decomposition)
├── agent_planner.py    # Planner (GPT-4o-mini step breakdown)
├── agent_executor.py   # Executor (GPT-4o-mini action generation)
└── agent_tools.py      # Utilities (git commit, test runner)
```

### Jira Issue Hierarchy

```
Initiative
  └── Feature
        └── Agent Task  <-- agents operate here
              └── Agent Subtask  <-- created by Architect automatically
```

### Custom Jira Fields

| Field             | Type     | Purpose                                      |
|-------------------|----------|----------------------------------------------|
| Agent Status      | Select   | Idle / Running / Blocked / Completed / Failed |
| Agent Type        | Select   | Architect / Coder / Reviewer / Tester / Deployer |
| Execution Context | Textarea | JSON payload passed to the agent (workspace path, goal) |
| Agent Output      | Textarea | Result written back by the agent              |

---

## Agent Flows

### Architect Task

```
Jira: Agent Task (Agent Type = Architect)
            |
            v
  agent_architect.py
            |
   [1] GPT-4o: generate technical design + task list
            |
   [2] Create git workspace at ~/agent-projects/<issue-key>/
       Write DESIGN.md, init git repo, push to GitHub
            |
   [3] Create child Agent Task issues in Jira
       Set Execution Context on each (workspace path + goal)
       Link child issues back to parent (Blocks relationship)
            |
   [4] For each child task → run_agent_task()
            |
   [5] Post design + task summary as Jira comments
       Transition parent issue → Done
```

### Standard Agent Task (Coder)

```
Jira: Agent Task (Agent Type = Coder or unset)
            |
            v
  agent_runtime.py → run_agent_task()
            |
   [1] agent_planner.py (GPT-4o-mini)
       Reads DESIGN.md from workspace (if set by Architect)
       Produces numbered step-by-step plan
            |
   [2] agent_executor.py (GPT-4o-mini)
       Converts plan to a list of actions:
         - write_file: path + content
         - shell: bash command (static checks only, no interactive input)
            |
   [3] Execute actions in the workspace directory
       Commit all changes to git
       Push to GitHub if remote exists
            |
   [4] Write Agent Output field in Jira
       Post execution log as comment
       Transition issue → Done (or Failed)
```

---

## Setup

### 1. Bootstrap Jira

Edit `.env` (see `.env.example`):

```
JIRA_BASE_URL=https://yourorg.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=...
PROJECT_LEAD_ACCOUNT_ID=...
OPENAI_API_KEY=...
```

Run the one-time setup:

```bash
pip install -r requirements.txt
python setup_jira.py
```

This creates the `AGENT` project in Jira with all custom fields and issue types. The script is fully idempotent — safe to re-run.

### 2. Start the Webhook Server

```bash
python webhook_server.py
```

Runs on port `5005`. Register the endpoint in Jira:

```
Jira Settings → System → Webhooks
URL: http://YOUR_SERVER:5005/jira/webhook
Events: Issue Created, Issue Updated
```

### 3. Trigger an Agent

Create an `Agent Task` in the `AGENT` project:

- Set **Agent Type** to `Architect` for design + full task decomposition
- Leave **Agent Type** unset (or `Coder`) for a direct implementation task
- Fill **Execution Context** with JSON if you need to pass extra context (e.g. `{"workspace": "/path/to/repo"}`)

Jira fires the webhook → agent runs → results appear as comments and field updates.

---
