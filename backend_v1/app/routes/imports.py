"""Status and error-report endpoints for asynchronous spreadsheet imports."""
from io import BytesIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Group, ImportJob, User, UserRole
from ..schemas import ImportJobOut
from ..security import CurrentUser
from ..storage import storage

router = APIRouter(prefix="/api/import-jobs", tags=["imports"])
DbSession = Annotated[Session, Depends(get_db)]


def _visible(job: ImportJob, user: User, db: Session) -> bool:
    if user.role == UserRole.admin and job.created_by_id == user.id:
        return True
    if user.role == UserRole.teacher and job.created_by_id == user.id:
        group = db.get(Group, job.group_id) if job.group_id else None
        return group is not None and group.owner_id == user.id
    return False


def _out(job: ImportJob, request: Request) -> ImportJobOut:
    result = ImportJobOut.model_validate(job)
    if job.error_file_key:
        result.error_file_url = str(request.url_for("import_error_file", import_job_id=job.id))
    return result


@router.get("/{import_job_id}", response_model=ImportJobOut)
def import_status(import_job_id: UUID, request: Request, db: DbSession, user: CurrentUser) -> ImportJobOut:
    job = db.get(ImportJob, import_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    if not _visible(job, user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this import job")
    return _out(job, request)


@router.get("/{import_job_id}/errors", name="import_error_file")
def import_error_file(import_job_id: UUID, db: DbSession, user: CurrentUser):
    job = db.get(ImportJob, import_job_id)
    if job is None or not _visible(job, user, db) or not job.error_file_key:
        raise HTTPException(status_code=404, detail="Error file not found")
    if not storage.exists(job.error_file_key):
        raise HTTPException(status_code=404, detail="Error file is no longer available")
    return StreamingResponse(BytesIO(storage.get_bytes(job.error_file_key)), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="import-{job.id}-errors.csv"'})
