# Dashboard API Documentation

## Overview

The Dashboard API provides comprehensive analytics and insights for the ORIN AI CRM system. It returns multi-card data suitable for building professional dashboard interfaces with various chart types (line charts, pie charts, bar charts, tables, and key metrics).

## Endpoint

```
GET /dashboard
```

## Response Structure

The response contains 10 cards, each with specific data suitable for different visualization types:

### Response Schema

```typescript
interface DashboardResponse {
  success: boolean;
  message: string;
  generated_at: string;  // ISO 8601 timestamp
  timezone: string;      // "Asia/Jakarta (WIB)"

  // Card 1: Overview Metrics (Key Value Cards)
  overview: OverviewMetrics;

  // Card 2: Conversation Trends (Line Chart)
  conversation_trends: ConversationTrendsCard;

  // Card 3: Customer Route Distribution (Pie Chart)
  route_distribution: RouteDistributionCard;

  // Card 4: Intent Analysis (Bar Chart)
  intent_analysis: IntentAnalysisCard;

  // Card 5: Meeting Status Distribution (Donut Chart)
  meeting_status: MeetingStatusCard;

  // Card 6: Recent Activities (Table)
  recent_activities: RecentActivitiesCard;

  // Card 7: Performance Metrics (Key Value Cards)
  performance: PerformanceMetrics;

  // Card 8: B2B vs B2C Distribution (Pie Chart)
  b2b_b2c_distribution: B2BB2CCard;

  // Card 9: Product Inquiry Trends (Bar Chart)
  product_inquiries: ProductInquiryCard;

  // Card 10: Top Inquiries (Table)
  top_inquiries: TopInquiriesCard;
}
```

---

## Card 1: Overview Metrics

**Visualization Type:** Key Value Cards (4-6 large number displays)

**Purpose:** Display key KPIs at a glance

### Schema

```typescript
interface OverviewMetrics {
  total_customers: number;      // Total unique customers
  active_today: number;         // Conversations started today
  meetings_booked: number;      // Total meetings booked (all time)
  product_inquiries: number;    // Total product inquiries (all time)
  b2b_customers: number;        // Total B2B customers
  b2c_customers: number;        // Total B2C customers
}
```

### Frontend Implementation Tips

- Display as 6 cards in a grid layout (3 columns x 2 rows on desktop, 2 columns on tablet, 1 column on mobile)
- Use large, bold numbers
- Add labels below each number
- Consider using icons for each metric
- Add color coding (e.g., green for positive metrics)
- Example icons:
  - `total_customers`: Users icon
  - `active_today`: Activity/Messages icon
  - `meetings_booked`: Calendar icon
  - `product_inquiries`: Shopping cart icon
  - `b2b_customers`: Building/Office icon
  - `b2c_customers`: User icon

---

## Card 2: Conversation Trends

**Visualization Type:** Line Chart

**Purpose:** Show conversation volume over time (last 7 days)

### Schema

```typescript
interface ConversationTrendsCard {
  title: string;           // "Conversation Trends"
  subtitle: string;        // "Daily conversation volume (last 7 days)"
  period_days: number;     // 7
  data: ConversationTrendPoint[];
  total_conversations: number;
  avg_per_day: number;
}

interface ConversationTrendPoint {
  date: string;           // Format: "YYYY-MM-DD"
  count: number;          // Number of conversations
  unique_customers: number; // Number of unique customers
}
```

### Frontend Implementation Tips

- Use a line chart with dates on X-axis and conversation count on Y-axis
- Display both `count` (total conversations) and `unique_customers` as two lines
- Add tooltips showing exact values on hover
- Consider showing trend percentage vs previous period
- X-axis: Show dates in short format (e.g., "Apr 01", "Apr 02")
- Y-axis: Auto-scale based on max value
- Add colors:
  - Total conversations: Primary color (blue)
  - Unique customers: Secondary color (green)

### Example Data

```json
{
  "title": "Conversation Trends",
  "subtitle": "Daily conversation volume (last 7 days)",
  "period_days": 7,
  "data": [
    {"date": "2026-03-27", "count": 45, "unique_customers": 38},
    {"date": "2026-03-28", "count": 52, "unique_customers": 44},
    {"date": "2026-03-29", "count": 38, "unique_customers": 32},
    {"date": "2026-03-30", "count": 61, "unique_customers": 53},
    {"date": "2026-03-31", "count": 55, "unique_customers": 47},
    {"date": "2026-04-01", "count": 48, "unique_customers": 41},
    {"date": "2026-04-02", "count": 67, "unique_customers": 58}
  ],
  "total_conversations": 366,
  "avg_per_day": 52.29
}
```

---

## Card 3: Customer Route Distribution

**Visualization Type:** Pie Chart

**Purpose:** Show how customers are being routed to different agents

### Schema

```typescript
interface RouteDistributionCard {
  title: string;           // "Customer Route Distribution"
  subtitle: string;        // "How customers are being routed"
  data: RouteDistributionItem[];
  total_routed: number;
}

interface RouteDistributionItem {
  route: string;           // "SALES", "ECOMMERCE", "SUPPORT"
  count: number;
  percentage: number;      // 0-100
  color: string;           // Hex color code (e.g., "#3B82F6")
}
```

### Frontend Implementation Tips

- Use a pie chart or donut chart
- Show route labels with percentages
- Use the provided `color` field for each slice
- Add legend if needed
- On hover/click, show count and percentage
- Consider adding total count in center of donut chart

### Color Scheme

The API provides colors, but here's the reference:
- SALES: `#3B82F6` (Blue)
- ECOMMERCE: `#10B981` (Green)
- SUPPORT: `#F59E0B` (Amber)

---

## Card 4: Intent Analysis

**Visualization Type:** Horizontal Bar Chart

**Purpose:** Show most common customer intents

### Schema

```typescript
interface IntentAnalysisCard {
  title: string;           // "Intent Classification Analysis"
  subtitle: string;        // "Most common customer intents"
  data: IntentAnalysisItem[];
  total_classified: number;
}

interface IntentAnalysisItem {
  intent: string;          // Intent type (e.g., "product_inquiry")
  count: number;
  avg_confidence: number;  // 0.0 to 1.0
  color: string;           // Hex color code
}
```

### Frontend Implementation Tips

- Use a horizontal bar chart (intents on Y-axis, counts on X-axis)
- Sort by count (descending)
- Display intent labels, not just values
- Show count on each bar or in tooltip
- Add confidence score as additional info (e.g., in tooltip or subtitle)
- Use provided colors for each bar
- Limit to top 10 intents

---

## Card 5: Meeting Status Distribution

**Visualization Type:** Donut Chart

**Purpose:** Show current status of all booked meetings

### Schema

```typescript
interface MeetingStatusCard {
  title: string;           // "Meeting Status Distribution"
  subtitle: string;        // "Current status of all booked meetings"
  data: MeetingStatusItem[];
  total_meetings: number;
}

interface MeetingStatusItem {
  status: string;          // "pending", "confirmed", "cancelled", "completed", "rescheduled"
  count: number;
  percentage: number;      // 0-100
  color: string;           // Hex color code
}
```

### Frontend Implementation Tips

- Use a donut chart with status as slices
- Display total meetings in center
- Use provided colors (semantic colors)
- Add legend with status names
- On hover, show count and percentage

### Color Scheme

- pending: `#6B7280` (Gray)
- confirmed: `#10B981` (Green)
- cancelled: `#EF4444` (Red)
- completed: `#3B82F6` (Blue)
- rescheduled: `#F59E0B` (Amber)

---

## Card 6: Recent Activities

**Visualization Type:** Table

**Purpose:** Show latest chat conversations

### Schema

```typescript
interface RecentActivitiesCard {
  title: string;           // "Recent Activities"
  subtitle: string;        // "Latest chat conversations"
  max_items: number;       // 10
  data: RecentActivityItem[];
}

interface RecentActivityItem {
  conversation_id: string | null;
  phone_number: string | null;
  contact_name: string | null;
  agent_route: string | null;     // "SALES", "ECOMMERCE", "SUPPORT"
  status: string;                 // "success", "failed", "timeout", etc.
  processing_duration_ms: number | null;
  timestamp: string;              // ISO 8601 format
  error_message: string | null;
}
```

### Frontend Implementation Tips

- Display as a table with the following columns:
  1. Time (formatted from `timestamp`, e.g., "19:30" or "2 hours ago")
  2. Customer (`contact_name` or `phone_number`)
  3. Route (`agent_route`)
  4. Status (badge with color coding)
  5. Duration (formatted from `processing_duration_ms`, e.g., "1.2s")

- Status color coding:
  - success: Green
  - failed: Red
  - timeout: Orange
  - in_progress: Blue
  - cancelled: Gray

- Add hover effects on rows
- Make rows clickable to view details (future feature)
- Format timestamp to relative time (e.g., "5 minutes ago")
- Truncate long text with ellipsis

---

## Card 7: Performance Metrics

**Visualization Type:** Key Value Cards

**Purpose:** Display system performance indicators

### Schema

```typescript
interface PerformanceMetrics {
  title: string;                    // "Performance Metrics"
  avg_processing_time_ms: number;   // Average processing time
  success_rate: number;             // Success rate percentage (0-100)
  total_processed: number;          // Total conversations processed
  timeout_count: number;            // Number of timeouts
  human_takeover_count: number;     // Number of human takeovers
  avg_ai_replies: number;           // Average AI replies per conversation
}
```

### Frontend Implementation Tips

- Display as 6 cards in a grid layout (similar to Overview Metrics)
- Format numbers appropriately:
  - `avg_processing_time_ms`: Show as seconds with 2 decimals (e.g., "1.23s")
  - `success_rate`: Show as percentage with 1 decimal (e.g., "98.5%")
  - `total_processed`: Show as integer (e.g., "1,234")
  - `timeout_count`: Show as integer with warning color if high
  - `human_takeover_count`: Show as integer
  - `avg_ai_replies`: Show as decimal (e.g., "2.3")

- Add visual indicators:
  - Success rate: Green if >95%, yellow if 80-95%, red if <80%
  - Processing time: Green if <1000ms, yellow if 1000-3000ms, red if >3000ms
  - Timeouts: Red if >0
  - Human takeovers: Orange if >0

---

## Card 8: B2B vs B2C Distribution

**Visualization Type:** Pie Chart

**Purpose:** Show distribution of B2B and B2C customers

### Schema

```typescript
interface B2BB2CCard {
  title: string;           // "Customer Type Distribution"
  subtitle: string;        // "B2B vs B2C customers"
  data: B2BB2CItem[];
  total_customers: number;
}

interface B2BB2CItem {
  type: string;            // "B2B" or "B2C"
  count: number;
  percentage: number;      // 0-100
  color: string;           // Hex color code
}
```

### Frontend Implementation Tips

- Use a pie chart or donut chart
- Display as two halves if roughly equal
- Use provided colors:
  - B2B: `#8B5CF6` (Purple)
  - B2C: `#EC4899` (Pink)
- Show percentages in legend or labels
- Add total count in subtitle or center

---

## Card 9: Product Inquiry Trends

**Visualization Type:** Bar Chart

**Purpose:** Show most inquired product categories

### Schema

```typescript
interface ProductInquiryCard {
  title: string;           // "Product Inquiry Trends"
  subtitle: string;        // "Most inquired product categories"
  data: ProductInquiryItem[];
  total_inquiries: number;
}

interface ProductInquiryItem {
  product_type: string;    // "TANAM", "INSTAN", etc.
  count: number;
  vehicle_type: string | null;
}
```

### Frontend Implementation Tips

- Use a vertical bar chart
- X-axis: Product types
- Y-axis: Inquiry count
- Sort by count (descending)
- Add labels on top of bars
- Use consistent colors for bars
- Add hover effects with exact counts
- Display total in subtitle

---

## Card 10: Top Inquiries

**Visualization Type:** Table

**Purpose:** Show recent product inquiries from customers

### Schema

```typescript
interface TopInquiriesCard {
  title: string;           // "Recent Product Inquiries"
  subtitle: string;        "Latest product inquiries from customers"
  max_items: number;       // 10
  data: TopInquiryItem[];
}

interface TopInquiryItem {
  customer_name: string | null;
  phone_number: string | null;
  product_type: string | null;    // "TANAM", "INSTAN", etc.
  vehicle_type: string | null;    // "mobil", "motor", etc.
  unit_qty: number | null;        // Number of units
  status: string;                 // "pending", "link_sent", "interested", "converted", "lost"
  created_at: string;             // ISO 8601 timestamp
}
```

### Frontend Implementation Tips

- Display as a table with the following columns:
  1. Time (formatted from `created_at`, e.g., "2 hours ago")
  2. Customer (`customer_name` or `phone_number`)
  3. Product (`product_type`)
  4. Vehicle (`vehicle_type`)
  5. Quantity (`unit_qty`)
  6. Status (badge with color coding)

- Status color coding:
  - pending: Gray
  - link_sent: Blue
  - interested: Yellow
  - converted: Green
  - lost: Red

- Format timestamps to relative time
- Add hover effects on rows
- Make rows clickable to view details (future feature)
- Truncate long text with ellipsis

---

## Recommended Dashboard Layout

### Desktop Layout (1200px+)

```
┌─────────────────────────────────────────────────────────────────┐
│  HEADER: Dashboard Title + Refresh Button + Last Updated        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Overview │ │          │ │          │ │          │ │         │ │
│  │ Metrics  │ │          │ │          │ │          │ │         │ │
│  │ (6 cards)│ │          │ │          │ │          │ │         │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘ │
│                                                                   │
│  ┌──────────────────────┐ ┌──────────────────┐                   │
│  │ Conversation Trends  │ │ Route Dist.      │                   │
│  │ (Line Chart)         │ │ (Pie Chart)      │                   │
│  └──────────────────────┘ └──────────────────┘                   │
│                                                                   │
│  ┌──────────────────────┐ ┌──────────────────┐                   │
│  │ Intent Analysis      │ │ Meeting Status   │                   │
│  │ (Bar Chart)          │ │ (Donut Chart)    │                   │
│  └──────────────────────┘ └──────────────────┘                   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Recent Activities (Table)                                   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────────────┐  │
│  │          │ │          │ │                                  │  │
│  │ Perf.    │ │ B2B/B2C  │ │ Product Inquiries                │  │
│  │ Metrics  │ │ Dist.    │ │ (Bar Chart)                      │  │
│  │          │ │          │ │                                  │  │
│  └──────────┘ └──────────┘ └──────────────────────────────────┘  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Top Inquiries (Table)                                       │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Tablet Layout (768px - 1199px)

- 2 columns grid for most cards
- Overview Metrics: 3 cards per row
- Charts: 1 per row (full width)

### Mobile Layout (<768px)

- 1 column layout
- All cards stack vertically
- Overview Metrics: 2 cards per row or 1 per row
- Tables: Enable horizontal scroll or card view

---

## Integration Example

### React + TypeScript Example

```typescript
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { LineChart, PieChart, BarChart } from './charts';

interface DashboardData {
  success: boolean;
  message: string;
  generated_at: string;
  timezone: string;
  overview: OverviewMetrics;
  conversation_trends: ConversationTrendsCard;
  // ... other cards
}

const Dashboard: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setLoading(true);
        const response = await axios.get<DashboardData>(
          '/api/dashboard'
        );
        setData(response.data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!data) return null;

  return (
    <div className="dashboard">
      <header>
        <h1>Dashboard</h1>
        <span>Last updated: {new Date(data.generated_at).toLocaleString()}</span>
      </header>

      {/* Overview Metrics */}
      <section className="overview-grid">
        <MetricCard label="Total Customers" value={data.overview.total_customers} />
        <MetricCard label="Active Today" value={data.overview.active_today} />
        <MetricCard label="Meetings Booked" value={data.overview.meetings_booked} />
        <MetricCard label="Product Inquiries" value={data.overview.product_inquiries} />
        <MetricCard label="B2B Customers" value={data.overview.b2b_customers} />
        <MetricCard label="B2C Customers" value={data.overview.b2c_customers} />
      </section>

      {/* Conversation Trends */}
      <section className="chart-section">
        <LineCard
          title={data.conversation_trends.title}
          subtitle={data.conversation_trends.subtitle}
          data={data.conversation_trends.data}
        />
      </section>

      {/* ... other cards */}
    </div>
  );
};

export default Dashboard;
```

### Vue 3 + TypeScript Example

```typescript
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import axios from 'axios';

interface DashboardData {
  // ... same as above
}

const data = ref<DashboardData | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const fetchDashboard = async () => {
  try {
    loading.value = true;
    const response = await axios.get<DashboardData>('/api/dashboard');
    data.value = response.data;
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown error';
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchDashboard();
});
</script>

<template>
  <div v-if="loading">Loading...</div>
  <div v-else-if="error">Error: {{ error }}</div>
  <div v-else-if="data" class="dashboard">
    <header>
      <h1>Dashboard</h1>
      <span>Last updated: {{ new Date(data.generated_at).toLocaleString() }}</span>
    </header>

    <!-- Overview Metrics -->
    <section class="overview-grid">
      <MetricCard label="Total Customers" :value="data.overview.total_customers" />
      <!-- ... other metrics -->
    </section>

    <!-- ... other cards -->
  </div>
</template>
```

---

## Error Handling

The endpoint may return errors in the following format:

```json
{
  "detail": "Error generating dashboard: <error message>"
}
```

### Common Error Scenarios

1. **Database Connection Error**: Check database connectivity
2. **Query Timeout**: Dashboard data is large, consider optimizing queries
3. **Internal Server Error**: Check server logs for details

### Recommended Error Handling

```typescript
try {
  const response = await axios.get('/api/dashboard');
  // Handle success
} catch (error) {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 500) {
      // Server error - show error message
      showError('Server error. Please try again later.');
    } else if (error.response?.status === 401) {
      // Unauthorized - redirect to login
      redirectToLogin();
    }
  } else {
    // Network error or other
    showError('Network error. Please check your connection.');
  }
}
```

---

## Refresh Strategy

### Auto-Refresh

- Recommended refresh interval: 30-60 seconds
- Implement a countdown timer showing next refresh
- Allow users to pause auto-refresh
- Add manual refresh button

### Manual Refresh

- Add a refresh button in the header
- Show loading state during refresh
- Preserve scroll position after refresh

### Example Implementation

```typescript
const REFRESH_INTERVAL = 30000; // 30 seconds

const Dashboard: React.FC = () => {
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [autoRefresh, setAutoRefresh] = useState(true);

  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchDashboard();
      setLastRefresh(new Date());
    }, REFRESH_INTERVAL);

    return () => clearInterval(interval);
  }, [autoRefresh]);

  return (
    <div>
      <button onClick={() => fetchDashboard()}>Refresh Now</button>
      <button onClick={() => setAutoRefresh(!autoRefresh)}>
        {autoRefresh ? 'Pause' : 'Resume'} Auto-Refresh
      </button>
      <span>Last refreshed: {lastRefresh.toLocaleTimeString()}</span>
    </div>
  );
};
```

---

## Performance Considerations

1. **Caching**: Consider caching dashboard data for 30-60 seconds
2. **Pagination**: For tables (Recent Activities, Top Inquiries), the API limits to 10 items
3. **Lazy Loading**: Load charts after initial render
4. **Debouncing**: Debounce manual refresh clicks
5. **Optimistic UI**: Show previous data while fetching new data

---

## Future Enhancements

Potential features to add:

1. **Date Range Filter**: Allow users to select custom date ranges
2. **Export to CSV/PDF**: Export dashboard data or charts
3. **Drill-down**: Click on cards to view detailed data
4. **Real-time Updates**: WebSocket integration for live updates
5. **Customizable Layout**: Allow users to rearrange cards
6. **Dark Mode**: Support dark theme
7. **Responsive Charts**: Ensure charts work on all screen sizes
8. **Accessibility**: Add ARIA labels and keyboard navigation

---

## Support

For questions or issues related to the Dashboard API, please contact the backend team or refer to the API documentation.
