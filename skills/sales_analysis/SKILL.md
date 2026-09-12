# sales_analysis

Use this skill for sales, revenue, order amount, product ranking, customer value,
and Top-K business questions.

Prefer:
- `orders.paid_amount` for order-level sales.
- `order_items.item_amount` for product-level sales.
- Joining `order_items` with `products` for product names, categories, and brands.
- Joining `orders` with `users` for customer-level analysis.

Filter out cancelled orders when the question asks for real sales.
