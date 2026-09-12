"""Generate repeatable e-commerce demo data."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.tools.database import connection


SEED = 20260911
random.seed(SEED)

CATEGORIES = {
    "手机数码": 0.10,
    "家用电器": 0.06,
    "美妆个护": 0.16,
    "服饰鞋包": 0.18,
    "食品生鲜": 0.05,
    "运动户外": 0.08,
    "母婴用品": 0.09,
}

BRANDS = ["北辰", "云栖", "青橙", "星禾", "松果", "澜庭", "森活", "优选"]
PROVINCES = [
    ("上海", "上海市"),
    ("北京", "北京市"),
    ("广东", "广州市"),
    ("浙江", "杭州市"),
    ("江苏", "南京市"),
    ("四川", "成都市"),
    ("湖北", "武汉市"),
    ("陕西", "西安市"),
]


def main() -> None:
    with connection(user="root", password=settings.mysql_root_password) as conn:
        with conn.cursor() as cursor:
            _clear(cursor)
            products = _insert_products(cursor)
            users = _insert_users(cursor)
            orders, items = _insert_orders_and_items(cursor, users, products)
            refunds = _insert_refunds(cursor, orders, items, products)
    print(
        "Seed complete: "
        f"users={len(users)}, products={len(products)}, orders={len(orders)}, "
        f"order_items={len(items)}, refunds={len(refunds)}"
    )


def _clear(cursor) -> None:
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    for table in ["refunds", "order_items", "orders", "products", "users"]:
        cursor.execute(f"TRUNCATE TABLE {table}")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")


def _insert_users(cursor):
    users = []
    surnames = ["林", "陈", "张", "王", "李", "赵", "周", "吴", "郑", "孙"]
    names = ["晨", "雨", "一", "宁", "嘉", "然", "琪", "宇", "可", "航"]
    for i in range(3000):
        province, city = random.choice(PROVINCES)
        is_vip = 1 if random.random() < 0.16 else 0
        level = random.choices(
            ["normal", "silver", "gold", "black"],
            weights=[55, 25, 15, 5] if not is_vip else [10, 30, 40, 20],
        )[0]
        register_date = date(2024, 1, 1) + timedelta(days=random.randint(0, 620))
        users.append((f"{surnames[i % len(surnames)]}{names[i % len(names)]}{i:04d}", level, city, province, random.choice(["female", "male", "unknown"]), register_date, is_vip))
    cursor.executemany(
        """
        INSERT INTO users (user_name, user_level, city, province, gender, register_date, is_vip)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        users,
    )
    cursor.execute("SELECT user_id, user_level, is_vip FROM users ORDER BY user_id")
    return cursor.fetchall()


def _insert_products(cursor):
    products = []
    for i in range(800):
        category = random.choice(list(CATEGORIES.keys()))
        brand = random.choice(BRANDS)
        base = {
            "手机数码": 1200,
            "家用电器": 1800,
            "美妆个护": 180,
            "服饰鞋包": 260,
            "食品生鲜": 90,
            "运动户外": 360,
            "母婴用品": 220,
        }[category]
        price = Decimal(str(round(random.uniform(base * 0.45, base * 2.1), 2)))
        cost = Decimal(str(round(float(price) * random.uniform(0.45, 0.72), 2)))
        price_band = random.choice(["入门款", "标准款", "高端款", "旗舰款"])
        # Similar names are intentional: they make product matching and ranking questions less toy-like.
        products.append((f"{brand}{category}{price_band}商品{(i % 120) + 1:03d}", category, brand, price, cost, date(2024, 1, 1) + timedelta(days=random.randint(0, 720)), 1))
    cursor.executemany(
        """
        INSERT INTO products (product_name, category, brand, list_price, cost_price, launch_date, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        products,
    )
    cursor.execute("SELECT product_id, category, list_price FROM products ORDER BY product_id")
    return cursor.fetchall()


def _insert_orders_and_items(cursor, users, products):
    order_rows = []
    order_items_by_order = []
    start = date(2025, 3, 1)
    hot_products = products[:25]
    for i in range(12000):
        user = random.choice(users)
        if random.random() < 0.38:
            user = random.choice([u for u in users if u["is_vip"] == 1])
        order_day = _weighted_order_date(start)
        status = random.choices(
            ["completed", "paid", "shipped", "cancelled", "unpaid"],
            weights=[64, 16, 10, 6, 4],
        )[0]
        payment = random.choice(["alipay", "wechat", "card", "cash"])
        item_count = random.choices([1, 2, 3, 4, 5], weights=[28, 34, 24, 10, 4])[0]
        chosen = []
        for _ in range(item_count):
            product = random.choice(hot_products) if random.random() < 0.32 else random.choice(products)
            quantity = random.choices([1, 2, 3, 4, 5], weights=[54, 25, 12, 6, 3])[0]
            price = Decimal(str(product["list_price"]))
            discount_rate = random.choices(
                [random.uniform(0, 0.05), random.uniform(0.05, 0.15), random.uniform(0.15, 0.35)],
                weights=[55, 35, 10],
            )[0]
            discount = Decimal(str(round(float(price) * quantity * discount_rate, 2)))
            amount = Decimal(str(round(float(price) * quantity - float(discount), 2)))
            chosen.append((product["product_id"], quantity, price, discount, amount))
        gross = sum((q * price for _, q, price, _, _ in chosen), Decimal("0"))
        discount = sum((d for _, _, _, d, _ in chosen), Decimal("0"))
        paid = sum((amount for _, _, _, _, amount in chosen), Decimal("0"))
        order_dt = datetime.combine(order_day, datetime.min.time()) + timedelta(hours=random.randint(8, 23), minutes=random.randint(0, 59))
        order_rows.append((user["user_id"], f"ADA{order_day:%Y%m%d}{i + 1:06d}", status, payment, order_dt, order_day, gross, discount, paid))
        order_items_by_order.append(chosen)

    cursor.executemany(
        """
        INSERT INTO orders (user_id, order_no, order_status, payment_method, order_datetime, order_date, gross_amount, discount_amount, paid_amount)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        order_rows,
    )
    cursor.execute("SELECT order_id, order_date, order_status FROM orders ORDER BY order_id")
    orders = cursor.fetchall()

    item_rows = []
    for order, chosen in zip(orders, order_items_by_order):
        for product_id, quantity, price, discount, amount in chosen:
            item_rows.append((order["order_id"], product_id, quantity, price, discount, amount))
    cursor.executemany(
        """
        INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount_amount, item_amount)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        item_rows,
    )
    cursor.execute("SELECT order_item_id, order_id, product_id, item_amount FROM order_items ORDER BY order_item_id")
    items = cursor.fetchall()
    return orders, items


def _weighted_order_date(start: date) -> date:
    day = start + timedelta(days=random.randint(0, 560))
    # June promotions, Singles' Day, and year-end holidays are peak seasons.
    if random.random() < 0.30:
        month = random.choices([6, 11, 12, 2, 8], weights=[18, 34, 24, 10, 14])[0]
        year = random.choices([2025, 2026], weights=[45, 55])[0]
        day = date(year, month, random.randint(1, 28))
    return day


def _insert_refunds(cursor, orders, items, products):
    product_by_id = {p["product_id"]: p for p in products}
    order_by_id = {o["order_id"]: o for o in orders}
    rows = []
    refund_index = 1
    for item in items:
        product = product_by_id[item["product_id"]]
        order = order_by_id[item["order_id"]]
        if order["order_status"] in {"cancelled", "unpaid"}:
            continue
        base_rate = CATEGORIES[product["category"]]
        if product["product_id"] <= 18:
            base_rate += 0.12
        if product["product_id"] > 720:
            base_rate *= 0.15
        if random.random() > base_rate:
            continue
        refund_date = order["order_date"] + timedelta(days=random.randint(1, 20))
        refund_ratio = random.choices(
            [random.uniform(0.2, 0.65), 1.0],
            weights=[72, 28],
        )[0]
        amount = Decimal(str(round(float(item["item_amount"]) * refund_ratio, 2)))
        rows.append(
            (
                item["order_id"],
                item["order_item_id"],
                item["product_id"],
                f"RF{refund_date:%Y%m%d}{refund_index:06d}",
                random.choice(["质量问题", "尺码不合适", "七天无理由", "物流破损", "描述不符"]),
                random.choices(["approved", "pending", "rejected"], weights=[82, 10, 8])[0],
                amount,
                datetime.combine(refund_date, datetime.min.time()) + timedelta(hours=random.randint(9, 21)),
                refund_date,
            )
        )
        refund_index += 1

    cursor.executemany(
        """
        INSERT INTO refunds (order_id, order_item_id, product_id, refund_no, refund_reason, refund_status, refund_amount, refund_datetime, refund_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    return rows


if __name__ == "__main__":
    main()
