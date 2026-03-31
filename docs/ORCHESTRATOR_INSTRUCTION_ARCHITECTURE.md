# Orchestrator-Sub-Agent Instruction Architecture

## Overview

This document describes the new multi-agent architecture where the Orchestrator provides direct instructions to sub-agents, which execute with fresh state and return ToolMessages to the main orchestrator.

## Architecture Change

### Previous Paradigm (Deprecated)
```
Orchestrator → produces "plan" (descriptive)
→ Sub-agent → continues with existing messages
→ Returns AIMessage responses
→ Orchestrator sees AIMessages
```

### New Paradigm (Current)
```
Orchestrator → produces "instruction" (direct command)
→ Sub-agent → receives FRESH state with only instruction
→ Returns ToolMessages only
→ ToolMessages appended to main orchestrator messages via operator.add
→ Orchestrator sees ToolMessages
```

## Key Changes

### 1. OrchestratorDecision Schema (`agent_graph.py`)

**Before:**
```python
class OrchestratorDecision(BaseModel):
    next_agent: Literal["profiling", "sales", "ecommerce", "support", "final"]
    reasoning: str
    plan: str  # Descriptive plan
```

**After:**
```python
class OrchestratorDecision(BaseModel):
    next_agent: Literal["profiling", "sales", "ecommerce", "support", "final"]
    reasoning: str
    instruction: str  # Direct command to next agent
```

### 2. Orchestrator Prompt (`default_prompts.py`)

The orchestrator prompt now emphasizes generating **direct instructions** instead of descriptive plans.

**Instruction Format:**
- Start with action verb: "Extract...", "Ask...", "Provide...", "Help..."
- Be specific and actionable
- Tell the agent EXACTLY what to do
- NOT descriptive, but DIRECTIVE

**Examples:**
- ✅ "Extract the customer's domicile from their message: 'saya di surabaya'"
- ✅ "Ask the customer if they want to schedule a meeting with our sales team"
- ✅ "Get product details for OBU V and provide pricing information"
- ❌ "The agent should extract domicile" (too descriptive)
- ❌ "Discuss product options" (too vague)

### 3. Sub-Agent Nodes (profiling_node, sales_node, ecommerce_node, support_node)

Each sub-agent node now:

**Creates Fresh State:**
```python
# Get instruction from orchestrator
orchestrator_decision = state.get('orchestrator_decision', {})
instruction = orchestrator_decision.get('instruction', 'Continue naturally.')

# Create FRESH state for sub-agent
fresh_state = dict(state)

# CRITICAL: Remove existing messages and replace with only instruction
from langchain_core.messages import AIMessage
fresh_state['messages'] = [AIMessage(content=instruction)]
```

**Invokes Agent with Fresh State:**
```python
# Invoke the agent with FRESH state (only instruction as message)
result = await agent.ainvoke(fresh_state, recursion_limit=10)
```

**Filters and Returns ToolMessages:**
```python
# Extract ToolMessages from result to append to main orchestrator messages
from langchain_core.messages import ToolMessage
tool_messages = [msg for msg in result.get('messages', []) if isinstance(msg, ToolMessage)]

# Return ToolMessages to append via operator.add
update = {
    'messages': tool_messages  # Only ToolMessages, not AIMessages
}
# ... other state updates
return update
```

### 4. State Initialization (`agent_entry_handler`)

**Before:**
```python
if 'orchestrator_plan' not in state:
    state['orchestrator_plan'] = ""
```

**After:**
```python
if 'orchestrator_instruction' not in state:
    state['orchestrator_instruction'] = ""
```

## Benefits

1. **Cleaner Message Flow**: Sub-agents start fresh without clutter from previous conversation
2. **Focused Execution**: Each sub-agent only sees the instruction, not the entire conversation history
3. **Better Orchestration**: Orchestrator can direct sub-agents more precisely with actionable instructions
4. **State Isolation**: Sub-agents don't accidentally use old message context
5. **Easier Debugging**: Each agent execution is self-contained with clear instruction

## Flow Diagram

```
User Message
    ↓
agent_entry_handler
    ↓
orchestrator_node
    ├─ Analyzes customer context
    ├─ Decides next_agent
    └─ Generates instruction (direct command)
    ↓
orchestrator_router
    ↓
Sub-Agent Node (e.g., profiling_node)
    ├─ Creates fresh_state with only instruction
    ├─ Invokes agent with fresh_state
    ├─ Filters ToolMessages from result
    └─ Returns {'messages': [ToolMessages, ...]}
    ↓
ToolMessages appended to main orchestrator messages (via operator.add)
    ↓
Back to orchestrator_node
    ├─ Sees ToolMessages from previous agent
    ├─ Decides next step
    └─ Loop until "final"
```

## Files Modified

1. **`src/orin_ai_crm/core/agents/custom/hana_agent/agent_graph.py`**
   - `OrchestratorDecision.plan` → `OrchestratorDecision.instruction`
   - `agent_entry_handler`: `orchestrator_plan` → `orchestrator_instruction`
   - `orchestrator_node`: Returns `orchestrator_instruction` instead of `orchestrator_plan`
   - `profiling_node`: Fresh state pattern + ToolMessages filter
   - `sales_node`: Fresh state pattern + ToolMessages filter
   - `ecommerce_node`: Fresh state pattern + ToolMessages filter
   - `support_node`: Fresh state pattern + ToolMessages filter

2. **`src/orin_ai_crm/core/agents/custom/hana_agent/default_prompts.py`**
   - Updated orchestrator prompt to generate instructions instead of descriptive plans
   - Added "CRITICAL: INSTRUCTION FORMAT" section with examples

## Testing

To verify the implementation:

1. **Check OrchestratorDecision fields:**
   ```python
   from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import OrchestratorDecision
   print(OrchestratorDecision.model_fields.keys())
   # Should include: 'next_agent', 'reasoning', 'instruction'
   ```

2. **Test fresh state creation:**
   - Check logs for "Fresh state created for X agent with 1 message (instruction)"
   - Verify sub-agents only receive instruction, not full conversation history

3. **Verify ToolMessages filtering:**
   - Check logs for "X agent produced N ToolMessages"
   - Verify AIMessages are NOT appended to main orchestrator messages

## Migration Notes

- The `orchestrator_plan` state field has been renamed to `orchestrator_instruction`
- Old code referencing `state['orchestrator_plan']` should now use `state['orchestrator_instruction']`
- Sub-agents are now more "agnostic" - they don't see the full conversation context
- Orchestrator must provide clear, actionable instructions for sub-agents to execute properly
