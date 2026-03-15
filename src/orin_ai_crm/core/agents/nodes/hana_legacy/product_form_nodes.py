"""
Product Form Node - Collect customer info using form + provide short answer
All logic uses LLM, no rule-based matching (see CLAUDE.md).
"""

import json
import os
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.models.schemas import AgentState, CustomerProfile
from src.orin_ai_crm.core.agents.tools.product_agent_tools import (
    get_all_active_products,
    format_products_for_llm,
)
from src.orin_ai_crm.core.agents.tools.hana_legacy.customer_tools import (
    update_customer_profile
)

logger = get_logger(__name__)
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))


async def node_product_form(state: AgentState):
    """
    Show form with short contextual answer.
    All decisions made by LLM (no rule-based matching).
    """
    logger.info("=" * 50)
    logger.info("ENTER: node_product_form")

    messages = state['messages']
    customer_data = state.get('customer_data', {})
    customer_id = state.get('customer_id')

    logger.info(f"Customer ID: {customer_id}, current_data: {customer_data}")

    # Check if form data is already complete (domicile, purpose, unit_qty)
    has_domicile = customer_data.get("domicile") not in [None, ""]
    has_purpose = customer_data.get("purpose") not in [None, ""]
    has_unit_qty = customer_data.get("unit_qty") not in [None, "", 0]

    if has_domicile and has_purpose and has_unit_qty:
        logger.info("Form data already complete, skipping form. Marking as submitted.")

        # Determine route based on is_b2b flag
        is_b2b = customer_data.get('is_b2b', False)
        next_route = "sales_node" if is_b2b else "ecommerce_node"

        # Generate acknowledgment without showing form
        ack = await generate_form_skip_acknowledgment_with_llm(customer_data, next_route)

        return {
            "messages": [AIMessage(content=ack)],
            "awaiting_form": False,
            "form_submitted": True,
            "customer_id": customer_id,
            "customer_data": customer_data,
            "next_route": next_route,
            "step": "form_completed"
        }

    # Get last user message
    last_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_message = msg.content
            break

    # 1. Generate short answer using LLM with database products
    short_answer = await generate_short_answer_with_llm(last_message, customer_data)

    # 2. Generate form with LLM (contextual to what's already known)
    form_text = await generate_form_with_llm(messages, customer_data)

    # 3. Combine
    response = f"{short_answer}\n\n{form_text}"

    logger.info(f"Form + short answer sent, awaiting_form=True")

    return {
        "messages": [AIMessage(content=response)],
        "awaiting_form": True,
        "form_submitted": False,
        "customer_id": customer_id,
        "customer_data": customer_data
    }


async def generate_short_answer_with_llm(question: str, customer_data: dict) -> str:
    """
    Generate short contextual answer using LLM with database products.
    Source of truth: database products table.
    """
    logger.info(f"generate_short_answer_with_llm called - question: {question[:50]}...")

    # Get all products from database (source of truth)
    result = await get_all_active_products.ainvoke({})
    all_products = result.get('products', [])
    products_context = format_products_for_llm(all_products)

    customer_name = customer_data.get('name', 'Kak')
    vehicle = customer_data.get('vehicle_alias', '')

    prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan.

{products_context}

Customer: {customer_name}
Pertanyaan: "{question}"
Info kendaraan: {vehicle if vehicle else '-'}

Tugas:
1. Berikan jawaban SINGKAT dan membantu (2-3 kalimat saja)
2. Rekomendasikan produk yang SESUAI dari database di atas
3. Jangan terlalu detail (nanti setelah isi form akan lebih lengkap)
4. Gunakan emoji yang sesuai
5. Jangan sebutkan harga detail (cukup range atau sebut "ada beberapa pilihan")
6. Jangan sebutkan link e-commerce (nanti setelah form)

Contoh respons:
"Untuk motor, kakak bisa pakai OBU D atau OBU T (tinggal colok OBD, praktis banget!) 🏍️"

Jawaban:"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])
    answer = response.content.strip()

    logger.info(f"Short answer generated: {answer[:100]}...")
    return answer


async def generate_form_with_llm(messages: list, customer_data: dict) -> str:
    """
    Generate form text, skipping fields we already know.
    LLM decides which fields to ask based on what's missing.
    """
    logger.info(f"generate_form_with_llm called - customer_data: {customer_data}")

    prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.

Customer data yang sudah diketahui: {json.dumps(customer_data, indent=2)}

Buat form untuk mengumpulkan data yang BELUM diketahui.

Fields yang diperlukan:
- name: Nama (skip jika sudah ada)
- domicile: Domisili/kota (untuk pengiriman & penawaran yang tepat)
- purpose: Kebutuhan kendaraan (pribadi, perusahaan, operasional kantor, fleet, delivery, dll)
- unit_qty: Jumlah unit (untuk penawaran yang tepat)

CATATAN PENTING:
- Jangan tanya field yang sudah terisi di customer_data
- Jelaskan bahwa data ini diperlukan untuk penawaran
- Gunakan bahasa ramah tapi tegas
- "Kebutuhan kendaraan" adalah tujuan penggunaan (pribadi/kantor/operasional), bukan jenis kendaraan
- Di akhir, jelaskan bahwa form harus diisi untuk lanjut

Contoh:
"Mohon isi data berikut ini ya kak:
Nama : ...
Domisili : ...
Kebutuhan kendaraan : ...
Jumlah unit : ...
Setelah kakak isi, baru Hana bisa kasih penawaran yang tepat 😊"

Form:"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])
    form = response.content.strip()

    logger.info(f"Form generated: {form[:100]}...")
    return form


async def handle_form_response(state: AgentState):
    """
    Handle customer's form response.
    Uses LLM to parse and determine next route.
    """
    logger.info("=" * 50)
    logger.info("ENTER: handle_form_response")

    messages = state['messages']
    customer_data = state.get('customer_data', {})
    customer_id = state.get('customer_id')

    # Get form response (last message)
    form_response = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            form_response = msg.content
            break

    logger.info(f"Form response: {form_response[:100]}...")

    # Parse with LLM
    parsed_data = await parse_form_response_with_llm(form_response, customer_data)

    logger.info(f"Parsed data: {parsed_data}")

    # Update customer_data (only non-null fields)
    for key, value in parsed_data.items():
        if key not in ["missing_fields", "reasoning"] and value is not None and value != "":
            customer_data[key] = value

    # Save to database (non-mandatory fields only)
    try:
        await update_customer_profile(
            customer_id=customer_id,
            profile=CustomerProfile(
                name=parsed_data.get('name') or customer_data.get('name') or "",
                domicile=parsed_data.get('domicile') or customer_data.get('domicile') or "",
                vehicle_id=customer_data.get('vehicle_id', -1),
                vehicle_alias=customer_data.get('vehicle_alias') or "",
                unit_qty=parsed_data.get('unit_qty') or customer_data.get('unit_qty', 0),
                is_b2b=parsed_data.get('is_company', False)
            )
        )
        logger.info("Customer profile updated")
    except Exception as e:
        logger.error(f"Error updating customer profile: {e}")

    # Check if customer is unsure/hesitant
    is_hesitant = await check_if_customer_hesitant_with_llm(form_response, messages)

    if is_hesitant:
        # Ask what they're unsure about
        logger.info("Customer is hesitant, asking what they're unsure about")
        response = await generate_hesitation_response_with_llm(parsed_data, customer_data)
        return {
            "messages": [AIMessage(content=response)],
            "customer_data": customer_data,
            "awaiting_form": True,  # Still waiting
            "form_submitted": False
        }

    # Determine route with LLM
    route_decision = await determine_route_with_llm(parsed_data, messages)
    route = route_decision.get("route", "ecommerce_node")
    reasoning = route_decision.get("reasoning", "")

    logger.info(f"Route determined: {route}, reasoning: {reasoning}")

    # Generate acknowledgment
    ack = await generate_form_acknowledgment_with_llm(parsed_data, route, reasoning)

    return {
        "messages": [AIMessage(content=ack)],
        "customer_data": customer_data,
        "awaiting_form": False,
        "form_submitted": True,
        "next_route": route,
        "step": "form_completed"
    }


async def parse_form_response_with_llm(form_response: str, customer_data: dict) -> dict:
    """
    Parse customer's form response using LLM.
    Extract whatever fields customer provided (non-mandatory).
    """
    logger.info(f"parse_form_response_with_llm called - response: {form_response[:100]}...")

    prompt = f"""Extract information from this customer response.

Response:
"{form_response}"

Current customer data: {json.dumps(customer_data, indent=2)}

Extract into JSON format (ONLY return valid JSON):
{{
    "name": "Budi" or null,
    "domicile": "Jakarta" or null,
    "purpose": "pribadi/perusahaan/operasional kantor/fleet/delivery/dll" or null,
    "unit_qty": 1 (as number) or null,
    "is_company": true/false,
    "missing_fields": ["field names not provided"],
    "reasoning": "explanation"
}}

Rules:
- Don't make up values
- If customer didn't provide a field, set to null
- Detect if customer is from company (perusahaan/kantor/pt/cv/fleet/armada/operasional)
- purpose adalah tujuan penggunaan (bukan jenis kendaraan!)
- Extract unit_qty as number
- Customer might skip fields - that's OK
- Customer might say "gaptek" or "bingung" - handle gracefully

Return ONLY valid JSON, no other text:"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    try:
        # Try to parse JSON
        result = json.loads(response.content.strip())
        logger.info(f"Form parsed successfully: {result}")
        return result
    except json.JSONDecodeError:
        # Try to extract JSON from response
        content = response.content.strip()
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
            result = json.loads(json_str)
            logger.info(f"Form parsed from code block: {result}")
            return result
        elif "{" in content:
            # Try to find JSON object
            start = content.find("{")
            end = content.rfind("}") + 1
            json_str = content[start:end]
            result = json.loads(json_str)
            logger.info(f"Form parsed from substring: {result}")
            return result
        else:
            logger.error(f"Failed to parse form response: {content}")
            return {
                "missing_fields": ["all"],
                "reasoning": "Could not parse form response"
            }


async def check_if_customer_hesitant_with_llm(form_response: str, messages: list) -> bool:
    """
    Check if customer is hesitant/unsure using LLM.
    """
    logger.info("check_if_customer_hesitant_with_llm called")

    prompt = f"""Analyze if this customer is hesitant or unsure.

Customer response: "{form_response}"

Indicators of hesitation:
- "tunggu", "pikir dulu", "belum yakin", "masih ragu"
- "saya gaptek", "bingung", "nggak ngerti"
- Asking questions instead of providing data
- Saying they need to check with someone else

Return JSON: {{"is_hesitant": true/false, "reasoning": "..."}}"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    try:
        result = json.loads(response.content.strip())
        is_hesitant = result.get("is_hesitant", False)
        logger.info(f"Customer hesitant: {is_hesitant}, reasoning: {result.get('reasoning')}")
        return is_hesitant
    except:
        logger.error("Failed to parse hesitation check")
        return False


async def generate_hesitation_response_with_llm(parsed_data: dict, customer_data: dict) -> str:
    """
    Generate response for hesitant customer.
    Ask what they're unsure about.
    """
    logger.info("generate_hesitation_response_with_llm called")

    prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.

Customer seems hesitant or unsure about proceeding.
Customer data: {json.dumps(customer_data, indent=2)}

Tugas:
1. Acknowledge their hesitation naturally
2. Ask what they're unsure about
3. Offer to explain more about the products
4. Be supportive, not pushy

Example:
"Oke kak, gapapa! Kalau masih ragu, boleh dong cerita apa yang membuat kakak ragu? Hana bisa jelaskan lebih lanjut 😊"

Respons (singkat dan ramah):"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])
    return response.content.strip()


async def determine_route_with_llm(form_data: dict, messages: list) -> dict:
    """
    Determine next route using LLM (ecommerce vs sales).
    No rule-based matching!
    """
    logger.info(f"determine_route_with_llm called - form_data: {form_data}")

    prompt = f"""Determine the best route for this customer.

Customer Data:
{json.dumps(form_data, indent=2)}

Routes:
1. ECOMMERCE - Customer wants to buy directly, small quantity, personal use, no meeting needed
2. SALES - Customer from company, needs meeting, wants consultation, large quantity

Consider:
- Is customer from company? (is_company field)
- Quantity (unit_qty) - but context matters more than numbers
- Purpose (purpose) - what do they need it for?
- Customer's intent from conversation

IMPORTANT:
- Even if company is TRUE, if they want direct purchase → ECOMMERCE
- Even if small quantity, if they want consultation → SALES
- Customer's explicit preference matters most
- Use LLM judgment, not fixed rules

Return JSON:
{{"route": "ecommerce_node" or "sales_node", "reasoning": "explanation"}}"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    try:
        result = json.loads(response.content.strip())
        logger.info(f"Route determined: {result}")
        return result
    except:
        logger.error("Failed to parse route determination, defaulting to ecommerce")
        return {"route": "ecommerce_node", "reasoning": "Default - parsing failed"}


async def generate_form_acknowledgment_with_llm(form_data: dict, route: str, reasoning: str) -> str:
    """
    Generate acknowledgment after form submission.
    """
    logger.info(f"generate_form_acknowledgment_with_llm called - route: {route}")

    customer_name = form_data.get('name') or 'Kak'
    purpose = form_data.get('purpose', 'pribadi')
    unit_qty = form_data.get('unit_qty', 1)

    if route == "sales_node":
        prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.

Customer just filled the form: {json.dumps(form_data)}
Route: SALES (needs meeting with sales team)

Generate acknowledgment:
1. Thank them (use their name)
2. Acknowledge their needs (purpose, quantity)
3. Explain that sales team will contact them
4. Mention what sales team will help with
5. Ask if there's anything they need help with while waiting

Use emoji, be friendly and professional.
Example format:
"Siap kak [Name]! 👍

Terima kasih sudah mengisi data..."

Response:"""

    else:  # ecommerce
        prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.

Customer just filled the form: {json.dumps(form_data)}
Route: ECOMMERCE (direct purchase, send product links)

Generate acknowledgment:
1. Thank them (use their name)
2. Acknowledge what they filled (purpose, quantity)
3. Say you'll provide product recommendations next
4. Keep it brief, don't provide links yet (next node will do that)

Use emoji, be friendly.
Example format:
"Siap kak [Name]! 👍

Makasih sudah isinya. Sekarang Hana kasih rekomendasi produk yang cocok ya..."

Response:"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])
    return response.content.strip()


async def generate_form_skip_acknowledgment_with_llm(customer_data: dict, route: str) -> str:
    """
    Generate acknowledgment when form is skipped (data already complete).
    """
    logger.info(f"generate_form_skip_acknowledgment_with_llm called - route: {route}")

    customer_name = customer_data.get('name') or 'Kak'

    if route == "sales_node":
        prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.

Customer data sudah lengkap: {json.dumps(customer_data)}
Route: SALES (tim sales akan menghubungi)

Generate acknowledgment:
1. Thank them (use their name)
2. Acknowledge that we already have their data
3. Explain that sales team will contact them
4. Be brief and friendly

Use emoji.
Example format:
"Siap kak [Name]! 👍

Data kakak sudah Hana terima ya. Tim sales kami akan segera menghubungi..."

Response:"""

    else:  # ecommerce
        prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.

Customer data sudah lengkap: {json.dumps(customer_data)}
Route: ECOMMERCE (langsung ke rekomendasi produk)

Generate acknowledgment:
1. Thank them (use their name)
2. Acknowledge that we already have their data
3. Say you'll provide product recommendations directly
4. Keep it brief

Use emoji, be friendly.
Example format:
"Siap kak [Name]! 👍

Data kakak sudah lengkap. Sekarang Hana kasih rekomendasi produk yang cocok ya..."

Response:"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])
    return response.content.strip()


def get_last_user_message(messages: list) -> str:
    """Get the last message from user (HumanMessage)"""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""
