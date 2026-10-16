"""Synthetic evidence retained by S2; checked provenance is in the fixture identity."""
import json
from pathlib import Path
from app.application.contracts.decision_evidence import DecisionEvidence
from app.application.contracts.plan_summary import SummaryRequest


def evidence_case(kind):
    raw=json.loads((Path(__file__).parent/'fixtures/decision_assistant/owner_summary_evidence.json').read_text(encoding='utf8'))[kind]
    return DecisionEvidence.model_validate(raw['evidence']),SummaryRequest.model_validate(raw['request'])
