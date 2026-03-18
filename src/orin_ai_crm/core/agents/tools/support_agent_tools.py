"""
Support & Complaint Agent Tools

LangChain StructuredTool objects for support and complaint operations.
These tools are used by the LangGraph agent for support-related operations.
"""

import os
import json
from typing import Annotated
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import InjectedState

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db
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
def forgot_password() -> dict:
    """
    Get the forgot password guide for customers.

    Use this tool when:
    - Customer asks about forgot password
    - Customer cannot login to their account
    - Customer needs password reset instructions

    Returns:
        dict with: message (str) - Password reset guide
    """
    logger.info("TOOL: forgot_password")

    message = """Halo Kak, maaf ya kendalanya 😔

Kalau Kakak lupa password, gampang banget kok caranya:

1️⃣ Buka website https://app.orin.id
2️⃣ Pilih menu "Lupa Password"
3️⃣ Ikuti langkah-langkahnya di sana

Kalau udah dicoba tapi masih belum bisa juga, tolong infoin ke Hana:
- Username untuk login
- Email yang dipakai

Nanti Hana bantu cek lebih lanjut ya 🙏"""

    return {
        'message': message
    }


@tool
async def license_extension(
    state: Annotated[dict, InjectedState],
) -> dict:
    """
    Get license extension guide based on customer's account type.

    Use this tool when:
    - Customer asks about license renewal/extension
    - Customer wants to extend their ORIN subscription
    - Customer asks about perpanjangan lisensi

    Returns:
        dict with: message (str) - License extension guide based on account type
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_account_type

    logger.info("TOOL: license_extension")

    # Get customer_id from state
    customer_id = state.get("customer_id")

    if not customer_id:
        logger.error("TOOL: license_extension - No customer_id in state!")
        return {
            'message': 'Maaf Kak, Hana belum bisa identifikasi akun Kakak. Tolong hubungi CS kami ya 🙏'
        }

    # Get account type from database
    account_type = await get_account_type(customer_id)
    logger.info(f"Account type for customer {customer_id}: {account_type}")

    # Generate message based on account type
    if account_type in ['free', 'lite', 'promo', 'pro']:
        message = """Untuk perpanjangan lisensi ORIN, Kakak bisa lakukan online dari browser kok 😊

Caranya gampang banget:
1️⃣ Login ke akun ORIN di https://app.orin.id
2️⃣ Buka link ini: https://app.orin.id/license/renew/
3️⃣ Pilih unit yang mau diperpanjang
4️⃣ Pilih jenis akun (Pro/Plus/Lite) dan periode (bulanan/tahunan)
5️⃣ Bayar via BCA Virtual Account atau metode lain yang tersedia

Silahkan dicoba ya Kak! Kalau ada kendala, hubungi Hana lagi 🙏"""
    else:  # account_type == 'plus'
        message = """Untuk perpanjangan HALO ORIN (free lisensi ORIN PLUS), Kakak bisa transfer ke:

🏦 **Bank BCA**
PT Vastel Telematika Integrasi
612-1001818

💰 **Harga:**
• Rp 300.000 untuk 6 bulan
• Rp 600.000 untuk 12 bulan

⚠️ Jangan lupa tulis **nomor polisi kendaraan** di kolom pesan ya Kak!

Setelah transfer, kirim bukti transfer ke Hana. Proses reaktivasi biasanya 2-3 hari kerja kalau terlambat bayar.

Terima kasih Kak! 🙏"""

    return {
        'message': message,
        'account_type': account_type
    }


@tool
async def device_troubleshooting(
    state: Annotated[dict, InjectedState],
) -> dict:
    """
    Get troubleshooting guide for offline GPS device.

    Use this tool when:
    - Customer reports GPS device is offline
    - Customer says GPS not updating
    - Customer reports device not showing location

    Args:
        device_name: The device name/identifier (e.g., "B1234ABC", "GPS-01", etc.)

    Returns:
        dict with: message (str), update_state (dict, optional), device_type (str)
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_device_type

    logger.info(f"TOOL: device_troubleshooting")

    # Get device type from database
    device_type = await get_device_type(state=state)
    logger.info(f"Device type for: {device_type}")

    # Generate message based on device type
    sms_devices = ['GT06N', 'TR06', 'T700', 'T2', 'T30', 'Wetrack', 'moplus', 'TR02']

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
   → Tolong kirimkan balasan SMS dari unit ke Hana untuk kami telaah lebih lanjut

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
    else:  # OBU and other devices
        message = f"""Untuk kendala GPS offline Kakak, coba langkah ini ya 😊

1️⃣ Coba hubungi nomor GSM di dalam unit lewat HP Kakak
   → Kalau **tidak ada nada sambung** atau langsung ke voicemail, berarti alat **OFFLINE**
   → Harap ke **installer terdekat** untuk cek fisik GPS

2️⃣ Kalau ada nada sambung, coba refresh unit:
   → Buka browser, masuk ke https://app.orin.id
   → Login dan pilih unit yang offline
   → Tekan tombol **REFRESH UNIT**

3️⃣ Kalau setelah isi pulsa dan refresh unit masih belum update:
   → Hubungi Hana lagi ya untuk bantu cek lebih lanjut

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


# List of support tools for easy import
SUPPORT_TOOLS = [
    human_takeover,
    forgot_password,
    license_extension,
    device_troubleshooting,
    get_company_profile,
]

__all__ = ['SUPPORT_TOOLS']
