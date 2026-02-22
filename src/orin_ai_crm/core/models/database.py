import os
import enum
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey

# Setup WIB timezone (UTC+7)
WIB = timezone(timedelta(hours=7))

# Load environment variables
load_dotenv()

DB_URL = f"mysql+aiomysql://{os.getenv('DB_USERNAME')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_DATABASE')}"

engine = create_async_engine(DB_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class ActionType(str, enum.Enum):
    MEETING_BOOKED = "meeting_booked"
    QUOTE_REQUESTED = "quote_requested"
    PRODUCT_INQUIRY = "product_inquiry"
    COMPLAINT = "complaint"
    FOLLOW_UP = "follow_up"
    OTHER = "other"

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=True)
    lid_number = Column(String(50), unique=True, index=True, nullable=True)
    contact_name = Column(String(100), nullable=True)  # Nama kontak dari WA
    name = Column(String(100), nullable=True)  # Nama asli customer
    domicile = Column(String(100), nullable=True)
    vehicle_type = Column(String(50), nullable=True)
    unit_qty = Column(Integer, nullable=True)
    is_b2b = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(WIB))
    updated_at = Column(DateTime, default=lambda: datetime.now(WIB), onupdate=lambda: datetime.now(WIB))

class LeadRouting(Base):
    __tablename__ = "leads_routing"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True)
    route_type = Column(String(20))  # SALES, ECOMMERCE, SUPPORT
    status = Column(String(50), default="pending")  # pending, contacted, converted, lost
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(WIB))
    updated_at = Column(DateTime, default=lambda: datetime.now(WIB), onupdate=lambda: datetime.now(WIB))

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True, nullable=True)
    message_role = Column(String(20))  # user, ai, system
    content = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(WIB))

class CustomerAction(Base):
    """Table untuk tracking action penting seperti meeting booking, quote request, dll"""
    __tablename__ = "customer_actions"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True)
    action_type = Column(String(50), nullable=False)  # meeting_booked, quote_requested, etc
    action_data = Column(Text, nullable=True)  # JSON data untuk detail action (meeting time, dll)
    status = Column(String(50), default="pending")  # pending, completed, cancelled
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(WIB))
    updated_at = Column(DateTime, default=lambda: datetime.now(WIB), onupdate=lambda: datetime.now(WIB))