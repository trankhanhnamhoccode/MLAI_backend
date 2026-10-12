"""Bound PLAN14 bodies while streaming, before JSON/Pydantic decoding."""
from app.application.contracts.planning_configuration import ConfigurationError


class PlanningBodyLimits:
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        path=scope.get('path','')
        pdf_export='/procurement-plans/' in path and path.endswith('/exports')
        if scope['type']!='http' or scope.get('method') not in ('PUT','POST') or not ('/planning-requirements' in path or path.endswith('/planning-budget') or path.endswith('/procurement-plans') or pdf_export):
            return await self.app(scope,receive,send)
        consumed=0
        async def bounded():
            nonlocal consumed
            message=await receive()
            consumed+=len(message.get('body',b''))
            if consumed>65536:
                scope.setdefault('state',{})['planning_body_limit']=True
                if pdf_export:raise ConfigurationError('RESOURCE_LIMIT_EXCEEDED',413)
                if path.endswith('/procurement-plans'):
                    from app.application.contracts.planning_configuration import FieldError
                    raise ConfigurationError('INVALID_PLANNING_CONFIGURATION',422,(FieldError(code='RESOURCE_LIMIT_EXCEEDED',field='request',message='Yêu cầu vượt giới hạn 64 KiB.'),))
                raise ConfigurationError('REQUEST_TOO_LARGE',413)
            return message
        await self.app(scope,bounded,send)
