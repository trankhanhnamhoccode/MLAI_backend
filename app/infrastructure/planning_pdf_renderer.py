"""Vietnamese owner report /3. Facts and compatibility use retained documents."""
from datetime import date
from fractions import Fraction
from io import BytesIO
from time import perf_counter
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak
from app.application.contracts.planning_pdf import PlanningPDFDocument
from app.infrastructure.planning_pdf_legacy import PlanningPDFRenderer as LegacyRenderer, fonts
from app.infrastructure.planning_pdf_v2 import PlanningPDFRenderer as Version2Renderer
from app.infrastructure.planning_pdf_display import (
    UNKNOWN, PATHS, STRATEGIES, RetainedLabels, fraction, number, quantity, money, percent, grouped_notices,
)
from app.infrastructure.planning_pdf_wording import day, synthetic, temporal_note, base_assessment, unmet_note, proof_notes, proof_trace


class PlanningPDFRenderer(LegacyRenderer):
    def render_legacy(self, document: PlanningPDFDocument) -> bytes:
        return super().render(document)

    def render_v2(self, document: PlanningPDFDocument) -> bytes:
        return Version2Renderer().render(document)

    def render(self, document: PlanningPDFDocument) -> bytes:
        started = perf_counter()
        fonts()
        body = ParagraphStyle('body2', fontName='ShelfCashNoto', fontSize=10, leading=15, spaceAfter=7)
        heading = ParagraphStyle('heading2', parent=body, fontName='ShelfCashNotoBold', fontSize=17,
                                 leading=23, spaceAfter=14, keepWithNext=True)
        cell = ParagraphStyle('cell2', parent=body, fontSize=8.5, leading=12, spaceAfter=0, splitLongWords=True)
        small = ParagraphStyle('trace2', parent=cell, fontSize=8, leading=11)
        emphasis = ParagraphStyle('emphasis3', parent=body, fontName='ShelfCashNotoBold', fontSize=12, leading=18)
        amount = ParagraphStyle('amount3', parent=body, fontName='ShelfCashNotoBold', fontSize=20, leading=28,
                                textColor=colors.HexColor('#185B45'))
        conclusion = ParagraphStyle('conclusion3', parent=body, backColor=colors.HexColor('#EDF5F1'), borderPadding=8,
                                    spaceBefore=8, spaceAfter=14)
        story = []
        view, option = document.view, document.option
        labels = RetainedLabels(document)
        currency = option.costs.currency

        def p(value, style=body):
            return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)

        def text(value):
            story.append(p(value))

        def title(value, new_page=False):
            if new_page:
                story.append(PageBreak())
            story.append(p(value, heading))

        def table(headers, rows, widths):
            if not rows:
                text('Chưa có dữ liệu được giữ lại để đánh giá.')
                return
            data = [[p(h, cell) for h in headers]] + [[p(v, cell) for v in row] for row in rows]
            result = LongTable(data, colWidths=widths, repeatRows=1, hAlign='LEFT', splitInRow=0)
            result.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DDEDE7')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F8F7')]),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LINEBELOW', (0, 0), (-1, 0), .6, colors.HexColor('#6C9887')),
                ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ]))
            story.extend((result, Spacer(1, 12)))

        title('ShelfCash — Kế hoạch mua hàng')
        text('Đề xuất mua hàng — chưa phải đơn đặt hàng.')
        # Explicit retained marker, never inferred from a model or name.
        if synthetic(document):
            text('DỮ LIỆU SYNTHETIC / DEMO: có nguồn đã đánh dấu giả lập; không dùng để xác nhận kết quả kinh doanh thực tế.')
        text(labels.name('Cửa hàng', view.store_id))
        story.append(p('Kỳ kế hoạch: ' + day(view.request.forecast_start_date) + ' đến ' + day(view.forecast.end_date if view.forecast else None), emphasis))
        basis = view.operational_basis
        if basis:
            text('Thời điểm chụp dữ liệu: ' + basis.captured_at.astimezone(ZoneInfo(basis.timezone)).strftime('%d/%m/%Y %H:%M') + ' (' + basis.timezone + ').')
        else:
            text('Thời điểm chụp dữ liệu / múi giờ: Chưa biết.')
        status = {'completed': 'Đã hoàn tất', 'failed': 'Thất bại', 'running': 'Đang xử lý', 'queued': 'Đang chờ'}[view.status]
        text('Trạng thái lần chạy: ' + status + '.')
        recommended = view.status == 'completed' and view.outcome == 'recommendation_available' and view.result is not None and view.result.winner_option_id == option.option_id and option.eligible
        if not option.eligible:
            story.append(p('PHƯƠNG ÁN KHÔNG ĐỦ ĐIỀU KIỆN — KHÔNG PHẢI KHUYẾN NGHỊ.', emphasis))
        elif recommended:
            story.append(p('Đang xuất phương án được khuyến nghị trong lần chạy này.', emphasis))
        else:
            story.append(p('Đang xem phương án tham khảo; không phải phương án được khuyến nghị trong lần chạy này.', emphasis))
        budget = view.configuration.budget
        merged_budget = Fraction(budget.limit) == Fraction(budget.ceiling_at_acceptance) and budget.currency == currency
        budget_label = 'Ngân sách hiệu lực / trần cửa hàng đã lưu' if merged_budget else 'Ngân sách hiệu lực đã lưu'
        overview = LongTable([[p('Tổng chi dự kiến', emphasis), p(budget_label, emphasis)],
                              [p(money(option.costs.total, currency), amount), p(money(budget.limit, budget.currency), amount)]],
                             colWidths=[257.5, 257.5], hAlign='LEFT')
        overview.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EDF5F1')),
                                     ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                     ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                                     ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
        story.extend((overview, Spacer(1, 12)))
        cost_rows = [
            ('Tiền mua nguyên liệu', money(option.costs.purchase, currency)),
            ('Phí phải trả', money(option.costs.payable_fees, currency)),
        ]
        if not merged_budget:
            cost_rows.append(('Trần cửa hàng lúc nhận yêu cầu', money(budget.ceiling_at_acceptance, budget.currency)))
        table(['Chi tiết đã lưu', 'Số tiền'], cost_rows, [290, 225])
        story.append(p(base_assessment(document), conclusion))
        if option.costs.fee_classification == 'PAYABLE_FEE_TYPE_NOT_CAPTURED':
            text('Phí phải trả đã biết số tiền; chưa lưu loại phí, chưa thể gọi là phí giao hàng.')
        elif option.costs.fee_classification == 'DECLARED_DELIVERY':
            text('Phí giao hàng đã khai báo: ' + money(option.costs.delivery_fees, currency) + '.')
        if view.scope:
            text(f'Phạm vi đầu vào: {view.scope.computed_count}/{view.scope.menu_count} món được đưa vào tính toán. Phạm vi này không tự chứng minh kết quả đáp ứng.')
        text(temporal_note(document))

        title('1. Danh sách mua dự kiến', True)
        text('Mỗi dòng giữ riêng nguyên liệu, nhà cung cấp, điều khoản và ngày nhận; không gộp các dòng mua.')
        rows = []
        for index, row in enumerate(option.purchases, 1):
            pack = number(fraction(row.quantity) / row.packs) + ' ' + row.unit
            rows.append((f'{index}. ' + labels.name('Nguyên liệu', row.ingredient_id),
                         f'{row.packs} gói\nMỗi gói: {pack}\nTổng: {quantity(row.quantity, row.unit)}',
                         labels.name('Nhà cung cấp', row.supplier_id), day(row.arrival_date), money(row.purchase_outlay, currency)))
        if rows:
            table(['Nguyên liệu', 'Quy cách / số lượng', 'Nhà cung cấp', 'Ngày dự kiến nhận', 'Tiền mua'], rows, [130, 120, 100, 80, 85])
        else:
            text('Phương án này không phát sinh dòng mua thêm nguyên liệu.')
        text('Thành tiền từng dòng là tiền mua; phí phải trả trình bày riêng, không cộng lặp vào từng dòng.')
        if option.costs.fee_components:
            table(['Phí đã lưu / phạm vi áp dụng', 'Số tiền'], [
                (('Theo điều khoản' if f.basis == 'OFFER' else 'Theo đơn nhà cung cấp') + ' — mã …' + labels.codes[f.entity_id], money(f.amount, currency))
                for f in option.costs.fee_components], [365, 150])
        text('Ngày nhận là giả định nếu thực hiện phương án, chưa xác nhận giao hàng. Quy cách mỗi gói = tổng lượng đã lưu / số gói; không đổi đơn vị hoặc suy mật độ.')
        text('Dấu ~ nghĩa là xấp xỉ do làm tròn; dấu < chỉ lượng dương nhỏ hơn ngưỡng hiển thị. Tổng dòng hiển thị có thể lệch tổng chi đã lưu do làm tròn; tổng chi không bị sửa.')

        title('2. Khả năng đáp ứng nhu cầu', True)
        text('Nhu cầu thấp, cơ sở và cao là ba kịch bản nhu cầu mô phỏng, không phải xác suất. Tỷ lệ thuộc từng món trong từng kịch bản, không phải tỷ lệ chung của kế hoạch.')
        services = {(r.product_id, r.path): r for r in option.product_services}
        product_ids = list(dict.fromkeys((*labels.products, *(r.product_id for r in option.product_services))))
        for path in ('BASE', 'LOW', 'HIGH'):
            story.append(p(PATHS[path] + ' (' + path + ')', ParagraphStyle('path-' + path, parent=body, fontName='ShelfCashNotoBold', keepWithNext=True)))
            rows = []
            for ident in product_ids:
                row = services.get((ident, path))
                assessment = next((a for a in option.requirements_assessment if a.product_id == ident and a.path == path), None)
                assessed = {'PASS': 'Đạt', 'FAIL': 'Chưa đạt', 'NOT_EVALUATED': 'Chưa đánh giá'}.get(assessment.status if assessment else '', 'Chưa có yêu cầu đã lưu' if path == 'BASE' else '')
                if assessment:
                    assessed += ' / mục tiêu ' + number(Fraction(assessment.target_percent), 1) + ' %'
                rows.append((labels.name('Món', ident), quantity(row.requested, row.unit) if row else 'Chưa đánh giá',
                             quantity(row.fulfilled, row.unit) if row else 'Chưa đánh giá',
                             quantity(row.lost_sales, row.unit) if row else 'Chưa đánh giá',
                             (('Không xác định (nhu cầu bằng 0)' if fraction(row.requested) == 0 else percent(row.service)) if row else 'Chưa đánh giá') + ('\n' + assessed if assessed else '')))
            table(['Món', 'Nhu cầu', 'Phục vụ mô phỏng', 'Chưa đáp ứng', 'Tỷ lệ / yêu cầu'], rows, [135, 85, 95, 85, 115])
        text('Món bị loại là chưa đánh giá, không có nghĩa nhu cầu bằng 0. Tỷ lệ không xác định khi nhu cầu bằng 0; lượng mô phỏng vẫn giữ phần lẻ.')

        title('3. Điểm cần kiểm tra', True)
        text(unmet_note(document))
        risks = []
        for detail in document.ingredients:
            if detail.daily_balances is None:
                text(labels.name('Nguyên liệu', detail.ingredient_id) + ': chưa có đánh giá mô phỏng theo ngày.')
                continue
            for path in ('BASE', 'LOW', 'HIGH'):
                for field, label in (('shortage', 'Thiếu nguyên liệu mô phỏng'), ('expired', 'Hết hạn mô phỏng')):
                    affected = [r for r in detail.daily_balances if r.path == path and fraction(getattr(r, field)) > 0]
                    if affected:
                        amount = sum((fraction(getattr(r, field)) for r in affected), Fraction())
                        risks.append((labels.name('Nguyên liệu', detail.ingredient_id), PATHS[path], label,
                                      number(amount) + ' ' + detail.unit, ', '.join(day(r.day) for r in affected)))
        if risks:
            text('Bảng rút gọn: tổng lượng dương theo ngày trong cùng nguyên liệu / đơn vị / đường nhu cầu; không phải tồn kho thực tế. Chi tiết gốc được giữ trong hệ thống.')
            table(['Nguyên liệu', 'Đường nhu cầu', 'Dấu hiệu', 'Tổng theo ngày', 'Ngày có bằng chứng'], risks, [135, 85, 105, 85, 105])
        for excluded in document.explanation.exclusions:
            text(labels.name('Món', excluded.product_id) + ': loại khỏi phạm vi, chưa đánh giá. Mã lý do: ' + ', '.join(excluded.reason_codes) + '. Ngày: ' + ', '.join(day(d) for d in excluded.affected_dates))
        for item, dates in grouped_notices((*document.explanation.blockers, *document.explanation.warnings, *option.issues)):
            suffix = (' — mã …' + labels.codes[item.details.entity_id]) if item.details.entity_id else ''
            text(item.message + suffix + ('. Ngày ảnh hưởng: ' + ', '.join(day(date.fromisoformat(d)) for d in dates) if dates else '') + ' [' + item.code + ']')
            if item.details.suggested_action:
                text('Cần kiểm tra: ' + item.details.suggested_action)
        if document.explanation.availability != 'available':
            text('Bằng chứng kết quả chỉ có một phần hoặc chưa có; không suy thành không có rủi ro.')
        for note in proof_notes(view.result.strategies if view.result else (), recommended):
            text(note)
        text('Kiểm tra số lượng, điều kiện nhà cung cấp và ngày nhận dự kiến trước khi đặt mua.')

        title('4. Cách đọc và truy vết')
        text('Tiền theo loại tiền đã lưu, không quy đổi. Lượng hiển thị tối đa 3 chữ số thập phân; tỷ lệ 1 chữ số. Giá trị chính xác và thông tin nguồn vẫn được giữ trong hệ thống; không in toàn bộ dữ liệu kỹ thuật chi tiết mặc định.')
        if any(row.unit == 'cup' for row in option.product_services) or (view.scope is not None and any(product.selling_unit == 'cup' for product in view.scope.menu_products)):
            text('Đơn vị được giữ nguyên theo dữ liệu đã lưu; chưa có nhãn tiếng Việt được xác nhận cho các mã đơn vị như cup. Không quy đổi lượng.')
        else:
            text('Đơn vị được giữ nguyên theo dữ liệu đã lưu; không quy đổi lượng.')
        if view.forecast:
            text('Mô hình đã dùng: ' + view.forecast.model_type + ' / ' + view.forecast.model_version + '. Chất lượng: ' + ('Chưa đánh giá' if view.forecast.quality_status == 'not_evaluated' else 'Đã có đánh giá') + '.')
        for label, value in [('Run', view.run_id), ('Phương án đang xuất', option.option_id),
                             ('Phương án khuyến nghị đã lưu', view.result.winner_option_id if view.result else None),
                             ('Result digest', document.explanation.result_digest), ('Renderer', 'planning-pdf/3'),
                             ('Chiến lược tạo phương án', ', '.join(STRATEGIES[s] for s in option.source_strategies))]:
            story.append(p(label + ': ' + (str(value) if value is not None else UNKNOWN), small))
        for row in proof_trace(view.result.strategies if view.result else ()):
            story.append(p(row, small))
        # Trace only suffixes actually used in prose/tables. Named entities are
        # discoverable through the retained Run; term IDs are mapped by line below.
        referenced = {view.store_id, *(r.supplier_id for r in option.purchases),
                      *(i.ingredient_id for i in document.ingredients if not i.display_name),
                      *(r.ingredient_id for r in option.purchases if not labels.ingredients.get(r.ingredient_id)),
                      *(ident for ident in product_ids if not labels.products.get(ident)),
                      *(f.entity_id for f in option.costs.fee_components)}
        referenced.update(item.details.entity_id for item in (*document.explanation.blockers, *document.explanation.warnings, *option.issues) if item.details.entity_id)
        table(['Mã trong báo cáo', 'ID đầy đủ'], [('…' + labels.codes[ident], ident) for ident in sorted(referenced)], [130, 385])
        if option.purchases:
            table(['Dòng mua', 'Điều khoản đầy đủ / hạn dùng dự kiến'],
                  [(str(i), str(r.supplier_term_id) + '\n' + (day(r.expiry_date) if r.expiry_date else 'Chưa biết hạn dùng')) for i, r in enumerate(option.purchases, 1)], [70, 445])
        output = BytesIO()
        pdf = SimpleDocTemplate(output, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=42,
                                bottomMargin=44, title='ShelfCash — Kế hoạch mua hàng', author='ShelfCash', invariant=1)

        def footer(canvas, doc):
            if doc.page > 1000 or perf_counter() - started > 120:
                raise ValueError('PDF representation budget exceeded')
            canvas.saveState()
            canvas.setFont('ShelfCashNoto', 8)
            canvas.setFillColor(colors.HexColor('#50616C'))
            canvas.drawString(40, 23, 'ShelfCash • Đề xuất mua hàng')
            canvas.drawRightString(A4[0] - 40, 23, 'Trang ' + str(doc.page))
            canvas.restoreState()

        pdf.build(story, onFirstPage=footer, onLaterPages=footer)
        return output.getvalue()
