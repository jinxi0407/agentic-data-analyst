"""Record local human-style adjudication of the 29 observed clarification questions.

This is evaluation evidence, never candidate logic. No SQL, labels, full intended
query or Ground Truth is loaded. Do not use this as an automatic answer generator.
"""

from eval.run_final_mixed import PACKET, REVIEWS
from eval.run_300_clarification_regression import read, sha
from eval.scoring import write_json


def record():
    assert not REVIEWS.exists(), 'Preserve the original reply review'
    reasons={
      141:'Asked for the recent period; the frozen start/end dates answer only that period.',
      143:'Asked what that time period means; the frozen explicit date interval supplies it.',
      147:'Asked how long the recent period is; the frozen interval supplies exactly the date filter.',
      149:'The English question asks for the date range; the frozen Chinese/numeric date interval directly answers it.',
      152:'Asked for the refund period, including the option of a custom range; the frozen interval matches.',
      153:'Asked only for the shared period; the frozen interval leaves both pre-existing date bases and status rules intact.',
      154:'Asked only for the sales/refund period; the frozen range does not add or change either business formula.',
      155:'Asked how long the refund period is; the frozen interval is a direct answer.',
      156:'Asked for the refund period; the fixed payment method and requested averages are untouched.',
      159:'Asked for the refund period; the frozen interval leaves the cash payment constraint unchanged.',
      171:'Asked aggregate-first ratio versus mean of product ratios; the frozen answer selects aggregate-first only.',
      172:'Asked whether the denominator includes unpaid orders; the frozen answer includes every status. The filter tag denotes the same missing denominator choice.',
      173:'Asked mean per order versus per purchasing user; the frozen answer selects per-order average only.',
      174:'Asked which SKU population to use; the frozen answer selects the pre-August-end/currently-active population. Entity versus metric tagging does not change the actual question.',
      180:'Asked same-period versus all-history denominator; the frozen answer selects the already-stated same period only.',
      181:'Asked which target city; the frozen city name is the complete single missing value.',
      182:'Asked which target city; the frozen city name adds no date or order-state information.',
      183:'Asked which target city; the frozen city name leaves gender and valid-order conditions intact.',
      184:'Asked which city or cities; one frozen city directly answers it. Filter versus entity tagging is not a semantic mismatch.',
      185:'Asked which target city; the frozen city name leaves category and customer conditions unchanged.',
      186:'Asked which target city; the frozen city name is sufficient despite the filter tag.',
      187:'Asked which target city; the frozen city name leaves the brand and latest-qualifying-order query unchanged.',
      188:'Asked which target city; the frozen city name adds no order threshold or date information.',
      190:'Asked which target city; the frozen city name leaves the refund cohort and payment grain unchanged.',
      191:'Asked which refund reason. Some illustrative reasons are not actual stored metadata, but the question is open-ended; the frozen valid reason directly answers it without adopting those examples.',
      192:'Asked which product category; the frozen category supplies exactly that filter.',
      193:'Asked which product category; the frozen category does not modify the existing launch/on-sale/absence conditions.',
      194:'Asked which product category; the frozen category supplies only the missing product filter.',
      196:'Asked which category or categories; the single frozen category is a valid direct response.',
    }
    packets=read(PACKET)
    assert {int(p['id'].rsplit('_',1)[1]) for p in packets}==set(reasons)
    reviews=[]
    for p in packets:
        assert p['slot_eligible'] and p['frozen_answer']
        reviews.append({'id':p['id'],'actual_question':p['actual_question'],
            'answerable':True,'reason':reasons[int(p['id'].rsplit('_',1)[1])],
            'packet_sha256':sha(PACKET),'review_method':'Local manual comparison of public question, actual follow-up and pre-frozen single-slot answer only'})
    write_json(REVIEWS,reviews)
    print('29 actual questions reviewed; 29 exact frozen single-slot answers eligible; no new answer text created')


if __name__=='__main__':
    record()
