# Gemini SystemMessage Fix

## Problem

Gemini API requires at least one `HumanMessage` in the conversation, but the code was only passing `SystemMessage`. This causes the error:

```
google.api_core.exceptions.InvalidArgument: 400 * GenerateContentRequest.contents: contents is not specified
```

## Root Cause

OpenAI accepts `invoke([SystemMessage(...)])` with just a system message, but Gemini's API requires:
1. At least one message with actual content
2. A user message (`HumanMessage`) to prompt the LLM

## Solution

Added a placeholder `HumanMessage` after the `SystemMessage` in all LLM invocations with structured output.

### Changes in `quality_check_nodes.py`

**1. Line 211 - `evaluate_answer_quality()` function:**
```python
# BEFORE
result = evaluator_llm.invoke([SystemMessage(content=system_prompt)])

# AFTER
result = evaluator_llm.invoke([
    SystemMessage(content=system_prompt),
    HumanMessage(content="Evaluate the above answer.")
])
```

**2. Line 331 - `generate_human_takeover_message()` function:**
```python
# BEFORE
response = human_takeover_llm.invoke([SystemMessage(content=system_prompt)])

# AFTER
response = human_takeover_llm.invoke([
    SystemMessage(content=system_prompt),
    HumanMessage(content="Generate the human takeover response.")
])
```

**3. Line 647 - `node_final_message()` function:**
```python
# BEFORE
result: FinalMessagesResponse = final_messages_llm_structured.invoke([SystemMessage(content=system_prompt)])

# AFTER
result: FinalMessagesResponse = final_messages_llm_structured.invoke([
    SystemMessage(content=system_prompt),
    HumanMessage(content="Generate the response based on the above instructions.")
])
```

## Why This Works

- **OpenAI**: Works with both formats (just SystemMessage or SystemMessage + HumanMessage)
- **Gemini**: Requires at least one HumanMessage with content

The placeholder HumanMessage prompts the LLM to generate the structured output based on the system prompt instructions. This is a common pattern for structured output generation.

## Backward Compatibility

✅ **Fully backward compatible** - OpenAI continues to work exactly as before.

## Testing

Please test with:
```bash
# In .env
LLM_PROVIDER="gemini"
GEMINI_API_KEY="your-key"
```

Then send a message like "halo" or "hello" to test the full flow.

## Files Changed

- `src/orin_ai_crm/core/agents/nodes/quality_check_nodes.py` (3 fixes)
