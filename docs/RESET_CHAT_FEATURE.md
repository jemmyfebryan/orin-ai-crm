# Reset Chat Command - Testing Feature

## Overview

Added a `reset_chat` command for testing purposes that allows allowed users to reset their chat session and start fresh.

## Usage

### How to Use

1. **Send message**: `reset_chat` (case-insensitive)
2. **Must be from**: Allowed phone number (in `ALLOWED_NUMBERS`)
3. **Result**: Customer is soft-deleted, chat history is reset

### Example

```
User (WhatsApp): reset_chat
Bot (Freshchat): ✅ Chat reset successful! Customer ID: 15. Starting fresh chat.
```

## What Happens

1. **Webhook receives message**
2. **Allowlist check** ✅ (phone number must be in allowed list)
3. **Command detected**: `message_content.strip().lower() == "reset_chat"`
4. **Customer soft-deleted**:
   - `deleted_at` timestamp set
   - Customer data preserved (not actually deleted)
   - Chat sessions preserved for training
5. **Confirmation sent** via Freshchat API
6. **Processing stops** (doesn't continue to AI agent)

## Implementation Details

### Files Modified

#### 1. `server/routes/admin.py`
- **Added**: `soft_delete_customer_by_phone()` function
- **Purpose**: Reusable function to soft-delete customer by phone number
- **Returns**: dict with `success`, `message`, `customer_id`

#### 2. `server/routes/freshchat.py`
- **Modified**: `process_freshchat_webhook_task()` function
- **Added**: Reset chat command check (after allowlist, before AI processing)
- **Flow**:
  ```python
  if message_content.strip().lower() == "reset_chat":
      # Delete customer
      result = await soft_delete_customer_by_phone(phone_number)
      # Send confirmation
      await send_message_to_freshchat(conversation_id, confirmation_msg)
      return  # Stop processing
  ```

### Security

✅ **Protected**: Only works for allowed phone numbers
✅ **Soft delete**: Data preserved for training
✅ **Confirmation**: User receives feedback message

## Testing

### Test Scenarios

#### Scenario 1: Successful Reset
```
Input: "reset_chat" (from allowed number)
Expected: Customer deleted, confirmation sent
Logs: "Reset chat command detected for phone: +628..."
```

#### Scenario 2: Not in Allowlist
```
Input: "reset_chat" (from non-allowed number)
Expected: No action, returns silently
Logs: "Phone number not in allowlist..."
```

#### Scenario 3: Customer Not Found
```
Input: "reset_chat" (from allowed number, but no customer exists)
Expected: Message sent: "No customer found for phone..."
Logs: "Customer not found for phone: ..."
```

#### Scenario 4: Already Deleted
```
Input: "reset_chat" (customer already deleted)
Expected: Message sent: "Customer already deleted at..."
Logs: "Customer already deleted: 15"
```

## Logs

### Successful Reset
```log
INFO - freshchat.py - Reset chat command detected for phone: +6285850434383
INFO - admin.py - Customer 15 soft-deleted successfully
INFO - freshchat.py - Reset chat completed for +6285850434383: Customer 15 deleted successfully. Chat reset complete.
INFO - freshchat_api.py - Successfully sent message to Freshchat conversation 6b1857f0-d615-4361-8b0b-555d040f9211
```

### Customer Not Found
```log
INFO - freshchat.py - Reset chat command detected for phone: +628123456789
INFO - admin.py - Customer not found for phone: +628123456789
INFO - freshchat.py - Reset chat completed for +628123456789: No customer found for phone: +628123456789
```

## Configuration

### Required Settings

In `.env` or environment:
```bash
# Allowed numbers that can use reset_chat
ALLOWED_NUMBERS=["+628123456789", "+6285850434383"]
```

In `server/config/settings.py`:
```python
self.allowed_numbers = [
    "+628123456789",
    "+6285850434383",
]
```

## API Endpoints

### Existing: `/delete-customer`
- **Method**: POST
- **Auth**: None (or add if needed)
- **Body**: `{ "phone_number": "+628..." }`
- **Purpose**: Admin endpoint for deleting customers
- **Now uses**: `soft_delete_customer_by_phone()` function

### New: Webhook Command
- **Method**: POST (via Freshchat webhook)
- **Trigger**: Message content = "reset_chat"
- **Auth**: Allowlist check
- **Purpose**: Testing feature for allowed users

## Benefits

✅ **Easy testing**: Allowed users can reset their chat anytime
✅ **No admin access needed**: Direct from WhatsApp
✅ **Data preserved**: Soft delete keeps data for training
✅ **Instant feedback**: Confirmation message sent immediately

## Future Enhancements

Possible improvements:
1. Add confirmation dialog ("Are you sure?")
2. Add more commands (debug, status, etc.)
3. Rate limiting (prevent abuse)
4. Command logging/audit trail
5. Add "undo" functionality

## Troubleshooting

### Command Not Working

**Check**:
1. Phone number is in `ALLOWED_NUMBERS`
2. Message is exactly "reset_chat" (case-insensitive)
3. Freshchat webhook is receiving messages
4. No errors in logs

### Confirmation Not Received

**Check**:
1. Freshchat API credentials are valid
2. Conversation ID is correct
3. Network connectivity to Freshchat API
4. Check logs for send_message errors

## Summary

| Feature | Status |
|---------|--------|
| Command "reset_chat" | ✅ Implemented |
| Allowlist protection | ✅ Active |
| Soft delete | ✅ Preserves data |
| Confirmation message | ✅ Sent via Freshchat |
| Reusable function | ✅ `soft_delete_customer_by_phone()` |
| Documentation | ✅ Complete |

**Ready for testing!** 🚀
