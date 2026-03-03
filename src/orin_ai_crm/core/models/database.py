import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float, JSON

# Setup WIB timezone (UTC+7)
WIB = timezone(timedelta(hours=7))

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
    lid_number = Column(String(50), unique=True, index=True, nullable=True)
    contact_name = Column(String(100), nullable=True)  # Nama kontak dari WA
    name = Column(String(100), nullable=True)  # Nama asli customer
    domicile = Column(String(100), nullable=True)
    vehicle_id = Column(Integer, nullable=True, default=-1)  # ID from vehicles table in VPS DB
    vehicle_alias = Column(String(100), nullable=True)  # Custom text from user (e.g., "CRF", "Avanza")
    unit_qty = Column(Integer, nullable=True)
    is_b2b = Column(Boolean, default=False)
    human_takeover = Column(Boolean, default=False)  # Flag untuk human takeover when AI cannot handle
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

class CustomerMeeting(Base):
    """Table untuk meeting bookings - dedicated table untuk meeting management"""
    __tablename__ = "customer_meetings"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True)
    meeting_datetime = Column(DateTime, nullable=True)  # WIB timezone
    meeting_format = Column(String(50), default="online")  # online, offline, hybrid
    status = Column(String(50), default="pending")  # pending, confirmed, cancelled, completed, rescheduled
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(WIB))
    updated_at = Column(DateTime, default=lambda: datetime.now(WIB), onupdate=lambda: datetime.now(WIB))

class ProductInquiry(Base):
    """Table untuk product inquiries yang mengarah ke e-commerce"""
    __tablename__ = "product_inquiries"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True)
    product_type = Column(String(100), nullable=True)  # TANAM, INSTAN, atau specific product
    vehicle_type = Column(String(50), nullable=True)
    unit_qty = Column(Integer, nullable=True)
    recommended_product = Column(String(200), nullable=True)  # Nama produk yang direkomendasikan
    ecommerce_link = Column(String(500), nullable=True)  # Link ke Tokopedia/Shopee/Official Store
    status = Column(String(50), default="pending")  # pending, link_sent, interested, converted, lost
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(WIB))
    updated_at = Column(DateTime, default=lambda: datetime.now(WIB), onupdate=lambda: datetime.now(WIB))

class CustomerAction(Base):
    """Table untuk tracking general action lainnya (complaint, follow-up, dll)"""
    __tablename__ = "customer_actions"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True)
    action_type = Column(String(50), nullable=False)  # complaint, follow_up, other, dll (NOT meeting or inquiry)
    action_data = Column(Text, nullable=True)  # JSON data untuk detail action
    status = Column(String(50), default="pending")  # pending, completed, cancelled
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(WIB))
    updated_at = Column(DateTime, default=lambda: datetime.now(WIB), onupdate=lambda: datetime.now(WIB))

class Product(Base):
    """Table master produk - menyimpan semua informasi produk GPS"""
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)  # Nama produk
    sku = Column(String(100), unique=True, index=True)  # SKU/Code produk
    category = Column(String(50), nullable=False)  # TANAM, INSTAN
    subcategory = Column(String(50), nullable=True)  # OBU F, OBU V, OBU D, T1, T
    vehicle_type = Column(String(50), nullable=True)  # mobil, motor, alat berat, truck
    description = Column(Text, nullable=True)  # Deskripsi lengkap
    features = Column(Text, nullable=True)  # Fitur-fitur dalam JSON
    price = Column(Integer, nullable=True)  # Harga dalam Rupiah
    installation_type = Column(String(50), nullable=False)  # pasang_technisi, colok_sendiri
    can_shutdown_engine = Column(Boolean, default=False)  # Bisa matikan mesin?
    is_realtime_tracking = Column(Boolean, default=True)  # Lacak real-time?
    ecommerce_links = Column(Text, nullable=True)  # JSON links ke Tokopedia, Shopee, etc
    images = Column(Text, nullable=True)  # JSON URLs gambar produk
    specifications = Column(Text, nullable=True)  # Spesifikasi teknis dalam JSON
    compatibility = Column(Text, nullable=True)  # JSON info kompatibilitas kendaraan
    is_active = Column(Boolean, default=True)  # Produk masih aktif?
    sort_order = Column(Integer, default=0)  # Urutan untuk sorting
    created_at = Column(DateTime, default=lambda: datetime.now(WIB))
    updated_at = Column(DateTime, default=lambda: datetime.now(WIB), onupdate=lambda: datetime.now(WIB))

class IntentClassification(Base):
    """Table untuk menyimpan intent classification - dataset untuk training model independen atau sebagai additional dataset"""
    __tablename__ = "intent_classifications"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True)
    intent = Column(String(100), nullable=False, index=True)  # Intent type: greeting, profiling, product_inquiry, meeting_request, complaint, support, reschedule, order, general_question
    confidence = Column(Float, nullable=False)  # Confidence score 0.0 - 1.0
    reasoning = Column(Text, nullable=True)  # Alasan klasifikasi dari LLM
    product_keywords = Column(JSON, nullable=True)  # List kata kunci terkait produk
    route = Column(String(50), nullable=True)  # Route yang diambil: UNASSIGNED, SALES, ECOMMERCE, SUPPORT, PRODUCT_INFO
    step = Column(String(50), nullable=True)  # Step yang dieksekusi
    message_context = Column(Text, nullable=True)  # Context pesan user (last message for reference)
    created_at = Column(DateTime, default=lambda: datetime.now(WIB))