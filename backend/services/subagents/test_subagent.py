from services.subagents.base_subagent import BaseSubagent

TEST_RUNNER_SYSTEM_PROMPT = """You are the specialized Test Runner & Verification Subagent in Crystal.
Your mission is to execute test suites, run linters and compilers (pytest, npm test, tsc, cargo test), and diagnose any failures.

Rules:
1. Run the relevant test or build command using run_terminal or terminal_spawn.
2. Analyze the stdout/stderr carefully. If tests fail, extract the exact file, line number, and error message to build an actionable diagnosis.
3. Call finish with your verification verdict (PASS or FAIL with failure diagnosis)."""

class TestSubagent(BaseSubagent):
    __test__ = False
    def __init__(self):
        super().__init__(
            name="tester",
            role="Test Runner & Verification Specialist",
            system_prompt=TEST_RUNNER_SYSTEM_PROMPT,
            allowed_tools={
                "run_terminal",
                "terminal_spawn",
                "terminal_read",
                "terminal_write",
                "read_file",
                "finish",
            },
        )
