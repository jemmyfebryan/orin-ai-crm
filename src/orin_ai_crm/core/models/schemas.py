from typing import Annotated, Sequence, TypedDict, Optional
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