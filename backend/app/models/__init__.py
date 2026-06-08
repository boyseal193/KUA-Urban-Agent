from app.models.user import User
from app.models.property import Property, Analysis
from app.models.scan import Scan, ScanHistory
from app.models.note import Note
from app.models.pipeline_status import PipelineStatusRecord
from app.models.auth_session import AuthSession

# Laundry vertical (independent tables, same Base.metadata so Alembic picks
# them up automatically). Importing here is safe — the laundry models do not
# touch any storage table.
from app.laundry.models import (  # noqa: F401
    LaundryProperty,
    LaundryAnalysis,
    LaundryScanJob,
    LaundryScanStep,
    LaundryGeneratedMemo,
    LaundryExport,
    LaundryAuditLog,
    LaundryDuplicate,
    LaundryError,
    LaundrySettings,
)

__all__ = [
    "User",
    "Property",
    "Analysis",
    "Scan",
    "ScanHistory",
    "Note",
    "PipelineStatusRecord",
    "AuthSession",
    "LaundryProperty",
    "LaundryAnalysis",
    "LaundryScanJob",
    "LaundryScanStep",
    "LaundryGeneratedMemo",
    "LaundryExport",
    "LaundryAuditLog",
    "LaundryDuplicate",
    "LaundryError",
    "LaundrySettings",
]
