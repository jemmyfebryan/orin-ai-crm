import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey

# Load environment variables
load_dotenv()

DB_URL = f"mysql+aiomysql://{os.getenv('DB_USERNAME')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_DATABASE')}"

engine = create_async_engine(DB_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=True)
    lid_number = Column(String(50), unique=True, index=True, nullable=True)  # WhatsApp LID untuk migrasi
    contact_name = Column(String(100), nullable=True)  # Nama kontak dari WA
    name = Column(String(100), nullable=True)  # Nama asli customer
    domicile = Column(String(100), nullable=True)
    vehicle_type = Column(String(50), nullable=True)
    unit_qty = Column(Integer, nullable=True)
    is_b2b = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class LeadRouting(Base):
    __tablename__ = "leads_routing"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    route_type = Column(String(20))
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), index=True, nullable=True)
    lid_number = Column(String(50), index=True, nullable=True)  # WhatsApp LID
    message_role = Column(String(20))
    content = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))