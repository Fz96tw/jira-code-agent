import os
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def plan_task(summary, description):
    prompt = f"""
You are a senior software engineer.

Task:
{summary}

Details:
{description}

Break this into concrete executable steps.
Return as a numbered list.
"""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return resp.choices[0].message.content