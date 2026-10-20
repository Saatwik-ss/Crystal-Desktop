import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class GitWorktreeManager:
    """
    Manages isolated Git worktrees for parallel agent execution,
    ticket-based isolation, and patch verification.
    """

    def __init__(self, worktree_base_dirname: str = ".crystal_worktrees"):
        self.worktree_base_dirname = worktree_base_dirname

    def _run_git(self, repo_dir: str, args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a git command in the repository directory."""
        return subprocess.run(
            ["git"] + args,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def is_git_repo(self, repo_dir: str) -> bool:
        """Check if path is directly a git repository (has its own .git)."""
        p = Path(repo_dir)
        if not p.exists() or not p.is_dir():
            return False
        return (p / ".git").exists()

    def ensure_git_repo(self, repo_dir: str) -> bool:
        """Ensure repo_dir has its own git repository and initial commit."""
        p = Path(repo_dir)
        if not p.exists() or not p.is_dir():
            return False
        if not (p / ".git").exists():
            self._run_git(repo_dir, ["init", "-b", "main"])
            self._run_git(repo_dir, ["add", "-A"])
            self._run_git(repo_dir, ["commit", "-m", "Initial commit of workspace files"])
        return True

    def get_current_branch(self, repo_dir: str) -> str:
        """Get the active branch of the repository or worktree."""
        res = self._run_git(repo_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
        if res.returncode == 0:
            return res.stdout.strip()
        return "HEAD"

    def _ensure_worktrees_ignored(self, repo_dir: str) -> None:
        """Ensure .crystal_worktrees is ignored by Git without mutating .gitignore."""
        exclude_file = Path(repo_dir) / ".git" / "info" / "exclude"
        if exclude_file.exists():
            try:
                content = exclude_file.read_text(encoding="utf-8")
                if self.worktree_base_dirname not in content:
                    with open(exclude_file, "a", encoding="utf-8") as f:
                        f.write(f"\n# Crystal worktree sandboxes\n{self.worktree_base_dirname}/\n")
            except Exception as e:
                logger.warning(f"Could not update .git/info/exclude: {e}")

    def get_worktree_dir(self, repo_dir: str, worktree_name: str) -> Path:
        """Get the full path to a named worktree directory."""
        return Path(repo_dir) / self.worktree_base_dirname / worktree_name

    def create_worktree(
        self,
        repo_dir: str,
        name: str,
        branch_name: Optional[str] = None,
        base_commit: str = "HEAD",
    ) -> Dict[str, Any]:
        """
        Create a new isolated git worktree on a dedicated branch.
        """
        self.ensure_git_repo(repo_dir)
        if not self.is_git_repo(repo_dir):
            raise ValueError(f"Directory {repo_dir} is not a valid git repository")

        self._ensure_worktrees_ignored(repo_dir)

        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name).strip("_")
        if not safe_name:
            safe_name = "worktree_sandbox"

        target_path = self.get_worktree_dir(repo_dir, safe_name)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.exists():
            # If directory already exists, verify if it is an active worktree
            wt_list = self.list_worktrees(repo_dir)
            for wt in wt_list:
                if Path(wt["path"]).resolve() == target_path.resolve():
                    return wt
            # Orphaned directory cleanup
            shutil.rmtree(target_path, ignore_errors=True)
            self._run_git(repo_dir, ["worktree", "prune"])

        target_branch = branch_name or f"mesh/{safe_name}"

        # Check if the branch already exists
        check_branch = self._run_git(repo_dir, ["rev-parse", "--verify", target_branch])
        branch_exists = (check_branch.returncode == 0)

        if branch_exists:
            # Check out existing branch in worktree
            res = self._run_git(
                repo_dir,
                ["worktree", "add", str(target_path), target_branch],
            )
        else:
            # Create branch pointing to base_commit
            res = self._run_git(
                repo_dir,
                ["worktree", "add", "-b", target_branch, str(target_path), base_commit],
            )

        if res.returncode != 0:
            raise RuntimeError(f"Git worktree add failed: {res.stderr.strip() or res.stdout.strip()}")

        # Fetch commit hash
        commit_res = self._run_git(str(target_path), ["rev-parse", "HEAD"])
        commit_hash = commit_res.stdout.strip() if commit_res.returncode == 0 else ""

        return {
            "name": safe_name,
            "path": str(target_path),
            "branch": target_branch,
            "commit_hash": commit_hash,
            "created_at": datetime.utcnow().isoformat(),
            "is_main": False,
        }

    def list_worktrees(self, repo_dir: str) -> List[Dict[str, Any]]:
        """List all git worktrees associated with the repository."""
        if not self.is_git_repo(repo_dir):
            return []

        res = self._run_git(repo_dir, ["worktree", "list", "--porcelain"])
        if res.returncode != 0:
            return []

        worktrees: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {}

        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                if current and "path" in current:
                    worktrees.append(current)
                current = {}
                continue

            if line.startswith("worktree "):
                current["path"] = line[len("worktree "):].strip()
            elif line.startswith("HEAD "):
                current["commit_hash"] = line[len("HEAD "):].strip()
            elif line.startswith("branch "):
                branch_ref = line[len("branch "):].strip()
                # e.g. refs/heads/mesh/tkt-142 -> mesh/tkt-142
                if branch_ref.startswith("refs/heads/"):
                    current["branch"] = branch_ref[len("refs/heads/"):]
                else:
                    current["branch"] = branch_ref
            elif line == "bare":
                current["bare"] = True
            elif line == "detached":
                current["detached"] = True

        if current and "path" in current:
            worktrees.append(current)

        # Enrich worktrees
        main_path = str(Path(repo_dir).resolve())
        enriched: List[Dict[str, Any]] = []
        for wt in worktrees:
            wt_path = str(Path(wt["path"]).resolve())
            is_main = (wt_path == main_path)
            name = "main" if is_main else Path(wt_path).name
            enriched.append({
                "name": name,
                "path": wt_path,
                "branch": wt.get("branch", "detached"),
                "commit_hash": wt.get("commit_hash", ""),
                "is_main": is_main,
            })

        return enriched

    def get_diff(
        self,
        worktree_path: str,
        base_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compute diff in the worktree against a base reference (or unstaged/staged working tree).
        Returns diff stats, list of changed files, and unified patch string.
        """
        p = Path(worktree_path)
        if not p.exists():
            raise FileNotFoundError(f"Worktree path does not exist: {worktree_path}")

        # Include untracked files in diff calculations
        self._run_git(worktree_path, ['add', '-N', '.'])

        # 1. If base_ref is given, diff against base_ref (e.g. main...HEAD)
        if base_ref:
            # Check if base_ref exists
            res_ref = self._run_git(worktree_path, ["rev-parse", "--verify", base_ref])
            if res_ref.returncode == 0:
                diff_cmd = ["diff", f"{base_ref}...HEAD"]
                stats_cmd = ["diff", "--numstat", f"{base_ref}...HEAD"]
            else:
                diff_cmd = ["diff", "HEAD"]
                stats_cmd = ["diff", "--numstat", "HEAD"]
        else:
            diff_cmd = ["diff", "HEAD"]
            stats_cmd = ["diff", "--numstat", "HEAD"]

        diff_res = self._run_git(worktree_path, diff_cmd, timeout=30)
        patch = diff_res.stdout if diff_res.returncode == 0 else ""

        stats_res = self._run_git(worktree_path, stats_cmd, timeout=30)
        additions = 0
        deletions = 0
        files_changed = []

        if stats_res.returncode == 0:
            for line in stats_res.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 3:
                    add = int(parts[0]) if parts[0].isdigit() else 0
                    dele = int(parts[1]) if parts[1].isdigit() else 0
                    filepath = parts[2].strip()
                    additions += add
                    deletions += dele
                    files_changed.append({
                        "file_path": filepath,
                        "additions": add,
                        "deletions": dele,
                    })

        return {
            "worktree_path": worktree_path,
            "additions": additions,
            "deletions": deletions,
            "files_count": len(files_changed),
            "files_changed": files_changed,
            "diff_patch": patch,
        }

    def commit(
        self,
        worktree_path: str,
        message: str,
        author_name: str = "Crystal Agent",
        author_email: str = "agent@crystal.local",
    ) -> Dict[str, Any]:
        """Commit all changes inside the worktree with attributed author."""
        p = Path(worktree_path)
        if not p.exists():
            raise FileNotFoundError(f"Worktree path does not exist: {worktree_path}")

        # Stage all changes
        add_res = self._run_git(worktree_path, ["add", "-A"])
        if add_res.returncode != 0:
            raise RuntimeError(f"Git add failed: {add_res.stderr.strip()}")

        # Commit
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
        }
        res = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        # Check commit hash
        rev_res = self._run_git(worktree_path, ["rev-parse", "HEAD"])
        commit_hash = rev_res.stdout.strip() if rev_res.returncode == 0 else ""

        return {
            "success": res.returncode == 0,
            "commit_hash": commit_hash,
            "message": message,
            "output": res.stdout.strip() if res.returncode == 0 else res.stderr.strip(),
        }

    def remove_worktree(
        self,
        repo_dir: str,
        name_or_path: str,
        delete_branch: bool = False,
    ) -> bool:
        """Safely remove a worktree and optionally prune its branch."""
        target_path = Path(name_or_path)
        if not target_path.is_absolute():
            target_path = self.get_worktree_dir(repo_dir, name_or_path)

        wt_list = self.list_worktrees(repo_dir)
        branch_to_delete = None
        for wt in wt_list:
            if Path(wt["path"]).resolve() == target_path.resolve():
                branch_to_delete = wt.get("branch")
                break

        res = self._run_git(repo_dir, ["worktree", "remove", "--force", str(target_path)])
        self._run_git(repo_dir, ["worktree", "prune"])

        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)

        if delete_branch and branch_to_delete and branch_to_delete not in ("main", "master", "HEAD"):
            self._run_git(repo_dir, ["branch", "-D", branch_to_delete])

        return True
