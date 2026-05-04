import os
import json
import subprocess
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

WORKDIR = "/tmp/agent-workspace"


def _plan_to_actions(plan_text, summary, description):
    prompt = f"""You are an AI agent executor. Given a task and its plan, produce a concrete implementation.

Task: {summary}
Description: {description}

Plan:
{plan_text}

Return a JSON object with an "actions" array. Each action must be one of:
- {{"type": "write_file", "path": "relative/filename", "content": "full file content"}}
- {{"type": "shell", "command": "bash command to run"}}

Rules:
- You are already inside the working directory. NEVER use cd commands.
- Use relative paths for all files and commands.
- Prefer write_file over shell commands that create files (touch, cat, heredoc).
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


def execute_plan(plan_text, summary="", description=""):
    os.makedirs(WORKDIR, exist_ok=True)
    results = []

    try:
        actions = _plan_to_actions(plan_text, summary, description)
    except Exception as e:
        return False, f"Failed to generate actions from plan: {e}"

    for action in actions:
        atype = action.get("type")

        if atype == "write_file":
            path = os.path.join(WORKDIR, action["path"])
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
                    cwd=WORKDIR,
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

    return True, "\n\n".join(results)
