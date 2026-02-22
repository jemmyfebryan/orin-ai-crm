"""
Sales Nodes - Sales flow with meeting management
"""

import os
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.nodes.profiling_nodes import get_natural_vehicle_type
from src.orin_ai_crm.core.agents.tools import (
    get_pending_meeting,
    extract_meeting_info,
    book_or_update_meeting
)

logger = get_logger(__name__)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))

HANA_PERSONA = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak).

ATURAN PERCAKAPAN:
- Bertanya SATU per SATU seperti manusia asli, jangan langsung kirim form lengkap
- Jika user memberikan info baru, update dan konfirmasi dengan sopan
- Contoh: "Oh dari Jakarta ya kak, kakak bisa sebutin nama kakak agar Hana bisa panggil dengan sopan?"
- Jangan meminta data lengkap dalam satu pesan
- Jika user menyebut "lainnya" atau "kantor" untuk jenis kendaraan, gunakan kata yang lebih natural seperti "kendaraan" atau "kebutuhan kantor"
"""


async def node_sales(state: AgentState):
    logger.info("=" * 50)
    logger.info("ENTER: node_sales")

    messages = state['messages']
    data = state['customer_data']
    customer_id = state.get('customer_id')

    # Gunakan natural vehicle type untuk response
    natural_vehicle = get_natural_vehicle_type(data.get('vehicle_type', ''))
    customer_name = data.get('name', 'Kak')

    logger.info(f"Customer: {customer_name}, vehicle: {natural_vehicle}, qty: {data.get('unit_qty')}, b2b: {data.get('is_b2b')}")

    # 1. Check existing meeting
    existing_meeting = await get_pending_meeting(customer_id)
    has_existing = existing_meeting is not None
    logger.info(f"Existing meeting: {has_existing}, id={existing_meeting.id if existing_meeting else 'N/A'}")

    # 2. Cek apakah user sudah sepakat booking meeting atau ingin reschedule
    meeting_info = extract_meeting_info(messages, customer_name, has_existing)

    # 3. Handle reschedule request
    if meeting_info.wants_reschedule and existing_meeting:
        logger.info("Customer wants to RESCHEDULE meeting")

        if meeting_info.has_meeting_agreement:
            # Customer sepakat dengan jadwal baru
            meeting_details = await book_or_update_meeting(
                customer_id=customer_id,
                meeting_info=meeting_info,
                existing_meeting=existing_meeting
            )

            confirm_message = f"""Siap kak {customer_name}! 👍

Meeting sudah Hana update:
📅 Tanggal: {meeting_details['date']}
⏰ Jam: {meeting_details['time']}
📍 Format: {meeting_details['format'].title()}

{meeting_details.get('clarification_msg', '')}

Tim sales kami akan menghubungi kakak sesuai jadwal baru tersebut. Sampai jumpa di meeting ya kak! 🙏"""

            logger.info(f"EXIT: node_sales -> Meeting rescheduled")
            logger.info("=" * 50)

            return {
                "messages": [AIMessage(content=confirm_message)],
                "route": "SALES",
                "customer_id": customer_id
            }
        else:
            # Masih negosiasi jadwal baru
            prompt = f"""{HANA_PERSONA}

Customer: {customer_name} ingin mengganti jadwal meeting yang sudah ada.
Meeting lama: {existing_meeting.notes}

Tugas:
1. Acknowledge permintaan ganti jadwal
2. Tanyakan kapan waktu yang cocok untuk meeting baru (tanggal & jam yang spesifik)
3. Jika waktu tidak spesifik (pagi/siang/sore), tanya lebih detail: "Kira-kira jam berapa kak?"
4. Ramah dan membantu"""

            response = llm.invoke([SystemMessage(content=prompt)] + messages)

            logger.info(f"EXIT: node_sales -> Negotiating reschedule")
            logger.info("=" * 50)

            return {
                "messages": [AIMessage(content=response.content)],
                "route": "SALES",
                "customer_id": customer_id
            }

    # 4. Handle new meeting booking
    if meeting_info.has_meeting_agreement and not existing_meeting:
        logger.info("Meeting AGREED - booking new meeting")

        meeting_details = await book_or_update_meeting(
            customer_id=customer_id,
            meeting_info=meeting_info,
            existing_meeting=None
        )

        # Check if need clarification for time
        if meeting_details.get('needs_clarification'):
            confirm_message = f"""Siap kak {customer_name}! 👍

Meeting sudah Hana catat:
📅 Tanggal: {meeting_details['date']}
⏰ Jam: {meeting_details['time']}

{meeting_details['clarification_msg']}

Mohon info lebih spesifik ya kak, biar tim sales bisa persisp dengan jadwalnya."""

            logger.info(f"EXIT: node_sales -> Meeting booked, needs clarification")
            logger.info("=" * 50)

            return {
                "messages": [AIMessage(content=confirm_message)],
                "route": "SALES",
                "customer_id": customer_id
            }

        # Buat konfirmasi meeting
        confirm_message = f"""Siap kak {customer_name}! 👍

Meeting sudah Hana catat:
📅 Tanggal: {meeting_details['date']}
⏰ Jam: {meeting_details['time']}
📍 Format: {meeting_details['format'].title()}

Tim sales kami akan menghubungi kakak sesuai jadwal tersebut. Sampai jumpa di meeting ya kak! 🙏

Ada yang bisa Hana bantu sebelum meeting?"""

        logger.info(f"EXIT: node_sales -> Meeting confirmed, route=SALES")
        logger.info("=" * 50)

        return {
            "messages": [AIMessage(content=confirm_message)],
            "route": "SALES",
            "customer_id": customer_id
        }

    # 5. Meeting sudah ada, customer menghubungi lagi (bukan reschedule)
    if existing_meeting and not meeting_info.wants_reschedule:
        logger.info(f"Existing meeting found, handling other inquiry")

        meeting_info_str = f"📅 Tanggal: {existing_meeting.notes}"
        prompt = f"""{HANA_PERSONA}

Customer: {customer_name} sudah punya meeting yang di-book.
Meeting: {meeting_info_str}

Customer sekarang chat lagi (bukan untuk ganti jadwal).

Tugas:
1. Sapa dengan nama mereka
2. Remind meeting mereka yang sudah di-book dengan singkat: "Meeting kakak sudah Hana catat ya untuk [tanggal/jam]"
3. Tanya apakah ada yang bisa dibantu sebelum meeting
4. Jangan buat meeting baru
5. Ramah dan membantu"""

        response = llm.invoke([SystemMessage(content=prompt)] + messages)

        logger.info(f"EXIT: node_sales -> Existing meeting reminder")
        logger.info("=" * 50)

        return {
            "messages": [AIMessage(content=response.content)],
            "route": "SALES",
            "customer_id": customer_id
        }

    # 6. Belum sepakat, lanjutkan negosiasi meeting baru
    logger.info("Meeting NOT agreed - continuing negotiation")

    prompt = f"""{HANA_PERSONA}

User ini masuk kategori SALES (B2B atau butuh >= 5 unit).
Data customer:
- Nama: {customer_name}
- Domisili: {data.get('domicile')}
- Kendaraan: {natural_vehicle} (original: {data.get('vehicle_type')})
- Jumlah unit: {data.get('unit_qty')}
- B2B: {data.get('is_b2b')}

Tugas:
1. Sapa dengan nama mereka
2. Konfirmasi kebutuhan mereka
3. Tawarkan Meeting Online dengan tim sales untuk penawaran khusus
4. Tanyakan kapan waktu yang cocok untuk meeting (tanggal & jam yang SPESIFIK)
5. Jika customer menyebut "pagi", "siang", atau "sore", tanya jam berapa: "Kira-kira jam berapa kak?"
6. JANGAN gunakan placeholder [Link Booking Meeting]
7. Focus untuk dapatkan kesepakatan jadwal meeting"""

    response = llm.invoke([SystemMessage(content=prompt)] + messages)

    logger.info(f"AI response generated: {response.content[:100]}...")
    logger.info(f"EXIT: node_sales -> Negotiating, route=SALES")
    logger.info("=" * 50)

    return {
        "messages": [AIMessage(content=response.content)],
        "route": "SALES",
        "customer_id": customer_id
    }
