# Gemini Tool Calling Issue - Root Cause and Solution

## Problem

When using Gemini with tools, the following error occurs:

```
langchain_google_genai.chat_models.ChatGoogleGenerativeAIError: Invalid argument provided to Gemini: 400
Function call is missing a thought_signature in functionCall parts. This is required for tools to work correctly,
and missing thought_signature may lead to degraded model performance.
Additional data, function call `default_api:get_all_active_products` , position 11.
```

## Root Cause

The issue is caused by using **Gemini 2.5 Pro Preview** models:

1. **`gemini-2.5-pro-preview-04-17`** requires `thought_signature` for all function calls
2. LangChain's `langchain-google-genai` (v2.1.12) does **not** support `thought_signature` yet
3. This is a known incompatibility between preview Gemini models and LangChain

### What is `thought_signature`?

`thought_signature` is a Gemini-specific feature for advanced reasoning models that:
- Helps the model explain its reasoning before calling a function
- Is required for Gemini 2.5 Pro Preview models
- Is not supported by LangChain yet

### Why This Happens

1. User tries to call a tool (e.g., `get_all_active_products`)
2. LLM (Gemini 2.5 Pro Preview) generates a function call response
3. Gemini API expects `thought_signature` in the function call
4. LangChain doesn't include `thought_signature` (doesn't support it)
5. Gemini API rejects the request with 400 error

## Solution

### Option 1: Use Stable Gemini Models (RECOMMENDED)

Change the Gemini models to use **stable models** that don't require `thought_signature`:

**In `.env`:**
```bash
# DON'T USE preview models - they require thought_signature
# GEMINI_MODEL_ADVANCED="gemini-2.5-pro-preview-04-17"  # ❌ NOT SUPPORTED

# USE stable models instead
GEMINI_MODEL_ADVANCED="gemini-2.0-flash-exp"  # ✅ WORKS
GEMINI_MODEL_MEDIUM="gemini-2.0-flash-exp"
GEMINI_MODEL_BASIC="gemini-2.0-flash-exp"
```

**Or use even more stable models:**
```bash
GEMINI_MODEL_ADVANCED="gemini-1.5-pro"
GEMINI_MODEL_MEDIUM="gemini-1.5-flash"
GEMINI_MODEL_BASIC="gemini-1.5-flash"
```

### Option 2: Use OpenAI for Tool Calling

Use OpenAI for agents that require tool calling (ecommerce, profiling, etc.):

```python
# In agent_graph.py, override provider for specific agents
ecommerce_llm = get_llm("advanced", provider="openai")  # Use OpenAI for tools
profiling_llm = get_llm("advanced", provider="openai")
orchestrator_llm = get_llm("advanced", provider="gemini")  # Gemini OK for orchestrator (no tools)
```

### Option 3: Wait for LangChain Support

Wait for `langchain-google-genai` to add support for `thought_signature`:
- Track: https://github.com/langchain-ai/langchain-google/issues
- This is a known issue that will be fixed in future versions

## Gemini Model Compatibility

### ✅ Models That Work with LangChain Tools

| Model | Tool Calling | Notes |
|-------|-------------|-------|
| `gemini-1.5-pro` | ✅ Yes | Stable, production-ready |
| `gemini-1.5-flash` | ✅ Yes | Fast, stable |
| `gemini-2.0-flash-exp` | ✅ Yes | Experimental but works |
| `gemini-2.5-flash-exp` | ✅ Yes | Experimental but works |

### ❌ Models That DON'T Work with LangChain Tools

| Model | Tool Calling | Issue |
|-------|-------------|-------|
| `gemini-2.5-pro-preview-04-17` | ❌ No | Requires `thought_signature` (not supported) |

## Updated `.env.example`

The `.env.example` has been updated with correct defaults:

```bash
# Gemini Configuration
GEMINI_API_KEY=

# IMPORTANT: Use stable models - preview models require thought_signature
# which LangChain doesn't support yet (as of v2.1.12)
GEMINI_MODEL_ADVANCED="gemini-2.0-flash-exp"
GEMINI_MODEL_MEDIUM="gemini-2.0-flash-exp"
GEMINI_MODEL_BASIC="gemini-2.0-flash-exp"
```

## How to Test

### Update Your `.env`

```bash
# Make sure you're using a compatible model
LLM_PROVIDER="gemini"
GEMINI_API_KEY="your-api-key"
GEMINI_MODEL_ADVANCED="gemini-2.0-flash-exp"  # ✅ Use this
# GEMINI_MODEL_ADVANCED="gemini-2.5-pro-preview-04-17"  # ❌ NOT this
```

### Test with Tool Calling

Send a message that requires tools:
- "Produk apa saja yang tersedia?" (Should call `get_all_active_products`)
- "Berapa harga GPS OBU V?" (Should call `get_product_details`)

### Expected Result

```
✓ Tools are called successfully
✓ LLM responses are generated
✓ No thought_signature errors
```

## Summary

| Issue | Solution |
|-------|----------|
| Gemini 2.5 Pro Preview + Tools | Use stable models (gemini-2.0-flash-exp, gemini-1.5-pro) |
| thought_signature error | Change model in `.env` to supported model |
| LangChain compatibility | Use gemini-2.0-flash-exp or wait for LangChain update |

## Files Changed

1. `.env.example` - Updated default Gemini models to use stable versions
2. `docs/GEMINI_TOOL_CALLING_FIX.md` - This documentation

## Backward Compatibility

✅ **Fully backward compatible** - OpenAI continues to work as before
✅ **No code changes required** - Just update `.env` with correct model name
