import os
import shutil
import git
import time
from typing import List
from nightingale.config import config
from nightingale.types import FileDiff

class Sandbox:
    def __init__(self, repo_path: str, sandbox_id: str):
        self.original_repo_path = repo_path
        self.sandbox_id = sandbox_id
        self.sandbox_path = os.path.join(config.get("sandbox_dir"), sandbox_id)
        
    def setup(self):
        """Creates a clean copy of the repo in the sandbox directory."""
        if os.path.exists(self.sandbox_path):
            shutil.rmtree(self.sandbox_path)
        shutil.copytree(self.original_repo_path, self.sandbox_path)
        # Initialize git in sandbox if not already (it should be copied, but good to be safe)
        if not os.path.exists(os.path.join(self.sandbox_path, ".git")):
             git.Repo.init(self.sandbox_path)

    def apply_diffs(self, diffs: List[FileDiff]):
        """Applies a list of file changes to the sandboxed repo."""
        for diff in diffs:
            file_path = os.path.join(self.sandbox_path, diff.file_path)
            
            if diff.change_type == "modify":
                # In a real system we might patch, here we essentially rewrite for simplicity
                # assuming diff_content IS the new content for this prototype
                with open(file_path, "w") as f:
                    f.write(diff.diff_content)
            elif diff.change_type == "add":
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w") as f:
                    f.write(diff.diff_content)
            elif diff.change_type == "delete":
                if os.path.exists(file_path):
                    os.remove(file_path)

    def run_command(self, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """Runs a command in the sandbox environment."""
        import subprocess
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                cwd=self.sandbox_path, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"

    def cleanup(self):
        """Removes the sandbox environment."""
        if os.path.exists(self.sandbox_path):
            shutil.rmtree(self.sandbox_path)
