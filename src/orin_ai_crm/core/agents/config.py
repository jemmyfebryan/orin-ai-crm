"""
Centralized LLM configuration for all agents.

This module provides a single source of truth for LLM model names
used across all agent nodes, tools, and workflows.

Supports multiple LLM providers with tiered model selection:
- Provider: OpenAI or Gemini (via LLM_PROVIDER env var)
- Tiers: Advanced, Medium, Basic

Provider Usage:
- Advanced: Best reasoning and tool calling (orchestrator, ecommerce, profiling)
- Medium: Balanced performance (sales, support, final message)
- Basic: Fast and cost-effective (quality check)
"""
import os
from enum import Enum
from typing import Union

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    GEMINI = "gemini"


class LLMConfig:
    """Centralized LLM configuration with multi-provider support."""

    # Provider selection
    PROVIDER = LLMProvider(os.getenv("LLM_PROVIDER", "openai").lower())

    # OpenAI models
    OPENAI_ADVANCED_MODEL = os.getenv("OPENAI_MODEL_ADVANCED", "gpt-4o")
    OPENAI_MEDIUM_MODEL = os.getenv("OPENAI_MODEL_MEDIUM", "gpt-4o-mini")
    OPENAI_BASIC_MODEL = os.getenv("OPENAI_MODEL_BASIC", "gpt-4o-mini")

    # Gemini models
    GEMINI_ADVANCED_MODEL = os.getenv("GEMINI_MODEL_ADVANCED", "gemini-2.5-pro-preview-04-17")
    GEMINI_MEDIUM_MODEL = os.getenv("GEMINI_MODEL_MEDIUM", "gemini-2.0-flash-exp")
    GEMINI_BASIC_MODEL = os.getenv("GEMINI_MODEL_BASIC", "gemini-2.0-flash-exp")

    # Default model to use for all agent operations (backward compatibility)
    DEFAULT_MODEL = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")

    @property
    def ADVANCED_MODEL(self) -> str:
        """Get advanced model for current provider."""
        if self.PROVIDER == LLMProvider.GEMINI:
            return self.GEMINI_ADVANCED_MODEL
        return self.OPENAI_ADVANCED_MODEL

    @property
    def MEDIUM_MODEL(self) -> str:
        """Get medium model for current provider."""
        if self.PROVIDER == LLMProvider.GEMINI:
            return self.GEMINI_MEDIUM_MODEL
        return self.OPENAI_MEDIUM_MODEL

    @property
    def BASIC_MODEL(self) -> str:
        """Get basic model for current provider."""
        if self.PROVIDER == LLMProvider.GEMINI:
            return self.GEMINI_BASIC_MODEL
        return self.OPENAI_BASIC_MODEL


# Global config instance
llm_config = LLMConfig()


def get_llm(
    tier: str = "medium",
    temperature: float = 0,
    provider: Union[LLMProvider, str, None] = None
) -> BaseChatModel:
    """
    Get LLM instance based on tier and provider.

    Args:
        tier: Model tier - "advanced", "medium", or "basic"
            - advanced: Best for complex reasoning and tool calling (gpt-4o or gemini-2.5-pro)
            - medium: Balanced performance (gpt-4o-mini or gemini-2.0-flash)
            - basic: Fast and cost-effective (gpt-4o-mini or gemini-2.0-flash)
        temperature: LLM temperature (default: 0)
        provider: Override provider (optional). If not specified, uses LLM_PROVIDER env var.
                  Options: "openai" or "gemini"

    Returns:
        BaseChatModel instance (ChatOpenAI or ChatGoogleGenerativeAI)

    Example:
        # Uses provider from .env (LLM_PROVIDER)
        orchestrator_llm = get_llm("advanced")

        # Override provider for specific call
        gemini_llm = get_llm("advanced", provider="gemini")

        # Explicit provider with enum
        openai_llm = get_llm("medium", provider=LLMProvider.OPENAI)
    """
    # Resolve provider
    if provider is None:
        provider = llm_config.PROVIDER
    elif isinstance(provider, str):
        provider = LLMProvider(provider.lower())

    # Get model name for tier
    if tier == "advanced":
        model = llm_config.ADVANCED_MODEL
    elif tier == "medium":
        model = llm_config.MEDIUM_MODEL
    elif tier == "basic":
        model = llm_config.BASIC_MODEL
    else:
        # Fallback to medium for unknown tier
        model = llm_config.MEDIUM_MODEL

    # Instantiate correct LLM based on provider
    if provider == LLMProvider.GEMINI:
        return ChatGoogleGenerativeAI(
            model=model,
            api_key=os.getenv("GEMINI_API_KEY"),
            temperature=temperature
        )
    else:
        return ChatOpenAI(
            model=model,
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=temperature
        )
