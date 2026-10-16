"""Compare frozen P1 /2 and owner /3 without overwriting P1 evidence.

Run from the checkout root: python -B -m scripts.owner_pdf_review
"""
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader
import pypdfium2
from app.infrastructure.planning_pdf_renderer import PlanningPDFRenderer
from app.application.contracts.planning_pdf import PlanningPDFDocument
from tests.fixtures.owner_plan_pdf import representative_document


def main() -> None:
    output = Path('runtime/p11-pdf')
    output.mkdir(parents=True, exist_ok=True)
    original = Path('runtime/p1-pdf')
    document = (PlanningPDFDocument.model_validate_json((original / 'data-oracle.json').read_text(encoding='utf-8'))
                if (original / 'data-oracle.json').exists() else representative_document())
    oracle = document.model_dump_json(indent=2)
    (output / 'data-oracle.json').write_text(oracle, encoding='utf-8')
    renderer = PlanningPDFRenderer()
    results = {}
    for name, render in [('before', renderer.render_v2), ('owner-plan-synthetic', renderer.render)]:
        path = output / (name + '.pdf')
        data = render(document)
        if name == 'before' and (original / 'owner-plan-synthetic.pdf').exists():
            assert data == (original / 'owner-plan-synthetic.pdf').read_bytes(), 'Frozen /2 must match original P1 bytes'
        path.write_bytes(data)
        reader = PdfReader(path)
        results[name] = dict(pages=len(reader.pages), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        (output / (name + '-text.txt')).write_text('\n'.join(p.extract_text() for p in reader.pages), encoding='utf-8')
        if name == 'owner-plan-synthetic':
            pdf = pypdfium2.PdfDocument(data)
            for index in range(len(pdf)):
                page = pdf[index]
                bitmap = page.render(scale=1.5)
                bitmap.to_pil().save(output / f'preview-{index + 1:02}.png')
                bitmap.close()
                page.close()
            pdf.close()
    assert document.model_dump_json(indent=2) == oracle
    (output / 'before-after.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
