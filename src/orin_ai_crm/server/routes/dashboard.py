"""
Dashboard endpoint for analytics and insights.
Provides comprehensive metrics across all business dimensions.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, and_, desc

from fastapi import APIRouter, HTTPException

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import (
    AsyncSessionLocal, Customer, LeadRouting,
    CustomerMeeting, ProductInquiry, IntentClassification, ChatLog
)
from src.orin_ai_crm.core.utils.db_retry import retry_db_endpoint
from src.orin_ai_crm.server.schemas.dashboard import (
    DashboardResponse, OverviewMetrics,
    ConversationTrendsCard, ConversationTrendPoint,
    RouteDistributionCard, RouteDistributionItem,
    IntentAnalysisCard, IntentAnalysisItem,
    MeetingStatusCard, MeetingStatusItem,
    RecentActivitiesCard, RecentActivityItem,
    PerformanceMetrics,
    B2BB2CCard, B2BB2CItem,
    ProductInquiryCard, ProductInquiryItem,
    TopInquiriesCard, TopInquiryItem
)

# Setup WIB timezone (UTC+7)
WIB = timezone(timedelta(hours=7))

logger = get_logger(__name__)
router = APIRouter()


# Color palette for charts
COLORS = {
    'sales': '#3B82F6',      # Blue
    'ecommerce': '#10B981',  # Green
    'support': '#F59E0B',    # Amber
    'pending': '#6B7280',    # Gray
    'confirmed': '#10B981',  # Green
    'cancelled': '#EF4444',  # Red
    'completed': '#3B82F6',  # Blue
    'rescheduled': '#F59E0B', # Amber
    'b2b': '#8B5CF6',        # Purple
    'b2c': '#EC4899',        # Pink
    'tanam': '#3B82F6',      # Blue
    'instan': '#10B981',     # Green
}


@retry_db_endpoint()
@router.get("/dashboard", response_model=DashboardResponse)
@router.get("/dashboard/", response_model=DashboardResponse)
async def get_dashboard():
    """
    Get comprehensive dashboard data with all metrics and charts.

    Returns 10 cards:
    1. Overview Metrics - Key KPIs
    2. Conversation Trends - Line chart (last 7 days)
    3. Customer Route Distribution - Pie chart
    4. Intent Analysis - Bar chart
    5. Meeting Status Distribution - Donut chart
    6. Recent Activities - Table
    7. Performance Metrics - Key values
    8. B2B vs B2C Distribution - Pie chart
    9. Product Inquiry Trends - Bar chart
    10. Top Inquiries - Table
    """
    try:
        logger.info("Generating dashboard data...")

        # Get current time in WIB
        now_wib = datetime.now(WIB)
        today_start = now_wib.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = today_start - timedelta(days=7)

        # Fetch all data in parallel using a single session
        async with AsyncSessionLocal() as db:
            # ========================================
            # CARD 1: OVERVIEW METRICS
            # ========================================
            total_customers_result = await db.execute(
                select(func.count(Customer.id)).where(Customer.deleted_at.is_(None))
            )
            total_customers = total_customers_result.scalar() or 0

            b2b_result = await db.execute(
                select(func.count(Customer.id)).where(
                    and_(Customer.deleted_at.is_(None), Customer.is_b2b == True)
                )
            )
            b2b_customers = b2b_result.scalar() or 0

            b2c_customers = total_customers - b2b_customers

            active_today_result = await db.execute(
                select(func.count(func.distinct(ChatLog.customer_id))).where(
                    ChatLog.started_at >= today_start
                )
            )
            active_today = active_today_result.scalar() or 0

            meetings_booked_result = await db.execute(
                select(func.count(CustomerMeeting.id))
            )
            meetings_booked = meetings_booked_result.scalar() or 0

            product_inquiries_result = await db.execute(
                select(func.count(ProductInquiry.id))
            )
            product_inquiries = product_inquiries_result.scalar() or 0

            overview = OverviewMetrics(
                total_customers=total_customers,
                active_today=active_today,
                meetings_booked=meetings_booked,
                product_inquiries=product_inquiries,
                b2b_customers=b2b_customers,
                b2c_customers=b2c_customers
            )

            # ========================================
            # CARD 2: CONVERSATION TRENDS (Line Chart)
            # ========================================
            conversation_trends_result = await db.execute(
                select(
                    func.date(ChatLog.started_at).label('date'),
                    func.count(func.distinct(ChatLog.conversation_id)).label('count'),
                    func.count(func.distinct(ChatLog.customer_id)).label('unique_customers')
                )
                .where(ChatLog.started_at >= week_ago)
                .group_by(func.date(ChatLog.started_at))
                .order_by(func.date(ChatLog.started_at))
            )
            trend_rows = conversation_trends_result.all()

            trend_data = []
            total_conv = 0
            for date, count, unique in trend_rows:
                trend_data.append(ConversationTrendPoint(
                    date=str(date),
                    count=count,
                    unique_customers=unique
                ))
                total_conv += count

            avg_per_day = total_conv / 7 if total_conv > 0 else 0

            conversation_trends = ConversationTrendsCard(
                title="Conversation Trends",
                subtitle="Daily conversation volume (last 7 days)",
                period_days=7,
                data=trend_data,
                total_conversations=total_conv,
                avg_per_day=round(avg_per_day, 2)
            )

            # ========================================
            # CARD 3: CUSTOMER ROUTE DISTRIBUTION (Pie Chart)
            # ========================================
            route_dist_result = await db.execute(
                select(
                    LeadRouting.route_type,
                    func.count(LeadRouting.id).label('count')
                )
                .group_by(LeadRouting.route_type)
            )
            route_rows = route_dist_result.all()

            total_routed = sum(row[1] for row in route_rows)
            route_data = []
            for route_type, count in route_rows:
                if route_type and count > 0:
                    percentage = (count / total_routed * 100) if total_routed > 0 else 0
                    color_key = route_type.lower()
                    route_data.append(RouteDistributionItem(
                        route=route_type,
                        count=count,
                        percentage=round(percentage, 2),
                        color=COLORS.get(color_key, '#6B7280')
                    ))

            route_distribution = RouteDistributionCard(
                title="Customer Route Distribution",
                subtitle="How customers are being routed",
                data=route_data,
                total_routed=total_routed
            )

            # ========================================
            # CARD 4: INTENT ANALYSIS (Bar Chart)
            # ========================================
            intent_result = await db.execute(
                select(
                    IntentClassification.intent,
                    func.count(IntentClassification.id).label('count'),
                    func.avg(IntentClassification.confidence).label('avg_confidence')
                )
                .group_by(IntentClassification.intent)
                .order_by(desc(func.count(IntentClassification.id)))
                .limit(10)
            )
            intent_rows = intent_result.all()

            total_classified = sum(row[1] for row in intent_rows)
            intent_data = []
            colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
                     '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1']
            for i, (intent, count, avg_conf) in enumerate(intent_rows):
                if intent and count > 0:
                    intent_data.append(IntentAnalysisItem(
                        intent=intent,
                        count=count,
                        avg_confidence=round(float(avg_conf or 0), 3),
                        color=colors[i % len(colors)]
                    ))

            intent_analysis = IntentAnalysisCard(
                title="Intent Classification Analysis",
                subtitle="Most common customer intents",
                data=intent_data,
                total_classified=total_classified
            )

            # ========================================
            # CARD 5: MEETING STATUS DISTRIBUTION (Donut Chart)
            # ========================================
            meeting_status_result = await db.execute(
                select(
                    CustomerMeeting.status,
                    func.count(CustomerMeeting.id).label('count')
                )
                .group_by(CustomerMeeting.status)
            )
            meeting_status_rows = meeting_status_result.all()

            total_meetings = sum(row[1] for row in meeting_status_rows)
            meeting_status_data = []
            for status, count in meeting_status_rows:
                if status and count > 0:
                    percentage = (count / total_meetings * 100) if total_meetings > 0 else 0
                    color_key = status.lower()
                    meeting_status_data.append(MeetingStatusItem(
                        status=status,
                        count=count,
                        percentage=round(percentage, 2),
                        color=COLORS.get(color_key, '#6B7280')
                    ))

            meeting_status = MeetingStatusCard(
                title="Meeting Status Distribution",
                subtitle="Current status of all booked meetings",
                data=meeting_status_data,
                total_meetings=total_meetings
            )

            # ========================================
            # CARD 6: RECENT ACTIVITIES (Table)
            # ========================================
            recent_activities_result = await db.execute(
                select(ChatLog)
                .order_by(desc(ChatLog.started_at))
                .limit(10)
            )
            recent_logs = recent_activities_result.scalars().all()

            recent_activities_data = []
            for log in recent_logs:
                recent_activities_data.append(RecentActivityItem(
                    conversation_id=log.conversation_id,
                    phone_number=log.phone_number,
                    contact_name=log.contact_name,
                    agent_route=log.agent_route,
                    status=log.status or "unknown",
                    processing_duration_ms=log.processing_duration_ms,
                    timestamp=log.started_at.isoformat() if log.started_at else None,
                    error_message=log.error_message
                ))

            recent_activities = RecentActivitiesCard(
                title="Recent Activities",
                subtitle="Latest chat conversations",
                max_items=10,
                data=recent_activities_data
            )

            # ========================================
            # CARD 7: PERFORMANCE METRICS
            # ========================================
            perf_avg_time_result = await db.execute(
                select(func.avg(ChatLog.processing_duration_ms)).where(
                    ChatLog.processing_duration_ms.isnot(None)
                )
            )
            avg_processing_time = perf_avg_time_result.scalar() or 0

            perf_total_result = await db.execute(
                select(func.count(ChatLog.id))
            )
            total_processed = perf_total_result.scalar() or 0

            perf_success_result = await db.execute(
                select(func.count(ChatLog.id)).where(ChatLog.status == "success")
            )
            success_count = perf_success_result.scalar() or 0
            success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0

            timeout_result = await db.execute(
                select(func.count(ChatLog.id)).where(ChatLog.timeout_triggered == True)
            )
            timeout_count = timeout_result.scalar() or 0

            takeover_result = await db.execute(
                select(func.count(ChatLog.id)).where(ChatLog.human_takeover_triggered == True)
            )
            takeover_count = takeover_result.scalar() or 0

            avg_replies_result = await db.execute(
                select(func.avg(ChatLog.ai_reply_count)).where(
                    ChatLog.ai_reply_count.isnot(None)
                )
            )
            avg_replies = avg_replies_result.scalar() or 0

            performance = PerformanceMetrics(
                title="Performance Metrics",
                avg_processing_time_ms=round(float(avg_processing_time), 2),
                success_rate=round(success_rate, 2),
                total_processed=total_processed,
                timeout_count=timeout_count,
                human_takeover_count=takeover_count,
                avg_ai_replies=round(float(avg_replies), 2)
            )

            # ========================================
            # CARD 8: B2B VS B2C DISTRIBUTION (Pie Chart)
            # ========================================
            b2b_b2c_data = []
            if b2b_customers > 0:
                b2b_percentage = (b2b_customers / total_customers * 100) if total_customers > 0 else 0
                b2b_b2c_data.append(B2BB2CItem(
                    type="B2B",
                    count=b2b_customers,
                    percentage=round(b2b_percentage, 2),
                    color=COLORS['b2b']
                ))
            if b2c_customers > 0:
                b2c_percentage = (b2c_customers / total_customers * 100) if total_customers > 0 else 0
                b2b_b2c_data.append(B2BB2CItem(
                    type="B2C",
                    count=b2c_customers,
                    percentage=round(b2c_percentage, 2),
                    color=COLORS['b2c']
                ))

            b2b_b2c_distribution = B2BB2CCard(
                title="Customer Type Distribution",
                subtitle="B2B vs B2C customers",
                data=b2b_b2c_data,
                total_customers=total_customers
            )

            # ========================================
            # CARD 9: PRODUCT INQUIRY TRENDS (Bar Chart)
            # ========================================
            product_inquiry_result = await db.execute(
                select(
                    ProductInquiry.product_type,
                    func.count(ProductInquiry.id).label('count')
                )
                .group_by(ProductInquiry.product_type)
                .order_by(desc(func.count(ProductInquiry.id)))
            )
            product_inquiry_rows = product_inquiry_result.all()

            total_prod_inquiries = sum(row[1] for row in product_inquiry_rows)
            product_inquiry_data = []
            for i, (product_type, count) in enumerate(product_inquiry_rows):
                if product_type and count > 0:
                    product_inquiry_data.append(ProductInquiryItem(
                        product_type=product_type,
                        count=count,
                        vehicle_type=None
                    ))

            product_inquiries = ProductInquiryCard(
                title="Product Inquiry Trends",
                subtitle="Most inquired product categories",
                data=product_inquiry_data,
                total_inquiries=total_prod_inquiries
            )

            # ========================================
            # CARD 10: TOP INQUIRIES (Table)
            # ========================================
            top_inquiries_result = await db.execute(
                select(ProductInquiry, Customer)
                .join(Customer, ProductInquiry.customer_id == Customer.id)
                .order_by(desc(ProductInquiry.created_at))
                .limit(10)
            )
            top_inquiry_rows = top_inquiries_result.all()

            top_inquiries_data = []
            for inquiry, customer in top_inquiry_rows:
                top_inquiries_data.append(TopInquiryItem(
                    customer_name=customer.name if customer else None,
                    phone_number=customer.phone_number if customer else None,
                    product_type=inquiry.product_type,
                    vehicle_type=inquiry.vehicle_type,
                    unit_qty=inquiry.unit_qty,
                    status=inquiry.status,
                    created_at=inquiry.created_at.isoformat() if inquiry.created_at else None
                ))

            top_inquiries = TopInquiriesCard(
                title="Recent Product Inquiries",
                subtitle="Latest product inquiries from customers",
                max_items=10,
                data=top_inquiries_data
            )

        # ========================================
        # BUILD COMPLETE RESPONSE
        # ========================================
        response = DashboardResponse(
            success=True,
            message="Dashboard data retrieved successfully",
            generated_at=now_wib.isoformat(),
            timezone="Asia/Jakarta (WIB)",
            overview=overview,
            conversation_trends=conversation_trends,
            route_distribution=route_distribution,
            intent_analysis=intent_analysis,
            meeting_status=meeting_status,
            recent_activities=recent_activities,
            performance=performance,
            b2b_b2c_distribution=b2b_b2c_distribution,
            product_inquiries=product_inquiries,
            top_inquiries=top_inquiries
        )

        logger.info("Dashboard data generated successfully")
        return response

    except Exception as e:
        logger.error(f"Error generating dashboard: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating dashboard: {str(e)}")
