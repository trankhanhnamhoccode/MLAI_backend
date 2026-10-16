"""Focused acceptance consumes remaining L4 slots only; no new budget group."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
from scripts.conversational_l4_live import ROOT as LEDGER_ROOT,reservations

ROOT=LEDGER_ROOT/'l41-candidate8'
CASES={'conversation':'Sữa cần mua bao nhiêu?','failed':'Run lỗi còn thông tin gì?',
    'mixed':'So sánh hai phương án, chênh lệch chi phí và phục vụ mô phỏng?'}


def freeze():
    from tests.live.test_chat_l31_live import fingerprint
    version=fingerprint();ROOT.mkdir(parents=True,exist_ok=True)
    paths=sorted([*Path('app').rglob('*.py'),*Path('tests/fixtures/decision_assistant').glob('*.json'),
        *Path('tests/fixtures/assistant_l41').glob('*.json'),
        Path('tests/assistant_l41_cases.py'),Path('tests/live/test_chat_l41_live.py'),Path('scripts/conversational_l41_live.py'),
        Path('tests/unit/test_assistant_l41.py'),Path('tests/integration/test_assistant_l41.py'),Path('tests/live/test_chat_l32_live.py')])
    meta=dict(frozen_version=version,checkpoint_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        group='L4-quality-evaluation-1',phase='l41-candidate8',prompt=7,validator=8,selection=8,renderer=9,resolver=5,schema=2,
        expected_behavior=json.loads(Path('tests/fixtures/assistant_l41/protocol.json').read_text(encoding='utf8')),
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    path=ROOT/f'freeze-{version}.json'
    if path.exists():assert json.loads(path.read_text(encoding='utf8'))==meta
    else:
        for p in paths:
            dest=ROOT/'source'/p;dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as out:out.write(p.read_bytes())
        with path.open('x',encoding='utf8') as out:json.dump(meta,out,ensure_ascii=False,indent=2)
    return version


def main():
    p=argparse.ArgumentParser();p.add_argument('--freeze-source',action='store_true')
    p.add_argument('--allow-paid-l41-remaining-l4-max-24-usd-0.50',dest='paid',action='store_true')
    p.add_argument('--case',choices=['all',*CASES],default='all');a=p.parse_args()
    if a.freeze_source:print(freeze());return
    if not a.paid:p.error('Explicit remaining L4 budget opt-in required')
    rows,_=reservations(LEDGER_ROOT.parent)
    if len(rows)>=24:p.error('L4 completion cap exhausted')
    if (LEDGER_ROOT/'STOP-429.json').exists():p.error('HTTP429: whole L4 group stopped')
    env={**os.environ,'SHELFCASH_CHAT_L41_LIVE':'remaining-l4'}
    raise SystemExit(subprocess.call([sys.executable,'-B','-m','scripts.assistant_tests','tests/live/test_chat_l41_live.py','-k',
        'l41_live' if a.case=='all' else a.case,'-q','-x','-p','no:cacheprovider','--tb=short'],env=env))


if __name__=='__main__':main()
