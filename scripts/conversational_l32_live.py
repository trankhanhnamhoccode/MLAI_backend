"""Explicit L3.2 opt-in; L3.1/L3.2 share durable reservations, never reset."""
import argparse
import os
import subprocess
import sys
import json
import hashlib
from pathlib import Path


def freeze_source():
    paths=sorted([*Path('app').rglob('*.py'),*Path('tests/fixtures/decision_assistant').glob('*.json')])
    version=hashlib.sha256(b''.join(str(p).encode()+p.read_bytes() for p in paths)).hexdigest()
    root=Path('runtime/assistant-test/conversational-l32-live');root.mkdir(parents=True,exist_ok=True)
    source={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for p in paths:
        dest=root/('source-'+version)/p;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():assert dest.read_bytes()==p.read_bytes()
        else:dest.write_bytes(p.read_bytes())
    meta=dict(frozen_version=version,checkpoint_sha=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),
        source_sha256=source,prompt_version='conversational_chat_prompt/5',validator_version='chat_assertions/6',selection_version='chat_evidence/6',
        scope='app Python and static assistant fixture JSON; no private configuration or runtime data')
    path=root/f'freeze-{version}.json'
    if path.exists():assert json.loads(path.read_text(encoding='utf8'))==meta
    else:
        with path.open('x',encoding='utf8') as out:json.dump(meta,out,indent=2)
    return version


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--allow-paid-shared-l31-l32-max-30-usd-1.00',dest='paid',action='store_true')
    p.add_argument('--freeze-source',action='store_true',help='Offline only: snapshot source, no DB/provider')
    p.add_argument('--case',default='all',choices=('all','budget','quantity','why','why_missing','proof','comparison','no_winner','conversation'))
    args=p.parse_args()
    if args.freeze_source:
        print(freeze_source());return
    if not args.paid:p.error('Explicit paid opt-in required')
    env={**os.environ,'SHELFCASH_CHAT_L32_LIVE':'shared-l31-l32-30-usd-1.00'}
    raise SystemExit(subprocess.call([sys.executable,'-B','-m','scripts.assistant_tests','tests/live/test_chat_l32_live.py',
        '-k','l32_live' if args.case=='all' else args.case,'-q','-x','-p','no:cacheprovider','--tb=short'],env=env))


if __name__=='__main__':main()
