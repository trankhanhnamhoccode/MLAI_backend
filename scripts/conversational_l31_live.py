"""Explicit synthetic L3.1 batch, independent of the exhausted L3 ledger."""
import argparse,os,subprocess,sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--allow-paid-synthetic-max-30-usd-1.00',required=True,action='store_true')
    parser.add_argument('--case',choices=('all','remaining','budget','proof','ingredient','tradeoff','no_winner','clarification','followup'),default='all')
    args=parser.parse_args()
    env={**os.environ,'SHELFCASH_CHAT_L31_LIVE':'synthetic-30-usd-1.00'}
    raise SystemExit(subprocess.call([sys.executable,'-B','-m','scripts.assistant_tests','tests/live/test_chat_l31_live.py',
        '-k','l31_live' if args.case=='all' else 'not budget' if args.case=='remaining' else args.case,'-q','-x','-p','no:cacheprovider','--tb=short'],env=env))


if __name__=='__main__':main()
