"""
Agentic Tools for Hana AI - Granular Tool-Calling Architecture

This file contains many small, focused tools that the LLM can compose together
to handle complex customer interactions. Each tool does ONE thing well.

IMPORTANT: The LLM CAN and SHOULD call MULTIPLE tools in parallel to handle
multi-intent messages. This is the power of the agentic approach!

Tool Categories:
1. CUSTOMER MANAGEMENT (3 tools)
2. PROFILING (7 tools)
3. SALES & MEETING (7 tools)
4. PRODUCT & E-COMMERCE (8 tools)
5. SUPPORT & COMPLAINTS (3 tools)
6. GREETING & CONVERSATION (2 tools)

Total: 30+ granular tools
"""

import os
import json
from typing import Optional
from datetime import timedelta, timezone
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.schemas import MeetingInfo
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer, LeadRouting, CustomerMeeting, Product, ProductInquiry
from sqlalchemy import select

# Import product tools function with alias to avoid naming conflict with our tool
from src.orin_ai_crm.core.agents.tools.product_tools import (
    get_all_active_products as get_all_active_products_from_db,
    format_products_for_llm as format_products_for_llm_impl
)

logger = get_logger(__name__)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))

HANA_PERSONA = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif.
Jangan terlalu kaku, gunakan bahasa natural seperti chat WhatsApp asli.

ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak)."""


# ============================================================================
# CATEGORY 1: CUSTOMER MANAGEMENT TOOLS (3 tools)
# ============================================================================

@tool
async def get_or_create_customer(
    phone_number: Optional[str] = None,
    lid_number: Optional[str] = None,
    contact_name: Optional[str] = None
) -> dict:
    """
    Get existing customer or create a new one from database.

    Use this tool when:
    - Starting a new conversation (need to identify the customer)
    - Customer provides their phone number or ID
    - You need customer_id for other operations

    Returns:
        dict with: customer_id, name, domicile, vehicle_id, vehicle_alias, unit_qty, is_b2b, is_onboarded

    Example:
        Input: phone_number="628123456789", contact_name="Budi"
        Output: {customer_id: 123, name: "Budi", domicile: "Jakarta", ...}
    """
    logger.info(f"TOOL: get_or_create_customer - phone: {phone_number}, lid: {lid_number}, contact: {contact_name}")

    identifier = {
        'phone_number': phone_number,
        'lid_number': lid_number
    }

    async with AsyncSessionLocal() as db:
        # Search by phone_number first (priority)
        customer = None
        if phone_number:
            query = select(Customer).where(Customer.phone_number == phone_number)
            result = await db.execute(query)
            customer = result.scalars().first()

        # If not found, search by lid_number
        if not customer and lid_number:
            query = select(Customer).where(Customer.lid_number == lid_number)
            result = await db.execute(query)
            customer = result.scalars().first()

        if customer:
            # Update missing identifiers
            need_update = False
            if phone_number and not customer.phone_number:
                customer.phone_number = phone_number
                need_update = True
            if lid_number and not customer.lid_number:
                customer.lid_number = lid_number
                need_update = True
            if contact_name and contact_name != customer.contact_name:
                customer.contact_name = contact_name
                need_update = True

            if need_update:
                await db.commit()
                await db.refresh(customer)

            db.expunge(customer)
            logger.info(f"Customer FOUND: id={customer.id}")
        else:
            # Create new customer
            customer = Customer(
                phone_number=phone_number,
                lid_number=lid_number,
                contact_name=contact_name,
                is_onboarded=False
            )
            db.add(customer)
            await db.commit()
            await db.refresh(customer)
            db.expunge(customer)
            logger.info(f"New customer CREATED: id={customer.id}")

    return {
        'customer_id': customer.id,
        'name': customer.name or '',
        'domicile': customer.domicile or '',
        'vehicle_id': customer.vehicle_id if customer.vehicle_id else -1,
        'vehicle_alias': customer.vehicle_alias or '',
        'unit_qty': customer.unit_qty if customer.unit_qty else 0,
        'is_b2b': customer.is_b2b if customer.is_b2b else False,
        'is_onboarded': customer.is_onboarded if customer.is_onboarded else False,
        'contact_name': customer.contact_name or ''
    }


@tool
async def get_customer_profile(customer_id: int) -> dict:
    """
    Get complete customer profile from database.

    Use this tool when:
    - You need to check what customer data we already have
    - Starting a conversation to see existing profile
    - Checking if profiling is complete

    Returns:
        dict with all customer profile fields
    """
    logger.info(f"TOOL: get_customer_profile - customer_id: {customer_id}")

    async with AsyncSessionLocal() as db:
        query = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(query)
        customer = result.scalars().first()

        if not customer:
            logger.warning(f"Customer NOT FOUND: {customer_id}")
            return {'error': f'Customer {customer_id} not found'}

        db.expunge(customer)

        # Get vehicle_alias from VPS DB if vehicle_id > 0 and no vehicle_alias
        vehicle_alias = customer.vehicle_alias or ''
        if not vehicle_alias and customer.vehicle_id and customer.vehicle_id > 0:
            from src.orin_ai_crm.core.agents.tools.vps_tools import get_vehicle_by_id
            vehicle_data = await get_vehicle_by_id(customer.vehicle_id)
            if vehicle_data:
                vehicle_alias = vehicle_data.get('name', '')

        return {
            'customer_id': customer.id,
            'name': customer.name or '',
            'domicile': customer.domicile or '',
            'vehicle_id': customer.vehicle_id if customer.vehicle_id else -1,
            'vehicle_alias': vehicle_alias,
            'unit_qty': customer.unit_qty if customer.unit_qty else 0,
            'is_b2b': customer.is_b2b if customer.is_b2b else False,
            'is_onboarded': customer.is_onboarded if customer.is_onboarded else False,
            'contact_name': customer.contact_name or ''
        }


@tool
async def update_customer_data(
    customer_id: int,
    name: Optional[str] = None,
    domicile: Optional[str] = None,
    vehicle_alias: Optional[str] = None,
    vehicle_id: Optional[int] = None,
    unit_qty: Optional[int] = None,
    is_b2b: Optional[bool] = None
) -> dict:
    """
    Update specific fields in customer profile.

    Use this tool when:
    - Customer provides new or updated information
    - After extracting customer info from messages
    - Need to update profile in database

    Only provided fields will be updated. Others remain unchanged.

    Args:
        customer_id: Customer database ID
        name: New name value
        domicile: New domicile value
        vehicle_alias: New vehicle alias
        vehicle_id: New vehicle ID
        unit_qty: New unit quantity
        is_b2b: New B2B flag

    Returns:
        dict with: success (bool), message, updated_fields
    """
    try:
        logger.info(f"TOOL: update_customer_data - customer_id: {customer_id}")
        logger.info(f"TOOL: update_customer_data - params: name={name}, domicile={domicile}, vehicle_alias={vehicle_alias}, vehicle_id={vehicle_id}, unit_qty={unit_qty}, is_b2b={is_b2b}")

        async with AsyncSessionLocal() as db:
            query = select(Customer).where(Customer.id == customer_id)
            result = await db.execute(query)
            customer = result.scalars().first()

            if not customer:
                logger.warning(f"TOOL: update_customer_data - Customer {customer_id} not found")
                return {'success': False, 'message': f'Customer {customer_id} not found', 'updated_fields': []}

            updated_fields = []

            if name and name != customer.name:
                customer.name = name
                updated_fields.append('name')

            if domicile and domicile != customer.domicile:
                customer.domicile = domicile
                updated_fields.append('domicile')

            if vehicle_alias and vehicle_alias != customer.vehicle_alias:
                customer.vehicle_alias = vehicle_alias
                updated_fields.append('vehicle_alias')

            if vehicle_id is not None and vehicle_id != customer.vehicle_id:
                customer.vehicle_id = vehicle_id
                updated_fields.append('vehicle_id')

            if unit_qty and unit_qty != customer.unit_qty:
                customer.unit_qty = unit_qty
                updated_fields.append('unit_qty')

            if is_b2b is not None and is_b2b != customer.is_b2b:
                customer.is_b2b = is_b2b
                updated_fields.append('is_b2b')

            if updated_fields:
                await db.commit()
                await db.refresh(customer)
                logger.info(f"TOOL: update_customer_data - Customer {customer_id} updated: {', '.join(updated_fields)}")
                return {
                    'success': True,
                    'message': f'Updated: {", ".join(updated_fields)}',
                    'updated_fields': updated_fields
                }
            else:
                logger.info(f"TOOL: update_customer_data - No changes needed for customer {customer_id}")
                return {
                    'success': True,
                    'message': 'No changes needed',
                    'updated_fields': []
                }
    except Exception as e:
        logger.error(f"TOOL: update_customer_data - ERROR: {str(e)}")
        return {
            'success': False,
            'message': f'Error updating customer: {str(e)}',
            'updated_fields': []
        }


# ============================================================================
# CATEGORY 2: PROFILING TOOLS (7 tools)
# ============================================================================

@tool
async def extract_customer_info_from_message(
    message: str,
    current_profile: dict
) -> dict:
    """
    Extract customer information from a message using LLM.

    Use this tool when:
    - Customer sends a message that might contain profile information
    - Need to parse name, domicile, vehicle, quantity from text
    - Customer updates their information

    The LLM intelligently extracts:
    - name: Customer's name
    - domicile: City/location
    - vehicle_alias: Vehicle type/name they mention
    - unit_qty: Number of units they need

    Args:
        message: The customer's message
        current_profile: Current customer profile dict

    Returns:
        dict with extracted fields (only fields found in message)
    """
    try:
        logger.info(f"TOOL: extract_customer_info_from_message - message: {message[:100]}")
        logger.info(f"TOOL: extract_customer_info_from_message - current_profile: {current_profile}")

        system_prompt = f"""Extract informasi customer dari pesan. Jangan mengarang info jika tidak disebutkan.

Profile saat ini:
- Nama: {current_profile.get('name', '-')}
- Domisili: {current_profile.get('domicile', '-')}
- Kendaraan: {current_profile.get('vehicle_alias', '-')}
- Jumlah Unit: {current_profile.get('unit_qty', 0)}

Jika user mengoreksi info, update field tersebut.
Jika user belum menyebutkan, biarkan field kosong.

IMPORTANT untuk vehicle_alias:
- Extract nama/alias kendaraan yang user sebutkan (e.g., "CRF", "Avanza", "XMAX", "motor", "mobil")
- HANYA extract jika user jelas menyebutkan kendaraan MILIK mereka
- JANGAN extract kata-kata: "orin", "gps", "tracker", "aplikasi", "sistem", "produk"
- Jika tidak jelas, biarkan vehicle_alias kosong

Return JSON with fields that were found (only include fields mentioned in the message):
{{"name": "...", "domicile": "...", "vehicle_alias": "...", "unit_qty": 5}}"""

        response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=message)])

        result = json.loads(response.content)
        logger.info(f"TOOL: extract_customer_info_from_message - Extracted: {result}")
        return result
    except Exception as e:
        logger.error(f"TOOL: extract_customer_info_from_message - ERROR: {str(e)}")
        return {}


@tool
def check_profiling_completeness(profile: dict) -> dict:
    """
    Check if customer profiling is complete and determine route.

    Use this tool when:
    - Need to check if we have enough customer data to proceed
    - Determining if profiling is done
    - Deciding between SALES vs ECOMMERCE route

    Profiling is considered complete if at least ONE of:
    - domicile (location)
    - unit_qty (number of units, > 0)
    - vehicle_alias (vehicle type)

    Args:
        profile: Customer profile dict with keys: name, domicile, vehicle_alias, unit_qty, is_b2b

    Returns:
        dict with: is_complete (bool), missing_fields (list), recommended_route (str)
    """
    try:
        logger.info(f"TOOL: check_profiling_completeness - profile: {profile}")

        # Check if we have enough data to proceed
        # At least one of: domicile, unit_qty (>0), or vehicle_alias
        has_domicile = bool(profile.get('domicile'))
        has_unit_qty = profile.get('unit_qty', 0) > 0
        has_vehicle_alias = bool(profile.get('vehicle_alias'))

        is_complete = has_domicile or has_unit_qty or has_vehicle_alias

        # Determine route based on unit_qty
        # - If unit_qty >= 5 OR is_b2b = True → SALES
        # - Otherwise → ECOMMERCE
        unit_qty = profile.get('unit_qty', 0)
        is_b2b = profile.get('is_b2b', False)

        if is_complete:
            recommended_route = "SALES" if (unit_qty >= 5 or is_b2b) else "ECOMMERCE"
        else:
            recommended_route = "CONTINUE_PROFILING"

        # For logging: what's missing
        missing_fields = []
        if not has_domicile:
            missing_fields.append('domicile')
        if not has_unit_qty:
            missing_fields.append('unit_qty')
        if not has_vehicle_alias:
            missing_fields.append('vehicle_alias')

        result = {
            'is_complete': is_complete,
            'missing_fields': missing_fields,
            'recommended_route': recommended_route,
            'unit_qty': unit_qty,
            'is_b2b': is_b2b,
            'has_domicile': has_domicile,
            'has_unit_qty': has_unit_qty,
            'has_vehicle_alias': has_vehicle_alias
        }
        logger.info(f"TOOL: check_profiling_completeness - result: {result}")
        return result
    except Exception as e:
        logger.error(f"TOOL: check_profiling_completeness - ERROR: {str(e)}")
        return {
            'is_complete': False,
            'missing_fields': ['domicile', 'unit_qty', 'vehicle_alias'],
            'recommended_route': "CONTINUE_PROFILING",
            'unit_qty': 0,
            'is_b2b': False
        }


@tool
def determine_next_profiling_field(profile: dict) -> dict:
    """
    Determine which field to ask for next in profiling flow.

    Use this tool when:
    - Profiling is incomplete
    - Need to know what to ask customer next

    Priority order: name → domicile → vehicle_alias → unit_qty

    Args:
        profile: Customer profile dict with keys: name, domicile, vehicle_alias, unit_qty, is_b2b

    Returns:
        dict with: next_field (str), reason (str)
    """
    try:
        logger.info(f"TOOL: determine_next_profiling_field - profile keys: {list(profile.keys())}")
        logger.info(f"TOOL: determine_next_profiling_field - profile: {profile}")

        if not profile.get('name'):
            logger.info("TOOL: determine_next_profiling_field - Missing 'name', returning name")
            return {
                'next_field': 'name',
                'reason': 'Customer name is required for personalized service'
            }

        if not profile.get('domicile'):
            logger.info("TOOL: determine_next_profiling_field - Missing 'domicile', returning domicile")
            return {
                'next_field': 'domicile',
                'reason': 'Domicile is needed for location-based offers and shipping'
            }

        if not profile.get('vehicle_alias'):
            logger.info("TOOL: determine_next_profiling_field - Missing 'vehicle_alias', returning vehicle_alias")
            return {
                'next_field': 'vehicle_alias',
                'reason': 'Vehicle information helps recommend the right GPS product'
            }

        if profile.get('unit_qty', 0) == 0:
            logger.info("TOOL: determine_next_profiling_field - Missing 'unit_qty', returning unit_qty")
            return {
                'next_field': 'unit_qty',
                'reason': 'Quantity is needed to determine pricing and route (sales vs ecommerce)'
            }

        logger.info("TOOL: determine_next_profiling_field - All fields complete, returning 'complete'")
        return {
            'next_field': 'complete',
            'reason': 'All profiling fields are complete'
        }
    except Exception as e:
        logger.error(f"TOOL: determine_next_profiling_field - ERROR: {str(e)}")
        return {
            'next_field': 'name',
            'reason': 'Error determining next field, defaulting to name'
        }


@tool
async def generate_profiling_question(
    field_name: str,
    customer_name: str,
    current_profile: dict,
    conversation_context: str
) -> dict:
    """
    Generate a natural, personalized profiling question.

    Use this tool when:
    - Need to ask customer for specific information
    - Continuing profiling flow

    Args:
        field_name: The field to ask about (name, domicile, vehicle_alias, unit_qty)
        customer_name: Customer's name (or "Kak" if unknown)
        current_profile: Current customer profile dict
        conversation_context: Recent conversation for context

    Returns:
        dict with: question (str) - The natural question to ask
    """
    logger.info(f"TOOL: generate_profiling_question - field: {field_name}")

    field_prompts = {
        "name": f"""Generate a greeting to ask for the customer's name.
Context: {conversation_context}
Task: Perkenalkan diri sebagai Hana dari ORIN GPS Tracker, lalu tanya nama dengan sopan.
Response: Pesan natural untuk WhatsApp""",

        "domicile": f"""Generate a question to ask for customer's domicile/location.
Customer Name: {customer_name}
Current Profile: {current_profile}
Context: {conversation_context}
Task: Tanya domisili/kota customer dengan alasan untuk penawaran yang lebih pas.
Response: Pesan natural untuk WhatsApp""",

        "vehicle_alias": f"""Generate a question to ask about customer's vehicle.
Customer Name: {customer_name}
Location: {current_profile.get('domicile', 'kota kakak')}
Context: {conversation_context}
Task: Tanya jenis dan nama kendaraan (e.g., "Honda CRF", "Toyota Avanza") untuk rekomendasi produk yang pas.
Response: Pesan natural untuk WhatsApp""",

        "unit_qty": f"""Generate a question to ask how many units customer needs.
Customer Name: {customer_name}
Vehicle: {current_profile.get('vehicle_alias', 'kendaraan kakak')}
Context: {conversation_context}
Task: Tanya berapa unit yang akan dipasang GPS.
Response: Pesan natural untuk WhatsApp"""
    }

    prompt = field_prompts.get(field_name, field_prompts["name"])
    prompt = f"""{HANA_PERSONA}

{prompt}

RULES:
- Gunakan emoji secara wajar
- Natural seperti chat WhatsApp asli
- Personalized berdasarkan info yang sudah diketahui
- Tanya SATU field saja
- Response HANYA dengan pesan yang akan dikirim"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'question': response.content,
        'field_asked': field_name
    }


@tool
async def search_vehicle_in_vps(vehicle_name: str) -> dict:
    """
    Search for vehicle in VPS database to get exact vehicle_id and name.

    Use this tool when:
    - Customer mentions a vehicle name/alias
    - Need to find exact vehicle match in database

    Returns:
        dict with: found (bool), vehicle_id (int), vehicle_name (str), matches (list)
    """
    logger.info(f"TOOL: search_vehicle_in_vps - searching: {vehicle_name}")

    from src.orin_ai_crm.core.agents.tools.vps_tools import search_vehicle_by_name, get_vehicle_by_id

    vehicle_id, matches = await search_vehicle_by_name(vehicle_name)

    if vehicle_id and vehicle_id > 0:
        vehicle_data = await get_vehicle_by_id(vehicle_id)
        return {
            'found': True,
            'vehicle_id': vehicle_id,
            'vehicle_name': vehicle_data.get('name', vehicle_name) if vehicle_data else vehicle_name,
            'exact_match': True,
            'matches': []
        }
    elif matches and len(matches) > 0:
        return {
            'found': True,
            'vehicle_id': -1,
            'vehicle_name': vehicle_name,
            'exact_match': False,
            'matches': [m.get('name') for m in matches[:5]]
        }
    else:
        return {
            'found': False,
            'vehicle_id': -1,
            'vehicle_name': vehicle_name,
            'exact_match': False,
            'matches': []
        }


@tool
async def create_lead_routing(
    customer_id: int,
    route_type: str,
    notes: Optional[str] = None
) -> dict:
    """
    Create a lead routing record when profiling is complete.

    Use this tool when:
    - Profiling is complete
    - Customer is ready to be routed to SALES or ECOMMERCE

    Args:
        customer_id: Customer database ID
        route_type: "SALES" or "ECOMMERCE"
        notes: Optional notes about the customer

    Returns:
        dict with: success (bool), routing_id (int)
    """
    logger.info(f"TOOL: create_lead_routing - customer: {customer_id}, route: {route_type}")

    async with AsyncSessionLocal() as db:
        # Check for existing pending routing
        query = select(LeadRouting).where(
            (LeadRouting.customer_id == customer_id) &
            (LeadRouting.status == "pending")
        )
        result = await db.execute(query)
        existing = result.scalars().first()

        if existing:
            return {
                'success': True,
                'routing_id': existing.id,
                'message': 'Routing already exists'
            }

        routing = LeadRouting(
            customer_id=customer_id,
            route_type=route_type,
            status="pending",
            notes=notes
        )
        db.add(routing)
        await db.commit()
        await db.refresh(routing)

        logger.info(f"Lead routing CREATED: {routing.id}")

        return {
            'success': True,
            'routing_id': routing.id,
            'message': f'Routing created for {route_type}'
        }


@tool
async def generate_greeting_message(
    customer_name: str,
    conversation_context: str
) -> dict:
    """
    Generate a friendly, personalized greeting message. Before use this tool, use get_customer_profile tools to gather their information.

    Use this tool when:
    - Customer sends a greeting (halo, hai, selamat pagi)
    - Starting a new conversation
    - Customer says thank you

    Returns:
        dict with: greeting (str) - The greeting message
    """
    logger.info(f"TOOL: generate_greeting_message - customer: {customer_name}")

    prompt = f"""{HANA_PERSONA}

Customer: {customer_name}
Context: {conversation_context}

TASK:
Generate a natural, friendly greeting response.

RULES:
- Gunakan emoji yang sesuai
- Natural seperti chat WhatsApp asli
- Tanya bagaimana bisa membantu
- Jangan terlalu formal
- Response HANYA dengan pesan yang akan dikirim"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'greeting': response.content
    }


# ============================================================================
# CATEGORY 3: SALES & MEETING TOOLS (7 tools)
# ============================================================================

@tool
async def get_pending_meeting(customer_id: int) -> dict:
    """
    Get pending or confirmed meeting for customer.

    Use this tool when:
    - Checking if customer has an existing meeting
    - Customer wants to reschedule
    - Customer mentions an existing meeting

    Returns:
        dict with: found (bool), meeting_id (int), date (str), time (str), status (str)
    """
    logger.info(f"TOOL: get_pending_meeting - customer: {customer_id}")

    async with AsyncSessionLocal() as db:
        query = select(CustomerMeeting).where(
            (CustomerMeeting.customer_id == customer_id) &
            (CustomerMeeting.status.in_(["pending", "confirmed"]))
        ).order_by(CustomerMeeting.created_at.desc())

        result = await db.execute(query)
        meeting = result.scalars().first()

        if meeting:
            return {
                'found': True,
                'meeting_id': meeting.id,
                'date': meeting.notes.split(', ')[0].split(': ')[1] if meeting.notes else '',
                'time': meeting.notes.split(', ')[1].split(': ')[1] if meeting.notes and ', ' in meeting.notes else '',
                'status': meeting.status,
                'notes': meeting.notes
            }
        else:
            return {
                'found': False,
                'meeting_id': None,
                'date': '',
                'time': '',
                'status': '',
                'notes': ''
            }


@tool
async def extract_meeting_details(
    message: str,
    customer_name: str,
    has_existing_meeting: bool = False
) -> dict:
    """
    Extract meeting details from customer message using LLM.

    Use this tool when:
    - Customer mentions booking a meeting
    - Customer wants to reschedule
    - Customer agrees to a meeting time

    Extracts:
    - has_agreement: Did customer agree to book meeting?
    - wants_reschedule: Does customer want to change existing meeting?
    - date: Meeting date (can be "besok", "Senin depan", or "2024-01-15")
    - time: Meeting time (can be "jam 2", "pagi", or "14:00")

    Returns:
        dict with extracted meeting details
    """
    logger.info(f"TOOL: extract_meeting_details - has_existing: {has_existing_meeting}")

    existing_context = ""
    if has_existing_meeting:
        existing_context = "\nCustomer already has a meeting booked. Detect if they want to RESCHEDULE."

    prompt = f"""Extract meeting information from customer message.

Customer: {customer_name}
Message: "{message}"
{existing_context}

Extract:
1. has_meeting_agreement: true if customer AGREED to book (not just asking, but confirmed)
2. wants_reschedule: true if customer wants to change existing meeting
3. meeting_date: Date mentioned (can be natural like "besok", "Senin depan", or specific date)
4. meeting_time: Time mentioned (can be natural like "jam 2", "pagi", or specific time like "14:00")
5. meeting_format: "online", "offline", or null

Examples:
- "Boleh, booking meeting besok jam 2" → agreement: true, date: "besok", time: "jam 2"
- "Oke, Senin depan jam 10 pagi" → agreement: true, date: "Senin depan", time: "10 pagi"
- "Bisa ganti jadwal besok?" → wants_reschedule: true, agreement: true (new date)
- "Kira-kira kapan saja?" → agreement: false (still negotiating)

Return JSON format."""

    extractor_llm = llm.with_structured_output(MeetingInfo)
    meeting_info = extractor_llm.invoke([SystemMessage(content=prompt)])

    logger.info(f"Extracted meeting details: agreement={meeting_info.has_meeting_agreement}, reschedule={meeting_info.wants_reschedule}")

    return {
        'has_meeting_agreement': meeting_info.has_meeting_agreement,
        'wants_reschedule': meeting_info.wants_reschedule,
        'meeting_date': meeting_info.meeting_date or '',
        'meeting_time': meeting_info.meeting_time or '',
        'meeting_format': meeting_info.meeting_format or 'online',
        'notes': meeting_info.notes or ''
    }


@tool
async def book_or_update_meeting_db(
    customer_id: int,
    meeting_date: str,
    meeting_time: str,
    meeting_format: str = "online",
    wants_reschedule: bool = False,
    existing_meeting_id: Optional[int] = None
) -> dict:
    """
    Book new meeting or update existing meeting in database.

    Use this tool when:
    - Customer has agreed to a meeting time
    - Need to create new meeting record
    - Need to update existing meeting (reschedule)

    Returns:
        dict with: success (bool), meeting_id (int), action (str)
    """
    logger.info(f"TOOL: book_or_update_meeting_db - customer: {customer_id}, reschedule: {wants_reschedule}")

    async with AsyncSessionLocal() as db:
        if wants_reschedule and existing_meeting_id:
            # Update existing meeting
            query = select(CustomerMeeting).where(CustomerMeeting.id == existing_meeting_id)
            result = await db.execute(query)
            existing_meeting = result.scalars().first()

            if existing_meeting:
                existing_meeting.notes = f"Date: {meeting_date}, Time: {meeting_time}"
                existing_meeting.status = "rescheduled"
                await db.commit()

                logger.info(f"Meeting RESCHEDULED: {existing_meeting.id}")

                return {
                    'success': True,
                    'meeting_id': existing_meeting.id,
                    'action': 'rescheduled',
                    'date': meeting_date,
                    'time': meeting_time
                }

        # Create new meeting
        meeting = CustomerMeeting(
            customer_id=customer_id,
            meeting_datetime=None,
            meeting_format=meeting_format,
            status="pending",
            notes=f"Date: {meeting_date}, Time: {meeting_time}"
        )
        db.add(meeting)
        await db.commit()
        await db.refresh(meeting)

        logger.info(f"Meeting CREATED: {meeting.id}")

        return {
            'success': True,
            'meeting_id': meeting.id,
            'action': 'created',
            'date': meeting_date,
            'time': meeting_time
        }


@tool
async def generate_meeting_negotiation_message(
    customer_name: str,
    conversation_context: str,
    is_reschedule: bool = False
) -> dict:
    """
    Generate message to negotiate meeting time with customer.

    Use this tool when:
    - Customer is in sales flow but hasn't agreed to specific time
    - Need to ask for specific meeting time
    - Continue meeting negotiation

    Args:
        customer_name: Customer's name
        conversation_context: Recent messages for context
        is_reschedule: True if rescheduling existing meeting

    Returns:
        dict with: message (str) - Negotiation message
    """
    logger.info(f"TOOL: generate_meeting_negotiation_message - reschedule: {is_reschedule}")

    task = "reschedule meeting" if is_reschedule else "book new meeting"

    prompt = f"""{HANA_PERSONA}

Customer: {customer_name}
Context: {conversation_context}

TASK:
Generate message to negotiate meeting time for {task}.

RULES:
- Ask for SPECIFIC date and time
- If customer said "pagi/siang/sore", ask for specific hour
- Ramah dan membantu
- Gunakan emoji
- Natural seperti chat WhatsApp asli
- Response HANYA dengan pesan yang akan dikirim"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'message': response.content
    }


@tool
async def generate_meeting_confirmation(
    customer_name: str,
    meeting_date: str,
    meeting_time: str,
    meeting_format: str = "online"
) -> dict:
    """
    Generate meeting confirmation message for customer.

    Use this tool when:
    - Meeting has been successfully booked or rescheduled
    - Need to confirm details with customer

    Returns:
        dict with: confirmation_message (str)
    """
    logger.info(f"TOOL: generate_meeting_confirmation")

    confirmation = f"""Siap kak {customer_name}! 👍

Meeting sudah Hana catat:
📅 Tanggal: {meeting_date}
⏰ Jam: {meeting_time}
📍 Format: {meeting_format.title()}

Tim sales kami akan menghubungi kakak sesuai jadwal tersebut. Sampai jumpa di meeting ya kak! 🙏

Ada yang bisa Hana bantu sebelum meeting?"""

    return {
        'confirmation_message': confirmation
    }


@tool
async def generate_existing_meeting_reminder(
    customer_name: str,
    existing_meeting_info: dict,
    conversation_context: str
) -> dict:
    """
    Generate reminder message when customer has existing meeting.

    Use this tool when:
    - Customer with existing meeting contacts us again
    - Not trying to reschedule, just following up
    - Remind them of their scheduled meeting

    Returns:
        dict with: reminder_message (str)
    """
    logger.info(f"TOOL: generate_existing_meeting_reminder")

    prompt = f"""{HANA_PERSONA}

Customer: {customer_name}
Existing Meeting: {existing_meeting_info}
Context: {conversation_context}

TASK:
Generate a friendly reminder about their existing meeting.
Don't create a new meeting, just remind them of the scheduled one.
Ask if there's anything you can help with before the meeting.

RULES:
- Ramah dan membantu
- Gunakan emoji
- Natural seperti chat WhatsApp asli
- Response HANYA dengan pesan yang akan dikirim"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'reminder_message': response.content
    }


# ============================================================================
# CATEGORY 4: PRODUCT & E-COMMERCE TOOLS (8 tools)
# ============================================================================

@tool
async def get_all_active_products() -> dict:
    """
    Get all active products from database.

    Use this tool when:
    - Need product information for recommendations
    - Customer asks about available products
    - Building product context for LLM

    Returns:
        dict with: products (list of product dicts), count (int)
    """
    logger.info(f"TOOL: get_all_active_products")

    async with AsyncSessionLocal() as db:
        query = select(Product).where(
            Product.is_active == True
        ).order_by(Product.sort_order.asc(), Product.name.asc())

        result = await db.execute(query)
        products = result.scalars().all()

        product_list = []
        for p in products:
            product_list.append({
                'id': p.id,
                'name': p.name,
                'sku': p.sku,
                'category': p.category,
                'subcategory': p.subcategory,
                'vehicle_type': p.vehicle_type,
                'description': p.description,
                'price': p.price,
                'ecommerce_links': json.loads(p.ecommerce_links) if p.ecommerce_links else {},
                'features': json.loads(p.features) if p.features else {},
                'installation_type': p.installation_type,
                'can_shutdown_engine': p.can_shutdown_engine,
            })

        logger.info(f"Retrieved {len(product_list)} active products")

        return {
            'products': product_list,
            'count': len(product_list)
        }


@tool
async def search_products(
    keyword: str,
    category: Optional[str] = None,
    vehicle_type: Optional[str] = None
) -> dict:
    """
    Search products by keyword, category, or vehicle type.

    Use this tool when:
    - Customer asks about specific products
    - Need to filter products by criteria
    - Customer mentions specific vehicle type

    Args:
        keyword: Search term (product name, SKU, or feature)
        category: Optional filter by category (TANAM, INSTAN, KAMERA, AKSESORIS)
        vehicle_type: Optional filter by vehicle type (mobil, motor, alat berat)

    Returns:
        dict with: products (list), count (int), search_criteria (dict)
    """
    logger.info(f"TOOL: search_products - keyword: {keyword}, category: {category}, vehicle: {vehicle_type}")

    async with AsyncSessionLocal() as db:
        query = select(Product).where(Product.is_active == True)

        # Apply filters
        if category:
            query = query.where(Product.category == category)
        if vehicle_type:
            query = query.where(Product.vehicle_type == vehicle_type)
        if keyword:
            query = query.where(
                (Product.name.ilike(f"%{keyword}%")) |
                (Product.description.ilike(f"%{keyword}%")) |
                (Product.sku.ilike(f"%{keyword}%"))
            )

        query = query.order_by(Product.sort_order.asc())
        result = await db.execute(query)
        products = result.scalars().all()

        product_list = []
        for p in products:
            product_list.append({
                'id': p.id,
                'name': p.name,
                'sku': p.sku,
                'category': p.category,
                'description': p.description,
                'price': p.price,
                'features': json.loads(p.features) if p.features else {},
            })

        return {
            'products': product_list,
            'count': len(product_list),
            'search_criteria': {
                'keyword': keyword,
                'category': category,
                'vehicle_type': vehicle_type
            }
        }


@tool
async def get_product_details(product_id: int) -> dict:
    """
    Get detailed information about a specific product.

    Use this tool when:
    - Customer asks about specific product details
    - Need full product information including specs, features, links

    Returns:
        dict with complete product information
    """
    logger.info(f"TOOL: get_product_details - product_id: {product_id}")

    async with AsyncSessionLocal() as db:
        query = select(Product).where(Product.id == product_id)
        result = await db.execute(query)
        product = result.scalars().first()

        if not product:
            return {
                'found': False,
                'product': None
            }

        return {
            'found': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'category': product.category,
                'subcategory': product.subcategory,
                'vehicle_type': product.vehicle_type,
                'description': product.description,
                'price': product.price,
                'installation_type': product.installation_type,
                'can_shutdown_engine': product.can_shutdown_engine,
                'is_realtime_tracking': product.is_realtime_tracking,
                'features': json.loads(product.features) if product.features else {},
                'specifications': json.loads(product.specifications) if product.specifications else {},
                'ecommerce_links': json.loads(product.ecommerce_links) if product.ecommerce_links else {},
                'images': json.loads(product.images) if product.images else [],
                'compatibility': json.loads(product.compatibility) if product.compatibility else {},
            }
        }


@tool
async def answer_product_question(
    question: str,
    customer_profile: dict
) -> dict:
    """
    Answer product questions using LLM with database product context.

    Use this tool when:
    - Customer asks about products (features, prices, differences)
    - Customer wants recommendations
    - Customer asks how to buy

    Args:
        question: The customer's question
        customer_profile: Customer profile for personalization

    Returns:
        dict with: answer (str) - AI-generated answer
    """
    logger.info(f"TOOL: answer_product_question")

    # Get all products for context
    products_result = await get_all_products()
    products_context = format_products_for_llm(products_result['products'])

    customer_name = customer_profile.get('name') or 'Kak'
    customer_info = f"""
Customer Profile:
- Nama: {customer_name}
- Kendaraan: {customer_profile.get('vehicle_alias', '-')}
- Jumlah Unit: {customer_profile.get('unit_qty', 0)}
- B2B: {customer_profile.get('is_b2b', False)}
"""

    prompt = f"""{HANA_PERSONA}

{products_context}

{customer_info}
Pertanyaan Customer: {question}

TASK:
Jawab pertanyaan customer dengan sopan dan ramah.
Berikan informasi produk yang akurat dari database.
Jika tanya harga, sebutkan harganya.
Jika tanya cara beli, berikan link e-commerce yang tersedia.
JANGAN mengarang info yang tidak ada di database.
Gunakan emoji yang sesuai (🚗, 🏍️, ✅, dll).

Response HANYA dengan jawaban yang akan dikirim ke customer."""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'answer': response.content
    }


@tool
async def get_ecommerce_links(product_id: int) -> dict:
    """
    Get e-commerce purchase links for a product.

    Use this tool when:
    - Customer wants to buy a product
    - Customer asks for purchase links
    - Need to provide Tokopedia/Shopee links

    Returns:
        dict with: product_name (str), links (dict with platform: url)
    """
    logger.info(f"TOOL: get_ecommerce_links - product_id: {product_id}")

    async with AsyncSessionLocal() as db:
        query = select(Product).where(Product.id == product_id)
        result = await db.execute(query)
        product = result.scalars().first()

        if not product:
            return {
                'found': False,
                'product_name': '',
                'links': {}
            }

        links = json.loads(product.ecommerce_links) if product.ecommerce_links else {}

        return {
            'found': True,
            'product_name': product.name,
            'links': links
        }


@tool
async def create_product_inquiry(
    customer_id: int,
    product_type: str,
    vehicle_type: str,
    unit_qty: int
) -> dict:
    """
    Create a product inquiry record for tracking.

    Use this tool when:
    - Customer asks about products for the first time
    - Need to track product interest

    Returns:
        dict with: success (bool), inquiry_id (int)
    """
    logger.info(f"TOOL: create_product_inquiry - customer: {customer_id}")

    async with AsyncSessionLocal() as db:
        # Check for existing pending inquiry
        query = select(ProductInquiry).where(
            (ProductInquiry.customer_id == customer_id) &
            (ProductInquiry.status == "pending")
        )
        result = await db.execute(query)
        existing = result.scalars().first()

        if existing:
            return {
                'success': True,
                'inquiry_id': existing.id,
                'message': 'Inquiry already exists'
            }

        inquiry = ProductInquiry(
            customer_id=customer_id,
            product_type=product_type,
            vehicle_type=vehicle_type,
            unit_qty=unit_qty,
            status="pending"
        )
        db.add(inquiry)
        await db.commit()
        await db.refresh(inquiry)

        logger.info(f"Product inquiry CREATED: {inquiry.id}")

        return {
            'success': True,
            'inquiry_id': inquiry.id,
            'message': 'Inquiry created'
        }


@tool
async def get_pending_product_inquiry(customer_id: int) -> dict:
    """
    Get pending product inquiry for customer.

    Use this tool when:
    - Customer has ongoing product inquiry
    - Need to check inquiry status

    Returns:
        dict with: found (bool), inquiry (dict or None)
    """
    logger.info(f"TOOL: get_pending_product_inquiry - customer: {customer_id}")

    async with AsyncSessionLocal() as db:
        query = select(ProductInquiry).where(
            (ProductInquiry.customer_id == customer_id) &
            (ProductInquiry.status == "pending")
        )
        result = await db.execute(query)
        inquiry = result.scalars().first()

        if inquiry:
            return {
                'found': True,
                'inquiry': {
                    'id': inquiry.id,
                    'product_type': inquiry.product_type,
                    'vehicle_type': inquiry.vehicle_type,
                    'unit_qty': inquiry.unit_qty,
                    'status': inquiry.status
                }
            }
        else:
            return {
                'found': False,
                'inquiry': None
            }


@tool
async def recommend_products_for_customer(
    customer_profile: dict,
    preferences: Optional[str] = None
) -> dict:
    """
    Recommend products based on customer profile using LLM.

    Use this tool when:
    - Customer wants product recommendations
    - Profiling is complete, suggesting products
    - Customer asks "what's best for me?"

    Args:
        customer_profile: Customer profile with vehicle, qty, etc.
        preferences: Optional customer preferences/budget

    Returns:
        dict with: recommended_products (list), explanation (str)
    """
    logger.info(f"TOOL: recommend_products_for_customer")

    # Get relevant products based on vehicle type
    vehicle_alias = customer_profile.get('vehicle_alias', '')
    vehicle_type = 'motor' if 'motor' in vehicle_alias.lower() else 'mobil'

    products_result = await search_products(
        keyword='',
        vehicle_type=vehicle_type
    )

    products = products_result['products']

    if not products:
        # Fallback to all products
        all_products = await get_all_active_products()
        products = all_products['products']

    products_context = format_products_for_llm(products)

    customer_name = customer_profile.get('name') or 'Kak'
    unit_qty = customer_profile.get('unit_qty', 1)

    prompt = f"""{HANA_PERSONA}

{products_context}

CUSTOMER NEEDS:
- Nama: {customer_name}
- Kendaraan: {vehicle_alias}
- Jumlah Unit: {unit_qty}
- Preferensi: {preferences or '-'}

TASK:
Rekomendasikan 1-3 produk terbaik dari daftar di atas.
Jelaskan alasan rekomendasi.
Berikan link e-commerce untuk pembelian.
Ramah dan natural.

Response HANYA dengan rekomendasi yang akan dikirim ke customer."""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'recommended_products': [p['name'] for p in products[:3]],
        'explanation': response.content
    }


# ============================================================================
# CATEGORY 5: SUPPORT & COMPLAINT TOOLS (3 tools)
# ============================================================================

@tool
async def classify_issue_type(message: str) -> dict:
    """
    Classify customer issue type (complaint vs support question).

    Use this tool when:
    - Customer has a problem or question
    - Need to determine if it's a complaint or support inquiry

    Returns:
        dict with: issue_type (str: "complaint", "support", "general"), severity (str)
    """
    logger.info(f"TOOL: classify_issue_type")

    prompt = f"""Classify the customer message type.

Message: "{message}"

Classify as:
1. "complaint" - Customer is complaining, unhappy, reporting issues
2. "support" - Customer needs technical help, asks how to do something
3. "general" - General question, greeting, thanks

Also assess severity:
- "high" - Urgent, angry, critical issue
- "medium" - Needs attention but not urgent
- "low" - Simple question, inquiry

Return JSON: {{"issue_type": "...", "severity": "...", "reasoning": "..."}}"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    try:
        result = json.loads(response.content)
        return result
    except:
        return {
            'issue_type': 'general',
            'severity': 'low',
            'reasoning': 'Could not classify, defaulting to general'
        }


@tool
async def generate_empathetic_response(
    message: str,
    customer_name: str,
    issue_type: str
) -> dict:
    """
    Generate empathetic response for customer issues.

    Use this tool when:
    - Customer has a complaint or problem
    - Customer needs support
    - Need to show empathy and offer help

    Args:
        message: Customer's message
        customer_name: Customer's name
        issue_type: "complaint", "support", or "general"

    Returns:
        dict with: response (str) - Empathetic message
    """
    logger.info(f"TOOL: generate_empathetic_response - type: {issue_type}")

    if issue_type == "complaint":
        task = "Customer has a complaint. Apologize sincerely, acknowledge their frustration, ask for details to help, and assure them you'll resolve it."
    elif issue_type == "support":
        task = "Customer needs technical support. Offer help patiently, ask for specifics if needed, and provide guidance."
    else:
        task = "Customer sent a general message. Respond warmly and ask how you can help."

    prompt = f"""{HANA_PERSONA}

Customer: {customer_name}
Message: "{message}"

TASK:
{task}

RULES:
- Tunjukkan empati yang tulus
- Gunakan emoji yang sesuai
- Natural seperti chat WhatsApp asli
- Jika perlu, tanya detail masalahnya
- Berikan assurance bahwa tim akan membantu
- Response HANYA dengan pesan yang akan dikirim"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'response': response.content
    }


@tool
async def set_human_takeover_flag(customer_id: int) -> dict:
    """
    Set human_takeover flag to true for a customer.

    Use this tool when:
    - Issue is too complex for AI to handle
    - Customer explicitly asks for human agent
    - Quality check fails repeatedly

    Returns:
        dict with: success (bool), message (str)
    """
    logger.info(f"TOOL: set_human_takeover_flag - customer: {customer_id}")

    async with AsyncSessionLocal() as db:
        query = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(query)
        customer = result.scalars().first()

        if not customer:
            return {
                'success': False,
                'message': f'Customer {customer_id} not found'
            }

        customer.human_takeover = True
        await db.commit()

        logger.info(f"Human takeover flag SET for customer {customer_id}")

        return {
            'success': True,
            'message': 'Human takeover flag set'
        }

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_all_products():
    """Helper to get all active products - uses product_tools function"""
    result = await get_all_active_products_from_db()
    return result


def format_products_for_llm(products: list) -> str:
    """Format products for LLM context"""
    return format_products_for_llm_impl(products)


# ============================================================================
# TOOL LIST FOR AGENT
# ============================================================================

# Group tools by category for better organization
CUSTOMER_MANAGEMENT_TOOLS = [
    get_or_create_customer,
    get_customer_profile,
    update_customer_data,
]

PROFILING_TOOLS = [
    extract_customer_info_from_message,
    check_profiling_completeness,
    determine_next_profiling_field,
    generate_profiling_question,
    search_vehicle_in_vps,
    create_lead_routing,
    generate_greeting_message,
]

SALES_MEETING_TOOLS = [
    get_pending_meeting,
    extract_meeting_details,
    book_or_update_meeting_db,
    generate_meeting_negotiation_message,
    generate_meeting_confirmation,
    generate_existing_meeting_reminder,
]

PRODUCT_ECOMMERCE_TOOLS = [
    get_all_active_products,
    search_products,
    get_product_details,
    answer_product_question,
    get_ecommerce_links,
    create_product_inquiry,
    get_pending_product_inquiry,
    recommend_products_for_customer,
]

_SUPPORT_TOOLS = [
    classify_issue_type,
    generate_empathetic_response,
    set_human_takeover_flag,
]

# All tools combined
AGENT_TOOLS = (
    CUSTOMER_MANAGEMENT_TOOLS +
    PROFILING_TOOLS +
    SALES_MEETING_TOOLS +
    PRODUCT_ECOMMERCE_TOOLS +
    _SUPPORT_TOOLS
)

__all__ = [
    'AGENT_TOOLS',
    'CUSTOMER_MANAGEMENT_TOOLS',
    'PROFILING_TOOLS',
    'SALES_MEETING_TOOLS',
    'PRODUCT_ECOMMERCE_TOOLS',
    '_SUPPORT_TOOLS',
    'CONVERSATION_TOOLS',
]
