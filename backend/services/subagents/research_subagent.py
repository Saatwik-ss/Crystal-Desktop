from services.subagents.base_subagent import BaseSubagent

RESEARCH_SYSTEM_PROMPT = """You are the specialized Research Subagent in Crystal.
Your mission is to look up documentation, test live web endpoints, explore accessibility trees, and query Model Context Protocol (MCP) servers.

Rules:
1. Use browser_navigate to visit web pages, extract state, or inspect UI layout.
2. Formulate clear, concise summaries of documentation, schema definitions, and API specifications.
3. Call finish once you have gathered the required findings for the Coder subagent."""

class ResearchSubagent(BaseSubagent):
    def __init__(self):
        super().__init__(
            name="researcher",
            role="Web & Documentation Specialist",
            system_prompt=RESEARCH_SYSTEM_PROMPT,
            allowed_tools={
                "browser_navigate",
                "browser_click",
                "browser_type",
                "browser_press_key",
                "browser_screenshot",
                "browser_extract_state",
                "read_file",
                "list_files",
                "finish",
            },
        )
