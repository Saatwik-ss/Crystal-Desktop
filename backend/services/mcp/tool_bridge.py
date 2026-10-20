from typing import Dict, Any, List

def mcp_tool_to_crystal_schema(server_name: str, mcp_tool: Any) -> Dict[str, Any]:
    """
    Translates an MCP Tool object into Crystal's function calling schema.
    Prefixes tool name to avoid collisions: mcp__{server}__{tool}
    """
    tool_name = getattr(mcp_tool, "name", "")
    description = getattr(mcp_tool, "description", "") or f"MCP tool from {server_name}"
    input_schema = getattr(mcp_tool, "inputSchema", {}) or {}

    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    crystal_properties = {}
    for prop_name, prop_def in properties.items():
        spec = {
            "type": prop_def.get("type", "string"),
            "description": prop_def.get("description", ""),
        }
        if "enum" in prop_def:
            spec["enum"] = prop_def["enum"]
        if "default" in prop_def:
            spec["default"] = prop_def["default"]
        crystal_properties[prop_name] = spec

    namespaced_name = f"mcp__{server_name}__{tool_name}"

    return {
        "name": namespaced_name,
        "description": f"[{server_name.upper()} MCP] {description}",
        "parameters": crystal_properties,
        "raw_server": server_name,
        "raw_name": tool_name,
    }
