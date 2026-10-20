import re
import hashlib
import logging
from enum import Enum
from typing import Dict, Any, Tuple, Set, Optional

logger = logging.getLogger(__name__)

class RiskTier(str, Enum):
    SAFE = "safe"          # Read-only operations, queries
    CAUTION = "caution"    # Edits, standard tests, package additions
    DANGEROUS = "dangerous"# Destructive commands, disk wipes, cloud push, exfiltration

# Pattern matchers for dangerous shell commands
DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+(-[rfRF]{1,4}\s+)?(/|~|\*|\$HOME|[a-zA-Z]:\\)", re.IGNORECASE),
    re.compile(r"\b(del|erase|rmdir|rd)\s+([/\\a-zA-Z0-9_*?-]+)?(/s|/q)?", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
    re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
    re.compile(r"\bgit\s+clean\s+-[xfd]{1,4}\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+(DATABASE|TABLE|SCHEMA)\b", re.IGNORECASE),
    re.compile(r"\b(curl|wget)\s+.*(-d|--data|--upload-file|-F)\b", re.IGNORECASE),
    re.compile(r"\b(gcloud|aws|az|kubectl)\s+.*(delete|destroy|apply|push)\b", re.IGNORECASE),
    re.compile(r"\b(mkfs|dd\s+if=)\b", re.IGNORECASE),
]

# Pattern matchers for safe shell commands
SAFE_SHELL_PREFIXES = (
    "ls", "dir", "git status", "git diff", "git log", "git branch",
    "cat ", "type ", "head ", "tail ", "echo ", "pwd", "cd ",
    "python --version", "node --version", "npm --version",
)

class PolicyEngine:
    """
    Evaluates actions against safety rules and manages Human-in-the-Loop approvals.
    Defaults to 'strict' mode as configured.
    """

    def __init__(self, mode: str = "strict"):
        # Mode: 'strict' | 'balanced' | 'permissive'
        self.mode = mode
        self.session_allowed_all = False
        self.approved_action_ids: Set[str] = set()
        self.pending_approvals: Dict[str, Dict[str, Any]] = {}

    def compute_action_id(self, action_type: str, details: Dict[str, Any]) -> str:
        raw = f"{action_type}:{sorted(details.items())}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]

    def evaluate(self, action_type: str, details: Dict[str, Any]) -> Tuple[RiskTier, bool, str]:
        """
        Evaluate an action.
        Returns: (RiskTier, needs_user_approval: bool, reason: str)
        """
        action_id = self.compute_action_id(action_type, details)

        # If already approved or session allows all
        if self.session_allowed_all or action_id in self.approved_action_ids:
            return RiskTier.SAFE, False, "Approved by developer"

        # 1. Shell commands evaluation
        if action_type == "terminal_command":
            raw_cmd = details.get("command", "") or details.get("cmd", "")
            if isinstance(raw_cmd, list):
                if len(raw_cmd) >= 3 and raw_cmd[0] in ("bash", "sh", "zsh") and raw_cmd[1] in ("-c", "-lc", "-cl"):
                    cmd = str(raw_cmd[2]).strip()
                elif len(raw_cmd) >= 2 and raw_cmd[0] in ("bash", "sh", "zsh") and raw_cmd[1].startswith("-c"):
                    cmd = " ".join(str(x) for x in raw_cmd[1:]).strip()
                else:
                    cmd = " ".join(str(x) for x in raw_cmd).strip()
            else:
                cmd = str(raw_cmd or "").strip()
            # Check for catastrophic patterns
            for pat in DANGEROUS_PATTERNS:
                if pat.search(cmd):
                    return RiskTier.DANGEROUS, True, f"Potentially destructive command detected: {cmd}"

            # Check mode first: in strict mode, commands require confirmation
            if self.mode == "strict":
                return RiskTier.CAUTION, True, f"Strict mode: Confirmation requested for command: {cmd}"

            cmd_lower = cmd.lower()
            if any(cmd_lower.startswith(p) for p in SAFE_SHELL_PREFIXES):
                return RiskTier.SAFE, False, "Read-only inspection command"

            # Safe verification and test commands in balanced/permissive mode
            if any(cmd_lower.startswith(p) for p in ("pytest", "python -m pytest", "npm test", "npm run", "cargo test", "go test", "tsc", "eslint", "ruff", "mypy")):
                return RiskTier.SAFE, False, "Standard verification test command"

            return RiskTier.CAUTION, False, "Standard build/test command"

        # 2. File edit or creation
        if action_type in ("write_file", "apply_patch", "propose_edit"):
            file_path = details.get("file_path", "")
            if file_path.endswith((".env", ".pem", ".key", "id_rsa")):
                return RiskTier.DANGEROUS, True, f"Modifying sensitive credential file: {file_path}"

            if self.mode == "strict":
                return RiskTier.CAUTION, True, f"Strict mode: Confirmation requested to write/edit {file_path}"
            return RiskTier.CAUTION, False, "Standard file edit"

        # 3. Browser actions
        if action_type.startswith("browser_"):
            if self.mode == "strict" and action_type in ("browser_click", "browser_type"):
                return RiskTier.CAUTION, True, f"Strict mode: Confirmation requested for browser interaction: {action_type}"
            return RiskTier.SAFE, False, "Browser action permitted"

        # 4. OS desktop control actions
        if action_type.startswith("desktop_"):
            return RiskTier.DANGEROUS, True, f"Desktop OS control requested: {action_type}"

        return RiskTier.SAFE, False, "Safe operation"

    def register_pending_approval(self, action_id: str, payload: Dict[str, Any]):
        self.pending_approvals[action_id] = payload

    def grant_approval(self, action_id: str, scope: str = "once"):
        self.approved_action_ids.add(action_id)
        if scope == "session":
            self.session_allowed_all = True
        self.pending_approvals.pop(action_id, None)

    def reject_approval(self, action_id: str):
        self.approved_action_ids.discard(action_id)
        self.pending_approvals.pop(action_id, None)
