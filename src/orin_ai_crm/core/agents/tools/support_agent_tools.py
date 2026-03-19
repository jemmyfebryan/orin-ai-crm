"""
Support & Complaint Agent Tools

LangChain StructuredTool objects for support and complaint operations.
These tools are used by the LangGraph agent for support-related operations.
"""

import os
import json
from typing import Annotated, Optional
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import InjectedState

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db, get_agent_name
from sqlalchemy import select

logger = get_logger(__name__)
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
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
async def device_troubleshooting(
    state: Annotated[dict, InjectedState],
    device_name: Optional[str] = None,
) -> dict:
    """
    Get troubleshooting guide for offline GPS device.
    Use tool list_customer_devices to get the List of device_name.

    Use this tool when:
    - Customer reports GPS device is offline
    - Customer says GPS not updating
    - Customer reports device not showing location

    Args:
        state: Agent state (contains customer_id)
        device_name: Optional device name to troubleshoot specific device.
                     If not provided, will use customer's first device.

    Returns:
        dict with: message (str), update_state (dict, optional), device_type (str)
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_device_type
    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    logger.info(f"TOOL: device_troubleshooting - device_name: {device_name}")

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
    device_type = await get_device_type(customer_id, device_name)
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

    # Generate message based on device type
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

💡 Biasanya masalah GPS ini karena kartu GSM kehabisan pulsa Kakak :)"""
    elif device_type.lower() == 'postpaid':
        message = """Maaf Kak, untuk jenis kartu pascabayar ini perlu bantuan langsung dari tim kami ya 🙏

Tim CS Orin akan segera membantu pengecekan lebih lanjut."""
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

💡 Biasanya masalah GPS ini karena kartu GSM kehabisan pulsa Kakak :)"""

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


# List of support tools for easy import
SUPPORT_TOOLS = [
    human_takeover,
    forgot_password,
    get_account_info,
    license_extension,
    device_troubleshooting,
    get_company_profile,
    list_customer_devices,
]

# Export human_takeover separately for sales_agent
HUMAN_TAKEOVER_TOOL = [human_takeover]

__all__ = ['SUPPORT_TOOLS', 'HUMAN_TAKEOVER_TOOL']
