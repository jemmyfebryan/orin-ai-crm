# Security Audit: customer_id Parameter Vulnerability

## Summary

Found **4 active tools** with the same vulnerability as `update_customer_data` - they accept `customer_id` as a parameter that the LLM must provide, which can lead to:
- Wrong customer data being updated
- Cross-customer data leaks
- Security vulnerability

---

## 🚨 Active Vulnerable Tools (Currently Used by Agent)

### 1. **product_agent_tools.py**

#### ❌ `create_product_inquiry` (Line 700)
```python
@tool
async def create_product_inquiry(
    customer_id: int,  # ❌ VULNERABLE
    product_type: str,
    vehicle_type: str,
    unit_qty: int
) -> dict:
```
- **Status**: ✅ Active (in PRODUCT_ECOMMERCE_TOOLS)
- **Risk**: Creates inquiry for wrong customer
- **Impact**: Medium

#### ❌ `get_pending_product_inquiry` (Line 753)
```python
@tool
async def get_pending_product_inquiry(
    customer_id: int  # ❌ VULNERABLE
) -> dict:
```
- **Status**: ❌ Inactive (commented out in PRODUCT_ECOMMERCE_TOOLS)
- **Risk**: Low (not currently used)

#### ❌ `get_pending_inquiry` (Line 1138)
```python
@tool
async def get_pending_inquiry(
    customer_id: int  # ❌ VULNERABLE
) -> dict:
```
- **Status**: ❌ Inactive (commented out in PRODUCT_ECOMMERCE_TOOLS)
- **Risk**: Low (not currently used)

---

### 2. **meeting_agent_tools.py**

#### ❌ `get_pending_meeting` (Line 35)
```python
@tool
async def get_pending_meeting(
    customer_id: int  # ❌ VULNERABLE
) -> dict:
```
- **Status**: ✅ Active (in SALES_MEETING_TOOLS)
- **Risk**: Retrieves meeting for wrong customer
- **Impact**: Medium

#### ❌ `book_or_update_meeting_db` (Line 145)
```python
@tool
async def book_or_update_meeting_db(
    customer_id: int,  # ❌ VULNERABLE
    meeting_date: str,
    meeting_time: str,
    ...
) -> dict:
```
- **Status**: ✅ Active (in SALES_MEETING_TOOLS)
- **Risk**: Books meeting for wrong customer
- **Impact**: HIGH (business impact)

---

### 3. **support_agent_tools.py**

#### ❌ `set_human_takeover_flag` (Line 131)
```python
@tool
async def set_human_takeover_flag(
    customer_id: int  # ❌ VULNERABLE
) -> dict:
```
- **Status**: ✅ Active (in SUPPORT_TOOLS)
- **Risk**: Sets takeover flag for wrong customer
- **Impact**: Medium

---

## 📊 Summary Table

| Tool | File | Active | Risk Level | Impact |
|------|------|--------|------------|---------|
| `create_product_inquiry` | product_agent_tools.py | ✅ Yes | Medium | Creates inquiry for wrong customer |
| `get_pending_meeting` | meeting_agent_tools.py | ✅ Yes | Medium | Retrieves meeting for wrong customer |
| `book_or_update_meeting_db` | meeting_agent_tools.py | ✅ Yes | **HIGH** | Books meeting for wrong customer |
| `set_human_takeover_flag` | support_agent_tools.py | ✅ Yes | Medium | Sets flag for wrong customer |

---

## 🔧 Recommended Fixes

### Option 1: Use InjectedState (RECOMMENDED)

Apply the same fix as `update_customer_data`:

```python
@tool
async def create_product_inquiry(
    state: Annotated[dict, InjectedState],  # ← Add this
    product_type: str,
    vehicle_type: str,
    unit_qty: int
) -> dict:
    customer_id = state.get("customer_id")  # ← Get from state

    if not customer_id:
        return {'success': False, 'message': 'No customer_id in state'}

    # ... rest of function
```

### Option 2: Remove Tool Parameter

Keep the tool signature but inject customer_id before calling:

```python
# In a wrapper/middleware layer
async def safe_create_product_inquiry(
    product_type: str,
    vehicle_type: str,
    unit_qty: int
) -> dict:
    # Inject customer_id from context
    from langgraph.prebuilt import InjectedState
    state = InjectedState()
    customer_id = state.get("customer_id")

    return await create_product_inquiry(
        customer_id=customer_id,
        product_type=product_type,
        vehicle_type=vehicle_type,
        unit_qty=unit_qty
    )
```

---

## 📋 Proposed Implementation Order

### Priority 1 (Critical - Business Impact)
1. `book_or_update_meeting_db` - Could book meetings for wrong customers

### Priority 2 (High - Data Integrity)
2. `create_product_inquiry` - Could create inquiries for wrong customers
3. `set_human_takeover_flag` - Could trigger takeover for wrong customers

### Priority 3 (Medium)
4. `get_pending_meeting` - Lower risk (read-only)

---

## 🛡️ Legacy Tools (Not Currently Active)

These tools are in `hana_legacy/` folder and are **not currently used** by the agent:

- `tools/hana_legacy/product_tools.py`:
  - `get_pending_inquiry` (Line 305)
  - `create_product_inquiry` (Line 321)

- `tools/hana_legacy/customer_tools.py`:
  - `update_customer_profile` (Line 96)
  - `get_chat_history` (Line 162)

- `tools/hana_legacy/meeting_tools.py`:
  - `get_pending_meeting` (Line 23)
  - `create_meeting` (Line 40)
  - `book_or_update_meeting` (Line 145)

**Recommendation**: These can be fixed later if needed, or removed if obsolete.

---

## ✅ Already Fixed

- `customer_agent_tools.py`:
  - ✅ `update_customer_data` (Fixed with InjectedState)
  - ✅ `get_customer_profile` (Always used InjectedState)

---

## 📝 Implementation Checklist

### Phase 1: Critical Fixes (Do First)
- [ ] Fix `book_or_update_meeting_db`
- [ ] Fix `create_product_inquiry`
- [ ] Fix `set_human_takeover_flag`
- [ ] Fix `get_pending_meeting`

### Phase 2: Legacy Tools (Optional)
- [ ] Fix or remove legacy tools if still in use

### Phase 3: Testing
- [ ] Test each fixed tool with actual agent
- [ ] Verify customer_id comes from state (check logs)
- [ ] Add regression tests for customer_id validation

---

## 🧪 Testing Procedure

For each fixed tool, verify:

1. **Import test**: `python -c "from ... import tool_name"`

2. **Log verification**:
   ```
   # Before fix:
   TOOL: book_or_update_meeting_db - customer_id: 1

   # After fix:
   TOOL: book_or_update_meeting_db - customer_id: 15 (from state)
   ```

3. **Agent test**: Send test message and verify correct customer is updated

---

## 📊 Risk Assessment

### Before Fixes
- **Probability**: High (LLM has already shown wrong customer_id)
- **Impact**: High (data corruption, privacy leak)
- **Overall Risk**: 🔴 **CRITICAL**

### After Fixes
- **Probability**: Low (customer_id from state, not LLM)
- **Impact**: Low (validation prevents errors)
- **Overall Risk**: 🟢 **MITIGATED**

---

## 🎯 Next Steps

**Do you want me to implement the fixes for the 4 active vulnerable tools?**

I recommend fixing all 4 in one go using Option 1 (InjectedState), which is:
- ✅ Consistent with the fix already applied
- ✅ Most secure
- ✅ Minimal code changes
- ✅ Easy to test

Please confirm if you want me to proceed with these fixes.
