import os
import json
import subprocess
from openai import OpenAI
from agent_runtime import (
    jira_set_agent_status,
    jira_transition_by_name,
    jira_comment,
    jira_create_issue,
    jira_link_issues,
    jira_set_execution_context,
    jira_get_issue,
    run_agent_task,
)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _generate_design(summary, description):
    prompt = f"""You are a senior software architect. Analyze the requirements below and produce:
1. A complete technical design covering architecture, components, data flow, and key decisions.
2. A sequential task breakdown — ordered by dependency, each task is a self-contained component or workstream.

Requirements:
Summary: {summary}
Description: {description}

Return a JSON object with:
- "design": full technical design in markdown (headings, bullet points, code blocks as needed). Include a "Primary output files" section listing the exact filenames that will be produced.
- "tasks": array of 3-8 objects, each with "title" (short, <80 chars) and "description" (detailed, what to build, which specific file(s) to create or modify, and how it fits the overall design)

Return ONLY valid JSON, no markdown fences."""

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(resp.choices[0].message.content)


def _init_workspace(issue_key):
    path = os.path.expanduser(f"~/agent-projects/{issue_key}")
    os.makedirs(path, exist_ok=True)
    if not os.path.isdir(os.path.join(path, ".git")):
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", f"init: {issue_key} project workspace"],
            cwd=path, capture_output=True
        )
        r = subprocess.run(
            ["gh", "repo", "create", issue_key.lower(), "--public", "--source=.", "--push"],
            cwd=path, capture_output=True, text=True
        )
        if r.returncode == 0:
            print(f"  🐙 GitHub repo created: {r.stdout.strip()}")
        else:
            print(f"  ⚠️  GitHub repo creation failed: {r.stderr.strip()}")
    return path


def _write_design_file(workspace, issue_key, design_md):
    path = os.path.join(workspace, "DESIGN.md")
    with open(path, "w") as f:
        f.write(f"# {issue_key} — Technical Design\n\n")
        f.write(design_md)
    subprocess.run(["git", "add", "DESIGN.md"], cwd=workspace, capture_output=True)
    subprocess.run(["git", "commit", "-m", f"[{issue_key}] add technical design"], cwd=workspace, capture_output=True)
    return path


def run_architect_task(issue_key, summary, description):
    print(f"\n🏛️  Running architect task: {issue_key}")

    jira_set_agent_status(issue_key, "Running")
    jira_transition_by_name(issue_key, "In Progress")
    jira_comment(issue_key, "🏛️ Architect agent analyzing requirements...")

    try:
        result = _generate_design(summary, description)
        design_md = result["design"]
        tasks = result["tasks"]

        # Initialize persistent git workspace
        workspace = _init_workspace(issue_key)
        print(f"📁 Workspace: {workspace}")

        # Write design doc to workspace
        design_path = _write_design_file(workspace, issue_key, design_md)
        print(f"📄 Design written to {design_path}")

        # Post design to Jira
        jira_comment(issue_key, f"## Technical Design\n\n{design_md}")

        # Create independent Agent Task issues, set execution context, link back
        project_key = issue_key.split("-")[0]
        created = []  # list of (key, task_dict)
        for i, task in enumerate(tasks, 1):
            new_key = jira_create_issue(project_key, task["title"], task["description"])
            if new_key:
                jira_set_execution_context(new_key, {
                    "architect_issue": issue_key,
                    "workspace": workspace,
                    "goal": summary,
                })
                jira_link_issues(outward_key=issue_key, inward_key=new_key)
                created.append((new_key, task))
                print(f"  ✅ Created {new_key}: {task['title']}")
            else:
                print(f"  ⚠️  Failed to create task {i}: {task['title']}")

        summary_comment = (
            "## Task Breakdown\n\n"
            + "\n".join(f"{i}. **{t['title']}** → {k}" for i, (k, t) in enumerate(created, 1))
            + f"\n\n📁 Workspace: `{workspace}`"
        )
        jira_comment(issue_key, summary_comment)

        # Run child tasks sequentially in-process
        design_context = open(design_path).read()
        for child_key, task in created:
            child_data = jira_get_issue(child_key)
            child_summary = child_data["fields"]["summary"]
            child_description = str(child_data["fields"].get("description", ""))
            run_agent_task(
                child_key, child_summary, child_description,
                workspace=workspace, design_context=design_context
            )

        jira_set_agent_status(issue_key, "Completed")
        jira_transition_by_name(issue_key, "Done")
        return True

    except Exception as e:
        jira_comment(issue_key, f"💥 Architect agent crashed:\n{str(e)}")
        jira_set_agent_status(issue_key, "Failed")
        return False
