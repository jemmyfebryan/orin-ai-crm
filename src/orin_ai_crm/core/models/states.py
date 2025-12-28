import operator
from typing import Optional, Annotated, List, TypedDict

from pydantic import BaseModel, Field
from langchain.messages import AnyMessage

from src.orin_ai_crm.core.models.types import CustomerProfile

class WAState(TypedDict):
    move_to_human_agent: bool = False  # Apakah harus pindah ke human
    send_contact: List = []  # Mengirim kontak Sales
    send_sticker: List = []  # Mengirim sticker
    messages_to_send: List[str] = []  # Pesan yang rencananya akan dikirim

class CRMState(TypedDict):
    """State yang disimpan di setiap session (Phone Number)"""
    messages: Annotated[list[AnyMessage], operator.add]
    customer_profile: Optional[CustomerProfile] = Field(default_factory=dict)
    wa_state: Optional[WAState] = Field(default_factory=dict)
    llm_calls: int = 0