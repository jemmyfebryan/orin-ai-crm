"""
Dashboard endpoint Pydantic schemas.
Professional multi-card dashboard with various chart types.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# ============================================================================
# OVERVIEW CARD
# ============================================================================

class OverviewMetrics(BaseModel):
    """Overview metrics - key KPIs at a glance."""
    total_customers: int = Field(..., description="Total unique customers (excluding soft-deleted)")
    active_today: int = Field(..., description="Number of conversations started today")
    meetings_booked: int = Field(..., description="Total meetings booked (all time)")
    product_inquiries: int = Field(..., description="Total product inquiries (all time)")
    b2b_customers: int = Field(..., description="Total B2B customers")
    b2c_customers: int = Field(..., description="Total B2C customers")


# ============================================================================
# CONVERSATION TRENDS CARD (Line Chart)
# ============================================================================

class ConversationTrendPoint(BaseModel):
    """Single data point for conversation trend line chart."""
    date: str = Field(..., description="Date in format 'YYYY-MM-DD'")
    count: int = Field(..., description="Number of conversations on this date")
    unique_customers: int = Field(..., description="Number of unique customers on this date")


class ConversationTrendsCard(BaseModel):
    """Conversation trends over time - line chart data."""
    title: str = "Conversation Trends"
    subtitle: str = "Daily conversation volume (last 7 days)"
    period_days: int = 7
    data: List[ConversationTrendPoint]
    total_conversations: int = Field(..., description="Total conversations in period")
    avg_per_day: float = Field(..., description="Average conversations per day")
    growth_percentage: Optional[float] = Field(None, description="Growth % vs previous period")


# ============================================================================
# CUSTOMER ROUTE DISTRIBUTION CARD (Pie Chart)
# ============================================================================

class RouteDistributionItem(BaseModel):
    """Single route distribution item."""
    route: str = Field(..., description="Route type: SALES, ECOMMERCE, SUPPORT")
    count: int = Field(..., description="Number of customers routed to this route")
    percentage: float = Field(..., description="Percentage of total")
    color: str = Field(..., description="Hex color code for chart")


class RouteDistributionCard(BaseModel):
    """Customer route distribution - pie chart data."""
    title: str = "Customer Route Distribution"
    subtitle: str = "How customers are being routed"
    data: List[RouteDistributionItem]
    total_routed: int


# ============================================================================
# INTENT ANALYSIS CARD (Bar Chart)
# ============================================================================

class IntentAnalysisItem(BaseModel):
    """Single intent analysis item."""
    intent: str = Field(..., description="Intent type: greeting, profiling, product_inquiry, etc.")
    count: int = Field(..., description="Number of times this intent was classified")
    avg_confidence: float = Field(..., description="Average confidence score (0-1)")
    color: str = Field(..., description="Hex color code for chart")


class IntentAnalysisCard(BaseModel):
    """Intent classification analysis - horizontal bar chart data."""
    title: str = "Intent Classification Analysis"
    subtitle: str = "Most common customer intents"
    data: List[IntentAnalysisItem]
    total_classified: int


# ============================================================================
# MEETING STATUS CARD (Donut Chart)
# ============================================================================

class MeetingStatusItem(BaseModel):
    """Single meeting status item."""
    status: str = Field(..., description="Meeting status: pending, confirmed, cancelled, completed, rescheduled")
    count: int = Field(..., description="Number of meetings with this status")
    percentage: float = Field(..., description="Percentage of total")
    color: str = Field(..., description="Hex color code for chart")


class MeetingStatusCard(BaseModel):
    """Meeting status distribution - donut chart data."""
    title: str = "Meeting Status Distribution"
    subtitle: str = "Current status of all booked meetings"
    data: List[MeetingStatusItem]
    total_meetings: int


# ============================================================================
# RECENT ACTIVITIES CARD (Table)
# ============================================================================

class RecentActivityItem(BaseModel):
    """Single recent activity item."""
    conversation_id: Optional[str] = Field(None, description="Freshchat conversation ID")
    phone_number: Optional[str] = Field(None, description="Customer phone number")
    contact_name: Optional[str] = Field(None, description="Customer contact name")
    agent_route: Optional[str] = Field(None, description="Route taken: SALES, ECOMMERCE, SUPPORT")
    status: str = Field(..., description="Processing status: success, failed, timeout, etc.")
    processing_duration_ms: Optional[int] = Field(None, description="Processing time in milliseconds")
    timestamp: str = Field(..., description="Activity timestamp in ISO format")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class RecentActivitiesCard(BaseModel):
    """Recent activities - table data."""
    title: str = "Recent Activities"
    subtitle: str = "Latest chat conversations"
    max_items: int = 10
    data: List[RecentActivityItem]


# ============================================================================
# PERFORMANCE METRICS CARD (Key Value Cards)
# ============================================================================

class PerformanceMetrics(BaseModel):
    """System performance metrics."""
    title: str = "Performance Metrics"
    avg_processing_time_ms: float = Field(..., description="Average processing time (milliseconds)")
    success_rate: float = Field(..., description="Success rate (percentage)")
    total_processed: int = Field(..., description="Total conversations processed")
    timeout_count: int = Field(..., description="Number of timeouts")
    human_takeover_count: int = Field(..., description="Number of human takeovers")
    avg_ai_replies: float = Field(..., description="Average AI replies per conversation")


# ============================================================================
# B2B VS B2C CARD (Pie Chart)
# ============================================================================

class B2BB2CItem(BaseModel):
    """Single B2B/B2C item."""
    type: str = Field(..., description="Customer type: B2B or B2C")
    count: int = Field(..., description="Number of customers")
    percentage: float = Field(..., description="Percentage of total")
    color: str = Field(..., description="Hex color code for chart")


class B2BB2CCard(BaseModel):
    """B2B vs B2C distribution - pie chart data."""
    title: str = "Customer Type Distribution"
    subtitle: str = "B2B vs B2C customers"
    data: List[B2BB2CItem]
    total_customers: int


# ============================================================================
# PRODUCT INQUIRY TRENDS CARD (Bar Chart)
# ============================================================================

class ProductInquiryItem(BaseModel):
    """Single product inquiry item."""
    product_type: str = Field(..., description="Product type: TANAM, INSTAN, etc.")
    count: int = Field(..., description="Number of inquiries")
    vehicle_type: Optional[str] = Field(None, description="Vehicle type if available")


class ProductInquiryCard(BaseModel):
    """Product inquiry trends - bar chart data."""
    title: str = "Product Inquiry Trends"
    subtitle: str = "Most inquired product categories"
    data: List[ProductInquiryItem]
    total_inquiries: int


# ============================================================================
# TOP INQUIRIES CARD (Table)
# ============================================================================

class TopInquiryItem(BaseModel):
    """Single top inquiry item."""
    customer_name: Optional[str] = Field(None, description="Customer name")
    phone_number: Optional[str] = Field(None, description="Customer phone number")
    product_type: Optional[str] = Field(None, description="Product type inquired")
    vehicle_type: Optional[str] = Field(None, description="Vehicle type")
    unit_qty: Optional[int] = Field(None, description="Unit quantity")
    status: str = Field(..., description="Inquiry status: pending, link_sent, interested, converted, lost")
    created_at: str = Field(..., description="Inquiry timestamp in ISO format")


class TopInquiriesCard(BaseModel):
    """Top product inquiries - table data."""
    title: str = "Recent Product Inquiries"
    subtitle: str = "Latest product inquiries from customers"
    max_items: int = 10
    data: List[TopInquiryItem]


# ============================================================================
# COMPLETE DASHBOARD RESPONSE
# ============================================================================

class DashboardResponse(BaseModel):
    """Complete dashboard response with all cards."""
    success: bool = True
    message: str = "Dashboard data retrieved successfully"
    generated_at: str = Field(..., description="Timestamp when dashboard was generated (ISO format)")
    timezone: str = "Asia/Jakarta (WIB)"

    # Card 1: Overview Metrics (Key Value Cards)
    overview: OverviewMetrics

    # Card 2: Conversation Trends (Line Chart)
    conversation_trends: ConversationTrendsCard

    # Card 3: Customer Route Distribution (Pie Chart)
    route_distribution: RouteDistributionCard

    # Card 4: Intent Analysis (Bar Chart)
    intent_analysis: IntentAnalysisCard

    # Card 5: Meeting Status Distribution (Donut Chart)
    meeting_status: MeetingStatusCard

    # Card 6: Recent Activities (Table)
    recent_activities: RecentActivitiesCard

    # Card 7: Performance Metrics (Key Value Cards)
    performance: PerformanceMetrics

    # Card 8: B2B vs B2C (Pie Chart)
    b2b_b2c_distribution: B2BB2CCard

    # Card 9: Product Inquiry Trends (Bar Chart)
    product_inquiries: ProductInquiryCard

    # Card 10: Top Inquiries (Table)
    top_inquiries: TopInquiriesCard


# ============================================================================
# DASHBOARD FILTER REQUEST (Optional)
# ============================================================================

class DashboardFilterRequest(BaseModel):
    """Optional filter request for dashboard data."""
    period_days: int = Field(7, description="Number of days for trend analysis (default: 7)")
    include_recent_activities: bool = Field(True, description="Include recent activities table")
    recent_activities_limit: int = Field(10, description="Max items in recent activities table")
    include_top_inquiries: bool = Field(True, description="Include top inquiries table")
    top_inquiries_limit: int = Field(10, description="Max items in top inquiries table")
