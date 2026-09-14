"""Materialize the manually reviewed, question-only simulated-user decisions."""

import json
from pathlib import Path

from eval.scoring import write_json

ROOT=Path(__file__).resolve().parents[1]


def main():
    target=ROOT/'eval/scoped_reply_review.json'
    assert not target.exists(), 'Do not overwrite prior user review'
    packet=json.loads((ROOT/'eval/scoped_reply_packet.json').read_text())
    times={61,62,63,64,65,66,67,68,69,70,71,72,73,76,77,79,80}
    metrics={81,82,83,84,85,86,87,88,89,92,93,94,95,96,97,98,99,100}
    filters={101,102,103,104,105,106,108,109,110,111,112,113,114,115,116,117,118,119,120}
    rejected={35,55}
    assert {int(p['id'].split('-')[1]) for p in packet}==times|metrics|filters|rejected
    rows=[]
    for p in packet:
        n=int(p['id'].split('-')[1])
        if n in rejected:
            reason='明确城市问题被要求确认数据库精确存储值；预设用户没有数据库存储知识，不猜测市后缀，不替换城市。'
        elif n in times:
            reason='实际反问请求时间范围；仅提供预设起止日期和边界。日期区间与天数是同一时间槽的等价表达，不补其他条件。'
        elif n in metrics:
            reason='实际反问请求业务指标；只提供预设指标口径，不追加时间、实体、排名或完整标准问题。'
        else:
            reason='实际反问请求题面缺失的筛选或实体范围；仅提供相应预设值，不补其他条件。'
        if n==103:
            reason='反问确实询问退款原因，另外询问是否限时间。只回复已知原因；原问题累计按既有全部历史口径，不编造日期。若系统仍要求新时间，完整性检查须失败。'
        if n==110:
            reason='实际询问VIP身份范围，示例偏向VIP等级但属于开放举例。只提供预设非VIP身份，不接受示例中未经验证的等级等价关系。'
        if n==115:
            reason='反问中的部分退款原因举例不是实际存储值，但明确允许直接提供确切文本。只回复预设的七天无理由，不改为示例中的其他原因。'
        if n in {97,98,99,100}:
            reason+=' 反问允许其他指标，故可明确提供商品行金额、退款记录条数或平均金额，不被错误或不完整的示例限定。'
        rows.append({'id':p['id'],'actual_question':p['actual_question'],
                     'valid_question':n not in rejected,
                     'answer_segments':[] if n in rejected else [p['persona_answer']],
                     'reason':reason,'review_method':'manual question-only review; no SQL/GT/labels in packet'})
    write_json(target,rows)
    print('Reviewed 56 actual questions: 54 scoped replies, 2 unavailable. No candidate calls.')


if __name__=='__main__':main()
