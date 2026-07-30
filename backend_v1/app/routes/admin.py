"""Admin-only account and bulk student provisioning."""
from io import BytesIO
from pathlib import Path
import secrets
from typing import Annotated
from zipfile import BadZipFile, ZipFile
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from openpyxl import load_workbook
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import PhotoProcessingJob, Student, User, UserRole
from ..schemas import (
    BulkStudentImportOut,
    BulkStudentResult,
    PhotoJobOut,
    StudentOut,
    StudentProvisionOut,
    TeacherCreate,
    UserOut,
)
from ..security import hash_password, require_roles
from ..tasks import process_student_photo

router = APIRouter(prefix="/api/admin", tags=["admin"])
DbSession = Annotated[Session, Depends(get_db)]
email_adapter = TypeAdapter(EmailStr)


def _temporary_password() -> str:
    return f"ClassLens-{secrets.token_urlsafe(9)}"


def _stage_photo(student_id: UUID, file_name: str, content_type: str, content: bytes, db: Session) -> PhotoProcessingJob:
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if content_type not in allowed:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Use JPEG, PNG, or WebP")
    if len(content) > settings.max_profile_photo_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Profile photo is too large")
    suffix = Path(file_name).suffix.lower() or allowed[content_type]
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = allowed[content_type]
    key = f"pending/{student_id}/{secrets.token_urlsafe(24)}{suffix}"
    path = Path(settings.profile_photo_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    job = PhotoProcessingJob(student_id=student_id, storage_key=key, content_type=content_type)
    db.add(job)
    return job


def _create_student(db: Session, *, email: str, full_name: str, roll_no: str, password: str) -> Student:
    email = str(email).strip().lower()
    roll_no = roll_no.strip()
    full_name = full_name.strip()
    try:
        email = str(email_adapter.validate_python(email))
    except ValidationError as exc:
        raise ValueError("Email is invalid") from exc
    if len(full_name) < 2 or not roll_no:
        raise ValueError("Name and roll number are required")
    if db.query(User).filter(User.email == email).first():
        raise ValueError("Email is already registered")
    if db.query(Student).filter(Student.roll_no == roll_no).first():
        raise ValueError("Roll number is already registered")
    user = User(email=email, full_name=full_name, password_hash=hash_password(password), role=UserRole.student)
    db.add(user)
    db.flush()
    student = Student(user_id=user.id, roll_no=roll_no, full_name=full_name)
    db.add(student)
    db.flush()
    return student


def _student_out(student: Student) -> StudentOut:
    return StudentOut(
        id=student.id,
        user_id=student.user_id,
        roll_no=student.roll_no,
        full_name=student.full_name,
        profile_image_url=student.profile_image_url,
        photo_count=len(student.photos),
        photos=[],
    )


@router.post("/teachers", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_teacher(
    payload: TeacherCreate,
    db: DbSession,
    user: User = Depends(require_roles(UserRole.admin)),
) -> User:
    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    teacher = User(email=email, full_name=payload.full_name, password_hash=hash_password(payload.password), role=UserRole.teacher)
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.post("/students", response_model=StudentProvisionOut, status_code=status.HTTP_201_CREATED)
async def create_student(
    db: DbSession,
    email: str = Form(...),
    full_name: str = Form(...),
    roll_no: str = Form(...),
    password: str | None = Form(None),
    file: UploadFile | None = File(None),
    _: User = Depends(require_roles(UserRole.admin)),
) -> StudentProvisionOut:
    temporary_password = password or _temporary_password()
    job = None
    try:
        student = _create_student(db, email=email, full_name=full_name, roll_no=roll_no, password=temporary_password)
        if file is not None:
            job = _stage_photo(student.id, file.filename or "profile.jpg", file.content_type or "", await file.read(), db)
        db.commit()
    except (ValueError, HTTPException) as exc:
        db.rollback()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if job:
        process_student_photo.delay(job.id)
    db.refresh(student)
    return StudentProvisionOut(student=_student_out(student), photo_job=PhotoJobOut.model_validate(job) if job else None, temporary_password=temporary_password if password is None else None)


@router.post("/students/bulk", response_model=BulkStudentImportOut, status_code=status.HTTP_202_ACCEPTED)
async def bulk_create_students(
    db: DbSession,
    spreadsheet: UploadFile = File(...),
    images_zip: UploadFile | None = File(None),
    _: User = Depends(require_roles(UserRole.admin)),
) -> BulkStudentImportOut:
    if not (spreadsheet.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload an .xlsx or .xlsm Excel file")
    image_entries: dict[str, tuple[str, bytes]] = {}
    if images_zip is not None:
        try:
            with ZipFile(BytesIO(await images_zip.read())) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    normalized = info.filename.replace("\\", "/").lstrip("./")
                    if ".." in Path(normalized).parts:
                        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Image ZIP contains an unsafe path")
                    image_entries[normalized.lower()] = (Path(normalized).name, archive.read(info))
        except BadZipFile as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="images_zip is not a valid ZIP archive") from exc
    try:
        workbook = load_workbook(BytesIO(await spreadsheet.read()), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not read Excel file") from exc
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    headers = [str(value or "").strip().lower() for value in next(rows, ())]
    required = {"email", "full_name", "roll_no"}
    if not required.issubset(headers):
        workbook.close()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Excel must contain email, full_name, and roll_no columns")
    results: list[BulkStudentResult] = []
    for row_number, values in enumerate(rows, start=2):
        data = {headers[index]: values[index] if index < len(values) else None for index in range(len(headers))}
        email = str(data.get("email") or "").strip().lower()
        roll_no = str(data.get("roll_no") or "").strip()
        full_name = str(data.get("full_name") or "").strip()
        supplied_password = str(data.get("password") or "").strip()
        password = supplied_password or _temporary_password()
        job = None
        try:
            student = _create_student(db, email=email, full_name=full_name, roll_no=roll_no, password=password)
            photo_name = str(data.get("photo") or "").strip()
            if photo_name:
                normalized_name = photo_name.replace("\\", "/").lstrip("./").lower()
                entry = image_entries.get(normalized_name)
                if entry is None:
                    matches = [value for key, value in image_entries.items() if Path(key).name == Path(normalized_name).name]
                    entry = matches[0] if len(matches) == 1 else None
                if entry is None:
                    raise ValueError("Photo is missing from images_zip")
                file_name, content = entry
                suffix = Path(file_name).suffix.lower()
                content_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(suffix)
                if content_type is None:
                    raise ValueError("Photo must be JPEG, PNG, or WebP")
                job = _stage_photo(student.id, file_name, content_type, content, db)
            db.commit()
            if job:
                process_student_photo.delay(job.id)
            results.append(BulkStudentResult(row=row_number, email=email, roll_no=roll_no, status="created", student_id=student.id, photo_job_id=job.id if job else None, temporary_password=None if supplied_password else password))
        except (ValueError, HTTPException) as exc:
            db.rollback()
            results.append(BulkStudentResult(row=row_number, email=email or None, roll_no=roll_no or None, status="failed", error=str(exc.detail if isinstance(exc, HTTPException) else exc)))
    workbook.close()
    return BulkStudentImportOut(created=sum(result.status == "created" for result in results), failed=sum(result.status == "failed" for result in results), results=results)


@router.get("/photo-jobs/{job_id}", response_model=PhotoJobOut)
def photo_job_status(job_id: UUID, db: DbSession, _: User = Depends(require_roles(UserRole.admin))) -> PhotoProcessingJob:
    job = db.get(PhotoProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo job not found")
    return job
