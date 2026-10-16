"""Read-only original OOXML checks and redacted public API evidence for I5."""
import hashlib
import json
import os
import posixpath
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / 'tests/fixtures/import_i5_workbooks.json').read_text(encoding='utf-8'))['workbooks']
SOURCE_DIRECTORY = Path(os.environ.get('I5_WORKBOOK_DIRECTORY', ROOT.parent / 'backend/dts'))
EVIDENCE_DIRECTORY = Path(os.environ.get('I5_EVIDENCE_DIRECTORY', ROOT / 'runtime/verification/i5/exploratory'))


def cells_by_sheet(path: Path) -> dict[str, dict[str, str]]:
    """Independent ZIP/XML extraction: never imports discovery/matcher or mutates XLSX."""
    main = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    rel_id = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
    result = {}
    with ZipFile(path) as archive:
        shared = ([''.join(si.itertext()) for si in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall(main + 'si')]
                  if 'xl/sharedStrings.xml' in archive.namelist() else [])
        links = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        for sheet in workbook.find(main + 'sheets'):
            target = links[sheet.attrib[rel_id]]
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            cells = {}
            for cell in ET.fromstring(archive.read(target)).iter(main + 'c'):
                value, inline = cell.find(main + 'v'), cell.find(main + 'is')
                raw = value.text if value is not None else ''.join(inline.itertext()) if inline is not None else None
                if raw is not None:
                    cells[cell.attrib['r']] = shared[int(raw)] if cell.attrib.get('t') == 's' else raw
            result[sheet.attrib['name']] = cells
    return result


def save(name: str, data) -> None:
    EVIDENCE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIRECTORY / (name + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def redact(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if any(word in k.lower() for word in ('password', 'csrf', 'secret', 'token'))
                else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


@pytest.fixture
def i5_trace(monkeypatch, request):
    events = []
    original = httpx.Client.send
    def send(client, call, *args, **kwargs):
        response = original(client, call, *args, **kwargs)
        path = call.url.path
        if any(part in path for part in ('/imports', '/jobs', '/mapping-', '/readiness')):
            if call.headers.get('content-type', '').startswith('multipart/'):
                body = {'format': 'multipart', 'bytes': call.headers.get('content-length')}
            else:
                try:
                    body = json.loads(call.content) if call.content else None
                except (ValueError, httpx.RequestNotRead):
                    body = {'format': 'stream'}
            try:
                result = response.json()
            except ValueError:
                result = {'bytes': len(response.content)}
            events.append(dict(method=call.method, path=str(call.url), request=redact(body),
                               status=response.status_code, response=redact(result)))
        return response
    monkeypatch.setattr(httpx.Client, 'send', send)
    yield events
    save('api-' + hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:16],
         {'case': request.node.nodeid, 'events': events})
