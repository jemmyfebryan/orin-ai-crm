"""
Support & Complaint Agent Tools

LangChain StructuredTool objects for support and complaint operations.
These tools are used by the LangGraph agent for support-related operations.
"""

import os
import json
from typing import Annotated, Optional, List
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import InjectedState
import httpx

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config, get_llm
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db, get_agent_name
from src.orin_ai_crm.core.agents.tools.vps_tools import query_vps_db, get_user_id_from_device_id, get_user_token_from_user_id
from src.orin_ai_crm.core.agents.tools.db_tools import get_device_type
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db
from src.orin_ai_crm.core.agents.tools.api_tools import reset_device_unit
from src.orin_ai_crm.core.utils.phone_utils import build_phone_number_sql_conditions
from sqlalchemy import select

logger = get_logger(__name__)

# Use medium model for support tasks (FAQ-style responses)
llm = get_llm("medium")
WIB = timezone(timedelta(hours=7))


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
        # Handle different content formats from different LLM providers
        # - OpenAI returns: str (JSON string)
        # - Gemini 4.x returns: list[dict] with 'type', 'text', 'extras' keys
        content = response.content

        # Convert to string if it's a list (Gemini 4.x format)
        if isinstance(content, list):
            # Extract text from content blocks
            content_str = ""
            for block in content:
                if isinstance(block, dict):
                    # Gemini 4.x format: {'type': 'text', 'text': '...', 'extras': {...}}
                    if 'text' in block:
                        content_str += block['text']
                elif hasattr(block, 'text'):
                    content_str += block.text
                elif isinstance(block, str):
                    content_str += block
                elif hasattr(block, 'content'):
                    content_str += str(block.content)
            content = content_str

        # Strip markdown code blocks if present (```json ... ```)
        if isinstance(content, str):
            # Remove ```json and ``` markers
            content = content.strip()
            if content.startswith('```json'):
                content = content[7:]  # Remove ```json
            elif content.startswith('```'):
                content = content[3:]  # Remove ```
            if content.endswith('```'):
                content = content[:-3]  # Remove trailing ```
            content = content.strip()

        result = json.loads(str(content))
        return result
    except Exception as e:
        logger.error(f"TOOL: classify_issue_type - ERROR: {str(e)}")
        logger.error(f"TOOL: classify_issue_type - Response content type: {type(response.content)}")
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

    prompt = f"""Customer: {customer_name}
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
def human_takeover() -> dict:
    """
    Trigger human takeover for the customer.

    Use this tool when:
    - Issue is too complex for AI to handle
    - Customer explicitly asks for human agent
    - Customer sends username & email after forgot password guide

    Returns:
        dict with: message (str), update_state (dict)
    """
    logger.info("TOOL: human_takeover")

    return {
        'message': 'Tim kami akan segera membantu ya 🙏',
        'update_state': {
            'human_takeover': True
        }
    }


@tool
async def forgot_password() -> dict:
    """
    Get the forgot password guide for customers.

    Use this tool when:
    - Customer asks about forgot password
    - Customer cannot login to their account
    - Customer needs password reset instructions

    Returns:
        dict with: message (str) - Password reset guide
    """
    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    logger.info("TOOL: forgot_password")

    # Get agent name for dynamic messaging
    agent_name = get_agent_name()

    message = f"""Halo Kak, maaf ya kendalanya 😔

Kalau Kakak lupa password, gampang banget kok caranya:

1️⃣ Buka website https://app.orin.id
2️⃣ Pilih menu "Lupa Password"
3️⃣ Ikuti langkah-langkahnya di sana

Kalau udah dicoba tapi masih belum bisa juga, tolong infoin ke {agent_name}:
- Username untuk login
- Email yang dipakai

Nanti {agent_name} bantu cek lebih lanjut ya 🙏"""

    return {
        'message': message
    }


@tool
async def license_extension(
    state: Annotated[dict, InjectedState],
    account_type: Optional[str] = None,
) -> dict:
    """
    Get license extension guide based on customer's account type.

    Use this tool when:
    - Customer asks about license renewal/extension
    - Customer wants to extend their ORIN subscription
    - Customer asks about perpanjangan lisensi

    Args:
        state: Agent state (contains customer_id)
        account_type: Optional - if already known from get_account_info tool
                     If not provided, will fetch from database automatically

    Returns:
        dict with: message (str) - License extension guide based on account type
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_account_type
    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    logger.info("TOOL: license_extension")

    # Get agent name for dynamic messaging
    agent_name = get_agent_name()

    # Get customer_id from state
    customer_id = state.get("customer_id")

    if not customer_id:
        logger.error("TOOL: license_extension - No customer_id in state!")
        return {
            'message': f'Maaf Kak, {agent_name} belum bisa identifikasi akun Kakak. Tolong hubungi CS kami ya 🙏'
        }

    # Get account type from database if not provided
    if account_type is None:
        account_info = await get_account_type(customer_id)
        if account_info is None:
            logger.error(f"TOOL: license_extension - Could not get account info for customer {customer_id}")
            return {
                'message': f'Maaf Kak, {agent_name} belum bisa identifikasi akun Kakak. Tolong hubungi CS kami ya 🙏',
                'update_state': {
                    'human_takeover': True
                }
            }
        account_type = account_info.get('account_type')
        logger.info(f"Account type for customer {customer_id}: {account_type}")
    else:
        logger.info(f"Using provided account_type: {account_type}")

    # Generate message based on account type
    if account_type in ['free', 'lite', 'promo', 'pro']:
        message = f"""Untuk perpanjangan lisensi ORIN, Kakak bisa lakukan online dari browser kok 😊

Caranya gampang banget:
1️⃣ Login ke akun ORIN di https://app.orin.id
2️⃣ Buka link ini: https://app.orin.id/license/renew/
3️⃣ Pilih unit yang mau diperpanjang
4️⃣ Pilih jenis akun (Pro/Plus/Lite) dan periode (bulanan/tahunan)
5️⃣ Bayar via BCA Virtual Account atau metode lain yang tersedia

Silahkan dicoba ya Kak! Kalau ada kendala, hubungi {agent_name} lagi 🙏"""
    elif account_type == 'plus':
        message = f"""Untuk perpanjangan HALO ORIN dengan lisensi ORIN PLUS, Kakak bisa transfer ke:

🏦 **Bank BCA**
PT Vastel Telematika Integrasi
612-1001818

💰 **Harga:**
• Rp 300.000 untuk 6 bulan
• Rp 600.000 untuk 12 bulan

⚠️ Jangan lupa tulis **nomor polisi kendaraan** di kolom pesan ya Kak!

Setelah transfer, kirim bukti transfer ke {agent_name}. Proses reaktivasi biasanya 2-3 hari kerja kalau terlambat bayar.

Terima kasih Kak! 🙏"""
    else:  # account_type is None or unknown
        message = "Account type error, call human_takeover tool"
        return {
            'message': message,
            'account_type': account_type,
            'update_state': {
                'human_takeover': True
            }
        }

    return {
        'message': message,
        'account_type': account_type
    }


@tool
async def get_installation_cost(
    state: Annotated[dict, InjectedState],
) -> dict:
    """
    Get information about installation cost and technician coverage areas.

    Use this tool when:
    - Customer asks about installation cost/fee
    - Customer asks about installation price
    - Customer asks about biaya instalasi/pemasangan
    - Customer asks about technician availability in their area
    - Customer asks about teknisi area

    Returns:
        dict with: installation_info (dict) - Installation cost and coverage information
    """
    logger.info("TOOL: get_installation_cost")

    # Get customer data to check domicile
    customer_data = state.get('customer_data', {})
    domicile = customer_data.get('domicile', '')

    return {
        'installation_info': {
            'free_areas': ['Jakarta Timur', 'Surabaya'],
            'free_areas_description': 'Jakarta Timur & sekitarnya dan Surabaya & sekitarnya',
            'outside_area_fee': 'Ada biaya akomodasi teknis untuk area di luar Jakarta Timur dan Surabaya',
            'customer_domicile': domicile,
            'instruction': 'Berikan informasi ini ke customer. Jika customer bertanya tentang jumlah biaya akomodasi spesifik untuk area di luar Jakarta Timur/Surabaya, gunakan human_takeover tool untuk alihkan ke live agent.'
        }
    }


@tool
async def device_troubleshooting(
    state: Annotated[dict, InjectedState],
    device_id: Optional[int] = None,
    reset_by_agent: bool = False,
) -> dict:
    """
    Get troubleshooting guide for offline GPS device or reset the device.
    Use tool list_customer_devices to get the list of device_id and device_name.

    Use this tool when:
    - Customer reports GPS device is offline
    - Customer says GPS not updating
    - Customer reports device not showing location

    This tool is specific for GPS troubleshooting guide, other problem can use ask_technical_support tool instead

    Args:
        state: Agent state (contains customer_id)
        device_id: Optional device ID to troubleshoot specific device.
                   Get this from list_customer_devices tool. If not provided, will use customer's first device.
        reset_by_agent: Set to False when customer not yet confirm or no specific unit mentioned.
                        Set to True ONLY when customer explicitly want to reset and the device specifically mentioned.
                        Default: False
                       
    Returns:
        dict with: message (str), update_state (dict, optional), device_type (str)
    """

    logger.info(f"TOOL: device_troubleshooting - device_id: {device_id}, reset_by_agent: {reset_by_agent}")

    # Get agent name for dynamic messaging
    agent_name = get_agent_name()

    # Get customer_id from state
    customer_id = state.get("customer_id")

    if not customer_id:
        logger.error("TOOL: device_troubleshooting - No customer_id in state!")
        return {
            'message': 'Device type error, call human_takeover tool',
            'device_type': None,
            'update_state': {
                'human_takeover': True
            }
        }

    # Get device type from database
    device_type = await get_device_type(customer_id, device_id)
    logger.info(f"Device type for customer {customer_id}: {device_type}")

    # Check if device_type is None (error case)
    if device_type is None:
        message = "Device type error, call human_takeover tool"
        return {
            'message': message,
            'device_type': device_type,
            'update_state': {
                'human_takeover': True
            }
        }

    # Handle device reset if requested
    if reset_by_agent:
        logger.info(f"Resetting device {device_id} for customer {customer_id}")

        # Step 1: Get user_id from device_id
        user_id = await get_user_id_from_device_id(device_id)

        if user_id is None:
            message = """Maaf Kak, gagal me-reset perangkat 😔

Error: Device tidak ditemukan di database.

Silakan hubungi CS kami untuk bantuan lebih lanjut."""
            return {
                'message': message,
                'device_type': device_type,
                'reset_success': False,
                'error': 'Device not found'
            }

        logger.info(f"Found user_id: {user_id} for device_id: {device_id}")

        # Step 2: Get API token from user_id
        api_token = await get_user_token_from_user_id(user_id)

        # Check if api_token is an error message (starts with "Error:")
        if isinstance(api_token, str) and api_token.startswith("Error:"):
            logger.error(f"Failed to get API token: {api_token}")
            message = f"""Maaf Kak, gagal me-reset perangkat 😔

{api_token}

Silakan hubungi CS kami untuk bantuan lebih lanjut."""
            return {
                'message': message,
                'device_type': device_type,
                'reset_success': False,
                'error': api_token
            }

        logger.info(f"Successfully retrieved API token for user_id: {user_id}")

        # Step 3: Call the reset API
        reset_result = await reset_device_unit(device_id, api_token)

        if reset_result.get('success'):
            message = f"""Perangkat berhasil di-reset ✅

Mohon tunggu 5-10 menit untuk perangkat kembali online. Kalau setelah itu masih belum online juga, hubungi {agent_name} lagi ya 🙏"""
            return {
                'message': message,
                'device_type': device_type,
                'reset_success': True,
                'status_code': reset_result.get('status_code')
            }
        else:
            error_msg = reset_result.get('message', 'Unknown error')
            logger.error(f"Failed to reset device {device_id}: {error_msg}")
            message = f"""Maaf Kak, gagal me-reset perangkat 😔

Error: {error_msg}

Silakan hubungi CS kami untuk bantuan lebih lanjut."""
            return {
                'message': message,
                'device_type': device_type,
                'reset_success': False,
                'error': error_msg,
                'status_code': reset_result.get('status_code')
            }

    # Generate troubleshooting guide based on device type
    sms_devices = ['gt06n', 'tr06', 't700', 't2', 't30', 'wetrack', 'moplus', 'tr02']

    if device_type.lower() in sms_devices:
        message = f"""Untuk kendala GPS offline Kakak, coba langkah ini ya 😊

1️⃣ Coba hubungi nomor GSM di dalam unit lewat HP Kakak
   → Kalau **tidak ada nada sambung** atau langsung ke voicemail, berarti alat **OFFLINE**
   → Harap ke **installer terdekat** untuk cek fisik GPS

2️⃣ Kalau ada nada sambung, coba kirim SMS dengan format:
   **STATUS#** (jangan lupa tanda pagar di belakang, tanpa spasi)
   → Kirim ke nomor GSM di dalam unit GPS

3️⃣ Kalau unit **tidak membalas SMS**:
   → Coba isi pulsa **ALL data** (2G & 4G) Rp 25.000 ya Kak

4️⃣ Kalau unit **membalas SMS**:
   → Tolong kirimkan balasan SMS dari unit ke {agent_name} untuk kami telaah lebih lanjut

💡 Biasanya masalah GPS ini karena kartu GSM kehabisan pulsa Kakak :)

---
💬 **{agent_name} bisa bantu reset perangkat Kakak secara remote lho!**
   Kalau Kakak mau, bilang saja "Ya, tolong reset" ke {agent_name} 😊"""
    elif device_type.lower() == 'postpaid':
        message = f"""Maaf Kak, untuk jenis kartu pascabayar ini perlu bantuan langsung dari tim kami ya 🙏

Tim CS Orin akan segera membantu pengecekan lebih lanjut.

---
💬 **{agent_name} bisa bantu reset perangkat Kakak secara remote lho!**
   Kalau Kakak mau, bilang saja "Ya, tolong reset" ke {agent_name} 😊"""
        return {
            'message': message,
            'device_type': device_type,
            'update_state': {
                'human_takeover': True
            }
        }
    else:  # OBU and other devices (any other valid device type)
        message = f"""Untuk kendala GPS offline Kakak, coba langkah ini ya 😊

1️⃣ Coba hubungi nomor GSM di dalam unit lewat HP Kakak
   → Kalau **tidak ada nada sambung** atau langsung ke voicemail, berarti alat **OFFLINE**
   → Harap ke **installer terdekat** untuk cek fisik GPS

2️⃣ Kalau ada nada sambung, coba refresh unit:
   → Buka browser, masuk ke https://app.orin.id
   → Login dan pilih unit yang offline
   → Tekan tombol **REFRESH UNIT**

3️⃣ Kalau setelah isi pulsa dan refresh unit masih belum update:
   → Hubungi {agent_name} lagi ya untuk bantu cek lebih lanjut

💡 Biasanya masalah GPS ini karena kartu GSM kehabisan pulsa Kakak :)

---
💬 **{agent_name} bisa bantu reset perangkat Kakak secara remote lho!**
   Kalau Kakak mau, bilang saja "Ya, tolong reset" ke {agent_name} 😊"""

    return {
        'message': message,
        'device_type': device_type
    }


@tool
async def get_company_profile() -> dict:
    """
    Get company profile information from database.

    Use this tool ONLY when:
    - Customer EXPLICITLY asks about the company (ORIN GPS Tracker)
    - Customer asks about company address, contact info, working hours
    - Customer wants to know who we are and what we do
    - Customer asks about payment methods or services

    Args:
        None

    Returns:
        dict with: profile (str) - company profile text
    """
    logger.info("TOOL: get_company_profile")

    try:
        # Fetch company profile from database
        company_profile = await get_prompt_from_db("company_profile")

        if not company_profile:
            logger.warning("Company profile not found in database, return empty")
            return {
                'profile': ""
            }
        logger.info("TOOL: get_company_profile - Successfully retrieved company profile")
        return {
            'profile': company_profile
        }

    except Exception as e:
        logger.error(f"TOOL: get_company_profile - ERROR: {str(e)}")
        return {
            'profile': 'Maaf, terjadi kesalahan saat mengambil profil perusahaan. Silakan hubungi customer service.',
            'error': str(e)
        }


@tool
async def get_account_info(
    state: Annotated[dict, InjectedState],
) -> dict:
    """
    Get customer's account type and expiration date.

    Use this tool when:
    - Customer asks "What is my account type?" or "Akun saya apa?"
    - Customer asks about their account status
    - Customer asks "Akun saya gratis atau berbayar?"
    - Customer asks "Kapan masa berlakunya habis?" or "Berapa lama lagi?"
    - Need to check account type before providing specific information

    Args:
        state: Agent state (contains customer_id)

    Returns:
        dict with: account_type (str), account_expired_date (str), message (str) - User-friendly account info
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_account_type

    logger.info("TOOL: get_account_info")

    # Get agent name for dynamic messaging
    agent_name = get_agent_name()

    # Get customer_id from state
    customer_id = state.get("customer_id")

    if not customer_id:
        logger.error("TOOL: get_account_info - No customer_id in state!")
        return {
            'account_type': None,
            'account_expired_date': None,
            'message': f'Maaf Kak, {agent_name} belum bisa identifikasi akun Kakak. Tolong hubungi CS kami ya 🙏'
        }

    # Get account info from database
    account_info = await get_account_type(customer_id)

    if account_info is None:
        logger.error(f"TOOL: get_account_info - Could not get account info for customer {customer_id}")
        return {
            'account_type': None,
            'account_expired_date': None,
            'message': f'Maaf Kak, {agent_name} belum bisa identifikasi akun Kakak. Tolong hubungi CS kami ya 🙏'
        }

    account_type = account_info.get('account_type')
    account_expired_date = account_info.get('account_expired_date')

    logger.info(f"Account info for customer {customer_id}: type={account_type}, expired={account_expired_date}")

    # Generate user-friendly message
    account_type_names = {
        'free': 'ORIN FREE',
        'basic': 'ORIN BASIC',
        'lite': 'ORIN LITE',
        'promo': 'ORIN PROMO',
        'plus': 'ORIN PLUS',
        'pro': 'ORIN PRO'
    }

    display_name = account_type_names.get(account_type, account_type.upper() if account_type else 'UNKNOWN')

    if account_expired_date:
        # Format the date nicely (assuming it's in YYYY-MM-DD format)
        try:
            from datetime import datetime
            # Try parsing the date
            if isinstance(account_expired_date, str):
                try:
                    parsed_date = datetime.fromisoformat(account_expired_date.replace('Z', '+00:00'))
                    formatted_date = parsed_date.strftime('%d %B %Y')
                    message = f"Akun Kakak adalah **{display_name}** dengan masa berlaku sampai **{formatted_date}** 😊"
                except:
                    # If parsing fails, just display as is
                    message = f"Akun Kakak adalah **{display_name}** dengan masa berlaku sampai **{account_expired_date}** 😊"
            else:
                message = f"Akun Kakak adalah **{display_name}** dengan masa berlaku sampai **{account_expired_date}** 😊"
        except:
            message = f"Akun Kakak adalah **{display_name}** dengan masa berlaku sampai **{account_expired_date}** 😊"
    else:
        message = f"Akun Kakak adalah **{display_name}** 😊"

    return {
        'account_type': account_type,
        'account_expired_date': account_expired_date,
        'message': message
    }


@tool
async def list_customer_devices(
    state: Annotated[dict, InjectedState],
) -> dict:
    """
    List all devices for the current customer.

    Use this tool when:
    - Customer has multiple devices and needs to specify which one
    - You need to show the user their available devices
    - Customer asks about their devices

    Args:
        state: Agent state (contains customer_id)

    Returns:
        dict with: devices (list of dict with device_name, device_type, device_type_id)
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_customer_devices

    logger.info("TOOL: list_customer_devices")

    # Get customer_id from state
    customer_id = state.get("customer_id")

    if not customer_id:
        logger.error("TOOL: list_customer_devices - No customer_id in state!")
        return {
            'devices': [],
            'message': 'Maaf, belum bisa identifikasi akun Kakak. Tolong hubungi CS kami ya 🙏'
        }

    # Get all devices from database
    devices = await get_customer_devices(customer_id)
    logger.info(f"Found {len(devices)} devices for customer {customer_id}")

    if not devices:
        return {
            'devices': [],
            'message': 'Tidak ada device yang ditemukan untuk akun Kakak.'
        }

    return {
        'devices': devices
    }


@tool
async def ask_technical_support(
    state: Annotated[dict, InjectedState],
    question: str
) -> dict:
    """
    Ask the technical customer service by calling external API with customer's API tokens.

    Use this tool when customer asks about:
    Waktu operasional (jam kerja, durasi idle/moving), utilisasi kendaraan, jarak tempuh (KM), perilaku berkendara (overspeed, braking, cornering), analisis kecepatan, estimasi BBM, data statis gps lokasi/kecepatan, alert notifikasi (speeding, geofence, device on/off), laporan kendaraan (Excel), dan akun (password, status, expired)
    
    This tool will:
    1. Get customer's phone number from state
    2. Query VPS DB for all API tokens associated with the phone number
    3. Send conversation history + question to technical support API for each token
    4. Return responses from all successful API calls

    Args:
        state: Agent state (contains phone_number and messages_history)
        question: The specific question or instruction to ask technical support (will be appended as last user message)

    Returns:
        dict with: responses (list of str) - List of successful responses from technical support,
                    or error message if all requests failed
    """
    from dotenv import load_dotenv

    load_dotenv()

    logger.info("TOOL: ask_technical_support")
    logger.info(f"Question to technical support: {question[:100]}...")

    # Get phone_number from state
    phone_number = state.get("phone_number")

    if not phone_number:
        logger.error("TOOL: ask_technical_support - No phone_number in state!")
        return {
            'responses': [],
            'error': 'Maaf, belum bisa identifikasi nomor telepon Kakak. Tolong hubungi CS kami ya 🙏'
        }

    logger.info(f"Querying VPS DB for api_token with phone_number: {phone_number}")

    # Query VPS DB for api_tokens from users table
    # Use phone number variations to handle different formats in VPS DB
    phone_conditions = build_phone_number_sql_conditions(phone_number)
    sql_query = f"SELECT api_token FROM users WHERE ({phone_conditions}) AND deleted_at IS NULL"
    result = await query_vps_db(sql_query)

    if not result:
        logger.error(f"TOOL: ask_technical_support - VPS DB query failed for phone_number: {phone_number}")
        return {
            'responses': [],
            'error': 'Maaf, terjadi kesalahan saat menghubungi technical support. Silakan hubungi CS kami ya 🙏'
        }

    # VPS DB returns data in "rows" key
    rows = result.get("rows", [])
    api_tokens = [row.get("api_token") for row in rows if row.get("api_token")]

    if not api_tokens:
        logger.warning(f"No api_tokens found for phone_number: {phone_number} (tried multiple format variations)")
        return {
            'responses': [],
            'error': 'Maaf, belum bisa menemukan akun technical support Kakak. Silakan hubungi CS kami ya 🙏'
        }

    logger.info(f"Found {len(api_tokens)} api_tokens for phone_number: {phone_number}")

    # Get messages_history from state and convert to OpenAI format
    messages_history = state.get("messages_history", [])

    # Convert LangChain messages to OpenAI format (only HumanMessage and AIMessage)
    openai_messages = []
    for msg in messages_history:
        if isinstance(msg, HumanMessage):
            openai_messages.append({
                "role": "user",
                "content": msg.content
            })
        elif isinstance(msg, AIMessage):
            openai_messages.append({
                "role": "assistant",
                "content": msg.content
            })

    # Append the question as the last user message
    # This ensures the orchestrator instruction affects what the technical support receives
    openai_messages.append({
        "role": "user",
        "content": question
    })

    logger.info(f"Converted {len(openai_messages)} messages to OpenAI format (including question)")

    # Prepare API endpoint
    orinai_api_ip = os.getenv("ORINAI_API_IP", "localhost")
    orinai_api_port = os.getenv("ORINAI_API_PORT", "8085")
    api_url = f"http://{orinai_api_ip}:{orinai_api_port}/chat_api"

    logger.info(f"Calling technical support API at: {api_url}")

    # Make async POST requests for each api_token
    successful_responses = []
    errors = []

    async def call_api_for_token(api_token: str) -> Optional[str]:
        """Call API for a single token and return response or None if failed."""
        try:
            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "messages": openai_messages
            }

            logger.info(f"Calling API for token {api_token[:10]}... with {len(openai_messages)} messages")

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    api_url,
                    json=payload,
                    headers=headers
                )

                logger.info(f"Response status: {response.status_code} for token {api_token[:10]}...")
                logger.info(f"Response headers: {dict(response.headers)}")

                response.raise_for_status()

                # Parse response JSON
                response_json = response.json()
                logger.info(f"Response JSON for token {api_token[:10]}...: {str(response_json)[:200]}...")

                # Extract response from response_json.data.response
                if "data" in response_json and isinstance(response_json["data"], dict):
                    api_response = response_json["data"].get("response", "")
                    logger.info(f"API call successful for token {api_token[:10]}...")
                    return api_response
                else:
                    logger.warning(f"Unexpected response format for token {api_token[:10]}...: {response_json}")
                    return None

        except httpx.TimeoutException as e:
            logger.error(f"Timeout for token {api_token[:10]}... after 2 minutes")
            errors.append("Request timeout after 2 minutes")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP status error for token {api_token[:10]}...: {e.response.status_code} - {e.response.text[:200]}")
            errors.append(f"HTTP {e.response.status_code}: {e.response.text[:100]}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"HTTP error for token {api_token[:10]}...: {type(e).__name__}: {str(e)}")
            errors.append(f"{type(e).__name__}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error calling API for token {api_token[:10]}...: {type(e).__name__}: {str(e)}")
            errors.append(f"{type(e).__name__}: {str(e)}")
            return None

    # Call API for each token concurrently
    import asyncio
    tasks = [call_api_for_token(token) for token in api_tokens]
    results = await asyncio.gather(*tasks)

    # Filter out None responses (failed calls)
    successful_responses = [r for r in results if r is not None]

    logger.info(f"Successful responses: {len(successful_responses)}/{len(api_tokens)}")

    if not successful_responses:
        # All requests failed
        error_msg = f"Maaf, semua percobaan menghubungi technical support gagal. Silakan hubungi CS kami ya 🙏"
        if errors:
            # Log errors but don't expose to customer
            logger.error(f"All API calls failed. Errors: {errors}")
        return {
            'responses': [],
            'error': error_msg
        }

    # Return list of successful responses
    return {
        'responses': successful_responses
    }


# List of support tools for easy import
SUPPORT_TOOLS = [
    human_takeover,
    forgot_password,
    get_account_info,
    license_extension,
    get_installation_cost,
    device_troubleshooting,
    get_company_profile,
    list_customer_devices,
    ask_technical_support,
]

# Export human_takeover separately for sales_agent
HUMAN_TAKEOVER_TOOL = [human_takeover]

__all__ = ['SUPPORT_TOOLS', 'HUMAN_TAKEOVER_TOOL']
