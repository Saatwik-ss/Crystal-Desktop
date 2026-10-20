import sys
import subprocess
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class SandboxRunner:
    """
    Executes commands either directly on host or within an isolated environment (WSL2 / Docker).
    Defaults to 'host' execution with safety policy gating.
    """

    def __init__(self, mode: str = "host", docker_image: Optional[str] = None):
        # mode: 'host' | 'wsl' | 'docker'
        self.mode = mode
        self.docker_image = docker_image or "python:3.11-slim"

    def wrap_command(self, cmd: str, cwd: str) -> List[str]:
        """Wrap command based on configured isolation mode."""
        if self.mode == "wsl" and sys.platform == "win32":
            # Translate path and run in WSL
            return ["wsl.exe", "-e", "bash", "-c", f"cd {cwd} && {cmd}"]
        
        if self.mode == "docker":
            return [
                "docker", "run", "--rm",
                "-v", f"{cwd}:/workspace",
                "-w", "/workspace",
                self.docker_image,
                "sh", "-c", cmd
            ]

        # Host default
        return [cmd]
