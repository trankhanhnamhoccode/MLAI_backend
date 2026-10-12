"""Revalidate previously generated synthetic evidence with current boundaries; no solve."""
from pathlib import Path
import argparse
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.application.contracts.procurement_v2 import ProcurementResultV2
from app.application.contracts.procurement_selection import WinnerSelection


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=ROOT/'runtime/verification/procurement_v2')
    args=parser.parse_args()
    count=0
    for folder in (args.directory,):
        for products in (5,10):
            result=ProcurementResultV2.model_validate_json((folder/f'native_{products}p.json').read_text(encoding='utf-8'))
            selected=WinnerSelection.model_validate_json((folder/f'selection_{products}p.json').read_text(encoding='utf-8'))
            assert selected.comparison.source==result,'Source evidence correspondence mismatch'
            count+=1
    print(f'{count} native results + {count} selector artifacts: current boundary validation/source correspondence PASS; no solver/DB')


if __name__=='__main__':main()
