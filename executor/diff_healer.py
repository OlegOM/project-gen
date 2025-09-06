from __future__ import annotations
import subprocess, os

USE_LLM = os.getenv("USE_LLM","false").lower() == "true"

def run_and_heal(proj_dir: str, max_iters: int = 1):
    subprocess.run(["pytest", "-q"], cwd=proj_dir, check=False)
    return True
