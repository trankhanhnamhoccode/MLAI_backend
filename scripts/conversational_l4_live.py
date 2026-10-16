"""Separately authorized paired synthetic quality evaluation; hard shared cap24/$0.50."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
from decimal import Decimal

GROUP='L4-quality-evaluation-1'
ROOT=Path('runtime/assistant-test')/GROUP
BOUND=Decimal('0.0140592')
MAX_ATTEMPTS=24
MAX_USD=Decimal('.50')
OPT_IN='--allow-paid-l4-max-24-usd-0.50'


def reservations(base):
    rows=[json.loads(p.read_text(encoding='utf8')) for p in sorted((base/GROUP).glob('attempt-*.json'),key=lambda p:int(p.stem.split('-')[-1]))]
    for n,r in enumerate(rows,1):
        if r['attempt']!=n or r['budget_group']!=GROUP or Decimal(r['reserved_usd'])!=BOUND:raise ValueError('Invalid L4 journal')
    return rows,sum((Decimal(r['reserved_usd']) for r in rows),Decimal(0))


def reserve(base,record):
    root=base/GROUP;root.mkdir(parents=True,exist_ok=True)
    lock=root/'reservation.lock'
    with lock.open('x',encoding='utf8') as out:out.write('Fail closed on crash; no auto-refund.\n')
    try:
        if (root/'STOP-429.json').exists():raise ValueError('HTTP429: L4 batch stopped')
        rows,total=reservations(base)
        if len(rows)>=MAX_ATTEMPTS or total+BOUND>MAX_USD:raise ValueError('L4 cap exhausted')
        n=len(rows)+1
        with (root/f'attempt-{n}.json').open('x',encoding='utf8') as out:
            json.dump(dict(record,attempt=n,budget_group=GROUP,reserved_usd=str(BOUND)),out,ensure_ascii=False,indent=2)
            out.flush();os.fsync(out.fileno())
        return n
    finally:lock.unlink()


def freeze(phase):
    from tests.live.test_chat_l31_live import fingerprint
    version=fingerprint();root=ROOT/phase;root.mkdir(parents=True,exist_ok=True)
    paths=sorted([*Path('app').rglob('*.py'),*Path('tests/fixtures/decision_assistant').glob('*.json'),*Path('tests/fixtures/assistant_l4').glob('*.json'),
        Path('tests/live/test_chat_l4_live.py'),Path('tests/l4_cases.py'),Path('scripts/conversational_l4_live.py')])
    meta=dict(phase=phase,group=GROUP,frozen_version=version,checkpoint_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        corpus_sha256=hashlib.sha256(Path('tests/fixtures/assistant_l4/corpus.json').read_bytes()).hexdigest(),
        versions='prompt5/validator6/selection6/renderer7' if phase=='baseline' else 'prompt6/validator7/selection7/renderer8',
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    path=root/f'freeze-{version}.json'
    if path.exists():assert json.loads(path.read_text(encoding='utf8'))==meta
    else:
        for p in paths:
            dest=root/'source'/p;dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as out:out.write(p.read_bytes())
        with path.open('x',encoding='utf8') as out:json.dump(meta,out,indent=2)
    return version


def main():
    p=argparse.ArgumentParser();p.add_argument(OPT_IN,dest='paid',action='store_true')
    p.add_argument('--phase',choices=('baseline','candidate'),required=True);p.add_argument('--freeze-source',action='store_true')
    p.add_argument('--case',default='all',choices=('all','proof','comparison','no_winner','quantity','why','conversation'))
    a=p.parse_args()
    if a.freeze_source:print(freeze(a.phase));return
    if not a.paid:p.error('Separate L4 paid opt-in required')
    if (ROOT/'STOP-429.json').exists():p.error('HTTP429 stops the whole L4 group')
    env={**os.environ,'SHELFCASH_CHAT_L4_LIVE':a.phase}
    raise SystemExit(subprocess.call([sys.executable,'-B','-m','scripts.assistant_tests','tests/live/test_chat_l4_live.py','-k',
        'l4_live' if a.case=='all' else a.case,'-q','-x','-p','no:cacheprovider','--tb=short'],env=env))


if __name__=='__main__':main()
