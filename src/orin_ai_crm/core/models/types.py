from typing import Literal
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

class CustomerProfile(BaseModel):
    phone_number: str = ""  # Nomor WA customer
    lid_number: str = ""  # Nomor LID WA customer
    source: str = ""  # Customer berasal dari mana
    journey: Literal["profiling", "educating", "handover"] = "profiling"
    category: Literal["unknwon", "personal", "business", "other"] = "unknown"