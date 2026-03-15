# Fix: Wrong customer_id in update_customer_data Tool

## Bug Description

The `update_customer_data` tool was using a `customer_id` parameter that the LLM had to provide. This caused the LLM to hallucinate wrong customer_id values, leading to:
- Customer 15's data being updated to customer 1's profile
- Data leak vulnerability
- Incorrect customer updates

## Root Cause

**Before Fix:**
```python
@tool
async def update_customer_data(
    customer_id: int,  # ❌ LLM must provide this
    name: Optional[str] = None,
    ...
)
```

The LLM would sometimes call the tool with `customer_id=1` when it should have been `customer_id=15`.

## Solution: Option 1 - Use InjectedState

**After Fix:**
```python
@tool
async def update_customer_data(
    state: Annotated[dict, InjectedState],  # ✅ Gets customer_id from state
    name: Optional[str] = None,
    ...
):
    customer_id = state.get("customer_id")  # ✅ Always correct
```

## Changes Made

**File**: `src/orin_ai_crm/core/agents/tools/customer_agent_tools.py`

1. **Added parameter**: `state: Annotated[dict, InjectedState]`
2. **Removed parameter**: `customer_id: int`
3. **Added logic**: Get customer_id from state at the start of function
4. **Added validation**: Check if customer_id exists in state
5. **Updated logging**: Now logs "(from state)" to indicate source

## Benefits

✅ **Security**: LLM can no longer provide wrong customer_id
✅ **Consistency**: Now matches `get_customer_profile` implementation
✅ **Reliability**: Always uses correct customer_id from conversation state
✅ **Traceability**: Logging shows customer_id comes from state

## Testing

To verify the fix works:

```bash
# Test import
python -c "from src.orin_ai_crm.core.agents.tools.customer_agent_tools import update_customer_data"

# Test with actual agent
# Send message with form data, check logs for:
# "TOOL: update_customer_data - customer_id: X (from state)"
```

## Expected Logs After Fix

**Before**:
```
update_customer_data - customer_id: 1  # ❌ Wrong!
```

**After**:
```
update_customer_data - customer_id: 15 (from state)  # ✅ Correct!
```

## Impact

- **No breaking changes**: Tool functionality remains the same
- **Tool signature changed**: LLM no longer sees customer_id parameter
- **Call sites**: No changes needed - tool is called by agent, not manually
- **Database**: No migration needed
