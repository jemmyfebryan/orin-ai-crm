# LLM Provider Switching Guide

This guide explains how to switch between OpenAI and Gemini as your LLM provider.

## Overview

The Orin AI CRM now supports dynamic switching between OpenAI and Gemini as LLM providers. This allows you to:
- Switch providers globally via environment variable
- Use different providers for different agent tiers
- Override provider per-agent if needed

## Configuration

### 1. Environment Variables

Add the following to your `.env` file:

```bash
# Choose your LLM provider: "openai" or "gemini"
LLM_PROVIDER="openai"

# OpenAI Configuration
OPENAI_API_KEY="sk-..."
OPENAI_MODEL_ADVANCED="gpt-4o"
OPENAI_MODEL_MEDIUM="gpt-4o-mini"
OPENAI_MODEL_BASIC="gpt-4o-mini"

# Gemini Configuration
GEMINI_API_KEY="AIza..."
GEMINI_MODEL_ADVANCED="gemini-2.5-pro-preview-04-17"
GEMINI_MODEL_MEDIUM="gemini-2.0-flash-exp"
GEMINI_MODEL_BASIC="gemini-2.0-flash-exp"
```

### 2. Switching Providers

#### Global Switch (via .env)
Simply change the `LLM_PROVIDER` environment variable:
```bash
# Use OpenAI
LLM_PROVIDER="openai"

# Use Gemini
LLM_PROVIDER="gemini"
```

#### Per-Agent Override (in code)
```python
from src.orin_ai_crm.core.agents.config import get_llm, LLMProvider

# Use OpenAI for orchestrator
orchestrator_llm = get_llm("advanced")

# Use Gemini for ecommerce agent
ecommerce_llm = get_llm("advanced", provider="gemini")

# Explicit provider with enum
sales_llm = get_llm("medium", provider=LLMProvider.OPENAI)
```

## Model Tiers

The system uses three tiers for different use cases:

| Tier | Use Case | OpenAI Model | Gemini Model |
|------|----------|--------------|--------------|
| **Advanced** | Complex reasoning, tool calling (orchestrator, ecommerce, profiling) | `gpt-4o` | `gemini-2.5-pro-preview-04-17` |
| **Medium** | Balanced performance (sales, support, final message) | `gpt-4o-mini` | `gemini-2.0-flash-exp` |
| **Basic** | Fast and cost-effective (quality check) | `gpt-4o-mini` | `gemini-2.0-flash-exp` |

## Current Agent Assignments

```python
# In agent_graph.py
orchestrator_llm = get_llm("advanced")      # Uses LLM_PROVIDER from .env
ecommerce_llm = get_llm("advanced")         # Uses LLM_PROVIDER from .env
profiling_llm = get_llm("advanced")         # Uses LLM_PROVIDER from .env
sales_llm = get_llm("medium")               # Uses LLM_PROVIDER from .env
support_llm = get_llm("medium")             # Uses LLM_PROVIDER from .env
final_message_llm = get_llm("basic")        # Uses LLM_PROVIDER from .env
quality_check_llm = get_llm("basic")        # Uses LLM_PROVIDER from .env
```

## API Key Setup

### OpenAI
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Add to `.env`: `OPENAI_API_KEY="sk-..."`

### Gemini
1. Go to https://makersuite.google.com/app/apikey
2. Create a new API key
3. Add to `.env`: `GEMINI_API_KEY="AIza..."`

## Testing

Run the provider switching tests to verify configuration:

```bash
poetry run python tests/core/agents/test_llm_provider_switching.py
```

## Example: Cost Optimization with Gemini

To reduce costs, you can use Gemini for high-volume agents while keeping OpenAI for critical tasks:

```python
# In agent_graph.py (if you want to override per-agent)
orchestrator_llm = get_llm("advanced", provider="openai")  # Keep OpenAI for complex routing
ecommerce_llm = get_llm("advanced", provider="gemini")     # Use Gemini for heavy tool calls
sales_llm = get_llm("medium", provider="gemini")           # Use Gemini for simple flows
```

## Backward Compatibility

All existing code continues to work without changes:
- `get_llm("advanced")` uses the provider from `LLM_PROVIDER` env var
- Default provider is OpenAI if `LLM_PROVIDER` is not set
- All existing tests pass without modification
