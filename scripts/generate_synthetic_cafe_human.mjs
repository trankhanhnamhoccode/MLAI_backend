/** Natural Vietnamese views of a frozen oracle. No random facts or backend writes. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const root=process.cwd();
const modules=process.env.CODEX_ARTIFACT_NODE_MODULES || path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const require=createRequire(path.join(path.dirname(modules),'artifact-loader.cjs'));
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')));
const oracleDir=path.join(root,'tests/fixtures/synthetic_cafe_v1');
const out=path.join(root,'tests/fixtures/synthetic_cafe_human_v1');
const runtime=path.join(root,'runtime/verification/human-cafe-authoring');
await fs.mkdir(out,{recursive:true});await fs.mkdir(runtime,{recursive:true});
const oracleBytes=await fs.readFile(path.join(oracleDir,'dataset.json'));
const oracle=JSON.parse(oracleBytes);const books=oracle.workbooks;
const main='01_main_at_cutoff.xlsx',enough='02_sufficient_at_cutoff.xlsx';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const labels={
 products:{source_business_key:'Mã món nguồn',name:'Tên món',selling_unit:'ĐVT bán',sku:'SKU',price:'Giá bán',active:'Đang bán'},
 ingredients:{source_business_key:'Mã nguyên liệu nguồn',name:'Tên nguyên liệu',base_unit:'Đơn vị cơ sở',sku:'SKU',expiry_tracking:'Theo dõi hạn dùng',active:'Đang sử dụng'},
 suppliers:{source_supplier_key:'Mã nhà cung cấp nguồn',name:'Tên nhà cung cấp',active:'Đang hoạt động'},
 recipes:{product_id:'Món bán',ingredient_id:'Thành phần',quantity:'Định lượng nguyên liệu',unit:'Đơn vị NL',quantity_basis:'Cơ sở định lượng nguyên liệu',yield_quantity:'Sản lượng toàn mẻ',yield_unit:'Đơn vị SP',process_loss_rate:'Tỷ lệ hao hụt',version:'Phiên bản',effective_from:'Áp dụng từ',effective_to:'Ngày kết thúc hiệu lực'},
 sales:{sales_date:'Ngày bán',product_id:'Tên món',quantity:'SL bán',unit:'ĐVT',is_stockout:'Hết món?',business_report_key:'Mã báo cáo nghiệp vụ'},
 opening_stock:{ingredient_id:'Tên nguyên liệu',lot_code:'Mã lô',quantity:'Tồn cuối ngày',unit:'ĐVT',expiry_date:'Hạn dùng',received_date:'Ngày thực nhận',supplier_id:'Tên nhà cung cấp',unit_cost:'Giá một đơn vị vật lý',currency:'Tiền tệ',source_record_id:'Mã bản ghi mở sổ',observed_at:'Thời điểm chốt kho',reason:'Lý do'},
 usage_history:{source_record_key:'Mã ghi nhận sử dụng',usage_date:'Ngày sử dụng',ingredient_id:'Nguyên liệu sử dụng',quantity:'Lượng thực dùng',unit:'ĐVT',observed_at:'Thời điểm thực sử dụng',evidence_reference:'Bằng chứng khai báo'},
 purchase_history:{source_record_key:'Mã dòng mua hàng',ingredient_id:'Tên nguyên liệu',supplier_id:'Tên nhà cung cấp',quantity:'Lượng đã mua',unit:'ĐVT',order_date:'Ngày đặt mua',received_date:'Ngày thực nhận',report_date:'Ngày báo cáo mua',price:'Giá mua lịch sử',currency:'Tiền tệ',price_basis:'Cơ sở giá nguồn',price_quantity:'Lượng mẫu số của giá',price_unit:'Đơn vị mẫu số của giá',evidence_reference:'Bằng chứng khai báo'},
 supplier_terms:{source_term_key:'Mã điều khoản ở nguồn',supplier_id:'Tên nhà cung cấp',ingredient_id:'Tên nguyên liệu',pack_label:'Nhãn kiện mua',pack_size_base_quantity:'Lượng trong một kiện',unit:'Đơn vị cơ sở',pack_cost:'Giá mỗi pack',currency:'Tiền tệ',price_basis:'Cơ sở giá nguồn',price_quantity:'Lượng mẫu số của giá',price_unit:'Đơn vị mẫu số của giá',minimum_order_quantity:'MOQ',moq_basis:'Cơ sở MOQ nguồn',moq_unit:'Đơn vị lượng MOQ',lead_time_days:'Số ngày giao',shelf_life_days:'Số ngày hạn dùng',maximum_order_base_quantity:'Lượng mua tối đa',active:'Đang hoạt động',effective_from:'Ngày bắt đầu hiệu lực',effective_to:'Ngày kết thúc hiệu lực'},
 payable_fees:{source_fee_key:'Mã khai báo phí',scope:'Phạm vi',mode:'Cơ chế phí',coverage:'Mức khai báo đầy đủ',currency:'Tiền tệ',effective_from:'Ngày bắt đầu hiệu lực',effective_to:'Ngày kết thúc hiệu lực',components:'Các thành phần phí',covered_source_term_keys:'Điều khoản trong phạm vi',covered_source_supplier_keys:'Nhà cung cấp trong phạm vi',evidence_reference:'Bằng chứng khai báo',reason:'Lý do'},
 scope_declarations:{source_declaration_key:'Mã khai báo',declaration:'Nội dung khai báo'},
};
const names={products:'Menu',ingredients:'Nguyên liệu',suppliers:'Nhà cung cấp',recipes:'Định lượng món',supplier_terms:'Quy cách mua',sales:'Bán hàng',opening_stock:'Tồn kho theo lô',usage_history:'Thực dùng',purchase_history:'Mua hàng'};
const definitions=[
 ['01_danh_muc.xlsx',main,['products','ingredients','suppliers','recipes','supplier_terms'],'input'],
 ['02_ban_hang.xlsx',main,['sales'],'input'],
 ['03_lich_su.xlsx',main,['purchase_history','usage_history'],'input'],
 ['04_ton_kho.xlsx',main,['opening_stock'],'input'],
 ['05_ca_du_ton.xlsx',enough,['purchase_history','opening_stock'],'sufficient_only'],
 ['06_tuan_kiem_chung.xlsx','03_external_week_locked.xlsx',['sales'],'external_locked'],
 ['07_doi_soat.xlsx','04_inventory_reconciliation.xlsx',Object.keys(books['04_inventory_reconciliation.xlsx']),'reference_only'],
];
const ledgerLabels={day:'Ngày',ingredient:'Nguyên liệu',unit:'ĐVT',opening:'Tồn đầu ngày',received:'Thực nhận',expiry:'Hạn dùng',unit_cost:'Giá một đơn vị vật lý',consumed:'Thực dùng',expired:'Hết hạn',closing:'Tồn cuối ngày',key:'Mã lô nguồn',name:'Tên nguyên liệu',received_date:'Ngày thực nhận',expiry_date:'Hạn dùng',quantity:'Lượng ban đầu',remaining:'Còn lại'};
const manifest={version:1,label:'DỮ LIỆU GIẢ; chỉ đổi hình thức, không tạo facts mới',seed:'same frozen synthetic_cafe_v1; no resampling',oracle_sha256:sha(oracleBytes),oracle_workbook_hashes:JSON.parse(await fs.readFile(path.join(oracleDir,'hashes.json'),'utf8')),cutoff:oracle.manifest.cutoff_timestamp,source_system_key:oracle.manifest.source_system_key,report_type:'CAFE_INPUT_V1',files:{}};
for(const [file,source,schemas,role] of definitions){
 const entries=schemas.map((schema,index)=>{
  const rows=books[source][schema];const columns=Object.keys(labels[schema]||rows[0]).filter(k=>k in rows[0]).map(k=>({field:k,label:labels[schema]?.[k]||ledgerLabels[k]||k}));
  if(columns.some(c=>c.label===c.field && c.field!=='sku')) throw Error('Untranslated field '+schema);
  return {sheet:names[schema]||(schema.startsWith('main')?'Ca chính - ':'Đủ tồn - ')+(schema.endsWith('daily')?'theo ngày':'theo lô'),schema,header_row:4+(index%2),columns,row_count:rows.length,oracle_file:source,oracle_sheet:schema};
 });
 manifest.files[file]={role,sheets:entries};
 if(process.argv[2] && process.argv[2]!==file)continue;
 const wb=Workbook.create();
 for(const spec of entries){
  const rows=books[source][spec.schema];const sh=wb.worksheets.add(spec.sheet);sh.showGridLines=false;
  const notes=[spec.sheet+' — QUÁN CAFE GIẢ LẬP',role==='external_locked'?'KHÓA RIÊNG: thực tế 18–24/10/2026; không upload vào đầu vào Planning':role==='reference_only'?'CHỈ ĐỐI SOÁT; không nhập lại như hàng nhận hoặc tăng tồn':'Kỳ 19/04–17/10/2026; chốt 17/10/2026 23:59:59 +07:00', 'Nguồn: bộ giả Cafe V1; SKU khai báo riêng; mã nguồn không thay SKU'];
  for(let i=0;i<notes.length;i++){sh.getRangeByIndexes(i,0,1,1).values=[[notes[i]]];sh.getRangeByIndexes(i,0,1,spec.columns.length).format.rowHeight=i===0?28:23;}
  sh.getRange('A1').format.font={name:'Arial',size:14,bold:true};
  const convert=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)?Date.parse(v+'T00:00:00Z')/86400000+25569:v;
  const matrix=[spec.columns.map(c=>c.label),...rows.map(r=>spec.columns.map(c=>convert(r[c.field])))];
  const start=spec.header_row-1;sh.getRangeByIndexes(start,0,matrix.length,spec.columns.length).values=matrix;
  const body=sh.getRangeByIndexes(start,0,matrix.length,spec.columns.length);body.format.font={name:'Arial',size:11};body.format.rowHeight=22;body.format.verticalAlignment='center';
  sh.getRangeByIndexes(start,0,1,spec.columns.length).format={fill:'#334155',font:{name:'Arial',size:11,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:46,horizontalAlignment:'center'};
  for(let i=0;i<spec.columns.length;i++){
   const k=spec.columns[i].field;const col=sh.getRangeByIndexes(start,i,matrix.length,1);
   col.format.columnWidth=k==='reason'||k==='evidence_reference'?65:k==='name'||k.endsWith('_id')||k.startsWith('source_')?34:Math.max(16,Math.min(28,spec.columns[i].label.length+2));
   const textLength=Math.max(0,...rows.map(r=>typeof r[k]==='string'?r[k].length:0));
   col.format.columnWidth=Math.max(col.format.columnWidth,Math.min(70,textLength+3));
   if(k==='reason'||k==='evidence_reference'){
    sh.getRangeByIndexes(start+1,i,rows.length,1).format.wrapText=true;
    sh.getRangeByIndexes(start+1,0,rows.length,spec.columns.length).format.rowHeight=36;
   }
   const cells=sh.getRangeByIndexes(start+1,i,rows.length,1);
   if(rows.some(r=>typeof r[k]==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(r[k])))cells.setNumberFormat('dd/mm/yyyy');
   else if(k.endsWith('_at')){cells.setNumberFormat('dd/mm/yyyy hh:mm:ss "UTC"');col.format.columnWidth=33;}
   else if(rows.some(r=>typeof r[k]==='number'))cells.setNumberFormat(k==='unit_cost'?'#,##0.00':'#,##0');
  }
  sh.freezePanes.freezeRows(spec.header_row);
 }
 wb.recalculate();
 const check=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:20},maxChars:1000});
 await fs.writeFile(path.join(runtime,file+'.checks.json'),check.ndjson);
 const letter=n=>{let text='';for(n++;n;n=Math.floor((n-1)/26))text=String.fromCharCode(65+(n-1)%26)+text;return text;};
 for(const spec of entries)for(let offset=0;offset<spec.columns.length;offset+=6){
  const img=await wb.render({sheetName:spec.sheet,range:`${letter(offset)}1:${letter(Math.min(offset+5,spec.columns.length-1))}${spec.header_row+4}`,scale:1,format:'png'});
  await fs.writeFile(path.join(runtime,file+'-'+spec.schema+(offset?'-'+offset:'')+'.png'),new Uint8Array(await img.arrayBuffer()));
 }
 const xlsx=await SpreadsheetFile.exportXlsx(wb);await xlsx.save(path.join(out,file));
 try{await fs.rename(path.join(out,file+'.inspect.ndjson'),path.join(runtime,file+'.inspect.ndjson'));}catch(e){if(e.code!=='ENOENT')throw e;}
 console.log('Exported '+file);
}
// Structured declarations deliberately live outside Excel, using existing CSV intake.
const csvValue=v=>'"'+(v===null?'':typeof v==='object'?JSON.stringify(v):String(v)).replaceAll('"','""')+'"';
for(const [file,source,schema] of [['08_khai_bao_phi.csv',main,'payable_fees'],['09_pham_vi_ca_chinh.csv',main,'scope_declarations'],['10_pham_vi_du_ton.csv',enough,'scope_declarations']]){
 const rows=books[source][schema],columns=Object.keys(rows[0]).map(k=>({field:k,label:labels[schema][k]}));
 manifest.files[file]={role:'explicit_declaration',sheets:[{sheet:'CSV',schema,header_row:1,columns,row_count:rows.length,oracle_file:source,oracle_sheet:schema}]};
 if(!process.argv[2]||process.argv[2]==='--metadata')await fs.writeFile(path.join(out,file),[columns.map(c=>csvValue(c.label)).join(','),...rows.map(r=>columns.map(c=>csvValue(r[c.field])).join(','))].join('\r\n')+'\r\n','utf8');
}
if(!process.argv[2]||process.argv[2]==='--metadata'){
 await fs.writeFile(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
 const hashes={};for(const file of Object.keys(manifest.files))hashes[file]=sha(await fs.readFile(path.join(out,file)));
 await fs.writeFile(path.join(out,'hashes.json'),JSON.stringify(hashes,null,2)+'\n');
}
