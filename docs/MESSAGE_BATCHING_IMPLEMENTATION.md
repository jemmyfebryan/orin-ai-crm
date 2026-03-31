# Message Batching Implementation

## Overview
Implemented a message batching system for Freshchat webhooks to prevent multiple rapid messages from triggering separate AI processing workflows.

## Problem Solved
Previously, when a customer sent multiple messages in quick succession (e.g., "Hi", "Saya ingin bertanya...", "Produk apa ya"), each message would:
1. Trigger a separate webhook
2. Create an independent AI processing task
3. Send separate AI responses for each message

This was inefficient and resulted in too many messages being sent to the customer.

## Solution
Messages are now batched by conversation_id and processed together as a single request.

## Key Features

### 1. Dynamic Batching Window
- No hardcoded 5-second timer
- Batching window is "until AI processing completes"
- If new message arrives while AI is processing, cancel the task and restart with accumulated messages

### 2. Buffer Limits (Anti-Spam Protection)
- **Maximum 5 messages** per batch
- **Maximum 2000 characters** per batch
- Whichever limit is reached first
- 6th message onwards: saved to DB but not processed (Option A)

### 3. Message Storage
- Individual messages saved to DB **immediately** when webhook arrives
- Concatenated message used for AI processing only (NOT saved to DB)
- Preserves actual message timeline in database

### 4. Message Sending Order
- PDFs → Images → Text bubbles

## Implementation Details

### Files Created/Modified

#### 1. `src/orin_ai_crm/server/services/message_batcher.py` (NEW)
**Purpose**: Core message batching logic

**Key Components**:
- `pending_tasks`: dict[conversation_id -> asyncio.Task] - tracks AI processing tasks
- `message_buffers`: dict[conversation_id -> deque[str]] - accumulates messages
- `processing_locks`: dict[conversation_id -> asyncio.Lock] - prevents race conditions

**Functions**:
- `queue_or_batch_webhook()`: Called by webhook endpoint
  - Adds message to buffer (checks limits)
  - Cancels existing AI task if running
  - Starts new AI processing task
- `process_message_batch()`: Called after batching completes
  - Concatenates accumulated messages
  - Calls AI processor with skip_db_save=True
- `_process_with_lock()`: Thread-safe wrapper
  - Acquires lock before processing
  - Cleans up resources after completion

**Configuration**:
```python
MAX_BUFFER_SIZE = 5  # max messages per batch
MAX_CHAR_COUNT = 2000  # max characters per batch
```

#### 2. `src/orin_ai_crm/server/routes/freshchat.py` (MODIFIED)
**Changes**:
1. Added imports:
   - `queue_or_batch_webhook` from message_batcher
   - `save_message_to_db` from db_tools
   - `MAX_BUFFER_SIZE`, `MAX_CHAR_COUNT` constants

2. Modified `process_freshchat_webhook_task()`:
   - Added `skip_db_save: bool = False` parameter
   - Passes `skip_db_save` as `skip_user_save` to agent task

3. Modified `process_freshchat_agent_task()`:
   - Added `skip_user_save: bool = False` parameter
   - Passes `skip_user_save` to `process_chat_request()`

4. Modified `/freshchat-webhook` endpoint:
   - Fetches user details immediately (for allowlist and DB save)
   - Performs allowlist check
   - Gets/creates customer
   - **Saves individual message to DB immediately**
   - Calls `queue_or_batch_webhook()` instead of `background_tasks.add_task()`
   - Returns success response immediately

#### 3. `src/orin_ai_crm/server/services/chat_processor.py` (MODIFIED)
**Changes**:
1. Modified `process_chat_request()`:
   - Added `skip_user_save: bool = False` parameter
   - Conditional check before saving user message:
     ```python
     if not skip_user_save:
         await save_message_to_db(customer_id, "user", message)
     ```

## Flow Example

### Scenario: Customer sends 3 messages rapidly

```
t=0s: Webhook "Hi" arrives
  → Save to DB (row 1: "Hi")
  → buffer[conv1] = ["Hi"]
  → Start AI task with "Hi"

t=3s: Webhook "Saya ingin bertanya..." arrives (AI still processing)
  → Save to DB (row 2: "Saya ingin...")
  → Cancel AI task for conv1
  → buffer[conv1] = ["Hi", "Saya ingin..."]
  → Restart AI task with "Hi\n\nSaya ingin..."

t=7s: Webhook "Produk apa ya" arrives (AI still processing)
  → Save to DB (row 3: "Produk apa ya")
  → Cancel AI task for conv1
  → buffer[conv1] = ["Hi", "Saya ingin...", "Produk apa ya"]
  → Restart AI task with "Hi\n\nSaya ingin...\n\nProduk apa ya"

t=12s: AI finishes processing (no new messages for 5 seconds)
  → Send single AI response
  → Save AI response to DB
  → Clear buffer[conv1]
```

### Scenario: Anti-spam protection (buffer overflow)

```
t=0s: "Message 1" → buffer=[1], save to DB, start AI
t=1s: "Message 2" → buffer=[1,2], cancel, restart AI
t=2s: "Message 3" → buffer=[1,2,3], cancel, restart AI
t=3s: "Message 4" → buffer=[1,2,3,4], cancel, restart AI
t=4s: "Message 5" → buffer=[1,2,3,4,5], cancel, restart AI
t=5s: "Message 6" → save to DB, but BUFFER FULL (5/5), IGNORED
t=8s: AI finishes with messages 1-5 concatenated
```

## Key Design Decisions

### 1. Use conversation_id as batching key
- Different conversations from same user batch independently
- Each chat thread has its own buffer and processing state

### 2. No timer-based batching
- Batching window is "until AI finishes"
- More responsive: starts processing immediately, cancels if new message arrives
- Better UX: customer sees faster responses

### 3. Individual messages saved immediately
- Preserves actual message timeline in database
- Individual messages saved before batching (webhook endpoint)
- Concatenated message NOT saved (only for AI processing)

### 4. Thread safety
- One asyncio.Lock per conversation_id
- Prevents race conditions when multiple webhooks arrive simultaneously

### 5. Memory cleanup
- Buffer, task, and lock cleared after AI processing completes
- No memory leaks from abandoned conversations

## Testing Checklist

- [ ] Single message: saves to DB, processes normally
- [ ] Multiple messages within processing window: batched together
- [ ] Messages arriving after processing completes: separate batch
- [ ] Buffer limit (5 messages): 6th message saved but ignored
- [ ] Character limit (2000 chars): long message ignored
- [ ] Multiple customers: each has independent buffer
- [ ] Race condition: 2 webhooks arrive simultaneously
- [ ] Reset chat command: still works with batching
- [ ] PDF/Images: sent in correct order (PDFs → Images → Text)

## Monitoring

### Logs to Watch
```
# Message added to buffer
"Added message to buffer for conversation {id}: {n}/{MAX_BUFFER_SIZE} messages"

# Message ignored (buffer full)
"Message ignored for conversation {id}: buffer has {n}/{MAX_BUFFER_SIZE} messages"

# AI task cancelled
"Cancelling previous AI task for conversation {id}"

# Batch processing started
"Processing batched messages for conversation {id}: {n} messages, {chars} characters"

# Resources cleaned up
"Cleaned up resources for conversation {id}"
```

### Metrics to Track
- Average batch size (messages per batch)
- AI task cancellation rate
- Buffer overflow rate (messages ignored)
- Processing time per batch

## Future Enhancements

1. **Configurable limits**: Make MAX_BUFFER_SIZE and MAX_CHAR_COUNT environment variables
2. **Priority queue**: Give priority to certain message types
3. **Batch timeout**: Add max wait time (e.g., 30s) to prevent indefinite buffering
4. **Metrics**: Export Prometheus metrics for monitoring
