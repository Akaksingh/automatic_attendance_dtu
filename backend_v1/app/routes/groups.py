"""Role-scoped group membership and attendance read routes."""
import secrets
import string
from io import BytesIO
from uuid import UUID

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..database import get_db
from ..config import settings
from ..models import AttendanceStatus, AuditLog, AttendanceRecord, ClassSession, Group, GroupMembership, ImportJob, SessionState, Student, User, UserRole
from ..schemas import AddStudentRequest, AttendanceOut, AttendancePage, GroupAttendanceSummary, GroupCreate, GroupOut, GroupPage, GroupRosterImportOut, GroupRosterPage, GroupRosterResult, GroupRosterStudentOut, GroupUpdate, ImportJobOut, JoinGroupRequest, PageMeta, StudentAttendanceSummary
from ..security import CurrentUser, require_roles
from ..storage import storage
from ..tasks import process_import_job

router = APIRouter(prefix="/api/groups", tags=["groups"])
DbSession = Annotated[Session, Depends(get_db)]


def _join_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


def _get_visible_group(group_id: UUID, user: CurrentUser, db: Session) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if user.role == UserRole.admin or (user.role == UserRole.teacher and group.owner_id == user.id):
        return group
    if user.role == UserRole.student and db.query(GroupMembership).filter_by(group_id=group_id, student_id=user.id).first():
        return group
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this group")


def _get_manageable_group(group_id: UUID, user: User, db: Session) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if user.role != UserRole.admin and group.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only manage groups you created")
    return group


def _require_active_group(group: Group) -> None:
    if group.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Archived groups cannot be changed")


def _add_student_by_roll_no(group: Group, roll_no: str, db: Session) -> User:
    student = db.query(Student).filter(Student.roll_no == roll_no.strip()).first()
    if student is None:
        raise ValueError("Student roll number was not found")
    user = db.get(User, student.user_id)
    if user is None or user.role != UserRole.student:
        raise ValueError("Roll number does not belong to a student account")
    if db.query(GroupMembership).filter_by(group_id=group.id, student_id=user.id).first():
        raise ValueError("Student is already in this group")
    db.add(GroupMembership(group_id=group.id, student_id=user.id))
    return user


@router.get("", response_model=GroupPage)
def list_groups(user: CurrentUser, db: DbSession, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), search: str | None = Query(None, max_length=100)) -> GroupPage:
    if user.role == UserRole.admin:
        query = db.query(Group).order_by(Group.created_at.desc())
    elif user.role == UserRole.teacher:
        query = db.query(Group).filter(Group.owner_id == user.id).order_by(Group.created_at.desc())
    else:
        query = db.query(Group).join(GroupMembership).filter(GroupMembership.student_id == user.id).order_by(Group.created_at.desc())
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(Group.name.ilike(term), Group.join_code.ilike(term)))
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return GroupPage(items=items, meta=PageMeta(page=page, page_size=page_size, total=total, pages=(total + page_size - 1) // page_size))


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    db: DbSession,
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> Group:
    join_code = _join_code()
    while db.query(Group).filter(Group.join_code == join_code).first():
        join_code = _join_code()
    group = Group(name=payload.name, join_code=join_code, owner_id=user.id)
    db.add(group)
    db.add(AuditLog(actor_id=user.id, action="group.created", entity_type="group", entity_id=group.id))
    db.commit()
    db.refresh(group)
    return group


@router.patch("/{group_id}", response_model=GroupOut)
def update_group(
    group_id: UUID,
    payload: GroupUpdate,
    db: DbSession,
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> Group:
    group = _get_manageable_group(group_id, user, db)
    _require_active_group(group)
    group.name = payload.name
    db.commit()
    db.refresh(group)
    return group


@router.post("/{group_id}/archive", response_model=GroupOut)
def archive_group(
    group_id: UUID,
    db: DbSession,
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> Group:
    group = _get_manageable_group(group_id, user, db)
    if group.archived_at is None:
        from datetime import UTC, datetime
        group.archived_at = datetime.now(UTC)
        db.add(AuditLog(actor_id=user.id, action="group.archived", entity_type="group", entity_id=group.id))
        db.commit()
        db.refresh(group)
    return group


@router.post("/{group_id}/unarchive", response_model=GroupOut)
def unarchive_group(
    group_id: UUID,
    db: DbSession,
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> Group:
    group = _get_manageable_group(group_id, user, db)
    if group.archived_at is not None:
        group.archived_at = None
        db.add(AuditLog(actor_id=user.id, action="group.unarchived", entity_type="group", entity_id=group.id))
        db.commit()
        db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: UUID,
    db: DbSession,
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> None:
    group = _get_manageable_group(group_id, user, db)
    db.add(AuditLog(actor_id=user.id, action="group.deleted", entity_type="group", entity_id=group.id))
    db.delete(group)
    db.commit()


@router.post("/{group_id}/students", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def add_student_to_group(
    group_id: UUID,
    payload: AddStudentRequest,
    db: DbSession,
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> Group:
    group = _get_manageable_group(group_id, user, db)
    _require_active_group(group)
    try:
        _add_student_by_roll_no(group, payload.roll_no, db)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return group


@router.get("/{group_id}/students", response_model=GroupRosterPage)
def list_group_students(
    group_id: UUID,
    user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> GroupRosterPage:
    group = _get_visible_group(group_id, user, db)
    query = (
        db.query(GroupMembership, Student, User)
        .join(Student, Student.user_id == GroupMembership.student_id)
        .join(User, User.id == Student.user_id)
        .filter(GroupMembership.group_id == group.id)
        .order_by(Student.roll_no.asc())
    )
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    items = [GroupRosterStudentOut(student_id=student.id, user_id=student.user_id, roll_no=student.roll_no, full_name=student.full_name, email=user_row.email, profile_image_url=student.profile_image_url, joined_at=membership.joined_at) for membership, student, user_row in rows]
    return GroupRosterPage(items=items, meta=PageMeta(page=page, page_size=page_size, total=total, pages=(total + page_size - 1) // page_size))


@router.delete("/{group_id}/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def remove_student_from_group(group_id: UUID, student_id: UUID, db: DbSession, user: User = Depends(require_roles(UserRole.admin, UserRole.teacher))) -> Response:
    group = _get_manageable_group(group_id, user, db)
    _require_active_group(group)
    membership = db.query(GroupMembership).filter_by(group_id=group.id, student_id=student_id).first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student is not in this group")
    db.add(AuditLog(actor_id=user.id, action="group.student_removed", entity_type="group_membership", entity_id=membership.id))
    db.delete(membership)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{group_id}/students/bulk-legacy", response_model=GroupRosterImportOut, status_code=status.HTTP_202_ACCEPTED, include_in_schema=False)
async def bulk_add_students_to_group(
    group_id: UUID,
    db: DbSession,
    spreadsheet: UploadFile = File(...),
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> GroupRosterImportOut:
    group = _get_manageable_group(group_id, user, db)
    _require_active_group(group)
    if not (spreadsheet.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload an .xlsx or .xlsm Excel file")
    try:
        workbook = load_workbook(BytesIO(await spreadsheet.read()), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not read Excel file") from exc
    rows = workbook.active.iter_rows(values_only=True)
    headers = [str(value or "").strip().lower() for value in next(rows, ())]
    if not {"roll_no", "full_name"}.issubset(headers):
        workbook.close()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Excel must contain roll_no and full_name columns")
    results: list[GroupRosterResult] = []
    for row_number, values in enumerate(rows, start=2):
        data = {headers[index]: values[index] if index < len(values) else None for index in range(len(headers))}
        roll_no = str(data.get("roll_no") or "").strip()
        try:
            student = _add_student_by_roll_no(group, roll_no, db)
            db.commit()
            results.append(GroupRosterResult(row=row_number, roll_no=roll_no, status="added", student_id=student.id))
        except ValueError as exc:
            db.rollback()
            results.append(GroupRosterResult(row=row_number, roll_no=roll_no or None, status="failed", error=str(exc)))
    workbook.close()
    return GroupRosterImportOut(added=sum(item.status == "added" for item in results), failed=sum(item.status == "failed" for item in results), results=results)


@router.post("/{group_id}/students/bulk", response_model=ImportJobOut, status_code=status.HTTP_202_ACCEPTED)
async def queue_bulk_add_students_to_group(
    group_id: UUID,
    db: DbSession,
    spreadsheet: UploadFile = File(...),
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> ImportJobOut:
    group = _get_manageable_group(group_id, user, db)
    _require_active_group(group)
    if not (spreadsheet.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload an .xlsx or .xlsm Excel file")
    content = await spreadsheet.read(settings.max_spreadsheet_bytes + 1)
    if len(content) > settings.max_spreadsheet_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Spreadsheet is too large")
    key = f"imports/pending/{secrets.token_urlsafe(24)}.xlsx"
    storage.put_bytes(key, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    try:
        job = ImportJob(kind="group_roster", created_by_id=user.id, group_id=group.id, spreadsheet_key=key)
        db.add(job)
        db.commit()
        db.refresh(job)
        process_import_job.delay(job.id)
        return job
    except Exception:
        storage.delete(key)
        raise


@router.post("/join", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def join_group(
    payload: JoinGroupRequest,
    db: DbSession,
    user: User = Depends(require_roles(UserRole.student)),
) -> Group:
    group = db.query(Group).filter(Group.join_code == payload.join_code.upper()).first()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid group code")
    _require_active_group(group)
    if not db.query(GroupMembership).filter_by(group_id=group.id, student_id=user.id).first():
        db.add(GroupMembership(group_id=group.id, student_id=user.id))
        db.commit()
    return group


@router.get("/{group_id}/attendance", response_model=AttendancePage)
def group_attendance(group_id: UUID, user: CurrentUser, db: DbSession, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)) -> AttendancePage:
    group = _get_visible_group(group_id, user, db)
    query = (
        db.query(AttendanceRecord, ClassSession, Group)
        .join(ClassSession, AttendanceRecord.session_id == ClassSession.id)
        .join(Group, ClassSession.group_id == Group.id)
        .filter(Group.id == group.id)
    )
    if user.role == UserRole.student:
        query = query.filter(AttendanceRecord.student_id == user.id)
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    items = [
        AttendanceOut(session_id=session.id, group_id=group_row.id, group_name=group_row.name, status=record.status, marked_at=record.marked_at)
        for record, session, group_row in rows
    ]
    return AttendancePage(items=items, meta=PageMeta(page=page, page_size=page_size, total=total, pages=(total + page_size - 1) // page_size))


def _finalized_attendance_data(group: Group, db: Session) -> tuple[list[ClassSession], list[tuple[GroupMembership, Student, User]], dict[tuple[UUID, UUID], AttendanceStatus]]:
    sessions = db.query(ClassSession).filter(ClassSession.group_id == group.id, ClassSession.state == SessionState.finalized).order_by(ClassSession.started_at.asc()).all()
    roster = (
        db.query(GroupMembership, Student, User)
        .join(Student, Student.user_id == GroupMembership.student_id)
        .join(User, User.id == Student.user_id)
        .filter(GroupMembership.group_id == group.id)
        .order_by(Student.roll_no.asc())
        .all()
    )
    session_ids = [session.id for session in sessions]
    records = db.query(AttendanceRecord).filter(AttendanceRecord.session_id.in_(session_ids)).all() if session_ids else []
    statuses = {(record.session_id, record.student_id): record.status for record in records}
    return sessions, roster, statuses


def _attendance_workbook(group: Group, sessions: list[ClassSession], roster: list[tuple[GroupMembership, Student, User]], statuses: dict[tuple[UUID, UUID], AttendanceStatus]) -> Workbook:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Attendance"
    headers = ["Roll no.", "Student", "Present", "Absent", "Attendance %"] + [session.started_at.strftime("%d %b %Y") for session in sessions]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="334155")
    for _, student, user in roster:
        present = sum(statuses.get((session.id, user.id)) == AttendanceStatus.present for session in sessions)
        absent = len(sessions) - present
        percentage = round((present / len(sessions)) * 100, 2) if sessions else 0.0
        values = [student.roll_no, student.full_name, present, absent, percentage]
        values.extend("Present" if statuses.get((session.id, user.id)) == AttendanceStatus.present else "Absent" for session in sessions)
        sheet.append(values)
    sheet.freeze_panes = "F2"
    sheet.auto_filter.ref = sheet.dimensions
    for column, width in {"A": 16, "B": 28, "C": 12, "D": 12, "E": 16}.items():
        sheet.column_dimensions[column].width = width
    for index in range(6, 6 + len(sessions)):
        sheet.column_dimensions[get_column_letter(index)].width = 16
    return workbook


@router.get("/{group_id}/summary", response_model=GroupAttendanceSummary)
def group_attendance_summary(group_id: UUID, user: CurrentUser, db: DbSession) -> GroupAttendanceSummary:
    group = _get_visible_group(group_id, user, db)
    sessions, roster, statuses = _finalized_attendance_data(group, db)
    students = []
    for _, student, user_row in roster:
        present = sum(statuses.get((session.id, user_row.id)) == AttendanceStatus.present for session in sessions)
        absent = len(sessions) - present
        students.append(StudentAttendanceSummary(student_id=student.id, user_id=user_row.id, roll_no=student.roll_no, full_name=student.full_name, present=present, absent=absent, percentage=round((present / len(sessions)) * 100, 2) if sessions else 0.0))
    return GroupAttendanceSummary(group_id=group.id, total_sessions=len(sessions), students=students)


@router.get("/{group_id}/attendance.xlsx")
def export_group_attendance(group_id: UUID, user: CurrentUser, db: DbSession) -> Response:
    group = _get_visible_group(group_id, user, db)
    sessions, roster, statuses = _finalized_attendance_data(group, db)
    workbook = _attendance_workbook(group, sessions, roster, statuses)
    output = BytesIO()
    workbook.save(output)
    filename = f"{group.name.strip().replace(' ', '_')}_attendance.xlsx"
    return Response(content=output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
