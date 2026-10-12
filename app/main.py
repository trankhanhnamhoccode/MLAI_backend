from contextlib import asynccontextmanager
from uuid import uuid4
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.health import router as health_router
from app.config import Settings
from app.api.auth import router as auth_router, clear_cookie
from app.application.contracts.auth import AuthError, ErrorDetails, ErrorEnvelope, ErrorInfo, Meta
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.staff import StaffUseCases
from app.api.staff import router as staff_router
from app.api.public_reads import router as public_read_router
from app.application.use_cases.public_reads import PublicReads
from app.application.use_cases.stock_writes import StockWrites
from app.api.stock_writes import router as stock_write_router
from app.application.use_cases.recipe_schedule import RecipeSchedule
from app.api.recipe_schedule import router as recipe_schedule_router
from app.application.contracts.public_reads import ReadErrorEnvelope,EmptyMeta
from app.infrastructure.database.engine import create_database_engine
from app.application.use_cases.import_staging import ImportStaging
from app.api.import_staging import router as import_router
from app.api.planning_configuration import router as planning_configuration_router
from app.application.use_cases.planning_configuration import PlanningConfigurationWrites
from app.application.contracts.planning_configuration import (
    ConfigurationError,ConfigurationErrorEnvelope,ConfigurationErrorInfo,ConfigurationErrorDetails,
)
from app.application.use_cases.forecast_serving import ForecastServing
from app.application.use_cases.readiness import ReadinessReads
from app.infrastructure.storage.forecast_artifacts import ForecastArtifactStore
from app.api.readiness import router as readiness_router
from app.api.planning_public import router as planning_public_router
from app.application.use_cases.planning_public import PublicPlanning


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()
    engine = create_database_engine(configuration)
    @asynccontextmanager
    async def lifespan(application):
        from app.infrastructure.import_worker import ImportWorker
        from app.infrastructure.planning_worker import PlanningWorker
        from app.infrastructure.planning_export_worker import PlanningExportWorker
        worker=ImportWorker(application.state.import_staging) if configuration.import_worker_enabled else None
        planning_worker=PlanningWorker(application.state.planning_execution) if configuration.planning_worker_enabled else None
        pdf_worker=PlanningExportWorker(application.state.planning_exports) if configuration.pdf_export_worker_enabled else None
        application.state.planning_worker=planning_worker
        if worker:worker.start()
        if planning_worker:planning_worker.start()
        if pdf_worker:pdf_worker.start()
        try:
            yield
        finally:
            if worker:worker.stop()
            if planning_worker:planning_worker.stop()
            if pdf_worker:pdf_worker.stop()
            engine.dispose()
    application = FastAPI(
        title=configuration.app_name,
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.settings = configuration
    application.state.auth = AuthUseCases(engine)
    application.state.staff = StaffUseCases(application.state.auth, configuration)
    application.state.public_reads = PublicReads(application.state.auth)
    application.state.stock_writes = StockWrites(application.state.auth, application.state.public_reads)
    application.state.recipe_schedule = RecipeSchedule(application.state.auth)
    application.state.import_staging = ImportStaging(application.state.auth, configuration)
    from app.application.use_cases.import_history import ImportHistoryReads
    application.state.import_history = ImportHistoryReads(application.state.import_staging)
    application.state.planning_configuration = PlanningConfigurationWrites(application.state.auth)
    application.state.forecast_serving = ForecastServing(engine,ForecastArtifactStore(configuration.model_artifact_directory))
    from app.application.use_cases.planning_worker import PlanningExecution
    application.state.planning_worker=None
    application.state.planning_execution=PlanningExecution(application.state.auth,application.state.forecast_serving)
    application.state.readiness = ReadinessReads(application.state.auth,application.state.forecast_serving,
        planning_available=lambda:application.state.planning_worker is not None and application.state.planning_worker.available)
    application.state.planning_public = PublicPlanning(application.state.auth,application.state.forecast_serving)
    from app.application.use_cases.planning_exports import PlanningExports
    from app.infrastructure.storage.planning_pdf import PlanningPDFStore
    from app.infrastructure.planning_pdf_renderer import PlanningPDFRenderer
    application.state.planning_exports = PlanningExports(application.state.planning_public,
        PlanningPDFStore(configuration.runtime_directory/'planning_exports'),PlanningPDFRenderer())
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(staff_router)
    application.include_router(public_read_router)
    application.include_router(stock_write_router)
    application.include_router(recipe_schedule_router)
    application.include_router(import_router)
    application.include_router(planning_configuration_router)
    application.include_router(readiness_router)
    application.include_router(planning_public_router)
    from app.api.history import router as history_router
    application.include_router(history_router)
    from app.api.planning_exports import router as pdf_router
    application.include_router(pdf_router)
    from app.infrastructure.import_body_limits import ImportBodyLimits
    application.add_middleware(ImportBodyLimits)
    from app.infrastructure.planning_body_limits import PlanningBodyLimits
    application.add_middleware(PlanningBodyLimits)

    def config_failure(error):
        body=ConfigurationErrorEnvelope(data=None,meta=EmptyMeta(),error=ConfigurationErrorInfo(
            code=error.code,message='Không thể thực hiện yêu cầu cấu hình.',
            details=ConfigurationErrorDetails(field_errors=error.field_errors or None)))
        return JSONResponse(status_code=error.status,content=body.model_dump(mode='json'))

    @application.exception_handler(ConfigurationError)
    async def configuration_error(request,error):
        return config_failure(error)

    def public_read(request):
        import re
        return request.method=='GET' and re.fullmatch(r'/api/v1/stores/[^/]+/(products|inventory)(/[^/]+(/(lots|movements))?)?',request.url.path) is not None

    def planning_surface(request):
        return any(segment in request.url.path for segment in ("/planning-requirements", "/planning-budget", "/readiness", "/planning-context", "/procurement-plans"))

    def failure(request, error):
        body = ErrorEnvelope(data=None, meta=Meta(request_id=getattr(request.state, "request_id", str(uuid4()))), error=ErrorInfo(code=error.code, message=error.code, details=ErrorDetails()))
        if public_read(request) or planning_surface(request):
            body = ReadErrorEnvelope(data=None,meta=EmptyMeta(),error=body.error)
        response = JSONResponse(status_code=error.status, content=body.model_dump(mode="json", exclude_none=False))
        response.headers["Cache-Control"] = "no-store"
        if error.status == 401:
            clear_cookie(response, request)
        if error.retry_after is not None:
            response.headers["Retry-After"] = str(error.retry_after)
        return response

    @application.exception_handler(AuthError)
    async def auth_error(request, error):
        return failure(request, error)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        issues = error.errors()
        if '/planning-requirements' in request.url.path or request.url.path.endswith('/planning-budget') or '/procurement-plans' in request.url.path:
            from app.application.contracts.planning_configuration import FieldError
            if any(i['loc'][:1]==('header',) for i in issues):
                return config_failure(ConfigurationError('INVALID_REQUEST',400))
            if any(i['type']=='json_invalid' for i in issues):
                return config_failure(ConfigurationError('INVALID_REQUEST',400))
            if any(i['loc'][:1]==('path',) for i in issues):
                return config_failure(ConfigurationError('INVALID_RESOURCE_ID',422))
            if any(i['loc'][:1]==('query',) for i in issues):
                return config_failure(ConfigurationError('INVALID_CURSOR' if any(i['loc'][-1:]==('cursor',) for i in issues) else 'INVALID_FILTER',422))
            errors=[]
            for i in issues:
                location='.'.join(str(x) for x in i['loc'][1:])
                code='UNKNOWN_FIELD' if i['type']=='extra_forbidden' else 'INVALID_NAME' if i['loc'][-1:] == ('name',) else 'INVALID_DECIMAL_TEXT' if i['loc'][-1:] in (('amount',),('min_fill_rate_percent',),('budget_limit',)) else 'INVALID_FIELD'
                errors.append(FieldError(code=code,field=location,message='Kiểm tra lại trường cấu hình.'))
            return config_failure(ConfigurationError('INVALID_PLANNING_CONFIGURATION',422,errors))
        code = "VALIDATION_ERROR"
        if any(i["loc"][:1] == ("query",) for i in issues):
            code = "INVALID_FILTER"
            if request.url.path.endswith('/imports/calendar') and any(i['loc'][-1:]==('month',) for i in issues):code='INVALID_MONTH'
            elif request.url.path.endswith('/imports') and any(i['loc'][-1:]==('import_date',) for i in issues):code='INVALID_DATE'
        elif public_read(request) and any(i['loc'][:1]==('path',) for i in issues):
            code = 'INVALID_RESOURCE_ID' if '/products' in request.url.path else 'VALIDATION_ERROR'
        elif any(i["loc"][-1:] == ("email",) for i in issues):
            code = "INVALID_EMAIL"
        elif "/staff-invitations/" in request.url.path and any(i["loc"][-1:] in (("token",), ("invitation_token",), ("X-Invitation-Token",)) for i in issues):
            code = "INVALID_TOKEN"
        elif request.url.path.endswith("/credentials/complete") and any(i["loc"][-1:] == ("password",) for i in issues):
            code = "PASSWORD_POLICY_VIOLATION"
        return failure(request, AuthError(code, 422))

    @application.exception_handler(StarletteHTTPException)
    async def transport_error(request,error):
        if request.url.path.startswith('/api/v1/imports/'):
            return failure(request,AuthError('INVALID_REQUEST' if error.status_code==400 else 'RESOURCE_NOT_FOUND' if error.status_code==404 else 'VALIDATION_ERROR',error.status_code))
        if '/planning-requirements' in request.url.path or request.url.path.endswith('/planning-budget'):
            return config_failure(ConfigurationError('INVALID_REQUEST',error.status_code))
        from fastapi.exception_handlers import http_exception_handler
        return await http_exception_handler(request,error)

    @application.exception_handler(SQLAlchemyError)
    async def unavailable(request, error):
        logging.getLogger(__name__).error("Auth persistence failure (%s)", type(error).__name__)
        return failure(request, AuthError("SERVICE_UNAVAILABLE", 503))

    @application.middleware("http")
    async def private_headers(request: Request, call_next):
        request.state.request_id = str(uuid4())
        loopback = {"localhost", "127.0.0.1", "::1"}
        if request.url.path.startswith("/api/v1/") and configuration.auth_dev_cookie and (request.url.hostname not in loopback or not request.client or request.client.host not in loopback):
            response = failure(request, AuthError("CSRF_CHECK_FAILED"))
        else:
            try:
                response = await call_next(request)
            except Exception as error:
                if not request.url.path.startswith("/api/v1/"):
                    raise
                logging.getLogger(__name__).error("Auth execution failure (%s)", type(error).__name__)
                response = failure(request, AuthError("SERVICE_UNAVAILABLE", 503))
        if request.url.path.startswith("/api/v1/"):
            if getattr(request.state,'planning_body_limit',False):
                if request.url.path.endswith('/procurement-plans'):
                    from app.application.contracts.planning_configuration import FieldError
                    response=config_failure(ConfigurationError('INVALID_PLANNING_CONFIGURATION',422,(FieldError(code='RESOURCE_LIMIT_EXCEEDED',field='request',message='Yêu cầu vượt giới hạn 64 KiB.'),)))
                else:response=config_failure(ConfigurationError('RESOURCE_LIMIT_EXCEEDED' if '/procurement-plans/' in request.url.path and request.url.path.endswith('/exports') else 'REQUEST_TOO_LARGE',413))
            if getattr(request.state,'import_resource_limit',False):
                response=failure(request,AuthError('RESOURCE_LIMIT_EXCEEDED',413))
            response.headers["Cache-Control"] = "private, no-store" if public_read(request) or response.headers.get('Content-Type')=='application/pdf' else "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Request-ID"] = request.state.request_id
        return response

    application.add_middleware(CORSMiddleware, allow_origins=configuration.auth_allowed_origins,
        allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Content-Type", "X-CSRF-Token", "If-Match", "If-None-Match", "Idempotency-Key", "X-Invitation-Token"],
        expose_headers=["ETag", "Location", "Retry-After", "X-Request-ID", "Content-Disposition", "Content-Length", "X-Content-Type-Options"])
    return application


app = create_app()
