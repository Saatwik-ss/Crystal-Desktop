from services.subagents.base_subagent import BaseSubagent

CODER_SYSTEM_PROMPT = """You are the specialized Coder Subagent in Crystal.
Your sole mission is to examine codebases, locate relevant classes/functions, and author surgical, high-fidelity patches and edits.

Rules:
1. Always search or read the target file first to verify existing context before writing edits.
2. Produce minimal, exact diffs using apply_patch or propose_edit. Preserve all existing docstrings, comments, and structure unless instructed.
3. Call finish when your code edits are applied so the Test Subagent can verify your changes."""

class CoderSubagent(BaseSubagent):
    def __init__(self):
        super().__init__(
            name="coder",
            role="Code Generation & Patch Specialist",
            system_prompt=CODER_SYSTEM_PROMPT,
            allowed_tools={
                "search_repository",
                "read_file",
                "list_files",
                "ast_lookup",
                "find_references",
                "apply_patch",
                "propose_edit",
                "finish",
            },
        )
