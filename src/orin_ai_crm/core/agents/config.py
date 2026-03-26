"""
Centralized LLM configuration for all agents.

This module provides a single source of truth for LLM model names
used across all agent nodes, tools, and workflows.

Supports tiered model selection:
- Advanced: Best reasoning and tool calling (orchestrator, ecommerce, profiling)
- Medium: Balanced performance (sales, support, final message)
- Basic: Fast and cost-effective (quality check)
"""
import os
from langchain_openai import ChatOpenAI


class LLMConfig:
    """Centralized LLM configuration with tiered model support."""

    # Tiered model configuration
    ADVANCED_MODEL = os.getenv("OPENAI_MODEL_ADVANCED", "gpt-4o")
    MEDIUM_MODEL = os.getenv("OPENAI_MODEL_MEDIUM", "gpt-4o-mini")
    BASIC_MODEL = os.getenv("OPENAI_MODEL_BASIC", "gpt-4o-mini")

    # Default model to use for all agent operations (backward compatibility)
    DEFAULT_MODEL = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")


# Global config instance
llm_config = LLMConfig()


def get_llm(tier: str = "medium", temperature: float = 0) -> ChatOpenAI:
    """
    Get LLM instance based on tier.

    Args:
        tier: Model tier - "advanced", "medium", or "basic"
            - advanced: Best for complex reasoning and tool calling (gpt-4o)
            - medium: Balanced performance (gpt-4o-mini)
            - basic: Fast and cost-effective (gpt-4o-mini)
        temperature: LLM temperature (default: 0)

    Returns:
        ChatOpenAI instance with appropriate model

    Example:
        orchestrator_llm = get_llm("advanced")
        sales_llm = get_llm("medium")
        quality_llm = get_llm("basic")
    """
    api_key = os.getenv("OPENAI_API_KEY")

    if tier == "advanced":
        model = llm_config.ADVANCED_MODEL
    elif tier == "medium":
        model = llm_config.MEDIUM_MODEL
    elif tier == "basic":
        model = llm_config.BASIC_MODEL
    else:
        # Fallback to default for unknown tier
        model = llm_config.DEFAULT_MODEL

    return ChatOpenAI(model=model, api_key=api_key, temperature=temperature)
