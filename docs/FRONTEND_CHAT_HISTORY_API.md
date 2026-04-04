# Chat History API Documentation

## Overview

This document provides comprehensive instructions for implementing the chat history viewer panel in the frontend admin dashboard. The chat history feature allows administrators to view all customer conversations and manage customer interactions effectively.

---

## Base URL

All chat history endpoints are prefixed with `/admin`:
```
http://your-domain.com/admin
```

---

## Authentication

All endpoints require authentication. Include your authentication headers with each request:
```javascript
headers: {
  'Content-Type': 'application/json',
  'Authorization': 'Bearer YOUR_TOKEN'
}
```

---

# Available Endpoints

## 1. Get All Contacts

Retrieve a list of all customers (contacts) with their chat information.

### Endpoint
```
GET /admin/contacts
```

### Description
Returns all customers where `deleted_at IS NULL` (active customers only), sorted by `last_message_time` in descending order (most recent first). This includes customers with no messages (their `last_message_time` will be `null`).

### Response Schema

```typescript
interface ContactItem {
  id: number;                    // Unique customer ID
  phone_number: string;          // WhatsApp phone number
  name: string | null;           // Customer's name (may be null)
  domicile: string | null;       // City/location (may be null)
  vehicle: string | null;        // Vehicle alias or "Vehicle ID: {id}" (may be null)
  unit_qty: number | null;       // Number of units (may be null)
  human_takeover: boolean;       // Whether human takeover is enabled for this customer
  created_at: string | null;     // Customer creation timestamp (ISO 8601 format)
  last_message_time: string | null;  // Last message timestamp (ISO 8601 format, null if no messages)
}

interface GetContactsResponse {
  success: boolean;
  contacts: ContactItem[];
  count: number;                 // Total number of contacts
}
```

### Example Response

```json
{
  "success": true,
  "contacts": [
    {
      "id": 123,
      "phone_number": "628123456789",
      "name": "John Doe",
      "domicile": "Jakarta",
      "vehicle": "CRF",
      "unit_qty": 2,
      "human_takeover": false,
      "created_at": "2026-04-01T10:30:00+07:00",
      "last_message_time": "2026-04-04T15:45:30+07:00"
    },
    {
      "id": 124,
      "phone_number": "628987654321",
      "name": null,
      "domicile": null,
      "vehicle": "Vehicle ID: 5",
      "unit_qty": 1,
      "human_takeover": true,
      "created_at": "2026-04-03T08:00:00+07:00",
      "last_message_time": "2026-04-04T14:20:15+07:00"
    },
    {
      "id": 125,
      "phone_number": "628555555555",
      "name": "New Customer",
      "domicile": "Bandung",
      "vehicle": null,
      "unit_qty": null,
      "human_takeover": false,
      "created_at": "2026-04-04T16:00:00+07:00",
      "last_message_time": null
    }
  ],
  "count": 3
}
```

### Frontend Implementation Example

```javascript
async function getContacts() {
  try {
    const response = await fetch('/admin/contacts', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer YOUR_TOKEN'
      }
    });

    const data = await response.json();

    if (!data.success) {
      throw new Error('Failed to fetch contacts');
    }

    return data.contacts;
  } catch (error) {
    console.error('Error fetching contacts:', error);
    throw error;
  }
}
```

### TypeScript Implementation

```typescript
interface ContactItem {
  id: number;
  phone_number: string;
  name: string | null;
  domicile: string | null;
  vehicle: string | null;
  unit_qty: number | null;
  human_takeover: boolean;
  created_at: string | null;
  last_message_time: string | null;
}

interface GetContactsResponse {
  success: boolean;
  contacts: ContactItem[];
  count: number;
}

async function getContacts(): Promise<ContactItem[]> {
  const response = await fetch('/admin/contacts', {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  });

  const data: GetContactsResponse = await response.json();

  if (!data.success) {
    throw new Error('Failed to fetch contacts');
  }

  return data.contacts;
}
```

---

## 2. Get Chat History for a Contact

Retrieve all chat messages for a specific customer.

### Endpoint
```
GET /admin/contacts/{customer_id}/chat-history
```

### Path Parameters
- `customer_id` (integer, required): The unique ID of the customer

### Description
Returns all chat messages for the specified customer, sorted by `timestamp` in ascending order (oldest to newest). Messages with role `ai` are mapped to `assistant` for consistency.

### Error Responses
- `404 Not Found`: Customer with the specified ID doesn't exist or has been deleted

### Response Schema

```typescript
interface ChatMessageItem {
  role: 'user' | 'assistant';     // Message sender role
  content: string;                // Message content/text
  timestamp: string;              // Message timestamp (ISO 8601 format)
}

interface GetChatHistoryResponse {
  success: boolean;
  customer_id: number;            // The customer ID for this chat history
  messages: ChatMessageItem[];
  count: number;                  // Total number of messages
}
```

### Example Response

```json
{
  "success": true,
  "customer_id": 123,
  "messages": [
    {
      "role": "user",
      "content": "Hello, I'm interested in GPS trackers",
      "timestamp": "2026-04-04T10:30:00+07:00"
    },
    {
      "role": "assistant",
      "content": "Hi! I'd be happy to help you with GPS tracker options. What type of vehicle do you have?",
      "timestamp": "2026-04-04T10:30:05+07:00"
    },
    {
      "role": "user",
      "content": "I have a Honda CRF",
      "timestamp": "2026-04-04T10:31:00+07:00"
    },
    {
      "role": "assistant",
      "content": "Great! For your Honda CRF, I recommend our OBU M model. It's perfect for electric motorcycles...",
      "timestamp": "2026-04-04T10:31:05+07:00"
    }
  ],
  "count": 4
}
```

### Frontend Implementation Example

```javascript
async function getChatHistory(customerId) {
  try {
    const response = await fetch(`/admin/contacts/${customerId}/chat-history`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer YOUR_TOKEN'
      }
    });

    if (response.status === 404) {
      throw new Error('Customer not found');
    }

    const data = await response.json();

    if (!data.success) {
      throw new Error('Failed to fetch chat history');
    }

    return data.messages;
  } catch (error) {
    console.error('Error fetching chat history:', error);
    throw error;
  }
}
```

### TypeScript Implementation

```typescript
interface ChatMessageItem {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

interface GetChatHistoryResponse {
  success: boolean;
  customer_id: number;
  messages: ChatMessageItem[];
  count: number;
}

async function getChatHistory(customerId: number): Promise<ChatMessageItem[]> {
  const response = await fetch(`/admin/contacts/${customerId}/chat-history`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  });

  if (response.status === 404) {
    throw new Error('Customer not found');
  }

  const data: GetChatHistoryResponse = await response.json();

  if (!data.success) {
    throw new Error('Failed to fetch chat history');
  }

  return data.messages;
}
```

---

## 3. Toggle Human Takeover

Enable or disable human takeover mode for a specific customer. When enabled, AI will not process messages and will route them directly to human agents.

### Endpoint
```
PUT /admin/contacts/{customer_id}/human-takeover
```

### Path Parameters
- `customer_id` (integer, required): The unique ID of the customer

### Description
Toggles the `human_takeover` flag for the specified customer. When `human_takeover` is `true`, the AI system will bypass automated processing and route messages directly to human agents. This is useful for complex customer issues that require human intervention.

The endpoint toggles the current state:
- If currently `false` → changes to `true`
- If currently `true` → changes to `false`

### Response Schema

```typescript
interface ToggleHumanTakeoverResponse {
  success: boolean;
  message: string;              // Human-readable message
  customer_id: number;          // The customer ID
  human_takeover: boolean;      // The new state after toggle
}
```

### Example Response

**When enabling human takeover:**
```json
{
  "success": true,
  "message": "Human takeover enabled for customer 123",
  "customer_id": 123,
  "human_takeover": true
}
```

**When disabling human takeover:**
```json
{
  "success": true,
  "message": "Human takeover disabled for customer 123",
  "customer_id": 123,
  "human_takeover": false
}
```

### Error Responses
- `404 Not Found`: Customer with the specified ID doesn't exist or has been deleted

### Frontend Implementation Example

```javascript
async function toggleHumanTakeover(customerId) {
  try {
    const response = await fetch(`/admin/contacts/${customerId}/human-takeover`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer YOUR_TOKEN'
      }
    });

    if (response.status === 404) {
      throw new Error('Customer not found');
    }

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.message || 'Failed to toggle human takeover');
    }

    // Update local state with new status
    return data;
  } catch (error) {
    console.error('Error toggling human takeover:', error);
    throw error;
  }
}
```

### TypeScript Implementation

```typescript
interface ToggleHumanTakeoverResponse {
  success: boolean;
  message: string;
  customer_id: number;
  human_takeover: boolean;
}

async function toggleHumanTakeover(customerId: number): Promise<ToggleHumanTakeoverResponse> {
  const response = await fetch(`/admin/contacts/${customerId}/human-takeover`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  });

  if (response.status === 404) {
    throw new Error('Customer not found');
  }

  const data: ToggleHumanTakeoverResponse = await response.json();

  if (!data.success) {
    throw new Error(data.message || 'Failed to toggle human takeover');
  }

  return data;
}
```

### UI Component Integration

Add a toggle switch button in the contact list item or chat header:

```typescript
const [isToggling, setIsToggling] = useState(false);

const handleToggleHumanTakeover = async (customerId: number, currentState: boolean) => {
  setIsToggling(true);
  try {
    const result = await toggleHumanTakeover(customerId);

    // Show success notification
    showNotification(result.message, 'success');

    // Refresh contact list to get updated state
    await loadContacts();

    // Or update local state directly for better UX
    setContacts(prev => prev.map(c =>
      c.id === customerId
        ? { ...c, human_takeover: result.human_takeover }
        : c
    ));
  } catch (error) {
    showNotification('Failed to toggle human takeover', 'error');
  } finally {
    setIsToggling(false);
  }
};
```

### Toggle Button Component

```typescript
interface HumanTakeoverToggleProps {
  customerId: number;
  is_enabled: boolean;
  onToggle: (customerId: number, newState: boolean) => void;
  disabled?: boolean;
}

const HumanTakeoverToggle: React.FC<HumanTakeoverToggleProps> = ({
  customerId,
  is_enabled,
  onToggle,
  disabled = false
}) => {
  const [isToggling, setIsToggling] = useState(false);

  const handleToggle = async () => {
    setIsToggling(true);
    try {
      const result = await toggleHumanTakeover(customerId);
      onToggle(customerId, result.human_takeover);
    } catch (error) {
      console.error('Toggle failed:', error);
    } finally {
      setIsToggling(false);
    }
  };

  return (
    <button
      onClick={handleToggle}
      disabled={disabled || isToggling}
      className={`human-takeover-toggle ${is_enabled ? 'enabled' : 'disabled'}`}
      title={is_enabled ? 'Disable human takeover' : 'Enable human takeover'}
    >
      {isToggling ? (
        <span className="spinner"></span>
      ) : is_enabled ? (
        <>
          <span className="icon">👤</span>
          <span>Human Mode ON</span>
        </>
      ) : (
        <>
          <span className="icon">🤖</span>
          <span>AI Mode</span>
        </>
      )}
    </button>
  );
};
```

### CSS Styling for Toggle Button

```css
.human-takeover-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border: 2px solid #e0e0e0;
  border-radius: 20px;
  background-color: white;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 14px;
  font-weight: 500;
}

.human-takeover-toggle:hover:not(:disabled) {
  transform: scale(1.05);
}

.human-takeover-toggle:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.human-takeover-toggle.enabled {
  background-color: #fff3e0;
  border-color: #ff9800;
  color: #e65100;
}

.human-takeover-toggle.disabled {
  background-color: #e3f2fd;
  border-color: #2196f3;
  color: #1565c0;
}

.human-takeover-toggle .icon {
  font-size: 16px;
}

.human-takeover-toggle .spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
```

---

# UI Component Implementation Guide

## Complete Chat History Viewer Component

### React Implementation

```typescript
import React, { useState, useEffect } from 'react';

interface ContactItem {
  id: number;
  phone_number: string;
  name: string | null;
  domicile: string | null;
  vehicle: string | null;
  unit_qty: number | null;
  human_takeover: boolean;
  created_at: string | null;
  last_message_time: string | null;
}

interface ChatMessageItem {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

const ChatHistoryViewer: React.FC = () => {
  const [contacts, setContacts] = useState<ContactItem[]>([]);
  const [selectedContact, setSelectedContact] = useState<ContactItem | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [messagesLoading, setMessagesLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Load contacts on component mount
  useEffect(() => {
    loadContacts();
  }, []);

  // Load messages when contact is selected
  useEffect(() => {
    if (selectedContact) {
      loadChatHistory(selectedContact.id);
    } else {
      setMessages([]);
    }
  }, [selectedContact]);

  const loadContacts = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetch('/admin/contacts', {
        headers: {
          'Authorization': 'Bearer YOUR_TOKEN'
        }
      }).then(res => res.json());

      if (data.success) {
        setContacts(data.contacts);
      } else {
        setError('Failed to load contacts');
      }
    } catch (err) {
      setError('Error loading contacts');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadChatHistory = async (customerId: number) => {
    setMessagesLoading(true);
    setError(null);
    try {
      const response = await fetch(`/admin/contacts/${customerId}/chat-history`, {
        headers: {
          'Authorization': 'Bearer YOUR_TOKEN'
        }
      });

      if (response.status === 404) {
        setError('Customer not found');
        return;
      }

      const data = await response.json();

      if (data.success) {
        setMessages(data.messages);
      } else {
        setError('Failed to load chat history');
      }
    } catch (err) {
      setError('Error loading chat history');
      console.error(err);
    } finally {
      setMessagesLoading(false);
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'No messages yet';
    return new Date(dateString).toLocaleString();
  };

  const formatMessageTime = (dateString: string) => {
    return new Date(dateString).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const handleToggleHumanTakeover = async (customerId: number) => {
    try {
      const response = await fetch(`/admin/contacts/${customerId}/human-takeover`, {
        method: 'PUT',
        headers: {
          'Authorization': 'Bearer YOUR_TOKEN'
        }
      });

      if (response.status === 404) {
        setError('Customer not found');
        return;
      }

      const data = await response.json();

      if (data.success) {
        // Update local state
        setContacts(prev => prev.map(c =>
          c.id === customerId
            ? { ...c, human_takeover: data.human_takeover }
            : c
        ));

        // Update selected contact if it's the same one
        if (selectedContact?.id === customerId) {
          setSelectedContact(prev => prev ? { ...prev, human_takeover: data.human_takeover } : null);
        }
      } else {
        setError('Failed to toggle human takeover');
      }
    } catch (err) {
      setError('Error toggling human takeover');
      console.error(err);
    }
  };

  return (
    <div className="chat-history-viewer">
      <h1>Chat History</h1>

      {error && (
        <div className="error-message">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      <div className="chat-container">
        {/* Contacts Sidebar */}
        <div className="contacts-sidebar">
          <h2>Contacts ({contacts.length})</h2>

          {loading ? (
            <div className="loading">Loading contacts...</div>
          ) : (
            <div className="contacts-list">
              {contacts.map(contact => (
                <div
                  key={contact.id}
                  className={`contact-item ${selectedContact?.id === contact.id ? 'active' : ''}`}
                  onClick={() => setSelectedContact(contact)}
                >
                  <div className="contact-name">
                    {contact.name || contact.phone_number}
                  </div>
                  <div className="contact-details">
                    {contact.vehicle && <span className="vehicle">{contact.vehicle}</span>}
                    {contact.unit_qty !== null && <span className="unit-qty">{contact.unit_qty} unit(s)</span>}
                  </div>
                  <div className="last-message">
                    {formatDate(contact.last_message_time)}
                  </div>
                  <button
                    className={`human-takeover-btn ${contact.human_takeover ? 'enabled' : ''}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleToggleHumanTakeover(contact.id);
                    }}
                    title={contact.human_takeover ? 'Disable human takeover' : 'Enable human takeover'}
                  >
                    {contact.human_takeover ? '👤 Human' : '🤖 AI'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Chat Messages Area */}
        <div className="chat-messages">
          {selectedContact ? (
            <>
              <div className="chat-header">
                <div className="chat-header-info">
                  <h3>{selectedContact.name || selectedContact.phone_number}</h3>
                  <div className="contact-info">
                    {selectedContact.domicile && <span>📍 {selectedContact.domicile}</span>}
                    {selectedContact.vehicle && <span>🚗 {selectedContact.vehicle}</span>}
                    {selectedContact.unit_qty !== null && <span>📦 {selectedContact.unit_qty} unit(s)</span>}
                  </div>
                </div>
                <button
                  className={`human-takeover-toggle ${selectedContact.human_takeover ? 'enabled' : 'disabled'}`}
                  onClick={() => handleToggleHumanTakeover(selectedContact.id)}
                  title={selectedContact.human_takeover ? 'Switch to AI mode' : 'Switch to human mode'}
                >
                  {selectedContact.human_takeover ? (
                    <>👤 Human Mode</>
                  ) : (
                    <>🤖 AI Mode</>
                  )}
                </button>
              </div>

              {messagesLoading ? (
                <div className="loading">Loading messages...</div>
              ) : messages.length === 0 ? (
                <div className="no-messages">No messages yet</div>
              ) : (
                <div className="messages-list">
                  {messages.map((message, index) => (
                    <div
                      key={index}
                      className={`message ${message.role}`}
                    >
                      <div className="message-content">
                        {message.content}
                      </div>
                      <div className="message-time">
                        {formatMessageTime(message.timestamp)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="select-contact">
              Select a contact to view chat history
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatHistoryViewer;
```

### CSS Styling

```css
.chat-history-viewer {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 20px;
}

.chat-container {
  display: flex;
  flex: 1;
  gap: 20px;
  margin-top: 20px;
}

/* Contacts Sidebar */
.contacts-sidebar {
  width: 350px;
  border-right: 1px solid #e0e0e0;
  overflow-y: auto;
}

.contacts-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.contact-item {
  padding: 15px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.contact-item:hover {
  background-color: #f5f5f5;
}

.contact-item.active {
  background-color: #e3f2fd;
  border-color: #2196f3;
}

.contact-name {
  font-weight: 600;
  margin-bottom: 5px;
}

.contact-details {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: #666;
  margin-bottom: 5px;
}

.vehicle {
  background-color: #f0f0f0;
  padding: 2px 8px;
  border-radius: 4px;
}

.last-message {
  font-size: 11px;
  color: #999;
}

/* Human Takeover Toggle Button (in contact list) */
.human-takeover-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  padding: 6px 12px;
  border: 2px solid #e0e0e0;
  border-radius: 16px;
  background-color: white;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.2s;
  z-index: 1;
}

.human-takeover-btn:hover {
  transform: scale(1.05);
}

.human-takeover-btn.enabled {
  background-color: #fff3e0;
  border-color: #ff9800;
  color: #e65100;
}

.human-takeover-btn:not(.enabled) {
  background-color: #e3f2fd;
  border-color: #2196f3;
  color: #1565c0;
}

/* Position contact-item relative to support absolute positioning */
.contact-item {
  position: relative;
}

/* Chat Messages Area */
.chat-messages {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  padding: 15px;
  border-bottom: 1px solid #e0e0e0;
  background-color: #f9f9f9;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 15px;
}

.chat-header-info {
  flex: 1;
}

.chat-header h3 {
  margin: 0 0 10px 0;
}

.contact-info {
  display: flex;
  gap: 15px;
  font-size: 14px;
  color: #666;
}

/* Human Takeover Toggle Button (in chat header) */
.human-takeover-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border: 2px solid #e0e0e0;
  border-radius: 24px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  white-space: nowrap;
}

.human-takeover-toggle:hover {
  transform: scale(1.05);
}

.human-takeover-toggle.enabled {
  background-color: #fff3e0;
  border-color: #ff9800;
  color: #e65100;
}

.human-takeover-toggle.disabled {
  background-color: #e3f2fd;
  border-color: #2196f3;
  color: #1565c0;
}

.messages-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.message {
  display: flex;
  flex-direction: column;
  max-width: 70%;
}

.message.user {
  align-self: flex-end;
}

.message.assistant {
  align-self: flex-start;
}

.message-content {
  padding: 12px 16px;
  border-radius: 12px;
  word-wrap: break-word;
}

.message.user .message-content {
  background-color: #2196f3;
  color: white;
}

.message.assistant .message-content {
  background-color: #f0f0f0;
  color: #333;
}

.message-time {
  font-size: 11px;
  color: #999;
  margin-top: 5px;
  align-self: flex-end;
}

/* Loading and Empty States */
.loading, .no-messages, .select-contact {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
  font-style: italic;
}

/* Error Message */
.error-message {
  background-color: #ffebee;
  color: #c62828;
  padding: 15px;
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.error-message button {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #c62828;
}
```

---

# Best Practices

## 1. Error Handling

Always implement proper error handling for both endpoints:

```javascript
async function safeGetContacts() {
  try {
    const response = await fetch('/admin/contacts', {
      headers: { 'Authorization': 'Bearer YOUR_TOKEN' }
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    if (!data.success) {
      throw new Error('API returned unsuccessful response');
    }

    return data.contacts;
  } catch (error) {
    // Log error for debugging
    console.error('Failed to fetch contacts:', error);

    // Show user-friendly error message
    showNotification('Unable to load contacts. Please try again.', 'error');

    // Return empty array as fallback
    return [];
  }
}
```

## 2. Loading States

Show loading indicators during data fetching:

```javascript
const [isLoading, setIsLoading] = useState(false);

const handleRefresh = async () => {
  setIsLoading(true);
  try {
    await loadContacts();
  } finally {
    setIsLoading(false);
  }
};
```

## 3. Null Handling

Handle nullable fields gracefully:

```javascript
const getDisplayName = (contact: ContactItem): string => {
  return contact.name || contact.phone_number || 'Unknown';
};

const getVehicleDisplay = (contact: ContactItem): string => {
  if (!contact.vehicle) return 'N/A';
  return contact.vehicle;
};

const getLastMessageTime = (contact: ContactItem): string => {
  if (!contact.last_message_time) return 'No messages';
  const date = new Date(contact.last_message_time);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
};
```

## 4. Auto-Refresh

Implement auto-refresh for real-time updates:

```javascript
useEffect(() => {
  loadContacts();

  // Refresh every 30 seconds
  const interval = setInterval(() => {
    loadContacts();
  }, 30000);

  return () => clearInterval(interval);
}, []);
```

## 5. Search and Filter

Add search functionality for better UX:

```javascript
const [searchTerm, setSearchTerm] = useState('');

const filteredContacts = contacts.filter(contact =>
  (contact.name?.toLowerCase() || '').includes(searchTerm.toLowerCase()) ||
  contact.phone_number.includes(searchTerm) ||
  (contact.domicile?.toLowerCase() || '').includes(searchTerm.toLowerCase())
);

// In JSX
<input
  type="text"
  placeholder="Search contacts..."
  value={searchTerm}
  onChange={(e) => setSearchTerm(e.target.value)}
/>
```

## 6. Pagination

For large datasets, implement pagination:

```javascript
const [page, setPage] = useState(1);
const pageSize = 50;

const paginatedContacts = filteredContacts.slice(
  (page - 1) * pageSize,
  page * pageSize
);
```

---

# Data Flow

### 1. Initial Load
```
Component Mount → GET /admin/contacts → Display Contact List
```

### 2. Select Contact
```
User Clicks Contact → GET /admin/contacts/{id}/chat-history → Display Messages
```

### 3. Error Handling Flow
```
API Error → Catch Exception → Log Error → Show User Message → Display Fallback UI
```

---

# Common Integration Patterns

## Pattern 1: Master-Detail View

Left sidebar shows contact list, right panel shows chat history (as shown in the complete example above).

## Pattern 2: Modal/Dialog

Click contact → Open modal with chat history:

```javascript
const [isModalOpen, setIsModalOpen] = useState(false);

<ContactModal
  isOpen={isModalOpen}
  contact={selectedContact}
  messages={messages}
  onClose={() => setIsModalOpen(false)}
/>
```

## Pattern 3: Separate Pages

Contact list page → Click "View Chat" → Navigate to chat history page:

```javascript
const handleViewChat = (contactId: number) => {
  navigate(`/admin/chat-history/${contactId}`);
};
```

---

# Testing Checklist

- [ ] Successfully loads and displays contacts list
- [ ] Handles null values (name, vehicle, domicile, last_message_time)
- [ ] Displays loading states during API calls
- [ ] Shows appropriate error messages
- [ ] Successfully loads chat history when contact is selected
- [ ] Handles 404 error for non-existent customer
- [ ] Messages are displayed in correct order (oldest to newest)
- [ ] User and assistant messages are visually distinct
- [ ] Timestamps are formatted correctly
- [ ] Contact selection highlights active contact
- [ ] Auto-refresh works without performance issues
- [ ] Search/filter functionality works correctly

---

# Performance Considerations

## 1. Lazy Loading Messages

For customers with many messages, implement virtual scrolling:

```javascript
import { FixedSizeList } from 'react-window';

<FixedSizeList
  height={600}
  itemCount={messages.length}
  itemSize={100}
  width="100%"
>
  {({ index, style }) => (
    <div style={style}>
      <MessageBubble message={messages[index]} />
    </div>
  )}
</FixedSizeList>
```

## 2. Debounce Search

Debounce search input to reduce API calls:

```javascript
import { useDebouncedCallback } from 'use-debounce';

const debouncedSearch = useDebouncedCallback(
  (value) => setSearchTerm(value),
  300
);
```

## 3. Memoization

Use React.memo for performance:

```javascript
const ContactItem = React.memo(({ contact, onSelect, isActive }) => {
  // Component implementation
});
```

---

# Troubleshooting

### Issue: Contacts not loading
- Check authentication token is valid
- Verify network connection
- Check browser console for CORS errors
- Verify backend server is running

### Issue: Messages not loading
- Verify customer ID is correct
- Check if customer exists (404 error)
- Verify backend has chat session data

### Issue: Timestamps showing incorrectly
- Ensure timezone handling (server returns +07:00 for WIB)
- Use proper Date parsing: `new Date(timestamp)`

### Issue: Performance with many contacts
- Implement pagination or virtual scrolling
- Add search/filter functionality
- Consider lazy loading

---

# Support

For issues or questions:
1. Check browser console for error messages
2. Verify backend endpoints are accessible
3. Review network tab in DevTools for API responses
4. Contact backend development team

---

# Changelog

## Version 1.0.0 (2026-04-04)
- Initial implementation
- GET /admin/contacts endpoint
- GET /admin/contacts/{customer_id}/chat-history endpoint
- Full TypeScript support
- React implementation example
