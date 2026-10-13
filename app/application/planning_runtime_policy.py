"""Accepted PLAN3/8 policy realized with explicit versioned native resource guards."""
from decimal import Decimal
from app.application.contracts.procurement_v2 import ProcurementPolicyV2
from app.application.readiness_evaluation import contains
from app.application.operational_import_facts import current_fees


def policy_for_acceptance(facts,start) -> ProcurementPolicyV2:
    fees=[r for r in current_fees(facts.snapshot) if contains(r['payload'],start)]
    # This discriminator never confirms absence/coverage. UNKNOWN coverage still
    # blocks in the separately captured declarations before computation.
    mode=fees[0]['payload']['mode'] if len(fees)==1 else 'NONE'
    return ProcurementPolicyV2(policy_id='procurement_api_policy',version=1,
        configuration_id='S49-native-resource-policy/1',configuration_version=1,
        provenance='PLAN3 per-Product100% construction; PLAN8 30s/reserve2s/8 solves; versioned existing native numeric guards; fee coverage independently required',
        rules=tuple(dict(strategy=s,path=p,target=Decimal(1),floors=()) for s,p in zip(('LEAN','BALANCED','PROTECTED'),('LOW','BASE','HIGH'))),
        service_units='PER_PRODUCT_HORIZON_RATIO',primary='MIN_OUTLAY_SUBJECT_TO_REQUIREMENTS',
        fallback='MAX_MIN_PRODUCT_THEN_EQUAL_MEAN_THEN_MIN_OUTLAY',tie_rule='SORTED_OFFER_UUID_PACK_VECTOR_LEXICOGRAPHIC',
        supplier_splitting=True,order_count=1,fee_mode=mode,computation_seconds=Decimal(30),
        validation_reserve_seconds=Decimal(2),max_solves_per_strategy=8,
        certification='DISABLED',certification_vector_limit=0,
        numeric=dict(integer_tolerance=Decimal('.0000001'),coefficient_min=Decimal('.0000000001'),
            coefficient_max=Decimal('10000000000'),scale_min=Decimal('1e-100'),scale_max=Decimal('1e100'),integer_max=2**53-1))
