"""Read-only rules regression measurement against the pinned I1 column reference.

No Settings, app, DB or provider. Not a blind/human-validated accuracy oracle;
this measures proposal regressions, never canonical correctness or import readiness.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from uuid import UUID

from app.application.import_analysis import discover
from app.infrastructure.import_parser import parse_source


def evaluate(directory: Path, expectations: Path) -> dict:
    expected = json.loads(expectations.read_text(encoding="utf-8"))
    oracle = {w["sha256"]: w["sheets"] for w in expected["workbooks"]}
    seen = set()
    totals = Counter({key: 0 for key in (
        "sheets", "columns", "classification_correct", "supported_sheets",
        "supported_classification_correct", "correct_target_proposals", "wrong_target_proposals",
        "useful_candidates_without_target", "unresolved_columns", "unresolved_supported_columns")})
    details = []
    for path in sorted(directory.glob("*.xlsx")):
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest not in oracle or digest in seen:
            raise ValueError("Unexpected or duplicate workbook content hash")
        seen.add(digest)
        sheets, issues, _ = discover(UUID(int=1), parse_source(content, "xlsx"))
        if len(sheets) != len(oracle[digest]):
            raise ValueError("Oracle sheet count mismatch")
        for sheet, answer in zip(sheets, oracle[digest], strict=True):
            columns = [i for i in issues if i.sheet_id == sheet.sheet_id
                       and i.issue_type in {"column", "schema_blocker"}]
            if len(columns) != len(answer["targets"]):
                raise ValueError("Oracle column count mismatch")
            counts = Counter(sheets=1, columns=len(columns))
            counts["classification_correct"] = int(sheet.selected_type == answer["schema"])
            counts["supported_sheets"] = int(answer["schema"] is not None)
            counts["supported_classification_correct"] = int(
                answer["schema"] is not None and sheet.selected_type == answer["schema"])
            for issue, target in zip(columns, answer["targets"], strict=True):
                if issue.target_field:
                    counts["correct_target_proposals" if issue.target_field == target
                           else "wrong_target_proposals"] += 1
                elif target is not None and target in issue.candidate_targets:
                    counts["useful_candidates_without_target"] += 1
                else:
                    counts["unresolved_columns"] += 1
                    if target is not None:
                        counts["unresolved_supported_columns"] += 1
            totals.update(counts)
            details.append(dict(workbook_sha256=digest, sheet=sheet.name, **counts))
    if seen != set(oracle):
        raise ValueError("Missing original workbook(s) from the pinned oracle")
    return dict(metrics=dict(totals), sheets=details,
                limits="Static rules only; no profile/source/identity/business declarations, "
                       "Owner approval, provider, preview/commit or audit-batch reproduction.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-directory", type=Path, required=True)
    parser.add_argument("--expectations", type=Path,
                        default=Path("tests/fixtures/import_curated_workbooks.json"))
    args = parser.parse_args()
    print(json.dumps(evaluate(args.input_directory, args.expectations), indent=2))
