# refund_analysis

Use this skill for refund amount, refund count, refund rate, high-refund products,
refund reasons, and return-related questions.

Prefer:
- `refunds.refund_amount` for refund amount.
- `refunds.refund_status = 'approved'` when calculating actual refunds.
- Joining `refunds` to `products` through `product_id`.
- Joining `refunds` to `orders` for order date or customer context.

Refund rate should be calculated deterministically in SQL or Pandas from real
query results, never guessed by the LLM.
