import os
import json
import subprocess
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

WORKDIR = "/tmp/agent-workspace"


def _plan_to_actions(plan_text, summary, description, existing_files=None):
    files_section = ""
    if existing_files:
        files_section = f"""Existing files in workspace (modify these rather than creating new ones with different names):
{chr(10).join(f"  - {f}" for f in existing_files)}

"""

    prompt = f"""You are an AI agent executor. Given a task and its plan, produce a concrete implementation.

Task: {summary}
Description: {description}

Plan:
{plan_text}

{files_section}Return a JSON object with an "actions" array. Each action must be one of:
- {{"type": "write_file", "path": "relative/filename", "content": "full file content"}}
- {{"type": "shell", "command": "bash command to run"}}

Rules:
- You are already inside the working directory. NEVER use cd commands.
- Use relative paths for all files and commands.
- Prefer write_file over shell commands that create files (touch, cat, heredoc).
- If existing files are listed above, write to those same filenames — do NOT invent new names.
- NEVER run scripts or programs that require interactive user input (e.g. read, stdin prompts).
- For validation, use static checks only: bash -n to check syntax, ls to confirm files exist.
- Return ONLY valid JSON, no markdown fences."""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    data = json.loads(resp.choices[0].message.content)
    return data.get("actions", [])


def execute_plan(plan_text, summary="", description="", workspace=None, issue_key=""):
    workdir = workspace or WORKDIR
    os.makedirs(workdir, exist_ok=True)
    results = []

    # Snapshot existing source files so the LLM knows what to modify vs create
    existing_files = [
        f for f in os.listdir(workdir)
        if os.path.isfile(os.path.join(workdir, f)) and not f.startswith(".")
    ]

    try:
        actions = _plan_to_actions(plan_text, summary, description, existing_files=existing_files)
    except Exception as e:
        return False, f"Failed to generate actions from plan: {e}"

    for action in actions:
        atype = action.get("type")

        if atype == "write_file":
            path = os.path.join(workdir, action["path"])
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w") as f:
                f.write(action["content"])
            results.append(f"✅ wrote {action['path']}")

        elif atype == "shell":
            cmd = action["command"].strip()
            if cmd.startswith("cd ") or cmd == "cd":
                results.append(f"⏭️ skipped cd (already in workdir)")
                continue
            if cmd.startswith("./") or cmd.startswith("bash ") and not "-n" in cmd:
                results.append(f"⏭️ skipped direct script execution (no interactive input available): {cmd}")
                continue
            try:
                output = subprocess.check_output(
                    cmd,
                    shell=True,
                    cwd=workdir,
                    stderr=subprocess.STDOUT,
                    timeout=60
                ).decode()
                results.append(f"✅ {cmd}\n{output}".strip())
            except subprocess.CalledProcessError as e:
                results.append(f"❌ {cmd}\n{e.output.decode()}".strip())
                return False, "\n\n".join(results)
            except Exception as e:
                results.append(f"❌ {cmd}\n{str(e)}")
                return False, "\n\n".join(results)

        else:
            results.append(f"⚠️ Unknown action type: {atype}")

    # Commit and push to GitHub if the workspace is a git repo with a remote
    if os.path.isdir(os.path.join(workdir, ".git")):
        label = f"[{issue_key}] {summary}" if issue_key else summary
        subprocess.run(["git", "add", "-A"], cwd=workdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", label], cwd=workdir, capture_output=True)
        results.append(f"✅ git commit: {label}")
        has_remote = subprocess.run(
            ["git", "remote"], cwd=workdir, capture_output=True, text=True
        ).stdout.strip()
        if has_remote:
            subprocess.run(["git", "push"], cwd=workdir, capture_output=True)
            results.append("✅ pushed to GitHub")

    return True, "\n\n".join(results)
