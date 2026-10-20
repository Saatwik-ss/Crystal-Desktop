import os
import subprocess
import tempfile
import pytest
from pathlib import Path
from services.git.worktree_manager import GitWorktreeManager

@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository with an initial commit."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir) / "test_repo"
        repo_path.mkdir(parents=True, exist_ok=True)

        # git init
        subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path), check=True)
        subprocess.run(["git", "config", "user.email", "test@crystal.local"], cwd=str(repo_path), check=True)

        # Initial commit
        readme = repo_path / "README.md"
        readme.write_text("# Test Repo\nInitial content\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(repo_path), check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True)

        yield str(repo_path)

def test_worktree_lifecycle(temp_git_repo):
    mgr = GitWorktreeManager()
    assert mgr.is_git_repo(temp_git_repo) is True

    # 1. Create worktree
    wt = mgr.create_worktree(temp_git_repo, "tkt-142")
    assert wt["name"] == "tkt-142"
    assert wt["branch"] == "mesh/tkt-142"
    wt_path = Path(wt["path"])
    assert wt_path.exists()
    assert (wt_path / "README.md").exists()

    # 2. List worktrees
    worktrees = mgr.list_worktrees(temp_git_repo)
    assert len(worktrees) == 2
    branches = [w["branch"] for w in worktrees]
    assert "main" in branches
    assert "mesh/tkt-142" in branches

    # 3. Modify a file in the worktree
    wt_file = wt_path / "feature.py"
    wt_file.write_text("def hello():\n    return 'mesh'\n", encoding="utf-8")

    # 4. Check diff
    diff_data = mgr.get_diff(str(wt_path))
    assert diff_data["additions"] == 2
    assert diff_data["files_count"] == 1
    assert "def hello():" in diff_data["diff_patch"]

    # 5. Commit in worktree
    commit_res = mgr.commit(str(wt_path), "Add feature.py", author_name="Agent-01")
    assert commit_res["success"] is True
    assert commit_res["commit_hash"] != ""

    # Verify main repo is untouched
    main_readme = Path(temp_git_repo) / "README.md"
    assert main_readme.read_text(encoding="utf-8") == "# Test Repo\nInitial content\n"
    assert not (Path(temp_git_repo) / "feature.py").exists()

    # 6. Remove worktree
    removed = mgr.remove_worktree(temp_git_repo, "tkt-142", delete_branch=True)
    assert removed is True
    assert not wt_path.exists()

    worktrees_after = mgr.list_worktrees(temp_git_repo)
    assert len(worktrees_after) == 1
