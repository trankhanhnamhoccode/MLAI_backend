"""Explicit persistence model registration; imports do not connect to the DB."""
from app.models.store import Store
from app.models.store_membership import StoreMembership
from app.models.user import User
from app.models.product import Product
from app.models.ingredient import Ingredient
from app.models.recipe import Recipe
from app.models.recipe_line import RecipeLine
from app.models.supplier import Supplier
from app.models.supplier_term import SupplierTerm
from app.models.import_history import ImportHistoryRecord
from app.models.sales_daily import SalesDaily
from app.models.inventory_lot import InventoryLot
from app.models.inventory_movement import InventoryMovement
from app.models.business_constraint import BusinessConstraint
from app.models.forecast_run import ForecastRun
from app.models.forecast_prediction import ForecastPrediction
from app.models.decision_run import DecisionRun
from app.models.forecast_run_input import ForecastRunInput
from app.models.forecast_execution_metadata import ForecastExecutionMetadata
from app.models.planning_run import PlanningRun
from app.models.auth import AuthAccount, AuthSession, CredentialToken, MembershipGrant, AuthAudit, AuthRateLimit
from app.models.email_verification import EmailVerificationToken, EmailVerificationDelivery
from app.models.password_reset import PasswordResetDelivery
from app.models.staff import StaffInvitation, StaffRequestReceipt, InvitationEventRecord, PermissionEventRecord, InvitationDeliveryIntent
from app.models.read_revision import PublicReadRevision
from app.models.import_staging import (ImportBatch, ImportFile, ImportBlob, ImportProfile, ImportProfileVersion,
    ImportSourceContext, ImportJob, ImportPreview, ImportReceipt, ImportAudit)

__all__ = [
    "ImportHistoryRecord",
    "SupplierSourceRecord", "TermSourceRecord", "PayableFeeRecord", "ScopeDeclarationRecord", "InventoryReceiptRecord", "InventoryThreshold", "StockRequestReceipt", "InventoryAudit",
    "ImportBatch", "ImportFile", "ImportBlob", "ImportProfile", "ImportProfileVersion",
    "ImportSourceContext", "ImportJob", "ImportPreview", "ImportReceipt", "ImportAudit",
    "PublicReadRevision",
    "StaffInvitation", "StaffRequestReceipt", "InvitationEventRecord", "PermissionEventRecord", "InvitationDeliveryIntent",
    "AuthAccount", "AuthSession", "CredentialToken", "MembershipGrant", "AuthAudit", "AuthRateLimit",
    "User", "Store", "StoreMembership", "Product", "Ingredient", "Recipe", "RecipeLine",
    "Supplier", "SupplierTerm", "SalesDaily", "InventoryLot", "InventoryMovement", "BusinessConstraint",
    "ForecastRun", "ForecastPrediction", "DecisionRun", "ForecastRunInput", "ForecastExecutionMetadata", "PlanningRun",
]

from app.models.operational_import import (SupplierSourceRecord, TermSourceRecord, PayableFeeRecord, ScopeDeclarationRecord, InventoryReceiptRecord, InventoryThreshold, StockRequestReceipt, InventoryAudit)

from app.models.recipe_schedule import RecipeScheduleChange, RecipeScheduleRequestReceipt
from app.models.planning_configuration import (PlanningDefault, PlanningBudget, SavedRequirement,
    PlanningConfigurationEvent, PlanningConfigurationRevision, PlanningConfigurationReceipt)
from app.models.model_serving import ModelServingConfiguration,ForecastServingIdentity
from app.models.planning_export import PlanningExport
from app.models.notifications import NotificationIntent, NotificationRecord, NotificationReadReceipt
from app.models.collaboration import PermissionRequestRecord, PermissionRequestAudit, MappingSubmissionRecord
from app.models.store_creation import StoreCreationReceipt
from app.models.plan_summary import PlanSummaryGeneration, PlanSummaryReceipt
from app.models.assistant_message import AssistantMessage
from app.models.chat_generation import ChatGenerationRow
