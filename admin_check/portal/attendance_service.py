"""Canonical attendance rules and event helpers.

This module is the only place where arrival timing is classified. Kiosk and
frontends render the returned values; they never recalculate them.
"""

import datetime as dt
import re
import uuid

from .enrollment import session_students
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import AttendanceRecord, AttendanceSession


METHOD_FACIAL_RECOGNITION = "FACIAL_RECOGNITION"


def _as_datetime(value, date=None):
    if isinstance(value, dt.datetime):
        if timezone.is_aware(value):
            return timezone.localtime(value).replace(tzinfo=None)
        return value
    if isinstance(value, dt.time):
        return dt.datetime.combine(date or timezone.localdate(), value)
    raise TypeError("Expected datetime or time")


def calculate_attendance_status(scheduled_time, check_in_time):
    """Return the canonical attendance classification for two times.

    Boundaries are minute-precise: 07:45:59 is still 15 minutes late and
    07:46:00 is 16 minutes late for a 07:30 schedule.
    """
    scheduled = _as_datetime(scheduled_time)
    check_in = _as_datetime(check_in_time, scheduled.date())
    delta_seconds = (check_in - scheduled).total_seconds()
    late_minutes = max(0, int(delta_seconds // 60))

    if delta_seconds <= 0:
        return {
            "status": "present",
            "attendance_code": "ON_TIME",
            "attendance_label": "ON TIME",
            "late_minutes": 0,
            "attendance_periods": 0,
        }
    if late_minutes <= 15:
        return {
            "status": "late",
            "attendance_code": "LATE_LEVEL_1",
            "attendance_label": "LATE — LEVEL 1",
            "late_minutes": late_minutes,
            "attendance_periods": 0,
        }
    if late_minutes < 60:
        return {
            "status": "late",
            "attendance_code": "LATE_ONE_PERIOD",
            "attendance_label": "LATE — 1 PERIOD",
            "late_minutes": late_minutes,
            "attendance_periods": 1,
        }
    if late_minutes <= 120:
        return {
            "status": "absent",
            "attendance_code": "ABSENT_TWO_PERIODS",
            "attendance_label": "ABSENT — 2 PERIODS",
            "late_minutes": late_minutes,
            "attendance_periods": 2,
        }
    return {
        "status": "absent",
        "attendance_code": "ABSENT",
        "attendance_label": "ABSENT",
        "late_minutes": late_minutes,
        "attendance_periods": None,
    }


def scheduled_time_for_period(period):
    return {
        1: dt.time(7, 0), 2: dt.time(7, 50), 3: dt.time(8, 50),
        4: dt.time(9, 40), 5: dt.time(10, 40), 6: dt.time(13, 0),
        7: dt.time(13, 50), 8: dt.time(14, 50), 9: dt.time(15, 40),
        10: dt.time(16, 40),
    }.get(period, dt.time(7, 0))


def get_session_scheduled_time(session):
    return scheduled_time_for_period(session.schedule.start_period)


def session_period_count(session):
    """Number of class periods represented by a schedule/session."""
    start = int(session.schedule.start_period or 1)
    end = int(session.schedule.end_period or start)
    return max(1, end - start + 1)


def next_attendance_id(day):
    # A random identifier avoids max()+1 collisions across sessions/workers.
    # 96 random bits fit the existing 40-character field and keep the date prefix.
    return f"ATT-{day:%Y%m%d}-{uuid.uuid4().hex[:24]}"


def session_external_id(session):
    if session.external_session_id:
        return session.external_session_id
    subject_code = re.sub(r"[^A-Za-z0-9]+", "", session.schedule.subject.code.upper()) or "SESSION"
    room = re.sub(r"[^A-Za-z0-9]+", "", session.schedule.room.upper()) or "ROOM"
    base = f"SES-{session.date:%Y%m%d}-{subject_code}-{room}"
    candidate = base
    suffix = 1
    while session.__class__.objects.filter(external_session_id=candidate).exclude(pk=session.pk).exists():
        suffix += 1
        candidate = f"{base}-{suffix:02d}"
    session.external_session_id = candidate
    session.save(update_fields=["external_session_id"])
    return candidate


def resolve_session(session_ref):
    """Resolve a stable external session ID or legacy numeric DB ID."""
    if session_ref in (None, ""):
        return None
    text = str(session_ref)
    try:
        return AttendanceSession.objects.select_related("schedule__subject", "schedule__classroom").get(
            external_session_id=text
        )
    except AttendanceSession.DoesNotExist:
        if text.isdigit():
            return AttendanceSession.objects.select_related("schedule__subject", "schedule__classroom").get(id=int(text))
        raise


def attendance_payload(record, session=None, already_checked_in=False):
    session = session or record.session
    status = record.status
    return {
        "attendance_id": record.attendance_id,
        "check_in_time": record.time_in.strftime("%H:%M:%S") if record.time_in else None,
        "late_minutes": record.late_minutes,
        "status": status,
        "attendance_code": record.attendance_code,
        "attendance_label": record.attendance_label,
        "attendance_periods": record.attendance_periods,
        "method": record.method,
        "device_id": record.device_id,
        "already_checked_in": already_checked_in,
    }


@transaction.atomic
def record_attendance_event(
    *,
    session,
    student,
    check_in_at=None,
    confidence=0.0,
    method=METHOD_FACIAL_RECOGNITION,
    device_id="",
    preferred_attendance_id=None,
    require_active=True,
):
    """Create or return the one canonical record for ``session + student``.

    Face recognition, manual recovery, and CSV import all use this function so
    the database remains the only source of truth for timing and duplicates.
    ``check_in_at`` may be a ``datetime`` or ``time``; omitted values use the
    server clock.
    """
    if session is None:
        raise ValueError("An attendance session is required")
    if require_active and session.status != "active":
        raise ValueError("Session is not active")
    if not session_students(session).filter(pk=student.pk).exists():
        raise ValueError("WRONG_CLASS: student is not enrolled in this class")

    check_in_dt = _as_datetime(check_in_at or timezone.now(), session.date)
    check_in_time = check_in_dt.time()
    scheduled_time = get_session_scheduled_time(session)
    timing = calculate_attendance_status(scheduled_time, check_in_time)
    existing = AttendanceRecord.objects.filter(session=session, student=student).first()
    if existing:
        if not existing.attendance_id:
            existing.attendance_id = next_attendance_id(existing.date)
            existing.save(update_fields=["attendance_id"])
        return existing, False, timing

    attendance_id = preferred_attendance_id or next_attendance_id(session.date)
    if AttendanceRecord.objects.filter(attendance_id=attendance_id).exists():
        raise IntegrityError(f"Duplicate attendance_id: {attendance_id}")

    try:
        with transaction.atomic():
            record = AttendanceRecord.objects.create(
                attendance_id=attendance_id,
                session=session,
                student=student,
                date=session.date,
                time_in=check_in_time,
                status=timing["status"],
                notes=timing["attendance_label"],
                confidence=float(confidence or 0),
                scheduled_time=scheduled_time,
                late_minutes=timing["late_minutes"],
                attendance_code=timing["attendance_code"],
                attendance_label=timing["attendance_label"],
                attendance_periods=timing["attendance_periods"],
                method=method or METHOD_FACIAL_RECOGNITION,
                device_id=str(device_id or "")[:80],
            )
    except IntegrityError:
        # Two frames can arrive at the same time. The unique session/student
        # constraint makes the second request a duplicate, not a new event.
        record = AttendanceRecord.objects.get(session=session, student=student)
        return record, False, timing
    from .attendance_archive import archive_attendance_record
    transaction.on_commit(lambda: archive_attendance_record(record), robust=True)
    return record, True, timing


@transaction.atomic
def record_absence_event(*, session, student, device_id='SYSTEM-FINALIZE', preferred_attendance_id=None):
    """Create the durable absent record for a student not scanned in a session."""
    existing = AttendanceRecord.objects.filter(session=session, student=student).first()
    if existing:
        return existing, False
    periods = session_period_count(session)
    record = AttendanceRecord.objects.create(
        attendance_id=preferred_attendance_id or next_attendance_id(session.date),
        session=session,
        student=student,
        date=session.date,
        time_in=None,
        status='absent',
        confidence=0.0,
        scheduled_time=get_session_scheduled_time(session),
        late_minutes=0,
        attendance_code='ABSENT',
        attendance_label='ABSENT',
        attendance_periods=periods,
        method='SYSTEM_FINALIZE',
        device_id=str(device_id or 'SYSTEM-FINALIZE')[:80],
        notes='Absent when the class session was finalized',
    )
    from .attendance_archive import archive_attendance_record
    transaction.on_commit(lambda: archive_attendance_record(record), robust=True)
    return record, True


@transaction.atomic
def finalize_session_attendance(session):
    """Persist ABSENT rows for all roster members who were not scanned."""
    from .models import Student
    existing = set(session.session_records.values_list('student_id', flat=True))
    created = 0
    for student in session_students(session).order_by('student_id'):
        if student.id not in existing:
            _, was_created = record_absence_event(session=session, student=student)
            created += int(was_created)
    return created
