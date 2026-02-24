from typing import Annotated, Literal, Sequence, TypedDict, Optional
import operator
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    phone_number: Optional[str]
    lid_number: Optional[str]
    contact_name: Optional[str]
    customer_id: Optional[int]  # Reference ke customers table
    step: str
    route: str
    customer_data: dict
    # Intent classification fields
    classified_intent: Optional[str]  # Intent yang sudah diklasifikasi
    intent_confidence: Optional[float]  # Confidence score 0-1
    # Meeting flags
    wants_meeting: Optional[bool]  # Set oleh intent_classification untuk meeting request
    existing_meeting_id: Optional[int]  # Set oleh intent_classification untuk reschedule

class CustomerProfile(BaseModel):
    name: Optional[str] = Field(default="", description="Nama pelanggan, kosongkan jika belum ada")
    domicile: Optional[str] = Field(default="", description="Domisili atau kota pelanggan, kosongkan jika belum ada")
    vehicle_type: Optional[str] = Field(default="", description="Jenis kendaraan: mobil, motor, alat berat, atau lainnya")
    unit_qty: int = Field(default=0, description="Jumlah unit yang ingin dipasang, 0 jika belum menyebutkan angka")
    is_b2b: bool = Field(default=False, description="True jika ini perusahaan/armada operasional, False jika pemakaian pribadi")
    

class IntentClassification(BaseModel):
    """User Intent Classification"""
    intent: Literal["greeting", "profiling", "product_inquiry", "meeting_request", "complaint", "support", "reschedule", "order", "general_question"] = Field(
        description="Intent utama user"
    )
    confidence: float = Field(
        description="Confidence score 0-1",
        ge=0.0,
        le=1.0
    )
    reasoning: str = Field(
        description="Alasan klasifikasi intent"
    )
    product_keywords: list[str] = Field(
        default=[],
        description="Keywords terkait produk yang disebutkan"
    )
    

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
    vehicle_type: Optional[str] = Field(default="", description="Jenis kendaraan")
    unit_qty: Optional[int] = Field(default=0, description="Jumlah unit")