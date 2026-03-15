"""
Centralized LLM configuration for all agents.

This module provides a single source of truth for LLM model names
used across all agent nodes, tools, and workflows.
"""
import os


class LLMConfig:
    """Centralized LLM configuration."""

    # Default model to use for all agent operations
    DEFAULT_MODEL = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")

    # Alternative model configurations (if needed in the future)
    # FAST_MODEL = os.getenv("OPENAI_FAST_MODEL", "gpt-4o-mini")
    # SMART_MODEL = os.getenv("OPENAI_SMART_MODEL", "gpt-4o")


# Global config instance
llm_config = LLMConfig()
