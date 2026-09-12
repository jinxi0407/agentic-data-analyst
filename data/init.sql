CREATE DATABASE IF NOT EXISTS agentic_data_analyst
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE agentic_data_analyst;

CREATE TABLE IF NOT EXISTS users (
  user_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_name VARCHAR(64) NOT NULL,
  user_level VARCHAR(20) NOT NULL,
  city VARCHAR(64) NOT NULL,
  province VARCHAR(64) NOT NULL,
  gender VARCHAR(20) NOT NULL,
  register_date DATE NOT NULL,
  is_vip TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS products (
  product_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  product_name VARCHAR(128) NOT NULL,
  category VARCHAR(64) NOT NULL,
  brand VARCHAR(64) NOT NULL,
  list_price DECIMAL(12,2) NOT NULL,
  cost_price DECIMAL(12,2) NOT NULL,
  launch_date DATE NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_products_category (category),
  INDEX idx_products_brand (brand)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS orders (
  order_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  order_no VARCHAR(40) NOT NULL UNIQUE,
  order_status VARCHAR(20) NOT NULL,
  payment_method VARCHAR(20) NOT NULL,
  order_datetime DATETIME NOT NULL,
  order_date DATE NOT NULL,
  gross_amount DECIMAL(12,2) NOT NULL,
  discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  paid_amount DECIMAL(12,2) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  INDEX idx_orders_user (user_id),
  INDEX idx_orders_date (order_date),
  INDEX idx_orders_status (order_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS order_items (
  order_item_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  order_id BIGINT NOT NULL,
  product_id BIGINT NOT NULL,
  quantity INT NOT NULL,
  unit_price DECIMAL(12,2) NOT NULL,
  discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  item_amount DECIMAL(12,2) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT fk_order_items_product FOREIGN KEY (product_id) REFERENCES products(product_id),
  INDEX idx_order_items_order (order_id),
  INDEX idx_order_items_product (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS refunds (
  refund_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  order_id BIGINT NOT NULL,
  order_item_id BIGINT NULL,
  product_id BIGINT NULL,
  refund_no VARCHAR(40) NOT NULL UNIQUE,
  refund_reason VARCHAR(64) NOT NULL,
  refund_status VARCHAR(20) NOT NULL,
  refund_amount DECIMAL(12,2) NOT NULL,
  refund_datetime DATETIME NOT NULL,
  refund_date DATE NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_refunds_order FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT fk_refunds_order_item FOREIGN KEY (order_item_id) REFERENCES order_items(order_item_id),
  CONSTRAINT fk_refunds_product FOREIGN KEY (product_id) REFERENCES products(product_id),
  INDEX idx_refunds_order (order_id),
  INDEX idx_refunds_product (product_id),
  INDEX idx_refunds_date (refund_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS core_table (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  checked TINYINT(1) NOT NULL DEFAULT 1,
  table_name VARCHAR(128) NOT NULL UNIQUE,
  table_comment TEXT NOT NULL,
  custom_comment TEXT NOT NULL,
  relationship TEXT NULL,
  embedding_json MEDIUMTEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS core_field (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  table_id BIGINT NOT NULL,
  checked TINYINT(1) NOT NULL DEFAULT 1,
  field_name VARCHAR(128) NOT NULL,
  field_type VARCHAR(128) NOT NULL,
  field_comment TEXT NOT NULL,
  custom_comment TEXT NOT NULL,
  relationship TEXT NULL,
  field_index INT NOT NULL,
  embedding_json MEDIUMTEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_core_field_table FOREIGN KEY (table_id) REFERENCES core_table(id) ON DELETE CASCADE,
  UNIQUE KEY uk_core_field (table_id, field_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO core_table (checked, table_name, table_comment, custom_comment, relationship)
VALUES
(1, 'users', '用户表，记录客户基础信息、会员等级、城市和注册时间。', '用户、客户、会员、VIP、高频客户、城市、省份、注册时间、人群分层。', 'users.user_id -> orders.user_id'),
(1, 'products', '商品表，记录商品名称、品类、品牌、标价、成本价和上下架状态。', '商品、产品、品类、品牌、价格、成本、毛利、热销商品。', 'products.product_id -> order_items.product_id; products.product_id -> refunds.product_id'),
(1, 'orders', '订单主表，记录用户订单、下单时间、订单状态、支付方式和订单金额。', '订单、销售额、成交额、支付金额、订单数、下单时间、月份、最近30天、最近三个月。', 'orders.user_id -> users.user_id; orders.order_id -> order_items.order_id; orders.order_id -> refunds.order_id'),
(1, 'order_items', '订单明细表，记录每个订单购买的商品、数量、单价、优惠和明细金额。', '订单明细、商品销量、销售数量、单品金额、Top商品、商品销售额、商品件数。', 'order_items.order_id -> orders.order_id; order_items.product_id -> products.product_id; order_items.order_item_id -> refunds.order_item_id'),
(1, 'refunds', '退款表，记录订单或商品维度的退款金额、原因、状态和退款时间。', '退款、退货、退款率、退款金额、退款原因、退款商品、高退款品类。', 'refunds.order_id -> orders.order_id; refunds.order_item_id -> order_items.order_item_id; refunds.product_id -> products.product_id')
ON DUPLICATE KEY UPDATE
  checked = VALUES(checked),
  table_comment = VALUES(table_comment),
  custom_comment = VALUES(custom_comment),
  relationship = VALUES(relationship);

INSERT INTO core_field (table_id, checked, field_name, field_type, field_comment, custom_comment, relationship, field_index)
SELECT t.id, 1, x.field_name, x.field_type, x.field_comment, x.custom_comment, x.relationship, x.field_index
FROM core_table t
JOIN (
  SELECT 'users' table_name, 'user_id' field_name, 'BIGINT' field_type, '用户主键' field_comment, '用户ID，关联订单表 user_id。' custom_comment, 'users.user_id -> orders.user_id' relationship, 1 field_index UNION ALL
  SELECT 'users', 'user_name', 'VARCHAR(64)', '用户姓名', '脱敏模拟姓名，不是真实个人信息。', NULL, 2 UNION ALL
  SELECT 'users', 'user_level', 'VARCHAR(20)', '用户等级', '普通、银卡、金卡、黑卡等客户分层。', NULL, 3 UNION ALL
  SELECT 'users', 'city', 'VARCHAR(64)', '城市', '用户所在城市，用于地域分析。', NULL, 4 UNION ALL
  SELECT 'users', 'province', 'VARCHAR(64)', '省份', '用户所在省份，用于地域分析。', NULL, 5 UNION ALL
  SELECT 'users', 'gender', 'VARCHAR(20)', '性别', '模拟性别字段。', NULL, 6 UNION ALL
  SELECT 'users', 'register_date', 'DATE', '注册日期', '用户注册日期。', NULL, 7 UNION ALL
  SELECT 'users', 'is_vip', 'TINYINT(1)', '是否 VIP', '1 表示 VIP 用户，0 表示非 VIP。', NULL, 8 UNION ALL
  SELECT 'products', 'product_id', 'BIGINT', '商品主键', '商品ID，关联订单明细和退款表。', 'products.product_id -> order_items.product_id; products.product_id -> refunds.product_id', 1 UNION ALL
  SELECT 'products', 'product_name', 'VARCHAR(128)', '商品名称', '商品名称，用于 Top-K 商品分析。', NULL, 2 UNION ALL
  SELECT 'products', 'category', 'VARCHAR(64)', '商品品类', '商品品类，例如手机、家电、美妆、服饰、食品。', NULL, 3 UNION ALL
  SELECT 'products', 'brand', 'VARCHAR(64)', '品牌', '商品品牌。', NULL, 4 UNION ALL
  SELECT 'products', 'list_price', 'DECIMAL(12,2)', '标价', '商品标价。', NULL, 5 UNION ALL
  SELECT 'products', 'cost_price', 'DECIMAL(12,2)', '成本价', '商品成本价，可用于毛利分析。', NULL, 6 UNION ALL
  SELECT 'products', 'launch_date', 'DATE', '上架日期', '商品上架时间。', NULL, 7 UNION ALL
  SELECT 'orders', 'order_id', 'BIGINT', '订单主键', '订单ID，关联订单明细和退款表。', 'orders.order_id -> order_items.order_id; orders.order_id -> refunds.order_id', 1 UNION ALL
  SELECT 'orders', 'user_id', 'BIGINT', '用户ID', '下单用户ID，关联 users.user_id。', 'orders.user_id -> users.user_id', 2 UNION ALL
  SELECT 'orders', 'order_no', 'VARCHAR(40)', '订单号', '业务订单号。', NULL, 3 UNION ALL
  SELECT 'orders', 'order_status', 'VARCHAR(20)', '订单状态', 'paid、completed、cancelled 等状态。', NULL, 4 UNION ALL
  SELECT 'orders', 'payment_method', 'VARCHAR(20)', '支付方式', 'alipay、wechat、card、cash。', NULL, 5 UNION ALL
  SELECT 'orders', 'order_datetime', 'DATETIME', '下单时间', '精确下单时间。', NULL, 6 UNION ALL
  SELECT 'orders', 'order_date', 'DATE', '下单日期', '用于最近30天、月份、季度、趋势分析。', NULL, 7 UNION ALL
  SELECT 'orders', 'gross_amount', 'DECIMAL(12,2)', '订单原始金额', '优惠前订单金额。', NULL, 8 UNION ALL
  SELECT 'orders', 'discount_amount', 'DECIMAL(12,2)', '订单优惠金额', '订单级优惠金额。', NULL, 9 UNION ALL
  SELECT 'orders', 'paid_amount', 'DECIMAL(12,2)', '实付金额', '销售额通常使用 paid_amount。', NULL, 10 UNION ALL
  SELECT 'order_items', 'order_item_id', 'BIGINT', '订单明细主键', '订单明细ID，关联退款表。', 'order_items.order_item_id -> refunds.order_item_id', 1 UNION ALL
  SELECT 'order_items', 'order_id', 'BIGINT', '订单ID', '关联 orders.order_id。', 'order_items.order_id -> orders.order_id', 2 UNION ALL
  SELECT 'order_items', 'product_id', 'BIGINT', '商品ID', '关联 products.product_id。', 'order_items.product_id -> products.product_id', 3 UNION ALL
  SELECT 'order_items', 'quantity', 'INT', '购买数量', '商品销量、件数。', NULL, 4 UNION ALL
  SELECT 'order_items', 'unit_price', 'DECIMAL(12,2)', '成交单价', '商品销售单价。', NULL, 5 UNION ALL
  SELECT 'order_items', 'discount_amount', 'DECIMAL(12,2)', '明细优惠金额', '单品优惠金额。', NULL, 6 UNION ALL
  SELECT 'order_items', 'item_amount', 'DECIMAL(12,2)', '明细实付金额', '商品维度销售额通常使用 item_amount。', NULL, 7 UNION ALL
  SELECT 'refunds', 'refund_id', 'BIGINT', '退款主键', '退款记录ID。', NULL, 1 UNION ALL
  SELECT 'refunds', 'order_id', 'BIGINT', '订单ID', '关联 orders.order_id。', 'refunds.order_id -> orders.order_id', 2 UNION ALL
  SELECT 'refunds', 'order_item_id', 'BIGINT', '订单明细ID', '关联 order_items.order_item_id。', 'refunds.order_item_id -> order_items.order_item_id', 3 UNION ALL
  SELECT 'refunds', 'product_id', 'BIGINT', '商品ID', '关联 products.product_id。', 'refunds.product_id -> products.product_id', 4 UNION ALL
  SELECT 'refunds', 'refund_no', 'VARCHAR(40)', '退款单号', '业务退款单号。', NULL, 5 UNION ALL
  SELECT 'refunds', 'refund_reason', 'VARCHAR(64)', '退款原因', '质量问题、尺码不合适、七天无理由等。', NULL, 6 UNION ALL
  SELECT 'refunds', 'refund_status', 'VARCHAR(20)', '退款状态', 'approved、rejected、pending。', NULL, 7 UNION ALL
  SELECT 'refunds', 'refund_amount', 'DECIMAL(12,2)', '退款金额', '实际退款金额。', NULL, 8 UNION ALL
  SELECT 'refunds', 'refund_datetime', 'DATETIME', '退款时间', '精确退款时间。', NULL, 9 UNION ALL
  SELECT 'refunds', 'refund_date', 'DATE', '退款日期', '用于退款趋势和时间范围过滤。', NULL, 10
) x ON x.table_name = t.table_name
ON DUPLICATE KEY UPDATE
  checked = VALUES(checked),
  field_type = VALUES(field_type),
  field_comment = VALUES(field_comment),
  custom_comment = VALUES(custom_comment),
  relationship = VALUES(relationship),
  field_index = VALUES(field_index);
