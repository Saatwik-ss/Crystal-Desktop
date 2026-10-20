import subprocess
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class GitCheckpointManager:
    """
    Manages atomic git checkpoints and rollbacks for the self-healing agent loop.
    """

    def __init__(self):
        self.checkpoints: Dict[str, Dict[str, str]] = {}

    def is_git_repo(self, repo_dir: str) -> bool:
        git_dir = Path(repo_dir) / ".git"
        return git_dir.exists()

    def create_checkpoint(self, repo_dir: str, message: str = "agent-checkpoint") -> Optional[str]:
        if not self.is_git_repo(repo_dir):
            return None

        checkpoint_id = str(uuid.uuid4())[:8]
        try:
            # 1. Use git stash create to create an unreferenced commit snapshot without modifying the working tree
            res = subprocess.run(
                ["git", "stash", "create", f"Crystal checkpoint: {checkpoint_id} - {message}"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            commit_hash = res.stdout.strip()
            if not commit_hash:
                # If working tree was clean, get HEAD commit
                res_head = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                commit_hash = res_head.stdout.strip()

            if commit_hash:
                self.checkpoints[checkpoint_id] = {
                    "id": checkpoint_id,
                    "commit_hash": commit_hash,
                    "repo_dir": repo_dir,
                    "created_at": datetime.now().isoformat(),
                    "message": message,
                }
                logger.info(f"[GitCheckpoint] Created checkpoint {checkpoint_id} at {commit_hash[:8]}")
                return checkpoint_id
        except Exception as e:
            logger.warning(f"[GitCheckpoint] Failed to create checkpoint: {e}")
        return None

    def rollback(self, checkpoint_id: str) -> bool:
        cp = self.checkpoints.get(checkpoint_id)
        if not cp:
            logger.warning(f"[GitCheckpoint] Checkpoint {checkpoint_id} not found")
            return False

        repo_dir = cp["repo_dir"]
        commit_hash = cp["commit_hash"]

        try:
            # Discard uncommitted changes and checkout snapshot tree
            subprocess.run(
                ["git", "checkout", commit_hash, "--", "."],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=15,
            )
            logger.info(f"[GitCheckpoint] Rolled back workspace to checkpoint {checkpoint_id} ({commit_hash[:8]})")
            return True
        except Exception as e:
            logger.error(f"[GitCheckpoint] Rollback failed: {e}")
            return False

    def list_checkpoints(self, repo_dir: Optional[str] = None) -> List[Dict[str, str]]:
        if not repo_dir:
            return list(self.checkpoints.values())
        return [c for c in self.checkpoints.values() if c["repo_dir"] == repo_dir]
