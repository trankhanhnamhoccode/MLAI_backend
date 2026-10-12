"""Private signed history cursor; snapshot/filter/actor bound on every request."""
import base64,hmac,json
from app.application.contracts.auth import AuthError,Pagination


def page(signer,token,domain,identity,snapshot,items,limit,cursor):
    offset=0
    if cursor:
        try:
            payload,signature=cursor.rsplit('.',1)
            if not hmac.compare_digest(signature,signer.sign(token,domain,payload)):raise ValueError()
            saved=json.loads(base64.urlsafe_b64decode(payload+'='*((-len(payload))%4)))
            if saved['identity']!=identity:raise ValueError()
            if saved['snapshot']!=snapshot:raise AuthError('SNAPSHOT_NOT_AVAILABLE',409)
            offset=saved['offset']
            if type(offset) is not int or not 0<offset<len(items):raise ValueError()
        except (ValueError,KeyError,TypeError):raise AuthError('INVALID_CURSOR',422) from None
    next_cursor=None
    if offset+limit<len(items):
        payload=base64.urlsafe_b64encode(json.dumps(dict(identity=identity,snapshot=snapshot,offset=offset+limit),separators=(',',':')).encode()).decode().rstrip('=')
        next_cursor=payload+'.'+signer.sign(token,domain,payload)
    return items[offset:offset+limit],Pagination(limit=limit,next_cursor=next_cursor,total_count=len(items))
