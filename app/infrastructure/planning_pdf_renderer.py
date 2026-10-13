"""Vietnamese multi-page retained report; deterministic data, embedded fonts."""
from io import BytesIO
from pathlib import Path
from time import perf_counter
from threading import Lock
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,LongTable,TableStyle,PageBreak
from app.application.contracts.planning_pdf import PlanningPDFDocument

_FONT_LOCK=Lock()
_ROOT=Path(__file__).resolve().parents[1]/'assets'/'fonts'


def fonts():
    with _FONT_LOCK:
        for name,file in [('ShelfCashNoto','NotoSans-Regular.ttf'),('ShelfCashNotoBold','NotoSans-Bold.ttf')]:
            if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(_ROOT/file)))


def exact(value):
    if value is None:return 'Chưa biết/Chưa đánh giá'
    if isinstance(value,dict) and {'numerator','denominator'}<=set(value):
        return value.get('decimal_view',value.get('percent_view',''))+' [exact '+str(value['numerator'])+'/'+str(value['denominator'])+']'
    return str(value)


def flat(value,prefix=''):
    if isinstance(value,dict):
        if {'numerator','denominator'}<=set(value):yield prefix,exact(value)
        elif not value:yield prefix,'Không có'
        else:
            for key,child in value.items():yield from flat(child,prefix+'.'+key if prefix else key)
    elif isinstance(value,list):
        if not value:yield prefix,'Không có'
        for index,child in enumerate(value):yield from flat(child,f'{prefix}[{index}]')
    else:yield prefix,exact(value)


class PlanningPDFRenderer:
    @property
    def available(self):
        return all((_ROOT/name).is_file() for name in ('NotoSans-Regular.ttf','NotoSans-Bold.ttf','OFL.txt'))

    def render(self,document:PlanningPDFDocument):
        started=perf_counter()
        fonts()
        base=ParagraphStyle('body',fontName='ShelfCashNoto',fontSize=8,leading=12,spaceAfter=5,splitLongWords=True)
        heading=ParagraphStyle('heading',parent=base,fontName='ShelfCashNotoBold',fontSize=14,leading=19,spaceBefore=10,spaceAfter=8,keepWithNext=True)
        cell=ParagraphStyle('cell',parent=base,fontSize=7,leading=10,spaceAfter=0)
        def p(value,style=base):return Paragraph(escape(str(value)),style)
        story=[]
        def title(value):story.append(p(value,heading))
        def table(headers,rows,widths):
            if not rows:story.append(p('Không có dòng dữ liệu.'));return
            data=[[p(h,cell) for h in headers]]+[[p(exact(v),cell) for v in row] for row in rows]
            result=LongTable(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
            result.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E7EEF2')),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#CDD7DF')),
                ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
                ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
            story.extend([result,Spacer(1,8)])
        view,option=document.view,document.option
        title('ShelfCash — Báo cáo phương án mua hàng')
        story.append(p('Đề xuất giả định P1; không phải hóa đơn, đơn đặt hàng hoặc xác nhận hàng thực nhận.'))
        story.append(p('LOW/BASE/HIGH là các đường nhu cầu; không phải khoảng tin cậy hay xác suất thiếu hàng.'))
        if not option.eligible:story.append(p('CẢNH BÁO: PHƯƠNG ÁN KHÔNG ĐỦ ĐIỀU KIỆN — KHÔNG PHẢI KHUYẾN NGHỊ.'))
        elif view.result.winner_option_id!=option.option_id:story.append(p('Phương án được chọn để kiểm tra; không phải winner được lưu.'))
        table(['Thông tin','Giá trị'],[
            ('Run',view.run_id),('Store',view.store_id),('Tên Store tại capture','Chưa được giữ lại'),
            ('Phương án',option.option_id),('Result digest',document.explanation.result_digest),
            ('Nhận yêu cầu',view.accepted_at.isoformat()),('Bắt đầu',view.started_at.isoformat() if view.started_at else None),
            ('Thời gian capture',document.ingredients[0].captured_stock.captured_at.isoformat() if document.ingredients else None),
            ('Khoảng ngày',str(view.request.forecast_start_date)+' — '+str(view.forecast.end_date if view.forecast else 'Chưa biết')),
            ('Tiền tệ',option.costs.currency),('Timezone',view.operational_basis.timezone if view.operational_basis else 'Chưa biết'),
            ('Ngân sách hiệu lực',view.configuration.budget.limit),('Trần Store lúc nhận',view.configuration.budget.ceiling_at_acceptance),
            ('Đủ điều kiện',option.eligible),('Winner',view.result.winner_option_id),
            ('Mô hình',view.forecast.model_type if view.forecast else None),('Phiên bản mô hình',view.forecast.model_version if view.forecast else None),
            ('Chất lượng mô hình','Chưa đánh giá' if view.forecast and view.forecast.quality_status=='not_evaluated' else view.forecast.quality_status if view.forecast else None)], [150,365])
        title('Chi phí và các dòng mua giả định')
        labels={'purchase':'Giá mua','payable_fees':'Phí phải trả','delivery_fees':'Phí giao hàng','total':'Tổng chi phí'}
        table(['Khoản','Giá trị exact'],[(labels[field],getattr(option.costs,field).model_dump(mode='json') if getattr(option.costs,field) is not None else None)
            for field in ('purchase','payable_fees','delivery_fees','total')],[150,365])
        table(['Nguyên liệu / term / nhà cung cấp','Packs / lượng / unit','Arrival / expiry','Chi phí'],[
            (f'{r.ingredient_id}\n{r.supplier_term_id}\n{r.supplier_id}',f'{r.packs} / '+exact(r.quantity.model_dump(mode='json'))+' '+r.unit,
             str(r.arrival_date)+' / '+str(r.expiry_date) if r.expiry_date else str(r.arrival_date)+' / Chưa biết',r.purchase_outlay.model_dump(mode='json'))
            for r in option.purchases],[185,125,100,105])
        title('Đáp ứng Product theo đường nhu cầu')
        table(['Product / path / unit','Yêu cầu','Phục vụ','Mất bán','Service'],[
            (f'{r.product_id} / {r.path} / {r.unit}',r.requested.model_dump(mode='json'),r.fulfilled.model_dump(mode='json'),
             r.lost_sales.model_dump(mode='json'),r.service.model_dump(mode='json') if r.service else None)
            for r in option.product_services],[180,85,85,85,80])
        title('Tồn vật lý tại capture và mô phỏng nguyên liệu')
        story.append(p('Lot vật lý được giữ nguyên tại capture, gồm lot hết hạn nếu có. Arrivals dưới đây là giả định. Ngày hết hạn X còn dùng trong ngày X, hết hạn cuối ngày X.'))
        for detail in document.ingredients:
            title((detail.display_name or 'Tên chưa được giữ lại')+' — '+str(detail.ingredient_id)+' / '+detail.unit)
            story.append(p('Khai báo: '+detail.captured_stock.scope_declaration+'; provenance: '+(detail.captured_stock.provenance or 'Chưa biết')))
            table(['Lot','Lượng exact','Nhận / hết hạn','Cost'],[
                (l.lot_id,l.quantity.model_dump(mode='json'),(str(l.received_date) if l.received_date else 'Chưa biết')+' / '+(str(l.expiry_date) if l.expiry_date else 'Chưa biết'),l.unit_cost)
                for l in detail.captured_stock.lots],[185,130,120,80])
            if detail.daily_balances is None:story.append(p('Mô phỏng: Chưa đánh giá.'))
            else:table(['Path / ngày','Yêu cầu','Có thể dùng','Thiếu','Dùng','Hết hạn','Hao hụt khác','Kết thúc','Đến giả định'],[
                (r.path+' / '+str(r.day),*[getattr(r,f).model_dump(mode='json') for f in ('requested','available','shortage','consumed','expired','other_waste','ending','incoming_quantity')])
                for r in detail.daily_balances],[103,*([51.5]*8)])
        title('Lý do, sản phẩm loại trừ, cảnh báo và giới hạn bằng chứng')
        for item in (*document.explanation.blockers,*document.explanation.warnings):story.append(p(item.code+': '+item.message))
        for item in document.explanation.exclusions:story.append(p(str(item.product_id)+': '+', '.join(item.reason_codes)))
        for strategy in view.result.strategies:
            story.append(p(f'{strategy.strategy}: execution={strategy.execution}; termination={strategy.termination}; feasibility={strategy.customer_feasibility}; proof={strategy.proof}; scope={strategy.proof_scope}; search_complete={strategy.search_complete}; domain_size={strategy.domain_size}'))
        story.append(p('UNPROVEN/UNKNOWN không chứng minh infeasibility. Bằng chứng finite domain không áp dụng ngoài nguồn đã capture.'))
        story.append(PageBreak())
        title('Phụ lục đầy đủ — exact values và nguồn đã giữ lại')
        story.append(p('Giá trị có nhãn exact n/d giữ numerator/denominator. decimal_view/percent_view chỉ là giá trị hiển thị làm tròn theo contract; không thay exact fraction. null là Chưa biết/Chưa đánh giá.'))
        table(['Trường nguồn được giữ lại','Giá trị'],list(flat(document.model_dump(mode='json'))),[205,310])
        output=BytesIO()
        doc=SimpleDocTemplate(output,pagesize=A4,leftMargin=40,rightMargin=40,topMargin=42,bottomMargin=42,
            title='ShelfCash — Báo cáo phương án',author='ShelfCash',pageCompression=1,invariant=1)
        def footer(canvas,doc):
            if doc.page>1000:raise ValueError('PDF representation page budget exceeded')
            if perf_counter()-started>120:raise ValueError('Cooperative PDF render deadline exceeded')
            canvas.saveState();canvas.setFont('ShelfCashNoto',7);canvas.setFillColor(colors.HexColor('#50616C'))
            canvas.drawString(40,23,'Run '+str(view.run_id));canvas.drawRightString(A4[0]-40,23,'Trang '+str(doc.page));canvas.restoreState()
        doc.build(story,onFirstPage=footer,onLaterPages=footer)
        return output.getvalue()
