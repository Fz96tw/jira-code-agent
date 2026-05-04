import subprocess

def git_commit(message):
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", message])

def run_tests():
    return subprocess.run(["pytest"], capture_output=True, text=True)