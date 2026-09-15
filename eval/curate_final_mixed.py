"""Pre-freeze reference curation only. Never imported by a candidate or its scorer."""

from pathlib import Path
import sqlglot

from eval.audit_final_mixed import OUT, ROOT, read, sha
from eval.scoring import write_json


def curate():
    assert not (ROOT/'eval/final_mixed_events.jsonl').exists(), 'No edits after candidate exposure'
    source=OUT/'draft_cases.json'
    cases=read(source)
    assert len(cases)==200
    changes=[]
    def edit(n,field,new,reason):
        c=cases[n-1]
        old=c[field]
        if old==new:
            return
        changes.append({'case_id':c['id'],'field':field,'before':old,'after':new,'reason':reason})
        c[field]=new
    def sub(n,field,old,new,reason):
        assert old in cases[n-1][field], (n,field,old)
        edit(n,field,cases[n-1][field].replace(old,new),reason)
    for n in [3,6,14,20]:
        for field in ['question','reference_sql']:
            value=cases[n-1][field].replace("'男'","'male'").replace("'女'","'female'")
            edit(n,field,value,'Same intended gender; actual demo storage enums are male/female/unknown, confirmed from seed and MySQL metadata.')
    sub(5,'question','按注册日期升序排列','按注册日期升序、同日按用户姓名升序排列','Stable tie-break specified before evaluation')
    sub(5,'reference_sql','ORDER BY register_date ASC','ORDER BY register_date ASC, user_name ASC','Match explicit tie-break')
    edit(15,'question','请列出注册最早和最晚的各5位用户；最早组按注册日期升序、姓名升序取5位，最晚组按注册日期降序、姓名升序取5位。返回用户姓名、注册日期、用户等级三列，合并后按注册日期和姓名升序排列。','Clarify deterministic selection and output order; same earliest/latest-five task')
    edit(15,'reference_sql',"SELECT user_name,register_date,user_level FROM ((SELECT user_name,register_date,user_level FROM users ORDER BY register_date ASC,user_name ASC LIMIT 5) UNION ALL (SELECT user_name,register_date,user_level FROM users ORDER BY register_date DESC,user_name ASC LIMIT 5)) t ORDER BY register_date ASC,user_name ASC",'MySQL UNION operands with local ORDER BY/LIMIT require parentheses')
    sub(19,'question','注册日期为当月1号','注册日期为各自注册月份的1号','Remove current-month versus each-registration-month wording ambiguity')
    sub(22,'question',"类商品的平均标价", "类在售商品的平均标价",'State the active-product scope of both averages and the count threshold')
    sub(30,'reference_sql','list_price / cost_price > 1.3','list_price / cost_price >= 1.3','The phrase 1.3倍以上 is inclusive')
    for n,old,new in [(31,'上市月份升序排列','上市月份升序、品牌升序、品类升序排列'),
                      (33,'上市季度降序排列','上市季度降序、品牌升序、品类升序排列')]:
        sub(n,'question',old,new,'Stable ordering before truncation; preserve all four requested columns')
        sub(n,'reference_sql',' LIMIT 100',' , brand ASC, category ASC LIMIT 100','Match question tie-breaks')
    sub(32,'reference_sql','ROUND(AVG(YEAR(launch_date)), 0)','AVG(YEAR(launch_date))','Do not round an unqualified mean to an integer')
    sub(32,'reference_sql','ROUND(AVG(QUARTER(launch_date)), 0)','AVG(QUARTER(launch_date))','Do not round an unqualified mean to an integer')
    sub(36,'question','和毛利率（','和逐商品毛利率的简单平均值（','Specify average of per-product ratios, not ratio of aggregated averages')
    edit(37,'question','按上市年份和月份统计在售商品数量、平均标价和平均成本价；仅返回上市年份、上市月份、商品数量、平均标价、平均成本价五列，均价保留2位小数。按年份、月份升序，最多100行。','Specify the same five projected columns without an implicit combined year-month format')
    edit(39,'question','按品类统计在售商品的上市年份中位数和上市年份总体标准差；只返回品类、中位数、总体标准差三列，标准差保留4位小数，按品类升序排列。','Keep the authored statistics but remove SQL implementation instructions')
    edit(39,'reference_sql',"WITH ranked AS (SELECT category,YEAR(launch_date) y,ROW_NUMBER() OVER(PARTITION BY category ORDER BY YEAR(launch_date),product_id) rn,COUNT(*) OVER(PARTITION BY category) cnt FROM products WHERE is_active=1), med AS (SELECT category,AVG(y) median_year FROM ranked WHERE rn IN(FLOOR((cnt+1)/2),CEIL((cnt+1)/2)) GROUP BY category), spread AS (SELECT category,ROUND(STDDEV_POP(YEAR(launch_date)),4) sd FROM products WHERE is_active=1 GROUP BY category) SELECT med.category,med.median_year,spread.sd FROM med JOIN spread ON med.category=spread.category ORDER BY med.category",'Median uses middle rows; population standard deviation must use all category rows, not only median rows. Fix missing-column scope.')
    for n in [44,47]:
        edit(n,'question',cases[n-1]['question'].rstrip('。')+'；只返回最早的100个日期。','Enforce the predeclared output cap explicitly in the question, before benchmark freeze')
        edit(n,'reference_sql',cases[n-1]['reference_sql'].rstrip(';')+' LIMIT 100','Match the explicitly bounded daily report')
    edit(50,'question','按支付方式统计状态为paid的订单平均下单日期：以自然日为单位求平均，四舍五入到最近自然日。只返回支付方式和平均日期两列，按支付方式升序。','State calendar-day arithmetic rather than MySQL numeric YYYYMMDD coercion')
    edit(50,'reference_sql',"SELECT payment_method,FROM_DAYS(ROUND(AVG(TO_DAYS(order_date)))) AS avg_order_date FROM orders WHERE order_status='paid' GROUP BY payment_method ORDER BY payment_method",'AVG(DATE) is numeric coercion, not a calendar-day mean')
    sub(61,'reference_sql','COUNT(*) AS valid_order_count','COUNT(o.order_id) AS valid_order_count','A LEFT JOIN unmatched user has zero orders, not one placeholder row')
    for n in [61,62,63,64,65,66,68,69,70]:
        edit(n,'question',cases[n-1]['question'].rstrip('。')+'。其中首次/末次下单和支付方式均只统计有效订单；涉及客户平均值和比例时，范围内零有效订单客户也计入分母。','Make the authored valid-order and all-customer scope unambiguous before candidate exposure')
    for n in [62,64,68,70]:
        for field in ['valid_order_count','distinct_payment_count']:
            sub(n,'reference_sql',f'AVG(t.{field})',f'AVG(COALESCE(t.{field},0))','Include customers with zero qualifying orders in the stated customer-level mean')
    sub(65,'reference_sql',"AND o.order_status IN ('paid','completed','shipped')", "AND o.order_status IN ('paid','completed','shipped') AND o.order_date < '2026-09-12'",'Apply the date constraint already present in the question')
    edit(66,'question','按客户等级统计全部客户：首末有效订单日期间隔大于30天的客户占比、每位客户有效订单数除以注册至2026-09-12的天数（含注册当天）后的简单平均值、平均使用支付方式数。零有效订单客户也计入分母，支付方式仅统计有效订单。返回客户等级和上述三项指标，两个比率保留4位小数，按等级升序。','Specify per-customer averaging and registration-day convention; preserve the same three authored measures')
    edit(66,'reference_sql',"WITH t AS (SELECT user_id,COUNT(*) n,MIN(order_date) first_day,MAX(order_date) last_day,COUNT(DISTINCT payment_method) methods FROM orders WHERE order_status IN('paid','completed','shipped') GROUP BY user_id) SELECT u.user_level,ROUND(AVG(CASE WHEN DATEDIFF(t.last_day,t.first_day)>30 THEN 1 ELSE 0 END),4) rate_span,ROUND(AVG(COALESCE(t.n,0)/NULLIF(DATEDIFF('2026-09-12',u.register_date)+1,0)),4) avg_frequency,AVG(COALESCE(t.methods,0)) avg_methods FROM users u LEFT JOIN t ON u.user_id=t.user_id GROUP BY u.user_level ORDER BY u.user_level",'Fix first-to-last span, aggregate-of-ratios versus ratio-of-sums, and zero-order-customer denominator')
    sub(69,'question','有效订单次数及是否为VIP','有效订单次数','Keep only the permitted five projected columns')
    sub(67,'question','用户ID、城市、客户等级、','用户ID、城市、','Enforce five-column protocol cap before data freeze')
    sub(67,'reference_sql','u.user_id, u.city, u.user_level,','u.user_id, u.city,','Match the five projected columns')
    sub(69,'reference_sql','COUNT(*) AS valid_order_count, u.is_vip','COUNT(*) AS valid_order_count','Match the five projected columns')
    sub(72,'reference_sql','AVG(unit_price)','ROUND(AVG(unit_price),2)','Monetary averages follow the existing two-decimal contract')
    for n in [73,77]:
        edit(n,'question',cases[n-1]['question']+' 排名使用展示的四位小数比率。','State rounded-rate ranking before evaluation')
    sub(75,'question','标准差','总体标准差','Specify population rather than sample standard deviation')
    edit(79,'question','不限订单状态，按商品ID统计所有订单明细行金额的中位数、最小值和最大值。中位数按通常定义，偶数个观测取中间两项平均，金额保留2位小数。返回商品ID和上述三项金额，按中位数降序，最多100行。','Replace implementation hints and incorrect percentile approximation with an explicit ordinary median')
    edit(79,'reference_sql',"WITH ranked AS (SELECT product_id,item_amount,ROW_NUMBER() OVER(PARTITION BY product_id ORDER BY item_amount,order_item_id) rn,COUNT(*) OVER(PARTITION BY product_id) cnt FROM order_items) SELECT product_id,ROUND(AVG(CASE WHEN rn IN(FLOOR((cnt+1)/2),CEIL((cnt+1)/2)) THEN item_amount END),2) median_item_amount,MIN(item_amount) min_item_amount,MAX(item_amount) max_item_amount FROM ranked GROUP BY product_id ORDER BY median_item_amount DESC LIMIT 100",'Compute an ordinary median including singleton and even-sized groups; min/max use the entire group')
    edit(81,'question','按品牌和品类，统计2026年9月12日前上架且当前在售的商品数量、平均标价及价格加成率。加成率为（平均标价-平均成本价）/平均成本价。仅返回品牌、品类、商品数量、平均标价、加成率五列，均价保留2位、比率保留4位，按商品数量降序，最多100行。','Keep the business task within the five-column protocol; cost remains in the formula, not a separate output')
    sub(81,'reference_sql','ROUND(AVG(cost_price), 2) AS avg_cost, ','','Match the five explicit projected columns')
    for n in [81,85,136]:
        sub(n,'reference_sql',"launch_date <= '2026-09-12'","launch_date < '2026-09-12'",'Before the reference date is an exclusive boundary')
    edit(84,'question','按品牌和品类统计在售商品的最低标价、最高标价与价格带宽度（最高价减最低价）。只保留价格带宽度超过200元且至少有8款商品的组合，仅返回品牌、品类、最低价、最高价、价格带宽度五列，按宽度降序，最多100行。','Keep the same price-range selection within the five-column protocol')
    sub(84,'reference_sql',', ROUND(AVG(list_price), 2) AS avg_price','','Match the five explicit projected columns')
    edit(86,'reference_sql',"WITH sku AS (SELECT p.brand,p.category,p.product_id,SUM(oi.quantity) qty FROM products p JOIN order_items oi ON oi.product_id=p.product_id JOIN orders o ON o.order_id=oi.order_id WHERE p.is_active=1 AND o.order_status IN('paid','completed','shipped') GROUP BY p.brand,p.category,p.product_id), ranked AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY brand,category ORDER BY qty DESC,product_id) rn FROM sku) SELECT brand,category,ROUND(SUM(CASE WHEN rn<=3 THEN qty ELSE 0 END)/SUM(qty),4) concentration FROM ranked GROUP BY brand,category HAVING SUM(qty)>=1000 ORDER BY concentration ASC LIMIT 100",'Apply the existing valid-order sales-quantity definition and aggregate each SKU exactly once')
    edit(87,'question','按品牌和品类计算两个独立平均值：所有在售商品的简单平均标价，以及这些商品在有效订单明细中的平均每行数量。只保留平均标价高于300元且平均每行数量大于5的组合，返回品牌、品类和两均值的乘积（保留2位小数），按乘积降序，最多100行。','Make product-grain catalogue mean and line-grain quantity mean explicit; retain the original threshold even if empty')
    edit(87,'reference_sql',"WITH prices AS (SELECT brand,category,AVG(list_price) avg_price FROM products WHERE is_active=1 GROUP BY brand,category), qty AS (SELECT p.brand,p.category,AVG(oi.quantity) avg_qty FROM products p JOIN order_items oi ON oi.product_id=p.product_id JOIN orders o ON o.order_id=oi.order_id WHERE p.is_active=1 AND o.order_status IN('paid','completed','shipped') GROUP BY p.brand,p.category) SELECT prices.brand,prices.category,ROUND(prices.avg_price*qty.avg_qty,2) price_quantity_weight FROM prices JOIN qty ON prices.brand=qty.brand AND prices.category=qty.category WHERE prices.avg_price>300 AND qty.avg_qty>5 ORDER BY price_quantity_weight DESC LIMIT 100",'Independent aggregation prevents item-frequency weighting of catalogue price')
    sub(89,'reference_sql',"AND o.order_status IN ('paid','completed','shipped')","AND o.order_status IN ('paid','completed','shipped') AND p.is_active=1 AND o.order_date <= '2026-09-12'",'Apply the active-product condition and fixed reference upper bound')
    sub(82,'reference_sql',"AND o.order_status IN ('paid','completed','shipped')","AND o.order_status IN ('paid','completed','shipped') AND o.order_date <= '2026-09-12'",'Bound the relative interval by the fixed reference date')
    edit(92,'question','统计2026年8月14日至9月12日（含首尾，共30个自然日）每天已批准退款的笔数和总金额。只返回有退款记录的日期、笔数、金额三列，按日期升序。','Disambiguate the authored inclusive 30-calendar-day convention without changing its period')
    sub(98,'question','统计退款原因中','统计全部状态退款记录的原因中','Make the authored all-record rather than approved-only scope explicit')
    edit(101,'question','对发生过已批准退款的订单，按支付方式统计已批准退款总金额和去重订单数。只返回支付方式、去重订单数、已批准退款总金额三列，按订单数降序，最多100行。','Separate refund-record amounts from unique refunded-order counts')
    for n,alias in [(101,'refund_order_count'),(104,'valid_order_count_with_refund'),
                    (108,'refund_order_count'),(110,'cash_refund_order_count')]:
        sub(n,'reference_sql',f'COUNT(*) AS {alias}',f'COUNT(DISTINCT o.order_id) AS {alias}','Count refunded orders once, not refund records')
    sub(106,'reference_sql','COUNT(*) AS count','COUNT(DISTINCT o.order_id) AS count','The question asks for orders by state, not refund-record counts')
    edit(102,'question','仅看发生过已批准退款的有效订单，按订单状态统计去重订单数、该集合每笔已批准退款的平均金额、该集合订单的实付总额（每单只计一次）。返回状态及上述三项指标，金额保留2位小数，按状态升序，最多100行。','Specify one consistent refunded-valid-order cohort and the distinct order/record grains')
    edit(102,'reference_sql',"WITH r AS (SELECT order_id,SUM(refund_amount) amount,COUNT(*) n FROM refunds WHERE refund_status='approved' GROUP BY order_id) SELECT o.order_status,COUNT(*) approved_refund_order_count,ROUND(SUM(r.amount)/SUM(r.n),2) avg_approved_refund_amount,ROUND(SUM(o.paid_amount),2) total_paid_amount_of_valid_orders FROM orders o JOIN r ON r.order_id=o.order_id WHERE o.order_status IN('paid','completed','shipped') GROUP BY o.order_status ORDER BY o.order_status ASC LIMIT 100",'Aggregate refunds per order before adding order paid amounts; weight the average by refund records')
    sub(103,'reference_sql',"BETWEEN '2026-08-14' AND '2026-09-12'","BETWEEN DATE_SUB('2026-09-12',INTERVAL 30 DAY) AND '2026-09-12'",'Follow the existing DATE_SUB(reference,30 DAY) rule for unqualified last30days')
    sub(104,'reference_sql','SUM(SUM(r.refund_amount)) OVER()',"(SELECT SUM(refund_amount) FROM refunds WHERE refund_status='approved')",'The stated denominator is all approved refund money, independent of the valid-order numerator filter')
    sub(105,'question','订单ID、订单状态、支付方式','订单ID、支付方式','Keep the same anomaly check within five projected columns')
    sub(105,'reference_sql','o.order_id, o.order_status, o.payment_method','o.order_id, o.payment_method','Match the five projected columns')
    sub(107,'question','订单状态、支付方式、退款原因','订单状态、退款原因','Keep the same geographic refund detail within five columns')
    sub(107,'reference_sql','o.order_status, o.payment_method, r.refund_reason','o.order_status, r.refund_reason','Match the five projected columns')
    edit(108,'question',cases[107]['question']+' 微信和支付宝合并统计，不分开列；只返回订单状态、去重退款订单数和退款总金额。','Specify combined payment-method population and projection')
    sub(109,'question','订单号、订单状态、支付方式','订单号、支付方式','Keep the same refund-versus-paid comparison within five columns')
    sub(109,'reference_sql','o.order_no, o.order_status, o.payment_method','o.order_no, o.payment_method','Match the five projected columns')
    for n in range(111,121):
        edit(n,'question',cases[n-1]['question']+' 只列出该期间有对应记录的日期或分组，没有记录的分组省略。','Specify the authored sparse-period output rather than invent zero-fill behavior')
    sub(115,'question',"格式'YYYY-Q'","例如2026-Q2",'Make quarter display format explicit')
    sub(115,'reference_sql',"CONCAT('2026-', QUARTER(order_date))","CONCAT('2026-Q', QUARTER(order_date))",'Match the explicit quarter display format')
    sub(122,'reference_sql',"WHERE p.category = '家用电器'","WHERE p.category = '家用电器' AND o2.order_status IN('paid','completed','shipped')",'Purchases require valid orders; the outer any-order population remains unchanged')
    edit(122,'question',cases[121]['question']+' “有订单”不限状态，“购买过”仅指有效订单。','Make the two authored populations explicit')
    for n in [123,130]:
        sub(n,'reference_sql','SELECT 1 FROM order_items oi WHERE oi.product_id = p.product_id',"SELECT 1 FROM order_items oi JOIN orders o ON o.order_id=oi.order_id WHERE oi.product_id=p.product_id AND o.order_status IN('paid','completed','shipped')",'Absence of valid purchases is not absence of all order-item rows')
    sub(124,'reference_sql'," AND r.refund_status = 'approved'",'','Any refund record includes pending and rejected records')
    edit(124,'question',cases[123]['question']+' “任何退款”包含批准、拒绝和待处理的全部退款记录。','Keep the explicitly stated any-record population')
    sub(126,'reference_sql',"u.register_date <= '2026-09-12'","u.register_date < '2026-09-12'",'Before the reference date is exclusive')
    sub(127,'question','从未被退款过','从未有已批准退款记录','State the authored approved-refund definition')
    edit(128,'question','不限订单状态，找出至少有一笔支付宝订单且该笔订单不含手机数码类商品的用户。只返回用户ID、姓名、省份，按省份和用户ID升序，最多100行。','The exclusion applies to a qualifying order, not to all purchases ever made by the customer')
    edit(128,'reference_sql',"SELECT u.user_id,u.user_name,u.province FROM users u WHERE EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.user_id AND o.payment_method='alipay' AND NOT EXISTS(SELECT 1 FROM order_items oi JOIN products p ON p.product_id=oi.product_id WHERE oi.order_id=o.order_id AND p.category='手机数码')) ORDER BY u.province,u.user_id LIMIT 100",'Correct existential quantifier grain from customer-wide exclusion to qualifying-order exclusion')
    sub(129,'reference_sql'," AND r.refund_status = 'approved'",'','Any refund record includes every refund status')
    sub(129,'reference_sql',"r.refund_date <= '2026-09-12'","r.refund_date < '2026-09-12'",'The question says before September12, excluding that day')
    edit(129,'question',cases[128]['question']+' 无任何退款记录包含全部退款状态，9月12日前不含9月12日。','Expose the original any-record and exclusive-date semantics')
    paraphrases={
        131:'帮我把上海市VIP会员的注册日期和会员等级列出来，先注册的排前面，最多100条，只要这两列。',
        132:'2026年9月12日的有效订单都用了哪些付款方式？每种分别有多少单？给我付款方式和单数，按付款方式编码的字母顺序排。',
        133:'想看南京市用户2026年8月的客单情况：按会员等级算每笔有效订单平均实付多少钱，金额保留两位，给我等级和均价，按等级升序。',
        134:'帮我找出2026年9月12日以前注册、到现在却一条订单记录也没有的用户。只列姓名和注册日期，先注册的在前，最多100条。',
        135:'成都市用户在2026年9月11日和12日这两天的已批准退款，各个退款原因分别退了多少钱？给我原因和总金额，金额保留两位，退得多的排前面。',
        136:'食品生鲜里，2026年9月12日以前上架而且现在还在卖的商品有哪些？列商品名、品牌、上架日期和标价，先按上架日期从早到晚，同日标价从高到低，最多100条。',
        137:'帮我看2026年9月12日下单、当前状态已完成的订单。列订单号、下单时间、实付金额和客户城市，按下单时间从早到晚，最多100条。',
        138:'2026年9月12日有有效订单的各会员等级，各用了几种不同的支付方式？重复的方式只算一次。给我等级和种类数，按等级升序。',
        139:'把2026年9月12日以前注册、等级是gold或black的用户列出来。我要用户ID、姓名、注册日期、VIP标记这四列，晚注册的排前面，最多100条。',
        140:'2026年9月12日因为描述不符申请、并且已经批准的退款有哪些？给我退款单号、退款金额、退款日期和原订单实付金额，金额保留两位，退款金额大的在前，最多100条。',
    }
    for n,question in paraphrases.items():
        edit(n,'question',question,'Natural operations wording of the independently authored task; preserve all dates, filters, projections and sorting')
        edit(n,'category','paraphrase','Explicitly label the protocol-required conversational subset')
    time_questions={
        141:'统计最近一段时间各城市新注册的人数，按城市升序，只返回城市和人数，最多100行。',
        142:'想看近期上架且目前在售的商品，各品类平均标价和平均成本是多少？均价保留2位，返回品类和两项均价，按品类升序，最多100行。',
        143:'帮我统计那段时间每天的有效订单数，只返回有订单的日期和单数，按日期从早到晚，最多100行。',
        144:'分析这一阵的支付方式构成：各方式有多少有效订单？只返回付款方式和单数，按方式升序，最多100行。',
        145:'最近注册的VIP用户都分布在哪些城市和等级？只返回城市、等级、人数，按城市和等级升序，最多100行。',
        146:'这段时间上架、现在仍在售的商品，按品牌和品类各有多少个SKU？只返回品牌、品类、SKU数，按品牌和品类升序，最多100行。',
        147:'最近一段时间各城市有多少付费用户？只返回城市和付费人数，按城市升序，最多100行。',
        148:'最近发生且已批准的退款，按原因各退了多少钱？只返回原因和总金额，金额保留2位，按原因升序，最多100行。',
        149:'这段时间各品类在有效订单中卖出了多少件商品？只返回品类和件数，按品类升序，最多100行。',
        150:'想看近期各城市每笔有效订单平均实付多少钱。只返回城市和平均实付金额，保留2位小数，按城市升序，最多100行。',
    }
    for n,question in time_questions.items():
        edit(n,'question',question,'A deliberately bounded but unresolved period is required: unqualified all-history totals are not genuine time ambiguity')
        edit(n,'ambiguity_alternatives',[cases[n-1]['simulated_answer'],'2026-08-01 至 2026-08-31'],
             'Both alternatives resolve the same missing interval and differ materially; the intended answer is included')
        edit(n,'ambiguity_explanation','问题明确指向近期或某一段期间，但未给起止范围。业务契约不定义无N值的近期；不同期间需要不同日期谓词。其他指标、维度和输出条件均已指定。',
             'Document the protocol-based ambiguity, not a claim that all unqualified questions require time clarification')
    sub(146,'reference_sql',"AND is_active = 1","AND is_active = 1",'The on-sale filter is now explicit in the question')
    edit(153,'question','统计过去一段时间内，各有效订单状态的有效订单数、已批准退款记录数，以及退款记录数/有效订单数（保留4位）。订单按下单日期、退款按退款日期分别落入该期间统计，退款仅取父单当前为有效状态的记录；只列有有效订单的状态。返回状态、两项数量、比率四列，按比率升序。','Define independent date/grain populations so only the interval itself remains missing')
    edit(153,'reference_sql',"WITH o AS (SELECT order_status,COUNT(*) n FROM orders WHERE order_status IN('paid','completed','shipped') AND order_date BETWEEN '2026-09-05' AND '2026-09-12' GROUP BY order_status), r AS (SELECT o.order_status,COUNT(*) n FROM refunds r JOIN orders o ON o.order_id=r.order_id WHERE r.refund_status='approved' AND o.order_status IN('paid','completed','shipped') AND r.refund_date BETWEEN '2026-09-05' AND '2026-09-12' GROUP BY o.order_status) SELECT o.order_status,o.n valid_order_count,COALESCE(r.n,0) refund_count,ROUND(COALESCE(r.n,0)/o.n,4) refund_rate FROM o LEFT JOIN r ON o.order_status=r.order_status ORDER BY refund_rate ASC",'Independent aggregation avoids dropping orders whose only refund falls outside the period')
    edit(154,'question','统计过去一段时间各品类的已批准退款金额、有效订单销售金额和两者比值（品类退款率）。退款按退款日期、销售按订单日期分别限制到该期间，只显示销售金额大于0的品类。返回品类、退款额、销售额、比率四列，金额保留2位、比率4位，按比率降序。','Make the existing contract date bases and positive-sales denominator explicit; only the time interval is missing')
    edit(154,'reference_sql',"WITH sales AS (SELECT p.category,SUM(oi.item_amount) amount FROM products p JOIN order_items oi ON oi.product_id=p.product_id JOIN orders o ON o.order_id=oi.order_id WHERE o.order_status IN('paid','completed','shipped') AND o.order_date BETWEEN '2026-08-15' AND '2026-09-12' GROUP BY p.category HAVING SUM(oi.item_amount)>0), refunds_by_category AS (SELECT p.category,SUM(r.refund_amount) amount FROM refunds r JOIN products p ON p.product_id=r.product_id WHERE r.refund_status='approved' AND r.refund_date BETWEEN '2026-08-15' AND '2026-09-12' GROUP BY p.category) SELECT sales.category,ROUND(COALESCE(r.amount,0),2) sum_refund_amount,ROUND(sales.amount,2) sum_sales_amount,ROUND(COALESCE(r.amount,0)/sales.amount,4) refund_rate FROM sales LEFT JOIN refunds_by_category r ON r.category=sales.category ORDER BY refund_rate DESC",'Avoid refund fanout and out-of-period-refund suppression of sales; use the real product foreign key for refund attribution')
    edit(157,'question','列出过去一段时间内、能够关联到商品的已批准退款中，退款金额超过500元的记录。只返回退款单号、退款原因、退款金额、退款日期，按金额降序，最多100行。','Clarify the authored product-linked record population and preserve the amount threshold and four columns')
    edit(157,'reference_sql',"SELECT r.refund_no,r.refund_reason,ROUND(r.refund_amount,2) refund_amount,r.refund_date FROM refunds r JOIN products p ON p.product_id=r.product_id WHERE r.refund_status='approved' AND r.refund_amount>500 AND r.refund_date BETWEEN '2026-09-07' AND '2026-09-12' ORDER BY r.refund_amount DESC LIMIT 100",'Use the actual refunds.product_id relationship without unnecessarily requiring an order-item link')
    for n in [158,160]:
        edit(n,'question',cases[n-1]['question']+' 这里只统计已批准退款。','Expose the authored approved-refund scope, leaving only the missing interval')
    edit(160,'question',cases[159]['question']+' 同日先按退款金额降序，再按退款单号升序。','Make existing secondary ordering and deterministic tie-break visible')
    metric_questions={
        161:('不限制时间，仅统计有效订单。想比较各城市的成交贡献占全站的比例，按贡献占比降序。只返回城市和占比（保留4位），最多100行。',['有效订单销售额','有效订单销售数量']),
        162:('不限制时间，仅看已批准退款。想比较各品牌在全站售后中各占多少，按占比降序。只返回品牌和占比（保留4位），最多100行。',['已批准退款金额','已批准退款记录数']),
        163:('统计全部历史有效订单，比较各省份的成交覆盖占全站的比例，按占比降序。只返回省份和占比（保留4位），最多100行。',['付费用户数','有效订单数']),
        164:('统计全部历史有效订单，比较各品类的购买规模在全站所占比例，按占比降序。只返回品类和占比（保留4位），最多100行。',['销售数量','购买过的商品SKU数']),
        165:('不限制时间，按用户等级比较全部客户的成交贡献占全站的比例，仅看有效订单。只返回用户等级和占比（保留4位），按占比降序，最多100行。',['销售金额','有效订单数']),
        166:('不限制时间，仅看已批准退款，比较各城市的售后发生规模占全站的比例。只返回城市和占比（保留4位），按占比降序，最多100行。',['退款记录数','发生退款的去重订单数']),
        167:('统计全部历史有效订单，比较各品牌的成交贡献占全站的比例。只返回品牌和占比（保留4位），按占比降序，最多100行。',['销售金额','销售数量']),
        168:('统计全部历史有效订单，比较各性别客户的购买规模占全站的比例。只返回性别和占比（保留4位），按占比降序，最多100行。',['销售数量','购买用户数']),
        169:('不限制时间，仅看已批准退款，比较各品类在全站售后中各占多少。只返回品类和占比（保留4位），按占比降序，最多100行。',['已批准退款金额','已批准退款记录数']),
        170:('统计全部历史有效订单，比较各城市的成交覆盖占全站的比例。只返回城市和占比（保留4位），按占比降序，最多100行。',['付费用户数','有效订单数']),
    }
    for n,(question,alternatives) in metric_questions.items():
        edit(n,'question',question,'Remove the accidentally exposed metric and accidental additional time ambiguity; retain the authored all-history reference population')
        edit(n,'ambiguity_alternatives',alternatives,'Use two reasonable metrics not competing implementations of an already-defined business metric')
        edit(n,'ambiguity_explanation','期间、分组、比例形式、状态和排序已指定，但贡献/覆盖/规模未指明具体度量。列出的两种度量都会改变分子分母，业务契约没有为这种泛称规定唯一指标。','Exactly one missing metric, not a missing period or reinterpretation of a defined metric')
    edit(162,'reference_sql',"SELECT p.brand,ROUND(SUM(r.refund_amount)/(SELECT SUM(refund_amount) FROM refunds WHERE refund_status='approved'),4) contribution_rate FROM products p JOIN refunds r ON r.product_id=p.product_id WHERE r.refund_status='approved' GROUP BY p.brand ORDER BY contribution_rate DESC LIMIT 100",'Use the real product relationship for brand attribution without excluding product-linked refunds lacking an item link')
    edit(169,'reference_sql',"SELECT p.category,ROUND(SUM(r.refund_amount)/(SELECT SUM(refund_amount) FROM refunds WHERE refund_status='approved'),4) contribution_rate FROM products p JOIN refunds r ON r.product_id=p.product_id WHERE r.refund_status='approved' GROUP BY p.category ORDER BY contribution_rate DESC LIMIT 100",'Use the real product relationship for category attribution')
    edit(171,'question','这份临时售后汇总要看云栖品牌手机数码的一个整体占比，不限时间。报表尚未说明是先汇总退款额和有效销售额再相除，还是逐商品计算退款率后取简单平均。请给出一个比率，保留4位小数。','A standard product refund rate is already defined and is not ambiguous; this explicitly asks for an as-yet-unspecified custom aggregation')
    edit(171,'simulated_answer','先把已批准退款金额和有效销售金额分别汇总，再用两项总额相除。','Chinese single-metric answer equivalent to the authored aggregate ratio')
    edit(171,'reference_sql',"SELECT ROUND((SELECT SUM(r.refund_amount) FROM refunds r JOIN products p ON p.product_id=r.product_id WHERE r.refund_status='approved' AND p.brand='云栖' AND p.category='手机数码')/NULLIF((SELECT SUM(oi.item_amount) FROM order_items oi JOIN orders o ON o.order_id=oi.order_id JOIN products p ON p.product_id=oi.product_id WHERE o.order_status IN('paid','completed','shipped') AND p.brand='云栖' AND p.category='手机数码'),0),4) refund_rate",'Denominator must include all qualifying valid sales, not only refunded lines; aggregate facts independently')
    edit(172,'question','南京市用户2026年9月订单的临时支付统计，分子已确定为当前状态有效的订单数，但成功率分母还未注明。请算一个成功率，保留4位小数；分母可能是全部状态订单，也可能排除unpaid状态订单。','Make the numerator and fixed month explicit; only denominator definition is missing')
    edit(172,'simulated_answer','分母包含这些用户在这个月创建的全部订单，不排除任何状态。','One denominator definition; do not repeat a full resolved query')
    edit(172,'ambiguity_alternatives',['分母为当月该城市全部订单数','分母为当月该城市排除unpaid后的订单数'],'Use actual observable state populations, not unsupported payment-attempt events')
    edit(173,'question','不限时间，统计至少买过一件松果品牌食品生鲜商品的有效订单，想看消费强度，但报表没说明按每单还是每位购买用户计算。只返回一个平均金额，保留2位小数；金额按符合条件订单整单实付计一次。','A defined order average is not ambiguous; the custom order-versus-customer aggregation is the sole missing metric choice')
    edit(173,'simulated_answer','按每笔有效订单算平均实付金额。','Single aggregation-grain choice in natural Chinese')
    edit(173,'reference_sql',"SELECT ROUND(AVG(o.paid_amount),2) avg_order_value FROM orders o WHERE o.order_status IN('paid','completed','shipped') AND EXISTS(SELECT 1 FROM order_items oi JOIN products p ON p.product_id=oi.product_id WHERE oi.order_id=o.order_id AND p.brand='松果' AND p.category='食品生鲜')",'Qualify orders with EXISTS so multiple matching items do not multiply order payments or counts')
    edit(174,'question','计算2026年8月服饰鞋包的动销覆盖比，分子是该月在有效订单中卖出过的去重SKU数。分母口径还没说明是全部商品SKU还是截至8月底仍在售的SKU，只返回一个比率，保留4位小数。','Specify the numerator while leaving only the denominator choice unresolved')
    edit(174,'simulated_answer','分母用8月31日及以前已上架、目前仍在售的SKU数，分子也限制在这个SKU集合。','One complete metric population definition')
    edit(174,'reference_sql',"SELECT ROUND((SELECT COUNT(DISTINCT oi.product_id) FROM order_items oi JOIN orders o ON o.order_id=oi.order_id JOIN products p ON p.product_id=oi.product_id WHERE p.category='服饰鞋包' AND p.is_active=1 AND p.launch_date<='2026-08-31' AND o.order_date BETWEEN '2026-08-01' AND '2026-08-31' AND o.order_status IN('paid','completed','shipped'))/NULLIF((SELECT COUNT(*) FROM products WHERE category='服饰鞋包' AND is_active=1 AND launch_date<='2026-08-31'),0),4) turnover_rate",'The SKU denominator includes unsold catalogue products, not only the joined sold subset')
    edit(175,'question','不限时间，统计北辰品牌美妆个护的一个售后覆盖比：分子是有效订单里发生过已批准退款的去重商品行数。分母尚未注明用该品牌品类有效订单数，还是有效商品行数。只返回一个比率，保留4位小数。','Define a custom record-coverage metric rather than reinterpret the business dictionary product refund rate')
    edit(175,'simulated_answer','用包含该品牌品类商品的去重有效订单数作分母。','One denominator choice, not a complete query')
    edit(175,'reference_sql',"WITH lines AS (SELECT oi.order_item_id,oi.order_id FROM order_items oi JOIN orders o ON o.order_id=oi.order_id JOIN products p ON p.product_id=oi.product_id WHERE p.brand='北辰' AND p.category='美妆个护' AND o.order_status IN('paid','completed','shipped')) SELECT ROUND((SELECT COUNT(DISTINCT l.order_item_id) FROM lines l JOIN refunds r ON r.order_item_id=l.order_item_id WHERE r.refund_status='approved')/NULLIF((SELECT COUNT(DISTINCT order_id) FROM lines),0),4) return_rate",'The denominator includes unrefunded qualifying orders; refunded lines are counted once across repeated refund records')
    edit(176,'question','不限时间，星禾品牌运动户外商品有效订单明细的折扣深度要怎么算？分子确定为明细优惠总额，但分母未说明用商品标价乘数量的总额，还是商品行实付总额。只返回一个比率，保留4位小数。','Specify a genuinely different pair of denominators for an undefined report metric')
    edit(176,'simulated_answer','用商品标价乘数量的合计作分母。','Single denominator choice in natural Chinese')
    edit(176,'ambiguity_alternatives',['商品标价乘数量之和','商品行实付金额之和'],'The raw alternative added discounts back and could equal the first denominator; use the genuinely distinct net-paid alternative stated in the question')
    edit(177,'question','不限时间，青橙品牌家用电器的重复购买客户占比是多少？分子确定为至少有两笔该品牌品类有效订单的客户数，但分母没说明是所有注册客户，还是至少买过一次的客户。只返回一个比率，保留4位小数。','Use two different populations; every historical buyer has a first purchase, so the raw alternatives were equivalent')
    edit(177,'simulated_answer','分母只算在这个品牌品类至少有一笔有效订单的客户。','Single metric-population definition')
    edit(177,'ambiguity_alternatives',['全部注册客户数','至少有一笔该品牌品类有效订单的去重客户数'],'Materially different denominators without adding a second missing date')
    sub(177,'reference_sql','COUNT(o.order_id) AS order_count','COUNT(DISTINCT o.order_id) AS order_count','Repeat buying counts separate orders, not multiple matching items in one order')
    edit(178,'question','不限时间，对澜庭品牌母婴用品的已批准退款，想知道从下单到发起退款的典型间隔是多少天。报表没有说明用算术平均还是中位数，只返回一个天数，保留2位小数。','The schema has order/refund dates, not approval-response timestamps. Use an observable elapsed interval and one missing aggregation choice')
    edit(178,'simulated_answer','用算术平均值。','One aggregation choice; approval state is already explicit')
    edit(178,'ambiguity_alternatives',['下单到发起退款间隔的算术平均','下单到发起退款间隔的中位数'],'Both alternatives are computable from the available dates')
    edit(178,'reference_sql',"SELECT ROUND(AVG(DATEDIFF(r.refund_date,o.order_date)),2) avg_interval_days FROM refunds r JOIN orders o ON o.order_id=r.order_id JOIN products p ON p.product_id=r.product_id WHERE p.brand='澜庭' AND p.category='母婴用品' AND r.refund_status='approved'",'Measure the observable purchase-to-refund interval, not an unsupported service-response time')
    edit(179,'question','以2026年9月12日为参考，近30天森活品牌手机数码有效订单明细的成本占比是多少？分子确定为商品成本价乘销量的总额，但分母未说明用商品行实付总额还是标价乘数量总额。只返回一个比率，保留4位小数。','Reject the unsupported inventory-turnover draft: the schema contains no inventory quantity. Replace it before any evaluation with a grounded cost metric and one denominator ambiguity')
    edit(179,'simulated_answer','用商品行实付总额作分母。','One grounded metric choice; no invented stock values')
    edit(179,'ambiguity_alternatives',['有效商品行实付总额','有效商品的标价乘数量总额'],'Both alternatives use existing fields; no inventory data or implicit initial stock assumption')
    edit(179,'reference_sql',"SELECT ROUND(SUM(oi.quantity*p.cost_price)/NULLIF(SUM(oi.item_amount),0),4) cost_rate FROM products p JOIN order_items oi ON oi.product_id=p.product_id JOIN orders o ON o.order_id=oi.order_id WHERE p.brand='森活' AND p.category='手机数码' AND o.order_status IN('paid','completed','shipped') AND o.order_date BETWEEN DATE_SUB('2026-09-12',INTERVAL 30 DAY) AND '2026-09-12'",'Remove fabricated initial inventory of 100 units; all inputs are actual schema fields and a fixed date range')
    edit(180,'question','优选品牌食品生鲜的新商品贡献比是多少？这里新品明确指2026年9月1日至12日上架的商品，分子是这些新品在同期间有效订单中的商品行销售额。分母尚未注明用该品牌品类同期间全部商品销售额，还是全历史销售额。只返回一个比率，保留4位小数。','Specify new-product and numerator periods so only the denominator definition is missing')
    edit(180,'simulated_answer','分母用同一期间该品牌品类全部商品的有效销售额。','One denominator choice; no full resolved query or result')
    edit(174,'question','计算2026年8月服饰鞋包的动销覆盖比，分子是选定SKU集合中该月在有效订单里卖出过的去重SKU数，分母是该集合的全部SKU数。集合还未说明是全部商品，还是8月底已上架且目前仍在售的商品，只返回一个比率，保留4位小数。','Make population choice the sole missing slot; answering must not alter an already-fixed numerator')
    edit(174,'simulated_answer','用8月31日及以前已上架、目前仍在售的SKU集合。','One population selection')
    sub(178,'question','发起退款','退款记录日期','Use observable refund date without claiming an unrecorded application timestamp')
    # Entity names and their suffix aliases are not distinct interpretations.
    entity_cases = {
      181: ('南京市','目标城市的VIP用户有哪些？返回姓名、注册日期，按注册日期升序，同日按用户ID升序，最多100人。',"SELECT user_name,register_date FROM users WHERE city='南京市' AND is_vip=1 ORDER BY register_date,user_id LIMIT 100"),
      182: ('成都市','目标城市在2026年9月12日前注册、最近一笔订单发生在2026年8月的用户，按用户等级统计人数。订单不限状态，按等级升序。',"WITH last_orders AS (SELECT user_id,MAX(order_date) d FROM orders GROUP BY user_id) SELECT u.user_level,COUNT(*) user_count FROM users u JOIN last_orders l ON l.user_id=u.user_id WHERE u.city='成都市' AND u.register_date<'2026-09-12' AND l.d BETWEEN '2026-08-01' AND '2026-08-31' GROUP BY u.user_level ORDER BY u.user_level"),
      183: ('杭州市','目标城市的女性付费用户首次有效订单日期是什么时候？返回姓名、等级、首次日期，按首次日期和用户ID升序，最多100人。',"SELECT u.user_name,u.user_level,MIN(o.order_date) first_date FROM users u JOIN orders o ON o.user_id=u.user_id WHERE u.city='杭州市' AND u.gender='female' AND o.order_status IN('paid','completed','shipped') GROUP BY u.user_id,u.user_name,u.user_level ORDER BY first_date,u.user_id LIMIT 100"),
      184: ('西安市','目标城市gold和black等级中，在2026年9月12日前有已批准退款记录的用户各有多少？按等级升序返回等级和去重人数。',"SELECT u.user_level,COUNT(DISTINCT u.user_id) user_count FROM users u JOIN orders o ON o.user_id=u.user_id JOIN refunds r ON r.order_id=o.order_id WHERE u.city='西安市' AND u.user_level IN('gold','black') AND r.refund_status='approved' AND r.refund_date<'2026-09-12' GROUP BY u.user_level ORDER BY u.user_level"),
      185: ('广州市','目标城市买过家用电器的付费用户有哪些？不限时间，返回姓名、城市、注册日期，按注册日期降序、用户ID升序，最多100人。',"SELECT u.user_name,u.city,u.register_date FROM users u WHERE u.city='广州市' AND EXISTS(SELECT 1 FROM orders o JOIN order_items oi ON oi.order_id=o.order_id JOIN products p ON p.product_id=oi.product_id WHERE o.user_id=u.user_id AND o.order_status IN('paid','completed','shipped') AND p.category='家用电器') ORDER BY u.register_date DESC,u.user_id LIMIT 100"),
      186: ('武汉市','目标城市silver用户中，2026年9月12日前有效订单累计实付超过5000元的有多少人？返回用户等级和人数。',"WITH spend AS (SELECT user_id,SUM(paid_amount) amount FROM orders WHERE order_status IN('paid','completed','shipped') AND order_date<'2026-09-12' GROUP BY user_id HAVING amount>5000) SELECT u.user_level,COUNT(*) user_count FROM users u JOIN spend s ON s.user_id=u.user_id WHERE u.city='武汉市' AND u.user_level='silver' GROUP BY u.user_level"),
      187: ('成都市','目标城市下过含云栖品牌商品订单的用户，最近一笔含该品牌商品的订单日期是什么？不限订单状态和时间，返回姓名、等级、最近日期，按日期降序、用户ID升序，最多100人。',"SELECT u.user_name,u.user_level,MAX(o.order_date) latest_date FROM users u JOIN orders o ON o.user_id=u.user_id WHERE u.city='成都市' AND EXISTS(SELECT 1 FROM order_items oi JOIN products p ON p.product_id=oi.product_id WHERE oi.order_id=o.order_id AND p.brand='云栖') GROUP BY u.user_id,u.user_name,u.user_level ORDER BY latest_date DESC,u.user_id LIMIT 100"),
      188: ('南京市','目标城市男性用户中，2026年9月12日前至少有3笔有效订单的各等级人数是多少？按等级升序返回等级和人数。',"WITH buyers AS (SELECT user_id FROM orders WHERE order_status IN('paid','completed','shipped') AND order_date<'2026-09-12' GROUP BY user_id HAVING COUNT(*)>=3) SELECT u.user_level,COUNT(*) user_count FROM users u JOIN buyers b ON b.user_id=u.user_id WHERE u.city='南京市' AND u.gender='male' GROUP BY u.user_level ORDER BY u.user_level"),
      189: ('杭州市','目标城市gold用户首次有效购买美妆个护商品是什么时候？不限时间，返回姓名、城市、首次日期，按日期升序、用户ID升序，最多100人。',"SELECT u.user_name,u.city,MIN(o.order_date) first_date FROM users u JOIN orders o ON o.user_id=u.user_id WHERE u.city='杭州市' AND u.user_level='gold' AND o.order_status IN('paid','completed','shipped') AND EXISTS(SELECT 1 FROM order_items oi JOIN products p ON p.product_id=oi.product_id WHERE oi.order_id=o.order_id AND p.category='美妆个护') GROUP BY u.user_id,u.user_name,u.city ORDER BY first_date,u.user_id LIMIT 100"),
      190: ('西安市','目标城市black用户中，2026年9月12日前有已批准退款的人，其全历史有效订单平均实付金额是多少？每笔有效订单计一次，不限于退款订单。返回等级、平均金额，金额保留2位小数。',"SELECT u.user_level,ROUND(AVG(o.paid_amount),2) avg_paid FROM users u JOIN orders o ON o.user_id=u.user_id WHERE u.city='西安市' AND u.user_level='black' AND o.order_status IN('paid','completed','shipped') AND EXISTS(SELECT 1 FROM refunds r JOIN orders ro ON ro.order_id=r.order_id WHERE ro.user_id=u.user_id AND r.refund_status='approved' AND r.refund_date<'2026-09-12') GROUP BY u.user_level"),
      191: ('七天无理由','以2026年9月12日为参考，近30天因指定原因发生已批准退款的商品有哪些？返回商品名、品牌、品类，去重，按商品名和商品ID升序，最多100件。',"SELECT p.product_name,p.brand,p.category FROM products p WHERE EXISTS(SELECT 1 FROM refunds r WHERE r.product_id=p.product_id AND r.refund_status='approved' AND r.refund_reason='七天无理由' AND r.refund_date BETWEEN DATE_SUB('2026-09-12',INTERVAL 30 DAY) AND '2026-09-12') ORDER BY p.product_name,p.product_id LIMIT 100"),
      192: ('家用电器','2026年8月指定品类中有有效销售的商品有哪些？返回商品名、品牌、上架日期，去重，按上架日期降序、商品ID升序，最多100件。',"SELECT p.product_name,p.brand,p.launch_date FROM products p WHERE p.category='家用电器' AND EXISTS(SELECT 1 FROM order_items oi JOIN orders o ON o.order_id=oi.order_id WHERE oi.product_id=p.product_id AND o.order_status IN('paid','completed','shipped') AND o.order_date BETWEEN '2026-08-01' AND '2026-08-31') ORDER BY p.launch_date DESC,p.product_id LIMIT 100"),
      193: ('手机数码','截至2026年9月12日，指定品类中已上架、目前仍在售，但从未出现在截至该日任何状态订单里的商品有哪些？返回商品名、品牌、标价，按标价和商品ID升序，最多100件。',"SELECT p.product_name,p.brand,p.list_price FROM products p WHERE p.category='手机数码' AND p.is_active=1 AND p.launch_date<='2026-09-12' AND NOT EXISTS(SELECT 1 FROM order_items oi JOIN orders o ON o.order_id=oi.order_id WHERE oi.product_id=p.product_id AND o.order_date<='2026-09-12') ORDER BY p.list_price,p.product_id LIMIT 100"),
      194: ('服饰鞋包','列出2026年9月11日创建、当前为有效状态的订单中指定品类的商品明细，返回订单号、商品名、数量，一行一条商品明细，按数量降序、订单项ID升序，最多100行。',"SELECT o.order_no,p.product_name,oi.quantity FROM orders o JOIN order_items oi ON oi.order_id=o.order_id JOIN products p ON p.product_id=oi.product_id WHERE o.order_date='2026-09-11' AND o.order_status IN('paid','completed','shipped') AND p.category='服饰鞋包' ORDER BY oi.quantity DESC,oi.order_item_id LIMIT 100"),
      195: ('美妆个护','云栖品牌指定品类中，2026年9月1日至12日发生过已批准退款的商品有哪些？返回商品名、上架日期、在售标记，去重，按上架日期和商品ID升序，最多100件。',"SELECT p.product_name,p.launch_date,p.is_active FROM products p WHERE p.brand='云栖' AND p.category='美妆个护' AND EXISTS(SELECT 1 FROM refunds r WHERE r.product_id=p.product_id AND r.refund_status='approved' AND r.refund_date BETWEEN '2026-09-01' AND '2026-09-12') ORDER BY p.launch_date,p.product_id LIMIT 100"),
      196: ('母婴用品','2026年9月12日创建的有效订单里，指定品类有哪些商品？返回商品名、品牌、成本价，去重，按成本价降序、商品ID升序，最多100件。',"SELECT p.product_name,p.brand,p.cost_price FROM products p WHERE p.category='母婴用品' AND EXISTS(SELECT 1 FROM order_items oi JOIN orders o ON o.order_id=oi.order_id WHERE oi.product_id=p.product_id AND o.order_date='2026-09-12' AND o.order_status IN('paid','completed','shipped')) ORDER BY p.cost_price DESC,p.product_id LIMIT 100"),
      197: ('运动户外','优选品牌指定品类，2026年8月有效订单明细的简单平均成交单价超过200元的商品有哪些？不按数量加权，返回商品名、品牌、品类、均价，均价保留2位小数，按显示均价降序、商品ID升序，最多100件。',"SELECT p.product_name,p.brand,p.category,ROUND(AVG(oi.unit_price),2) avg_price FROM products p JOIN order_items oi ON oi.product_id=p.product_id JOIN orders o ON o.order_id=oi.order_id WHERE p.brand='优选' AND p.category='运动户外' AND o.order_status IN('paid','completed','shipped') AND o.order_date BETWEEN '2026-08-01' AND '2026-08-31' GROUP BY p.product_id,p.product_name,p.brand,p.category HAVING AVG(oi.unit_price)>200 ORDER BY avg_price DESC,p.product_id LIMIT 100"),
      198: ('食品生鲜','南京市用户2026年9月11日创建、当前状态为shipped的订单中，指定品类商品明细有哪些？返回订单号、用户姓名、商品名、数量，按数量和订单项ID升序，最多100行。',"SELECT o.order_no,u.user_name,p.product_name,oi.quantity FROM users u JOIN orders o ON o.user_id=u.user_id JOIN order_items oi ON oi.order_id=o.order_id JOIN products p ON p.product_id=oi.product_id WHERE u.city='南京市' AND o.order_date='2026-09-11' AND o.order_status='shipped' AND p.category='食品生鲜' ORDER BY oi.quantity,oi.order_item_id LIMIT 100"),
      199: ('家用电器','北辰品牌指定品类，2026年9月1日至12日因七天无理由获批的退款记录有哪些？一行一条退款记录，返回商品名、品牌、品类、退款金额，按退款金额降序、退款记录ID升序，最多100行。',"SELECT p.product_name,p.brand,p.category,r.refund_amount FROM products p JOIN refunds r ON r.product_id=p.product_id WHERE p.brand='北辰' AND p.category='家用电器' AND r.refund_status='approved' AND r.refund_reason='七天无理由' AND r.refund_date BETWEEN '2026-09-01' AND '2026-09-12' ORDER BY r.refund_amount DESC,r.refund_id LIMIT 100"),
      200: ('美妆个护','成都市用户2026年9月12日创建的有效订单中，松果品牌指定品类的商品明细有哪些？一行一条商品明细，返回订单号、城市、商品名、品牌、品类，按商品名和订单项ID升序，最多100行。',"SELECT o.order_no,u.city,p.product_name,p.brand,p.category FROM users u JOIN orders o ON o.user_id=u.user_id JOIN order_items oi ON oi.order_id=o.order_id JOIN products p ON p.product_id=oi.product_id WHERE u.city='成都市' AND o.order_date='2026-09-12' AND o.order_status IN('paid','completed','shipped') AND p.brand='松果' AND p.category='美妆个护' ORDER BY p.product_name,oi.order_item_id LIMIT 100"),
    }
    for n,(value,question,sql) in entity_cases.items():
        edit(n,'question',question,'The raw draft supplied the entity and mistook aliases for ambiguity; specify all other conditions and leave exactly one target value missing before freeze')
        edit(n,'reference_sql',sql,'Match the observable fields, stated date scope, aggregation grain and public tie-break; no candidate results observed')
        edit(n,'simulated_answer',value+'。','Supply only the requested frozen entity/filter value')
        edit(n,'answer_slot','filter' if n==191 else 'entity','One missing refund reason, city or category')
        alternative='上海市' if n<=190 else ('质量问题' if n==191 else ('手机数码' if value!='手机数码' else '家用电器'))
        edit(n,'ambiguity_alternatives',[value,alternative],'Different stored entities, not abbreviations for the same entity')
        edit(n,'ambiguity_explanation','目标筛选值没有给出；两个真实数据库取值会筛选不同记录。','One materially different entity/filter choice')
    ties={
        71:('order_item_id','订单项ID'),72:('order_id','订单ID'),73:('order_item_id','订单项ID'),
        74:('order_item_id','订单项ID'),75:('product_id','商品ID'),77:('order_id','订单ID'),
        78:('order_item_id','订单项ID'),79:('product_id','商品ID'),80:('order_item_id','订单项ID'),
        81:('brand,category','品牌、品类'),82:('p.brand,p.category','品牌、品类'),
        83:('p.brand,p.category','品牌、品类'),84:('brand,category','品牌、品类'),
        85:('brand,category','品牌、品类'),86:('brand,category','品牌、品类'),
        87:('prices.brand,prices.category','品牌、品类'),88:('brand,category','品牌、品类'),
        89:('p.brand,p.category','品牌、品类'),90:('brand,category','品牌、品类'),
        94:('refund_no','退款单号'),97:('refund_no','退款单号'),99:('refund_no','退款单号'),
        101:('o.payment_method','支付方式'),103:('r.refund_id','退款记录ID'),104:('r.refund_reason','退款原因'),
        105:('r.refund_id','退款记录ID'),107:('r.refund_id','退款记录ID'),109:('r.refund_id','退款记录ID'),
        110:('r.refund_reason','退款原因'),121:('u.user_id','用户ID'),123:('p.product_id','商品ID'),
        126:('u.user_id','用户ID'),127:('p.product_id','商品ID'),129:('o.order_id','订单ID'),
        130:('p.product_id','商品ID'),131:('user_level','用户等级'),134:('user_name','用户姓名'),
        137:('o.order_no','订单号'),139:('user_id','用户ID'),140:('r.refund_no','退款单号'),
        151:('refund_reason','退款原因'),152:('o.payment_method','支付方式'),
        153:('o.order_status','订单状态'),154:('sales.category','品类'),155:('u.city','城市'),
        156:('r.refund_reason','退款原因'),157:('r.refund_no','退款单号'),158:('r.refund_no','退款单号'),
        159:('r.refund_reason','退款原因'),160:('r.refund_no','退款单号'),
        161:('u.city','城市'),162:('p.brand','品牌'),163:('u.province','省份'),
        164:('p.category','品类'),165:('u.user_level','用户等级'),166:('u.city','城市'),
        167:('p.brand','品牌'),168:('u.gender','性别'),169:('p.category','品类'),170:('u.city','城市'),
    }
    for n,(keys,words) in ties.items():
        tree=sqlglot.parse_one(cases[n-1]['reference_sql'],read='mysql')
        extra=sqlglot.parse_one('SELECT 1 ORDER BY '+keys,read='mysql').args['order'].expressions
        assert tree.args.get('order') is not None
        tree.args['order'].set('expressions',tree.args['order'].expressions+extra)
        edit(n,'reference_sql',tree.sql(dialect='mysql'),'Stable explicit tie-break; no scoring changes')
        edit(n,'question',cases[n-1]['question']+' 主排序值相同时，再按'+words+'升序。','Expose the deterministic tie-break to both modes')
    # Tie breaks are stated in both the public question and its reference, never hidden in scoring.
    for n,old,new,words in [(63,'ORDER BY u.register_date ASC','ORDER BY u.register_date ASC,u.user_id ASC','同注册日按用户ID升序'),
                            (65,'ORDER BY u.register_date DESC','ORDER BY u.register_date DESC,u.user_id ASC','同注册日按用户ID升序'),
                            (69,'ORDER BY DATEDIFF(MAX(o.order_date), MIN(o.order_date)) DESC, u.user_id ASC','ORDER BY DATEDIFF(MAX(o.order_date), MIN(o.order_date)) DESC, u.user_id ASC','跨度相同按用户ID升序')]:
        edit(n,'question',cases[n-1]['question']+' '+words+'。','Make reference tie-break visible to both systems')
        sub(n,'reference_sql',old,new,'Match the explicit tie-break')
    for n,c in enumerate(cases,1):
        edit(n,'intended_meaning',c['question'] if c['kind']=='clear' else c['question']+'\n预设单slot补充：'+c['simulated_answer'],'Keep private authoring intent consistent with the reviewed public question and single-slot answer')
        if n in (173,174,178,179) or n>=181:
            edit(n,'semantic_signature','reviewed-'+str(n)+'-'+c['question'],'Replace stale draft signatures after pre-freeze semantic review')
    target=OUT/'reviewed_cases.json'
    assert not target.exists(), 'Preserve prior reviewed artifact'
    write_json(target,cases)
    write_json(OUT/'curation_changes.json',{'source_sha256':sha(source),'curator_sha256':sha(Path(__file__)),
        'reviewed_sha256':sha(target),'candidate_calls':0,'changes':changes,
        'status':'Pre-freeze; further novelty and full reference review still required'})


if __name__=='__main__':
    curate()
