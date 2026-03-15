"""
Tool call tracker to prevent infinite loops in agent tool calling.

This module provides utilities to track tool calls and detect
when tools are being called repeatedly without progress.
"""
from typing import Dict


class ToolCallTracker:
    """
    Track tool calls within a single agent invocation
    to detect and prevent infinite loops.
    """

    def __init__(self, max_calls_per_tool: int = 2):
        """
        Initialize tracker.

        Args:
            max_calls_per_tool: Maximum allowed calls for each tool
        """
        self.max_calls_per_tool = max_calls_per_tool
        self.call_counts: Dict[str, int] = {}
        self.empty_result_counts: Dict[str, int] = {}

    def should_call_tool(self, tool_name: str) -> tuple[bool, str]:
        """
        Check if a tool should be called based on call history.

        Args:
            tool_name: Name of the tool being called

        Returns:
            (should_call, reason) tuple
        """
        # Increment call count
        self.call_counts[tool_name] = self.call_counts.get(tool_name, 0) + 1

        # Check if exceeds max
        if self.call_counts[tool_name] > self.max_calls_per_tool:
            return False, f"Tool {tool_name} called {self.call_counts[tool_name]} times (max: {self.max_calls_per_tool})"

        # Check for repeated empty results
        if self.empty_result_counts.get(tool_name, 0) >= 2:
            return False, f"Tool {tool_name} returned empty results {self.empty_result_counts[tool_name]} times"

        return True, "OK"

    def record_empty_result(self, tool_name: str):
        """Record that a tool returned an empty result."""
        self.empty_result_counts[tool_name] = self.empty_result_counts.get(tool_name, 0) + 1

    def get_summary(self) -> Dict:
        """Get summary of tool calls."""
        return {
            "call_counts": self.call_counts.copy(),
            "empty_result_counts": self.empty_result_counts.copy(),
            "total_calls": sum(self.call_counts.values())
        }
