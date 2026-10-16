"""Vietnamese owner report /2. All facts come from the retained PDF document."""
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
from app.infrastructure.planning_pdf_display_v2 import (
    UNKNOWN, PATHS, STRATEGIES, SYNTHETIC_PROVENANCE, RetainedLabels, fraction, number, quantity, money, percent, grouped_notices,
)


class PlanningPDFRenderer(LegacyRenderer):
    def render_legacy(self, document: PlanningPDFDocument) -> bytes:
        return super().render(document)

    def render(self, document: PlanningPDFDocument) -> bytes:
        started = perf_counter()
        fonts()
        body = ParagraphStyle('body2', fontName='ShelfCashNoto', fontSize=10, leading=15, spaceAfter=7)
        heading = ParagraphStyle('heading2', parent=body, fontName='ShelfCashNotoBold', fontSize=17,
                                 leading=23, spaceAfter=14, keepWithNext=True)
        cell = ParagraphStyle('cell2', parent=body, fontSize=8.5, leading=12, spaceAfter=0, splitLongWords=True)
        small = ParagraphStyle('trace2', parent=cell, fontSize=8, leading=11)
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
        # Explicit retained fixture marker, never inferred from a model or name.
        if any(i.captured_stock.provenance in SYNTHETIC_PROVENANCE for i in document.ingredients):
            text('DỮ LIỆU SYNTHETIC / DEMO: snapshot có nguồn đã đánh dấu; không dùng để xác nhận kết quả kinh doanh thực tế.')
        text(labels.name('Cửa hàng', view.store_id))
        text(f'Kỳ kế hoạch: {view.request.forecast_start_date} đến ' + (str(view.forecast.end_date) if view.forecast else 'Chưa biết') + '.')
        basis = view.operational_basis
        if basis:
            text('Thời điểm chụp dữ liệu: ' + basis.captured_at.astimezone(ZoneInfo(basis.timezone)).strftime('%d/%m/%Y %H:%M') + ' (' + basis.timezone + ').')
        else:
            text('Thời điểm chụp dữ liệu / múi giờ: Chưa biết.')
        status = {'completed': 'Đã hoàn tất', 'failed': 'Thất bại', 'running': 'Đang xử lý', 'queued': 'Đang chờ'}[view.status]
        text('Trạng thái lần chạy: ' + status + '.')
        recommended = view.status == 'completed' and view.outcome == 'recommendation_available' and view.result is not None and view.result.winner_option_id == option.option_id and option.eligible
        if not option.eligible:
            text('PHƯƠNG ÁN KHÔNG ĐỦ ĐIỀU KIỆN — KHÔNG PHẢI KHUYẾN NGHỊ.')
        elif recommended:
            text('Đang xuất phương án được khuyến nghị trong lần chạy này.')
        else:
            text('Đang xem phương án tham khảo; không phải phương án được khuyến nghị trong lần chạy này.')
        text('Chiến lược tạo phương án: ' + ', '.join(STRATEGIES[s] for s in option.source_strategies) + '.')
        table(['Khoản chi đã lưu', 'Số tiền'], [
            ('Tổng chi', money(option.costs.total, currency)),
            ('Tiền mua nguyên liệu', money(option.costs.purchase, currency)),
            ('Phí phải trả', money(option.costs.payable_fees, currency)),
            ('Ngân sách hiệu lực', money(view.configuration.budget.limit, view.configuration.budget.currency)),
            ('Trần cửa hàng lúc nhận yêu cầu', money(view.configuration.budget.ceiling_at_acceptance, view.configuration.budget.currency)),
        ], [290, 225])
        if option.costs.fee_classification == 'PAYABLE_FEE_TYPE_NOT_CAPTURED':
            text('Phí phải trả đã biết số tiền; chưa lưu loại phí, chưa thể gọi là phí giao hàng.')
        elif option.costs.fee_classification == 'DECLARED_DELIVERY':
            text('Phí giao hàng đã khai báo: ' + money(option.costs.delivery_fees, currency) + '.')
        if view.scope:
            text(f'Phạm vi đầu vào: {view.scope.computed_count}/{view.scope.menu_count} món được đưa vào tính toán. Phạm vi này không tự chứng minh kết quả đáp ứng.')
        text('Kiểm tra số lượng, điều kiện nhà cung cấp và ngày nhận dự kiến trước khi mua. Mô phỏng không phản ánh tồn kho hoặc tiêu thụ thực tế.')

        title('1. Danh sách mua dự kiến', True)
        text('Mỗi dòng giữ riêng nguyên liệu, nhà cung cấp, điều khoản và ngày nhận; không gộp các dòng mua.')
        rows = []
        for index, row in enumerate(option.purchases, 1):
            pack = number(fraction(row.quantity) / row.packs) + ' ' + row.unit
            rows.append((f'{index}. ' + labels.name('Nguyên liệu', row.ingredient_id),
                         f'{row.packs} gói\nMỗi gói: {pack}\nTổng: {quantity(row.quantity, row.unit)}',
                         labels.name('Nhà cung cấp', row.supplier_id), str(row.arrival_date), money(row.purchase_outlay, currency)))
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
        text('Nhu cầu thấp, cơ sở và cao là ba đường nhu cầu mô phỏng, không phải xác suất. Tỷ lệ thuộc đúng món và đường nhu cầu; không lấy trung bình thành KPI chung.')
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
        unmet = [r for r in option.product_services if fraction(r.lost_sales) > 0]
        if unmet:
            text(f'Có {len(unmet)} dòng món / đường nhu cầu còn nhu cầu chưa đáp ứng. Mọi lượng dương đáng chú ý được giữ theo món và đường nhu cầu tại cột “Chưa đáp ứng” trong phần 2.')
        else:
            text('Không ghi nhận nhu cầu chưa đáp ứng dương trong các dòng kết quả đã lưu; không kết luận cho món chưa đánh giá.')
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
                                      number(amount) + ' ' + detail.unit, ', '.join(str(r.day) for r in affected)))
        if risks:
            text('Bảng rút gọn: tổng lượng dương theo ngày trong cùng nguyên liệu / đơn vị / đường nhu cầu; không phải tồn kho thực tế. Chi tiết gốc được giữ trong hệ thống.')
            table(['Nguyên liệu', 'Đường nhu cầu', 'Dấu hiệu', 'Tổng theo ngày', 'Ngày có bằng chứng'], risks, [135, 85, 105, 85, 105])
        for excluded in document.explanation.exclusions:
            text(labels.name('Món', excluded.product_id) + ': loại khỏi phạm vi, chưa đánh giá. Mã lý do: ' + ', '.join(excluded.reason_codes) + '. Ngày: ' + ', '.join(map(str, excluded.affected_dates)))
        for item, dates in grouped_notices((*document.explanation.blockers, *document.explanation.warnings, *option.issues)):
            suffix = (' — mã …' + labels.codes[item.details.entity_id]) if item.details.entity_id else ''
            text(item.message + suffix + ('. Ngày ảnh hưởng: ' + ', '.join(dates) if dates else '') + ' [' + item.code + ']')
            if item.details.suggested_action:
                text('Cần kiểm tra: ' + item.details.suggested_action)
        if document.explanation.availability != 'available':
            text('Bằng chứng kết quả chỉ có một phần hoặc chưa có; không suy thành không có rủi ro.')
        if not view.result or not view.result.strategies:
            text('Chưa có bằng chứng tìm kiếm để kết luận tính khả thi.')
        else:
            for result in view.result.strategies:
                proof = 'Đã kiểm tra đầy đủ trong miền hữu hạn đã lưu.' if result.proof == 'COMPLETE_EXACT_ENUMERATION' and result.search_complete else 'Chưa kiểm tra đầy đủ trong miền hữu hạn đã lưu; không chứng minh không có phương án.'
                execution = {'FINISHED': 'Đã kết thúc', 'INCOMPLETE': 'Chưa hoàn tất', 'ERROR': 'Lỗi thực thi', 'BLOCKED': 'Bị chặn', 'NUMERIC_UNSUPPORTED': 'Giá trị số chưa hỗ trợ'}[result.execution]
                text(STRATEGIES[result.strategy] + ': ' + execution + '. ' + proof)
        text('So sánh chỉ áp dụng cho các phương án đã đánh giá, không chứng minh tối ưu toàn cục. Kiểm tra nguồn cung và điều kiện thực tế trước khi đặt mua.')

        title('4. Cách đọc và truy vết')
        text('Tiền theo loại tiền đã lưu, không quy đổi. Lượng hiển thị tối đa 3 chữ số thập phân; tỷ lệ 1 chữ số. Số exact và toàn bộ provenance vẫn được giữ trong hệ thống, không in dump mặc định.')
        if view.forecast:
            text('Mô hình đã dùng: ' + view.forecast.model_type + ' / ' + view.forecast.model_version + '. Chất lượng: ' + ('Chưa đánh giá' if view.forecast.quality_status == 'not_evaluated' else 'Đã có đánh giá') + '.')
        for label, value in [('Run', view.run_id), ('Phương án đang xuất', option.option_id),
                             ('Phương án khuyến nghị đã lưu', view.result.winner_option_id if view.result else None),
                             ('Result digest', document.explanation.result_digest), ('Renderer', 'planning-pdf/2')]:
            story.append(p(label + ': ' + (str(value) if value is not None else UNKNOWN), small))
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
                  [(str(i), str(r.supplier_term_id) + '\n' + (str(r.expiry_date) if r.expiry_date else 'Chưa biết hạn dùng')) for i, r in enumerate(option.purchases, 1)], [70, 445])
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
