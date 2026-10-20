from typing import Set, Dict, Any

class BaseSubagent:
    """Base class for specialized subagents in the hierarchical ReAct architecture."""

    def __init__(self, name: str, role: str, system_prompt: str, allowed_tools: Set[str]):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools

    def get_system_prompt(self, user_override: str = "") -> str:
        if user_override:
            return f"{self.system_prompt}\n\nAdditional user guidelines:\n{user_override}"
        return self.system_prompt
