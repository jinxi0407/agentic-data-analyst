"""Final local pre-freeze corrections; retain both earlier draft audit versions."""

import sqlglot
from eval.audit_final_mixed import ROOT, OUT, read, sha
from eval.scoring import write_json


def review():
    assert not (ROOT/'eval/final_mixed_events.jsonl').exists()
    source=OUT/'reviewed_cases.json'
    target=OUT/'accepted_cases.json'
    assert not target.exists()
    cases=read(source)
    changes=[]
    def edit(n,key,value,reason):
        before=cases[n-1][key]
        if before!=value:
            cases[n-1][key]=value
            changes.append({'id':cases[n-1]['id'],'field':key,'before':before,'after':value,'reason':reason})
    def replace(n,key,before,after,reason):
        assert before in cases[n-1][key]
        edit(n,key,cases[n-1][key].replace(before,after),reason)
    replace(175,'reference_sql','lines','qualified_items','MySQL reserves LINES; rename CTE without altering its query')
    edit(41,'question','按订单状态汇总全历史订单：返回状态、订单数、使用现金支付的订单占比（保留4位小数），按订单数降序、状态升序。','Reject historical count-only template before freeze; add a substantive payment-mix measure')
    edit(41,'reference_sql',"SELECT order_status,COUNT(*) n,ROUND(AVG(CASE WHEN payment_method='cash' THEN 1 ELSE 0 END),4) cash_share FROM orders GROUP BY order_status ORDER BY n DESC,order_status",'Match the distinct payment-mix question')
    edit(98,'question','不限时间，退款申请原因中，拒绝笔数最多的前3个原因是什么？返回原因、拒绝笔数、该原因全部状态退款记录数，按拒绝笔数降序、原因升序。','Reject the historical all-record count ranking; evaluate rejected workload and its population together')
    edit(98,'reference_sql',"SELECT refund_reason,SUM(CASE WHEN refund_status='rejected' THEN 1 ELSE 0 END) rejected_count,COUNT(*) all_count FROM refunds GROUP BY refund_reason ORDER BY rejected_count DESC,refund_reason LIMIT 3",'Both conditional and unconditional counts share the same reason population')
    edit(148,'question','最近发生且已批准的退款，按原因各有多少笔，平均每笔多少钱？只返回原因、笔数、平均金额，金额保留2位，按原因升序。','Separate this task from the sum-only reason ranking in 151; no mere date substitution')
    edit(148,'reference_sql',"SELECT refund_reason,COUNT(*) n,ROUND(AVG(refund_amount),2) avg_amount FROM refunds WHERE refund_date BETWEEN '2026-09-01' AND '2026-09-12' AND refund_status='approved' GROUP BY refund_reason ORDER BY refund_reason",'Freeze the same missing date slot but a different observable business summary')
    edit(59,'question','按下单月份和订单状态，统计全历史cancelled、unpaid订单的总毛额、总折扣额和总实收金额。返回月份（YYYY-MM）、状态和上述三项金额，按月份、状态升序，最多100行。','Avoid a status-literal-only copy of case 57; examine the monthly outstanding-order profile')
    edit(59,'reference_sql',"SELECT DATE_FORMAT(order_date,'%Y-%m') month,order_status,SUM(gross_amount) gross,SUM(discount_amount) discount,SUM(paid_amount) paid FROM orders WHERE order_status IN('cancelled','unpaid') GROUP BY month,order_status ORDER BY month,order_status LIMIT 100",'New monthly grain is explicit in the public question')
    edit(96,'question','看2026年9月1日至12日已批准退款的日金额和该期间截至当日的累计金额，只列有退款的日期。返回日期、当日金额、期间累计金额，按日期升序。','Distinguish the cumulative cash-outflow task from a date-only substitution of historical daily sums')
    edit(96,'reference_sql',"WITH daily AS (SELECT refund_date,SUM(refund_amount) amount FROM refunds WHERE refund_status='approved' AND refund_date BETWEEN '2026-09-01' AND '2026-09-12' GROUP BY refund_date) SELECT refund_date,amount,SUM(amount) OVER(ORDER BY refund_date ROWS UNBOUNDED PRECEDING) cumulative_amount FROM daily ORDER BY refund_date",'Period running total, not an all-history running total')
    edit(126,'question','列出2026年9月12日前注册、有订单但所有订单都为cancelled或unpaid的用户。只返回用户ID、姓名、注册日期，按注册日期降序、用户ID升序，最多100人。','The original no-order plus no-refund predicate was redundant with case 121; distinguish unsuccessful-order customers from never-order customers')
    edit(126,'reference_sql',"SELECT u.user_id,u.user_name,u.register_date FROM users u WHERE u.register_date<'2026-09-12' AND EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.user_id) AND NOT EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.user_id AND o.order_status NOT IN('cancelled','unpaid')) ORDER BY u.register_date DESC,u.user_id LIMIT 100",'Require at least one order, and no other order status')
    edit(134,'question','帮我按城市看看，2026年9月12日以前注册的用户里，到现在一条订单记录都没有的占多少？只给我城市和占比，保留四位小数，按城市升序。','Normal operational paraphrase with a distinct population-share task, not another no-order user listing')
    edit(134,'reference_sql',"SELECT u.city,ROUND(AVG(CASE WHEN NOT EXISTS(SELECT 1 FROM orders o WHERE o.user_id=u.user_id) THEN 1 ELSE 0 END),4) no_order_share FROM users u WHERE u.register_date<'2026-09-12' GROUP BY u.city ORDER BY u.city",'Denominator includes all registered users in each city, including those with orders')
    edit(18,'question','把用户按注册日期、用户ID升序排好，找出相邻两人注册日相差超过30天的位置。返回天数差和后一人的姓名，按天数差降序、后一人用户ID升序，最多100行。','The LAG tie-break determines which customer follows a gap; state it before execution')
    edit(18,'reference_sql',"SELECT DATEDIFF(register_date,prev_date) gap_days,user_name FROM (SELECT user_id,user_name,register_date,LAG(register_date) OVER(ORDER BY register_date,user_id) prev_date FROM users) t WHERE DATEDIFF(register_date,prev_date)>30 ORDER BY gap_days DESC,user_id LIMIT 100",'Stable window and output ordering')
    replace(125,'question','从未使用过微信支付','从未有任何状态微信支付方式订单记录','Do not infer actual completed payment from an unpaid order record')
    replace(140,'question','因为描述不符申请、并且已经批准的退款','记录的、原因为描述不符且已经批准的退款','Do not invent a separate application timestamp')
    replace(83,'reference_sql','HAVING coverage_rate > 0.005','HAVING COUNT(DISTINCT o.order_id)*1.0/(SELECT COUNT(*) FROM orders WHERE order_status IN (\'paid\',\'completed\',\'shipped\')) > 0.005','Threshold applies to the exact coverage, not its rounded display')
    replace(88,'reference_sql','HAVING unit_profit BETWEEN 50 AND 200','HAVING AVG(list_price)-AVG(cost_price) BETWEEN 50 AND 200','Threshold applies to the exact mean difference')
    edit(90,'question',cases[89]['question']+' x为商品标价，s为样本标准差；只纳入样本标准差大于0的组合。','Make the stated skewness formula and zero-variance treatment fully determined')
    ties={1:('gender','性别'),4:('province','省份'),6:('user_level','等级'),7:('gender','性别'),8:('city','城市'),9:('user_level','等级'),
          21:('product_id','商品ID'),22:('brand','品牌'),23:('product_id','商品ID'),24:('category','品类'),25:('product_id','商品ID'),
          26:('product_id','商品ID'),27:('brand','品牌'),28:('product_id','商品ID'),29:('brand','品牌'),30:('product_id','商品ID'),
          35:('product_id','商品ID'),38:('product_id','商品ID'),40:('product_id','商品ID'),46:('order_status','订单状态'),
          49:('order_status','订单状态'),54:('order_status','订单状态'),56:('o.order_status','订单状态'),91:('refund_reason','退款原因'),
          93:('refund_reason','退款原因'),135:('r.refund_reason','退款原因'),136:('product_id','商品ID')}
    for n,(key,label) in ties.items():
        tree=sqlglot.parse_one(cases[n-1]['reference_sql'],read='mysql')
        extra=sqlglot.parse_one('SELECT 1 ORDER BY '+key,read='mysql').args['order'].expressions
        tree.args['order'].set('expressions',tree.args['order'].expressions+extra)
        edit(n,'reference_sql',tree.sql(dialect='mysql'),'Public stable tie-break, no scoring modification')
        edit(n,'question',cases[n-1]['question']+' 以上排序相同时，再按'+label+'升序。','Expose tie-break to both candidates')
    for n,c in enumerate(cases,1):
        edit(n,'intended_meaning',c['question'] if c['kind']=='clear' else c['question']+'\n预设单slot补充：'+c['simulated_answer'],'Synchronize authoring intent before freeze')
    write_json(target,cases)
    write_json(OUT/'final_reference_review_changes.json',{'candidate_calls':0,'source_sha256':sha(source),
        'target_sha256':sha(target),'reviewer_source_sha256':sha(__import__('pathlib').Path(__file__)),
        'changes':changes,'status':'Awaiting final reference execution and novelty review'})


if __name__=='__main__':
    review()
