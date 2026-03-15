# Fixing Infinite Tool-Calling Loops in Agent

## Problem
Agent calls `check_profiling_completeness` → `determine_next_profiling` repeatedly without stopping, even when:
- User is asking product questions (not providing profile info)
- Tools return empty results multiple times
- Customer is already onboarded (`is_onboarded=True`)

## Root Cause
Agent doesn't know when to stop tool calling and keeps retrying profiling tools indefinitely.

---

## Solutions (Implement Multiple for Best Results)

### ✅ Solution 1: Improved System Prompt (ALREADY IMPLEMENTED)
**File**: `src/orin_ai_crm/core/agents/custom/hana_agent/agent_graph.py`

Added explicit stopping rules:
- Max 2 calls per profiling tool
- Prioritize answering product questions
- Stop if tools return empty 2x in a row

**Status**: ✅ Done

---

### ✅ Solution 2: Reduced recursion_limit (ALREADY IMPLEMENTED)
**File**: `src/orin_ai_crm/server/services/chat_processor.py`

Changed from `recursion_limit=50` to `recursion_limit=10`

**Impact**:
- Normal flow: 2-5 steps (plenty of room)
- Infinite loop: Stops after 10 steps instead of 50
- Saves API tokens and prevents rate limits

**Status**: ✅ Done

---

### 🔧 Solution 3: Add "should_continue" Flag to Tools
**File**: `src/orin_ai_crm/core/agents/tools/profiling_agent_tools.py`

Modify tools to return a flag that tells the agent to stop:

```python
@tool
async def check_profiling_completeness(...) -> dict:
    # ... existing logic ...

    # NEW: Add stop signal
    empty_results_count = _get_empty_results_count()  # Track in state
    if empty_results_count >= 2:
        return {
            "is_complete": False,
            "missing_fields": missing_fields,
            "recommended_route": None,
            "should_stop": True,  # ← NEW: Tells agent to stop
            "message": "Stop profiling and answer the user's question"
        }

    return {
        "is_complete": is_complete,
        "missing_fields": missing_fields,
        "recommended_route": recommended_route,
        "should_stop": False
    }
```

**Pros**: Explicit signal to agent
**Cons**: Requires state tracking between tool calls

---

### 🔧 Solution 4: Tool Call History Tracker
**File**: `src/orin_ai_crm/core/agents/custom/hana_agent/agent_graph.py`

Track tool calls and force stop after threshold:

```python
async def agent_node(state: AgentState) -> Dict:
    # ... existing code ...

    # NEW: Track tool calls in this invocation
    tool_call_history = {}  # tool_name -> count

    # Define a wrapper that counts calls
    async def counting_tool(tool_name, tool_input):
        tool_call_history[tool_name] = tool_call_history.get(tool_name, 0) + 1

        # Check if tool called too many times
        if tool_call_history[tool_name] >= 2:
            logger.warning(f"Tool {tool_name} called {tool_call_history[tool_name]} times, forcing stop")
            # Return early with answer to user's question
            return {
                "messages": [AIMessage(content="Maaf, saya akan jawab pertanyaan kakak sekarang.")],
                "step": "final_message"
            }

    # Use with agent
    result = await agent.ainvoke(state)
    return result
```

**Pros**: Hard limit enforcement
**Cons**: More complex implementation

---

### 🔧 Solution 5: Detect User Intent Before Agent Loop
**File**: `src/orin_ai_crm/server/services/chat_processor.py`

Add intent detection before invoking agent:

```python
async def process_chat_request(...):
    # ... existing code ...

    # NEW: Quick intent detection
    user_message = message.lower()
    product_keywords = ["bedanya", "produk", "obu", "gps", "harga", "fitur"]

    is_product_question = any(keyword in user_message for keyword in product_keywords)

    if is_product_question:
        # Skip agent, go directly to product answer
        logger.info("Product question detected, bypassing profiling")
        from src.orin_ai_crm.core.agents.tools.product_agent_tools import answer_product_question_from_db

        answer = await answer_product_question_from_db.ainvoke({
            'question': message,
            'customer_data': customer_data
        })

        return {
            'ai_replies': [answer],
            'tool_calls_used': ['direct_product_answer']
        }

    # Normal agent flow for non-product questions
    final_state = await hana_agent.ainvoke(initial_state, recursion_limit=10)
    # ...
```

**Pros**: Fast, avoids agent loop entirely for product questions
**Cons**: Bypasses agent's reasoning

---

## Recommended Implementation Priority

### Phase 1: Quick Wins (Done ✅)
1. ✅ Solution 1: System prompt improvements
2. ✅ Solution 2: Reduced recursion_limit

### Phase 2: Enhanced Protection (Next Steps)
3. 🔧 Solution 5: Intent detection (high impact, low effort)

### Phase 3: Robust Fallback (If needed)
4. 🔧 Solution 3: should_continue flag
5. 🔧 Solution 4: Tool call tracker

---

## Testing Checklist

After implementing solutions, test these scenarios:

- [ ] User asks product question with empty profile
- [ ] User provides profile info slowly (one field at a time)
- [ ] User asks question while profiling incomplete
- [ ] User sends gibberish (no clear intent)
- [ ] Already onboarded user asks product question
- [ ] New user asks multiple product questions in a row

---

## Monitoring

Add logging to track tool call patterns:

```python
# In agent_node
logger.info(f"Agent tool calls in this invocation: {tool_call_history}")
logger.warning(f"Recursion depth: {len(state['messages'])}")
```

This will help identify if loops still occur after fixes.
