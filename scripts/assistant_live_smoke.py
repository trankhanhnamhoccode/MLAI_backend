"""Explicit synthetic paid smoke; never invoked by regular pytest."""
import os
import subprocess
import sys


def main():
    if sys.argv[1:] != ['--allow-paid-synthetic-max-3-usd-0.10']:
        raise SystemExit('Require --allow-paid-synthetic-max-3-usd-0.10')
    env = {**os.environ,'SHELFCASH_LIVE_SMOKE':'authorized-synthetic-3-0.10'}
    raise SystemExit(subprocess.call([sys.executable,'-B','-m','scripts.assistant_tests',
        'tests/live/test_assistant_smoke.py','-q','-x','-p','no:cacheprovider','--tb=short'],env=env))


if __name__ == '__main__': main()
