"""Strict C2 header and canonical identifier transport checks."""
from uuid import UUID
from fastapi import Request
from app.application.contracts.auth import AuthError


ETAG_RESPONSE = {'headers': {'ETag': {'description': 'Quoted current version for the route CAS domain.', 'schema': {'type': 'string'}}}}


def strict_transport(request: Request):
    for name in ('Origin','Idempotency-Key','If-Match','X-CSRF-Token'):
        if len(request.headers.getlist(name))>1:
            raise AuthError('INVALID_REQUEST',400)
    for name,value in request.path_params.items():
        if name.endswith('_id'):
            try:
                if str(UUID(value))!=value: raise ValueError()
            except (ValueError,TypeError):
                raise AuthError('INVALID_RESOURCE_ID',422) from None
    for name in ('file_id','import_id'):
        if name in request.query_params:
            try:
                value=request.query_params[name]
                if str(UUID(value))!=value: raise ValueError()
            except (ValueError,TypeError):
                raise AuthError('INVALID_FILTER',422) from None
