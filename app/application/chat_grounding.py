"""Conservative compositional assertion grammar, not general natural-language proof.

Every material clause must parse completely to an issued fact. Unknown clauses,
polarity, roles, numbers, units, entity/path or compound additions fail closed.
The provider writes text, not template IDs. This grammar deliberately accepts only
a bounded bilingual language; unsupported true paraphrases may fall back.
"""
import re
import unicodedata
from app.application.contracts.chat_generation import ConversationalOutput
from app.application.contracts.assistant_chat import ChatClaim,AssistantResponse


def norm(text):
    # Preserve đ and negation; normalize case/spacing only, never strip semantics.
    return ' '.join(unicodedata.normalize('NFC',text).casefold().split())


def canonical_clause(card,locale='vi'):
    vi=locale=='vi';v=card.display;u=card.unit
    texts={
        'total':f'Tổng chi của phương án đang xem là {v} {u}' if vi else f'The viewed option total outlay is {v} {u}',
        'purchase_cost':f'Tiền mua là {v} {u}' if vi else f'Purchase outlay is {v} {u}',
        'fees':f'Phí phải trả là {v} {u}' if vi else f'Payable fees are {v} {u}',
        'budget':f'Ngân sách đã lưu là {v} {u}' if vi else f'The retained budget limit is {v} {u}',
        'cost_unknown':'Chi phí phương án chưa có, không đồng nghĩa bằng không' if vi else 'Option cost is unavailable, which does not mean zero',
        'winner':'Run này có phương án được khuyến nghị' if vi else 'This Run has a recommended option',
        'no_winner':'Run này chưa có phương án đủ điều kiện được chọn' if vi else 'No eligible option was selected in this Run',
        'failed':'Run gặp lỗi thực thi; winner đã lưu chỉ dùng chẩn đoán, không phải khuyến nghị khả dụng' if vi else 'The Run failed; its retained winner is diagnostic, not an available recommendation',
        'failed_unknown':'Run gặp lỗi thực thi; kết quả còn thiếu không phải khuyến nghị khả dụng' if vi else 'The Run failed; missing results are not an available recommendation',
        'blocked':'Run chưa tính được đầy đủ để tạo khuyến nghị; cần xem vấn đề chặn đã lưu' if vi else 'The Run could not complete computation for a recommendation; review retained blockers',
        'rejection':f'Phương án {card.entity_id}: {v}' if vi else f'Option {card.entity_id}: {v}',
        'selector':'Selector xét các phương án đủ điều kiện theo chi phí, sau đó mức đáp ứng từng món và thứ tự kỹ thuật khi hòa' if vi else 'The selector compares eligible options by outlay, then Product service and a stable technical tie-break',
        'proof_boundary':'Chỉ so sánh các phương án đã đánh giá, không chứng minh tối ưu toàn cục' if vi else 'Only evaluated options are compared, not proof of global optimality',
        'proof_unknown':'Chưa có bằng chứng selector để giải thích thứ hạng' if vi else 'Selector evidence for ranking is unavailable',
        'unproven':'Tìm kiếm chưa có chứng nhận đầy đủ trong miền hữu hạn đã lưu' if vi else 'Search has no complete certificate over the retained finite domain',
        'pair_cost':f'Chênh tổng chi của cặp đang xem là {v} {u} (sau trừ trước)' if vi else f'Viewed pair outlay change is {v} {u} (to minus from)',
        'pair_service':f'Món {card.entity_id} trên đường {card.path} chênh lượng phục vụ {v} {u} (sau trừ trước)' if vi else f'Product {card.entity_id} on path {card.path} has fulfilled change {v} {u} (to minus from)',
        'comparison_unknown':'Chưa có bằng chứng so sánh cặp phương án để kết luận lợi ích đánh đổi' if vi else 'Pairwise trade-off evidence is unavailable',
        'purchase_quantity':(f'Lượng mua đề xuất '+(f'của dòng {card.entity_id} ' if card.entity_id else '')+f'cho nguyên liệu đang xem là {v} {u}') if vi else (f'Proposed purchase quantity '+(f'on line {card.entity_id} ' if card.entity_id else '')+f'for the viewed Ingredient is {v} {u}'),
        'purchase_zero':'Phương án đang xem không có dòng mua đề xuất cho nguyên liệu này' if vi else 'The viewed option has no proposed purchase lines for this Ingredient',
        'purchase_unknown':'Lượng mua của phương án chưa có, không đồng nghĩa bằng không' if vi else 'Option purchase quantity is unavailable, which does not mean zero',
        'service':(f'Mô phỏng món {card.entity_id} trên đường {card.path}: yêu cầu {card.requested} {u}, phục vụ {v} {u}, mất bán {card.lost_sales} {u}, mức đáp ứng '+(f'{card.service_percent}%' if card.service_percent is not None else 'chưa xác định')) if vi else
            (f'Simulated Product {card.entity_id} on path {card.path}: requested {card.requested} {u}, fulfilled {v} {u}, lost sales {card.lost_sales} {u}, service '+(f'{card.service_percent}%' if card.service_percent is not None else 'undefined')),
        'coverage':f'Phạm vi đã tính gồm {v}/{u} món' if vi else f'Computed scope covers {v}/{u} Products',
        'limitations':'Chưa có bằng chứng nhân quả, xác suất, kết quả thực tế hoặc so sánh không mua' if vi else 'Causal, probability, actual-outcome and zero-purchase comparison evidence is unavailable',
    }
    return texts[card.kind]


def alternatives(card,locale):
    """Full-clause grammar patterns: exact slots, bounded synonyms and connectors."""
    v=re.escape(norm(card.display or ''));u=re.escape(norm(card.unit or ''))
    if card.unit=='VND':u=r'(?:vnd|đồng)'
    entity=re.escape(norm(card.entity_id or ''));path=re.escape(norm(card.path or ''))
    vi=locale=='vi';kind=card.kind
    patterns=[re.escape(norm(canonical_clause(card,locale)))]
    amount=rf'{v}\s+{u}'
    if vi:
        subjects=r'(?:(?:phương án|kế hoạch)(?: này| đang xem)?\s+)?'
        patterns+= {
            'total':[rf'{subjects}(?:có |cần |sẽ cần )?(?:tổng chi|tổng chi phí|tổng chi tiêu|tổng số tiền)(?: là| bằng|:)? {amount}',rf'{subjects}(?:tốn|chi|cần chi) {amount}',rf'(?:tổng chi|tổng chi phí)(?: của phương án| của kế hoạch)(?: này| đang xem)?(?: là| bằng|:)? {amount}'],
            'purchase_cost':[rf'(?:chi phí mua hàng|tiền mua|chi phí mua|tiền hàng)(?: là| bằng|:)? {amount}'],
            'fees':[rf'(?:phí phải trả|các khoản phí phải trả|phí)(?: là| bằng|:)? {amount}'],
            'budget':[rf'(?:ngân sách|giới hạn ngân sách)(?: đã lưu| của run| của kế hoạch)?(?: là| bằng|:)? {amount}'],
            'winner':[r'(?:run|kế hoạch) này (?:có|đã có) (?:một )?phương án (?:được |đủ điều kiện được )?khuyến nghị'],
            'no_winner':[r'(?:run|kế hoạch) này (?:(?:hiện |vẫn )?)(?:chưa có|không có) phương án (?:nào )?(?:đủ điều kiện )?được (?:chọn|lựa chọn|khuyến nghị)',r'chưa chọn được phương án đủ điều kiện trong run này'],
            'proof_boundary':[r'(?:kết quả|khuyến nghị|việc lựa chọn)(?: này)? chỉ (?:áp dụng cho|so sánh|xét) các phương án đã (?:được )?đánh giá(?:,| và|;) không (?:phải là |có |đủ )?(?:chứng minh|bằng chứng|chứng nhận)(?: cho)? tối ưu toàn cục'],
            'unproven':[r'(?:việc |quá trình )?tìm kiếm (?:chưa|không) có chứng nhận đầy đủ(?: trong| trên| cho) miền hữu hạn đã lưu'],
            'comparison_unknown':[r'(?:chưa|không) có (?:dữ liệu|bằng chứng) so sánh (?:cặp|giữa các) phương án(?: để kết luận lợi ích đánh đổi)?'],
            'purchase_zero':[r'(?:phương án|kế hoạch) đang xem (?:không có|chưa có) dòng mua đề xuất cho nguyên liệu (?:này|đang xem)'],
            'purchase_quantity':[rf'(?:lượng|số lượng) mua đề xuất (?:của|cho) dòng {entity}(?: cho nguyên liệu đang xem)?(?: là|:)? {amount}'],
            'selector':[r'(?:việc lựa chọn|selector) (?:dựa trên|xét|so sánh) (?:chi phí của )?các phương án đủ điều kiện(?: theo chi phí)?, sau đó (?:là )?mức đáp ứng từng món và thứ tự kỹ thuật khi hòa'],
        }.get(kind,[])
        patterns+= {
            'winner':[r'phương án được khuyến nghị(?: này)? (?:có sẵn|đã có sẵn)'],
            'selector':[r'các phương án đủ điều kiện đã được đánh giá và so sánh (?:dựa trên|theo) chi phí, sau đó là mức đáp ứng từng món và thứ tự kỹ thuật khi hòa'],
            'proof_boundary':[r'chỉ các phương án đã đánh giá mới được xem xét, không có tuyên bố về tính tối ưu toàn cục'],
            'unproven':[r'tìm kiếm chưa hoàn tất hoặc chưa có chứng nhận đầy đủ trong miền hữu hạn đã lưu'],
        }.get(kind,[])
        if card.option_role=='recommended':
            predicates={'total':r'(?:tổng chi|tổng chi phí)',
                        'purchase_cost':r'(?:chi phí mua|chi phí mua hàng|tiền mua)',
                        'fees':r'(?:phí phải trả|tổng phí phải trả)'}
            if kind in predicates:
                patterns+=[rf'{predicates[kind]} (?:cho|của) phương án được khuyến nghị(?: là| bằng|:)? {amount}']
        if kind=='purchase_quantity' and card.entity_id is None:
            patterns+=[rf'(?:nguyên liệu (?:này|đang xem) )?(?:có )?(?:lượng|số lượng) mua (?:được )?đề xuất(?: cho nguyên liệu (?:này|đang xem))?(?: là|:)? {amount}']
            # Contextual "need to buy" is accepted only for a single retained
            # purchase line; model_answer ALWAYS appends the proposal/option guard.
            patterns+=[rf'bạn cần mua {amount} (?:nguyên liệu này|nguyên liệu đang xem)',
                       rf'nguyên liệu (?:này|đang xem) được đề xuất mua {amount}']
            if card.option_role=='recommended':
                patterns+=[rf'phương án được khuyến nghị(?: cho nguyên liệu này)? (?:là|:) mua {amount}(?: nguyên liệu này)?',
                    rf'(?:bạn nên mua|khuyến nghị mua|nguyên liệu này được khuyến nghị mua) {amount}(?: (?:cho )?nguyên liệu này)?']
        if kind=='no_winner':
            patterns+=[r'(?:không|chưa) có phương án (?:được khuyến nghị|đủ điều kiện)(?: nào)?(?: được chọn)? trong (?:run|lần chạy|kế hoạch) này']
    else:
        patterns+= {
            'total':[rf'(?:the viewed option |this plan )?(?:has )?(?:total outlay|total cost)(?: is| of|:)? {amount}'],
            'budget':[rf'(?:the )?(?:retained )?budget(?: limit)?(?: is|:)? {amount}'],
            'proof_boundary':[r'(?:the recommendation|selection) (?:covers|compares) only evaluated options(?:,|;| and) (?:it is )?not (?:a )?proof of global optimality'],
            'no_winner':[r'(?:this run has no|there is no) (?:eligible )?(?:selected|recommended) option'],
        }.get(kind,[])
    return patterns


class GroundingFailure(ValueError):
    def __init__(self,reason):super().__init__(reason);self.reason=reason


def validate_output(output,plan,locale):
    output=ConversationalOutput.model_validate(output)
    available={f.fact_id:f for f in plan.facts};covered=set()
    if any(f.kind=='purchase_quantity' for f in plan.facts) and plan.ingredient_id is None:
        raise GroundingFailure('GROUNDING_REJECTED')
    claims=[]
    for statement in output.statements:
        if statement.text.rstrip().endswith('?'):raise GroundingFailure('COVERAGE_REJECTED')
        if len(set(statement.fact_ids))!=len(statement.fact_ids) or not set(statement.fact_ids)<=available.keys():
            raise GroundingFailure('GROUNDING_REJECTED')
        text=norm(statement.text).rstrip('.!? ')
        # Match whole statement first (some atomic facts contain a semicolon).
        matched=[]
        if len(statement.fact_ids)==1:
            card=available[statement.fact_ids[0]]
            if any(re.fullmatch(p,text) for p in alternatives(card,locale)):matched=[card.fact_id]
        if not matched:
            # Compound statements are accepted only if EVERY clause is entailed.
            clauses=re.split(r'\s*(?:;|\n|, (?=ngân sách|tiền mua|phí|tổng chi)| và (?=ngân sách|tiền mua|phí|tổng chi)| and (?=budget|total cost))\s*',text)
            for clause in clauses:
                matches=[key for key in statement.fact_ids if key not in matched and
                         any(re.fullmatch(p,clause) for p in alternatives(available[key],locale))]
                if len(matches)!=1:raise GroundingFailure('GROUNDING_REJECTED')
                matched.append(matches[0])
        if set(matched)!=set(statement.fact_ids) or covered.intersection(matched):raise GroundingFailure('GROUNDING_REJECTED')
        covered.update(matched)
        ids=tuple(dict.fromkeys(i for key in matched for i in available[key].evidence_ids))
        claims.append(ChatClaim(text=statement.text,evidence_ids=ids))
    if not set(plan.required)<=covered:raise GroundingFailure('COVERAGE_REJECTED')
    return tuple(claims)


def model_answer(output,plan,diagnostics):
    claims=validate_output(output,plan,plan.fallback.locale)+plan.safety_claims
    used={r for c in claims for r in c.evidence_ids}
    return AssistantResponse(**{**plan.fallback.model_dump(),'source':'model','answer':'\n\n'.join(c.text for c in claims),
        'claims':claims,'references':tuple(r for r in plan.fallback.references if r.evidence_id in used),'diagnostics':diagnostics})
