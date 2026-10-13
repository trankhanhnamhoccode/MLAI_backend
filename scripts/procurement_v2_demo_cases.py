"""Explicit synthetic inputs only, not an API/default resolution adapter."""
from copy import deepcopy


def upgrade(data,paths):
    data=deepcopy(data)
    data['prepared']['capture_version']=2
    data['policy'].update(policy_id='procurement_api_policy',service_units='PER_PRODUCT_HORIZON_RATIO',
        fallback='MAX_MIN_PRODUCT_THEN_EQUAL_MEAN_THEN_MIN_OUTLAY')
    for rule in data['policy']['rules']:rule.update(target='1',floors=[])
    data['requirements']=dict(paths=paths,provenance='SYNTHETIC explicit effective requirements')
    return data


def path(name,minimum,overrides=()):
    return dict(path=name,minimum=minimum,overrides=[dict(product_id=p,target=t) for p,t in overrides])
