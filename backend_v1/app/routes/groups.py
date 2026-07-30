"""Role-scoped group membership and attendance read routes."""
import secrets
import string
from io import BytesIO
from uuid import UUID

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AttendanceRecord, ClassSession, Group, GroupMembership, Student, User, UserRole
from ..schemas import AddStudentRequest, AttendanceOut, GroupCreate, GroupOut, GroupRosterImportOut, GroupRosterResult, GroupUpdate, JoinGroupRequest
from ..security import CurrentUser, require_roles

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


@router.get("", response_model=list[GroupOut])
def list_groups(user: CurrentUser, db: DbSession) -> list[Group]:
    if user.role == UserRole.admin:
        return db.query(Group).order_by(Group.created_at.desc()).all()
    if user.role == UserRole.teacher:
        return db.query(Group).filter(Group.owner_id == user.id).order_by(Group.created_at.desc()).all()
    return (
        db.query(Group)
        .join(GroupMembership)
        .filter(GroupMembership.student_id == user.id)
        .order_by(Group.created_at.desc())
        .all()
    )


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


@router.post("/{group_id}/students/bulk", response_model=GroupRosterImportOut, status_code=status.HTTP_202_ACCEPTED)
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


@router.get("/{group_id}/attendance", response_model=list[AttendanceOut])
def group_attendance(group_id: UUID, user: CurrentUser, db: DbSession) -> list[AttendanceOut]:
    group = _get_visible_group(group_id, user, db)
    query = (
        db.query(AttendanceRecord, ClassSession, Group)
        .join(ClassSession, AttendanceRecord.session_id == ClassSession.id)
        .join(Group, ClassSession.group_id == Group.id)
        .filter(Group.id == group.id)
    )
    if user.role == UserRole.student:
        query = query.filter(AttendanceRecord.student_id == user.id)
    return [
        AttendanceOut(session_id=session.id, group_id=group_row.id, group_name=group_row.name, status=record.status, marked_at=record.marked_at)
        for record, session, group_row in query.order_by(ClassSession.started_at.desc()).all()
    ]
