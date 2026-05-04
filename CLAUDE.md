# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

This is a one-shot Jira setup utility that creates an "Agent Control Plane" project in Jira — a Scrum project pre-configured with custom issue types and fields designed for managing AI agent tasks.

## Running the Script

```bash
python setup_jira.py
```

No dependencies beyond `requests` (install with `pip install requests` if needed).

## Configuration

Before running, edit the constants at the top of `setup_jira.py`:

- `JIRA_BASE_URL` — your Atlassian instance URL
- `EMAIL` — your Atlassian account email
- `API_TOKEN` — your Jira API token (generate at id.atlassian.com)
- `PROJECT_LEAD_ACCOUNT_ID` — account ID of the project lead (find via Jira REST API or profile URL)

## Architecture

Everything lives in `setup_jira.py`. The script is fully idempotent — each function checks whether a resource already exists before creating it:

1. **Project** — creates or retrieves a Scrum project with key `AGENT`
2. **Issue Types** — creates four custom types: Initiative, Feature, Agent Task, Agent Subtask
3. **Issue Type Scheme** — creates a scheme containing those types and attaches it to the project
4. **Custom Fields** — creates two text fields: `Execution Context` and `Agent Output`

All API calls target Jira REST API v3 using HTTP Basic Auth (email + API token).
