from typing import Annotated, Sequence, TypedDict
import operator
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    phone_number: str
    traffic_source: str 
    step: str 
    route: str 
    customer_data: dict 

class CustomerProfile(BaseModel):
    name: str = Field(description="Nama pelanggan, kosongkan jika belum ada")
    domicile: str = Field(description="Domisili atau kota pelanggan, kosongkan jika belum ada")
    vehicle_type: str = Field(description="Jenis kendaraan: mobil, motor, alat berat, atau lainnya")
    unit_qty: int = Field(description="Jumlah unit yang ingin dipasang, 0 jika belum menyebutkan angka")
    is_b2b: bool = Field(description="True jika ini perusahaan/armada operasional, False jika pemakaian pribadi")