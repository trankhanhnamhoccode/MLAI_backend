"""Explicit paid AS03 smoke, synthetic only; does not change .env or model flags."""
import argparse,os,subprocess,sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--allow-paid-synthetic-max-10-usd-0.10',action='store_true',required=True)
    parser.add_argument('--case',choices=('budget','proof','tradeoff','ingredient','no_winner','followup','remaining','all'),default='all')
    parser.add_argument('--natural-followup',action='store_true')
    parser.add_argument('--small-output',action='store_true')
    args=parser.parse_args()
    selection='not budget' if args.case=='remaining' else 'conversational_live' if args.case=='all' else args.case
    env={**os.environ,'SHELFCASH_CHAT_LIVE':'synthetic-10-usd-0.10'}
    if args.natural_followup:
        if args.case not in ('budget','proof'):parser.error('Natural follow-up is only for budget/proof')
        env['SHELFCASH_CHAT_VARIANT']='natural_followup'
    if args.small_output:
        if args.case not in ('ingredient','followup'):parser.error('Small output is only for a single Ingredient fact')
        env['SHELFCASH_CHAT_SMALL']='1'
    raise SystemExit(subprocess.call([sys.executable,'-B','-m','scripts.assistant_tests',
        'tests/live/test_conversational_smoke.py','-k',selection,'-q','-x','-p','no:cacheprovider','--tb=short'],env=env))


if __name__=='__main__':main()
