"""Explicit synthetic V6 acceptance; independent budget, never reopens old ledgers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from decimal import Decimal

GROUP='L32-V6-acceptance-1'
ROOT=Path('runtime/assistant-test')/GROUP
MAX_ATTEMPTS=16
MAX_USD=Decimal('0.30')
BOUND=Decimal('0.0140592')  # 24000 input bytes * .3/M + 1200 output * 2.5/M + framing reserve
OPT_IN='--allow-paid-l32-v6-acceptance-1-max-16-usd-0.30'
MATRIX={
    'budget':'Total 10 VND; distinguish budget and payable fees.',
    'quantity':'Fresh milk proposed purchase 20 g; correct option and Ingredient, not stock.',
    'why':'Fresh milk proposed 20 g plus retained simulated LOW requested/available/shortage 20/20/0 g; no exact causal/zero-purchase proof.',
    'why_missing':'Unavailable purchase quantity and causal evidence; no fabricated amount, zero or existing proposal.',
    'proof':'Viewed option eligible, each Product BASE target 95%, PASS/zero shortfall; evaluated scope and UNPROVEN boundary.',
    'comparison':'Real retained pair: to-minus-from cost +5 VND, Product/path simulated fulfilled deltas +5/+10 cup; no actual/causal claim.',
    'no_winner':'No eligible winner; retained rejection/blocker reasons and shortfalls 9.5/19 cup, no invented selection.',
    'conversation':['Milk ambiguity: deterministic clarification, no completion.',
                    'Fresh milk: resume original purchase question, 20 g.',
                    'Why that amount: same Ingredient, retained simulation and missing causality boundary.',
                    'Condensed milk: switch to its own Ingredient/fact IDs and simulation. Fixture independently proposes 20 g for BOTH milks; numeric equality alone cannot prove a correct switch.'],
}


def reservations(base):
    root=base/GROUP
    paths=sorted(root.glob('attempt-*.json'),key=lambda p:int(p.stem.split('-')[-1]))
    rows=[json.loads(p.read_text(encoding='utf8')) for p in paths]
    for n,r in enumerate(rows,1):
        if r['attempt']!=n or r['budget_group']!=GROUP or Decimal(r['reserved_usd'])!=BOUND:
            raise ValueError('Invalid acceptance reservation journal')
    return rows,sum((Decimal(r['reserved_usd']) for r in rows),Decimal(0))


def reserve(base,record):
    root=base/GROUP;root.mkdir(parents=True,exist_ok=True)
    lock=root/'reservation.lock'
    with lock.open('x',encoding='utf8') as out:out.write('Fail closed after crash; no automatic refund.\n')
    try:
        if (root/'STOP-429.json').exists():raise ValueError('HTTP429 stopped acceptance batch')
        rows,total=reservations(base)
        if len(rows)>=MAX_ATTEMPTS or total+BOUND>MAX_USD:raise ValueError('Acceptance cap exhausted')
        n=len(rows)+1
        with (root/f'attempt-{n}.json').open('x',encoding='utf8') as out:
            json.dump(dict(record,attempt=n,reserved_usd=str(BOUND),budget_group=GROUP),out,ensure_ascii=False,indent=2)
            out.flush();os.fsync(out.fileno())
        return n
    finally:lock.unlink()


def freeze():
    from tests.live.test_chat_l31_live import fingerprint
    version=fingerprint();ROOT.mkdir(parents=True,exist_ok=True)
    paths=sorted([*Path('app').rglob('*.py'),*Path('tests/fixtures/decision_assistant').glob('*.json'),
        Path(__file__).relative_to(Path.cwd()),Path('tests/live/test_chat_v6_acceptance.py'),Path('tests/live/test_chat_l32_live.py')])
    meta=dict(group=GROUP,frozen_version=version,checkpoint_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        prompt='conversational_chat_prompt/5',validator='chat_assertions/6',selection='chat_evidence/6',renderer='decision_chat_renderer/7',schema='conversational_assertions/2',
        maximum_attempts=MAX_ATTEMPTS,maximum_reserved_usd=str(MAX_USD),reservation_per_attempt_usd=str(BOUND),
        expected_behavior=MATRIX,label_author='Codex-authored before live; not independent human review.',
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    for p in paths:
        dest=ROOT/('source-'+version)/p;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():assert dest.read_bytes()==p.read_bytes(),'Frozen source changed'
        else:dest.write_bytes(p.read_bytes())
    path=ROOT/f'freeze-{version}.json'
    if path.exists():assert json.loads(path.read_text(encoding='utf8'))==meta
    else:
        with path.open('x',encoding='utf8') as out:json.dump(meta,out,ensure_ascii=False,indent=2)
    return version


def main():
    p=argparse.ArgumentParser();p.add_argument(OPT_IN,dest='paid',action='store_true')
    p.add_argument('--freeze-source',action='store_true');p.add_argument('--case',choices=['all',*MATRIX],default='all')
    args=p.parse_args()
    if args.freeze_source:print(freeze());return
    if not args.paid:p.error('Explicit acceptance budget opt-in required')
    if (ROOT/'STOP-429.json').exists():p.error('HTTP429: batch stopped')
    env={**os.environ,'SHELFCASH_CHAT_V6_ACCEPTANCE':GROUP}
    raise SystemExit(subprocess.call([sys.executable,'-B','-m','scripts.assistant_tests','tests/live/test_chat_v6_acceptance.py',
        '-k','v6_acceptance' if args.case=='all' else args.case,'-q','-x','-p','no:cacheprovider','--tb=short'],env=env))


if __name__=='__main__':main()
