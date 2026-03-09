# ORIN AI CRM - Development Guidelines for Claude

## 🚨 CORE PRINCIPLE: LLM-First, No Rule-Based Matching

### ❌ AVOID: Rule-Based Pattern Matching

```python
# BAD: Rule-based matching
if "harga" in message:
    return "HIGH_INTENT"

if "perusahaan" in message or "kantor" in message:
    return "COMPANY"

if qty >= 10:
    return "SALES_ROUTE"

if "motor" in vehicle_type:
    return "OBU_D"
```

**Problems:**
- ❌ Breaks on typos: "hargga", "perusaahan", "m0tor"
- ❌ Misses variations: "berapa", "bisakah", "company", "kendaraan roda dua"
- ❌ Inflexible to context
- ❌ Hard to maintain
- ❌ Cannot handle nuanced language

### ✅ USE: LLM for All User Input Interpretation

```python
# GOOD: LLM-based interpretation
def detect_intent_level(message: str) -> str:
    prompt = f"""Analyze this customer message and determine intent level:

Message: "{message}"

Classify as:
- HIGH_INTENT: Customer wants to buy/ask pricing/needs quick answer/ready to transact
- LOW_INTENT: Customer is browsing/just asking questions/unclear/early stage

Return only: HIGH or LOW"""

    return llm.invoke(prompt).content.strip()
```

**Benefits:**
- ✅ Handles typos naturally
- ✅ Understands context and nuance
- ✅ Flexible to variations
- ✅ Easy to maintain
- ✅ Can provide reasoning

---

## When to Use LLM vs Rules

### ✅ ALWAYS Use LLM For:
1. **Intent classification** - What does the user want?
2. **Sentiment analysis** - How is the user feeling?
3. **Entity extraction** - Name, location, vehicle type, etc.
4. **Company vs personal detection** - Is this from a business?
5. **Route determination** - Where should this conversation go?
6. **Form validation/interpretation** - What did the user provide?
7. **High vs low intent detection** - How urgent/serious is the user?
8. **Product matching** - Which products fit the user's needs?
9. **Any user input interpretation** - If it's from a user, ask LLM first

### ⚠️ Use Rules For:
1. **Technical validation** - Phone number format, email format (regex is OK)
2. **Database queries** - Exact matches by ID, SKU, etc.
3. **System operations** - File I/O, API calls, configuration
4. **Business logic constants** - Feature flags, environment variables
5. **Data transformation** - JSON parsing, type conversions

---

## Decision Checklist

Before writing any rule-based matching, ask yourself:

1. **Can LLM do this better?**
   - If YES → Use LLM
   - If NO → Rules might be OK

2. **Will rules break on typos/variations?**
   - If YES → Use LLM
   - If NO → Rules might be OK

3. **Is this interpreting user input?**
   - If YES → Use LLM
   - If NO → Rules might be OK

4. **Could context change the meaning?**
   - If YES → Use LLM
   - If NO → Rules might be OK

**If any answer is YES to "use LLM" → Use LLM!**

---

## Examples of LLM-First Implementation

### Example 1: Detect if User is from Company

❌ **BAD:**
```python
def is_company_user(message: str) -> bool:
    company_keywords = ["pt", "cv", "perusahaan", "kantor", "company"]
    return any(keyword in message.lower() for keyword in company_keywords)
```

✅ **GOOD:**
```python
async def is_company_user_llm(message: str, context: dict) -> bool:
    prompt = f"""Analyze if this customer is from a company/business.

Message: "{message}"
Context: {context}

Consider:
- Is this a personal purchase or company purchase?
- Even small quantity (5 units) could be for company
- User might not explicitly say "company"

Return JSON: {{"is_company": true/false, "reasoning": "..."}}"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])
    result = json.loads(response.content)
    return result.get("is_company", False)
```

### Example 2: Route Determination

❌ **BAD:**
```python
def determine_route(is_company: bool, unit_qty: int) -> str:
    if is_company or unit_qty >= 10:
        return "sales"
    else:
        return "ecommerce"
```

✅ **GOOD:**
```python
async def determine_route_llm(form_data: dict, conversation: list) -> str:
    prompt = f"""Determine the best route for this customer.

Customer Data: {json.dumps(form_data)}
Conversation: {conversation[-3:]}

Available Routes:
1. ECOMMERCE - Direct purchase, send product links
2. SALES - Need meeting, sales follow-up, large quantity

Consider:
- Is customer from company? (even small qty)
- What's the purpose? (personal, fleet, operational)
- Customer's urgency/intent
- Customer explicitly said no meeting?

Return JSON: {{"route": "ECOMMERCE/SALES", "reasoning": "..."}}"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])
    result = json.loads(response.content)
    return result.get("route", "ecommerce")
```

### Example 3: Form Response Detection

❌ **BAD:**
```python
def is_form_response(message: str) -> bool:
    return "\n" in message and ":" in message
```

✅ **GOOD:**
```python
async def is_form_response_llm(message: str) -> bool:
    prompt = f"""Is this message a form response or a question?

Message: "{message}"

Form response example:
"Jakarta, pribadi, 1 unit"

Question example:
"Elok banget, tapi saya mau tanya dulu"

Return JSON: {{"is_form": true/false, "extracted_data": {{...}}}}"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])
    result = json.loads(response.content)
    return result.get("is_form", False), result.get("extracted_data", {})
```

---

## Common Anti-Patterns to Avoid

### ❌ Pattern 1: Keyword Lists
```python
# Don't do this
HIGH_INTENT_KEYWORDS = ["harga", "beli", "order", "promo"]
if any(kw in message for kw in HIGH_INTENT_KEYWORDS):
    return "HIGH"
```

### ❌ Pattern 2: Fixed Thresholds
```python
# Don't do this
if unit_qty > 10:
    return "SALES"
```

### ❌ Pattern 3: String Contains
```python
# Don't do this
if "motor" in message.lower():
    product = "OBU_D"
```

### ❌ Pattern 4: Exact Matching
```python
# Don't do this
if message == "ya":
    proceed()
```

---

## Database as Source of Truth

### Product Information
✅ **ALWAYS** fetch from database, never hardcode:
- Product names, SKUs
- Features and specifications
- Prices (as flexible strings)
- E-commerce links
- Categories and subcategories

❌ **NEVER** hardcode product info in code or prompts

### Customer Data
✅ **ALWAYS**:
- Fetch latest from database
- Update non-mandatory fields only if provided
- Allow partial data (don't force completion)

❌ **NEVER**:
- Make form fields mandatory
- Block progress if customer skips field
- Assume all data is available

---

## Form Handling Best Practices

### ✅ DO:
1. Use LLM to generate contextual form (skip known fields)
2. Allow customers to skip fields
3. Use LLM to parse partial responses
4. Handle "I'm not sure" gracefully
5. Provide helpful guidance, not demands

### ❌ DON'T:
1. Make all fields required
2. Force customers to fill everything
3. Use validation errors that block progress
4. Show the same form repeatedly
5. Make customers feel interrogated

---

## Dynamic Routing, Not Fixed Paths

### ✅ DO:
1. Let LLM determine route based on intent
2. Allow customers to change their mind
3. Route to ecommerce even if company (if they want direct purchase)
4. Route to sales even if personal (if they request meeting)
5. Consider context, not just data values

### ❌ DON'T:
1. Use fixed rules like "company → sales"
2. Block routes based on data alone
3. Ignore customer's explicit preferences
4. Make routing decisions without LLM analysis

---

## Code Review Checklist

Before committing code, check:

- [ ] Am I using rule-based matching for user input?
- [ ] Should I use LLM instead?
- [ ] Can this break on typos?
- [ ] Is database the source of truth?
- [ ] Are form fields truly optional?
- [ ] Is routing dynamic (LLM-based)?
- [ ] Did I add comments explaining LLM decisions?

---

## Testing Strategy

### Unit Tests
- Test LLM prompts with various inputs
- Test edge cases (typos, variations)
- Test partial form submissions
- Test route changes mid-conversation

### Integration Tests
- Test full conversation flows
- Test database integration
- Test state transitions
- Test error handling

---

## Remember: **We Have GPT-4!**

We're paying for OpenAI API - use it! The LLM is:
- Smarter than rule-based matching
- More flexible to variations
- Better at understanding context
- Able to provide reasoning
- Worth the cost for better UX

**Rule-based matching is false economy.** It saves tokens but creates:
- Poor user experience
- More bugs
- Harder maintenance
- Lost customers

---

## Quick Reference

| Task | Use LLM? | Example |
|------|----------|---------|
| Intent classification | ✅ YES | "What does user want?" |
| Sentiment detection | ✅ YES | "Is user angry?" |
| Entity extraction | ✅ YES | "Extract name, location" |
| Company detection | ✅ YES | "Is this from business?" |
| Route determination | ✅ YES | "Ecommerce or sales?" |
| Form parsing | ✅ YES | "What did user provide?" |
| Product matching | ✅ YES | "Which products fit?" |
| Email validation | ❌ NO | Use regex |
| ID lookups | ❌ NO | Use DB query |
| Feature flags | ❌ NO | Use config |

---

**When in doubt: Use LLM!** 🤖
