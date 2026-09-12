# trend_analysis

Use this skill for time-series questions: monthly trend, recent days, recent
months, month-over-month, year-over-year, seasonality, and business change over
time.

Prefer:
- `orders.order_date` for sales trends.
- `refunds.refund_date` for refund trends.
- MySQL `DATE_FORMAT(date_column, '%Y-%m')` for monthly buckets.
- Ordered results by time bucket ascending.

For relative time windows, use the reference date from the question when present
such as `以 2026-09-12 为今天`; otherwise use `CURRENT_DATE`.
