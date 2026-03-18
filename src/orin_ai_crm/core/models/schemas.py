from typing import Annotated, Literal, Sequence, TypedDict, Optional
import operator
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    messages_history: Sequence[BaseMessage]
    phone_number: Optional[str]
    lid_number: Optional[str]
    contact_name: Optional[str]
    customer_id: Optional[int]  # Reference ke customers table
    step: str
    route: str
    customer_data: dict
    # Meeting flags
    wants_meeting: Optional[bool]  # Set oleh intent_classification untuk meeting request
    existing_meeting_id: Optional[int]  # Set oleh intent_classification untuk reschedule
    # Form handling fields
    # awaiting_form: bool  # True if waiting for customer to fill form
    # form_submitted: bool  # True if customer has submitted form
    send_form: bool
    form_data: dict  # Parsed data from form response
    next_route: Optional[str]  # Determined route after form (ecommerce_node or sales_node)
    # Final messages for user (multi-bubble chat response)
    final_messages: list[str]  # List of message strings to be sent as separate chat bubbles
    # Images to send before text messages
    send_images: list[str]  # List of image URLs to send before text messages
    # PDFs to send before text messages
    send_pdfs: list[str]  # List of PDF URLs to send before text messages
    # Orchestrator tracking fields
    orchestrator_step: int  # Current orchestrator iteration (0-based)
    max_orchestrator_steps: int  # Safety limit (default: 5)
    agents_called: list[str]  # List of agents already called (profiling, sales, ecommerce)
    orchestrator_plan: str  # Current plan for debugging
    orchestrator_decision: dict  # Latest routing decision from orchestrator
    human_takeover: bool  # Flag to trigger human takeover flow immediately

class CustomerProfile(BaseModel):
    name: Optional[str] = Field(default="", description="Nama pelanggan, kosongkan jika belum ada")
    domicile: Optional[str] = Field(default="", description="Domisili atau kota pelanggan, kosongkan jika belum ada")
    vehicle_id: int = Field(default=-1, description="ID kendaraan dari vehicles table di VPS DB. -1 jika belum diketahui atau tidak ditemukan")
    vehicle_alias: Optional[str] = Field(default="", description="Teks asli dari user tentang kendaraan (e.g., 'CRF', 'Avanza', 'XMAX', 'motor', 'mobil'). Disimpan ke DB untuk referensi dan display.")
    unit_qty: int = Field(default=0, description="Jumlah unit yang ingin dipasang, 0 jika belum menyebutkan angka")
    is_b2b: bool = Field(default=False, description="True jika ini perusahaan/armada operasional, False jika pemakaian pribadi")
    is_onboarded: bool = Field(default=False, description="True jika agent sudah pernah mengirimkan form/mengonboard user ini")

class IntentResult(BaseModel):
    """Single intent result with confidence and selection status"""
    intent_result: Literal[
        "greeting",
        "profiling",
        "product_inquiry",
        "complaint",
        "support",
        "general_question"
    ] = Field(
        description="Type of intent"
    )
    use_intent: bool = Field(
        description="True if LLM selected this intent as applicable to the user's message"
    )
    intent_confidence: float = Field(
        description="Confidence score 0-1 for this intent classification",
        ge=0.0,
        le=1.0
    )


class IntentClassification(BaseModel):
    """User Intent Classification - Contains all intents with their states"""
    intents: list[IntentResult] = Field(
        description="List of all 6 intents with their selection status and confidence"
    )
    reasoning: str = Field(
        description="Alasan klasifikasi intent secara keseluruhan"
    )
    product_keywords: list[str] = Field(
        default=[],
        description="Keywords terkait produk yang disebutkan"
    )

    def get_selected_intent(self) -> tuple[str, float] | None:
        """
        Get the intent with highest confidence among those marked as use_intent=True.

        Returns:
            Tuple of (intent_name, confidence) or None if no intent is selected
        """
        selected_intents = [i for i in self.intents if i.use_intent]
        if not selected_intents:
            return None

        # Sort by confidence descending and return the highest
        selected_intents.sort(key=lambda x: x.intent_confidence, reverse=True)
        highest = selected_intents[0]
        return (highest.intent_result, highest.intent_confidence)
    

class MeetingInfo(BaseModel):
    """Extract meeting information dari chat"""
    has_meeting_agreement: bool = Field(
        description="True jika user sudah sepakat untuk booking meeting"
    )
    wants_reschedule: bool = Field(
        default=False,
        description="True jika user ingin reschedule meeting yang sudah ada"
    )
    meeting_date: Optional[str] = Field(
        default=None,
        description="Tanggal meeting dalam format DD/MM/YYYY atau natural seperti 'besok', 'Senin depan'"
    )
    meeting_time: Optional[str] = Field(
        default=None,
        description="Jam meeting dalam format HH:MM atau natural seperti 'jam 2 siang', 'pagi', 'sore'"
    )
    meeting_format: Optional[str] = Field(
        default="online",
        description="Format meeting: online, offline, atau belum ditentukan"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Catatan tambahan dari user"
    )
    
class ProductInfo(BaseModel):
    """Product information extracted from conversation"""
    product_type: Optional[str] = Field(default="", description="Tipe produk: TANAM atau INSTAN")
    vehicle_id: int = Field(default=-1, description="ID kendaraan dari vehicles table di VPS DB. -1 jika tidak diketahui.")
    vehicle_alias: Optional[str] = Field(default="", description="Teks asli dari user tentang kendaraan (e.g., 'CRF', 'motor', 'mobil')")
    unit_qty: Optional[int] = Field(default=0, description="Jumlah unit")