"""
Profiling Agent Tools

LangChain StructuredTool objects for customer profiling operations.
These tools are used by the LangGraph agent for profiling-related operations.
"""

import os
import json
from typing import Optional
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, LeadRouting
from sqlalchemy import select

logger = get_logger(__name__)
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))

HANA_PERSONA = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif.
Jangan terlalu kaku, gunakan bahasa natural seperti chat WhatsApp asli.

ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak)."""


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
async def check_profiling_completeness(
    name: str = "",
    domicile: str = "",
    vehicle_alias: str = "",
    unit_qty: int = 0,
    is_b2b: bool = False
) -> dict:
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
        name: Customer name
        domicile: Customer location
        vehicle_alias: Vehicle type
        unit_qty: Number of units
        is_b2b: Business customer flag

    Returns:
        dict with: is_complete (bool), missing_fields (list), recommended_route (str)
    """
    profile = {
        'name': name,
        'domicile': domicile,
        'vehicle_alias': vehicle_alias,
        'unit_qty': unit_qty,
        'is_b2b': is_b2b
    }
    logger.info(f"TOOL: check_profiling_completeness CALLED - profile: {profile}")
    try:

        # Check if we have enough data to proceed
        # At least one of: domicile, unit_qty (>0), or vehicle_alias
        has_name = bool(profile.get('name'))
        has_domicile = bool(profile.get('domicile'))
        has_unit_qty = profile.get('unit_qty', 0) > 0
        has_vehicle_alias = bool(profile.get('vehicle_alias'))

        is_complete = has_name and (has_domicile or has_unit_qty or has_vehicle_alias)

        # Determine route based on unit_qty
        # - If unit_qty >= 5 OR is_b2b = True → SALES
        # - Otherwise → ECOMMERCE
        unit_qty = profile.get('unit_qty', 0)
        is_b2b = profile.get('is_b2b', False)

        if is_complete:
            recommended_route = "SALES" if (unit_qty >= 5 or is_b2b) else "ECOMMERCE"
        else:
            recommended_route = None

        # For logging: what's missing
        missing_fields = []
        if not has_name:
            missing_fields.append('name')
        if not has_domicile:
            missing_fields.append('domicile')
        if not has_unit_qty:
            missing_fields.append('unit_qty')
        if not has_vehicle_alias:
            missing_fields.append('vehicle_alias')

        result = {
            'is_complete': is_complete,
            # 'missing_fields': missing_fields,
            # 'recommended_route': recommended_route,
            # 'unit_qty': unit_qty,
            # 'is_b2b': is_b2b,
            # 'has_name': has_name,
            # 'has_domicile': has_domicile,
            # 'has_unit_qty': has_unit_qty,
            # 'has_vehicle_alias': has_vehicle_alias
        }
        if recommended_route: result['update_state'] = {'route': recommended_route}
        logger.info(f"TOOL: check_profiling_completeness - DONE - result: {result}")
        return result
    except Exception as e:
        logger.exception(f"TOOL: check_profiling_completeness - ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'is_complete': False,
            # 'missing_fields': None,
            # 'has_name': None,
            # 'has_domicile': None,
            # 'has_unit_qty': None,
            # 'has_vehicle_alias': None,
        }


@tool
async def determine_next_profiling(
    name: str = "",
    domicile: str = "",
    vehicle_alias: str = "",
    unit_qty: int = 0,
    is_b2b: bool = False
) -> dict:
    """
    Before use this tool, you need to use check_profiling_completeness tool first
    Determine which field to ask for next in profiling flow.

    Use this tool when:
    - Profiling is incomplete
    - Need to know what to ask customer next

    Priority order: name → domicile → vehicle_alias → unit_qty

    Args:
        name: Customer name
        domicile: Customer location
        vehicle_alias: Vehicle type
        unit_qty: Number of units
        is_b2b: Business customer flag

    Returns:
        dict with: next_field (str), reason (str)
    """
    profile = {
        'name': name,
        'domicile': domicile,
        'vehicle_alias': vehicle_alias,
        'unit_qty': unit_qty,
        'is_b2b': is_b2b
    }
    logger.info(f"TOOL: determine_next_profiling CALLED - profile: {profile}")
    try:
        logger.info(f"TOOL: determine_next_profiling - profile keys: {list(profile.keys())}")
        logger.info(f"TOOL: determine_next_profiling - profile: {profile}")

        if not profile.get('name'):
            logger.info("TOOL: determine_next_profiling - Missing 'name', returning name")
            return {
                'next_field': 'name',
                'reason': 'Customer name is required for personalized service'
            }

        if not profile.get('domicile'):
            logger.info("TOOL: determine_next_profiling - Missing 'domicile', returning domicile")
            return {
                'next_field': 'domicile',
                'reason': 'Domicile is needed for location-based offers and shipping'
            }

        if not profile.get('vehicle_alias'):
            logger.info("TOOL: determine_next_profiling - Missing 'vehicle_alias', returning vehicle_alias")
            return {
                'next_field': 'vehicle_alias',
                'reason': 'Vehicle information helps recommend the right GPS product'
            }

        if profile.get('unit_qty', 0) == 0:
            logger.info("TOOL: determine_next_profiling - Missing 'unit_qty', returning unit_qty")
            return {
                'next_field': 'unit_qty',
                'reason': 'Quantity is needed to determine pricing and route (sales vs ecommerce)'
            }

        logger.info("TOOL: determine_next_profiling - All fields complete, returning 'complete'")
        result = {
            'next_field': 'complete',
            'reason': 'All profiling fields are complete'
        }
        logger.info(f"TOOL: determine_next_profiling - DONE - result: {result}")
        return result
    except Exception as e:
        logger.exception(f"TOOL: determine_next_profiling - ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
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
    Check using tool check_profiling_completeness, if the profile is not yet complete, dont call this tool

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


# List of profiling tools for easy import
PROFILING_TOOLS = [
    extract_customer_info_from_message,
    check_profiling_completeness,
    determine_next_profiling,
    # generate_profiling_question,
    # search_vehicle_in_vps,
    # create_lead_routing,
]

__all__ = ['PROFILING_TOOLS']
