"""Staff corrections retain timing rules and a before/after audit trail."""
import datetime as dt

from .enrollment import session_students
from django.db import transaction

from .attendance_archive import rebuild_attendance_archive
from .attendance_service import calculate_attendance_status, get_session_scheduled_time, next_attendance_id, session_period_count
from .models import AttendanceAuditLog, AttendanceRecord, AttendanceSession


def snapshot(record):
    if record is None:
        return {}
    return {key: getattr(record, key) for key in (
        'status', 'attendance_code', 'attendance_label', 'attendance_periods', 'late_minutes', 'method', 'device_id', 'notes', 'confidence',
    )} | {'check_in_time': record.time_in.isoformat() if record.time_in else None,
          'check_out_time': record.time_out.isoformat() if record.time_out else None}


@transaction.atomic
def correct_attendance(*, session, student, user, outcome, check_in_time, reason):
    if not user.is_active or not user.is_staff:
        raise ValueError('Staff authentication required')
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        raise ValueError('A reason of 1–500 characters is required')
    session = AttendanceSession.objects.select_for_update().select_related('schedule').get(pk=session.pk)
    if session.status in ('cancelled', 'postponed'):
        raise ValueError('Cancelled or postponed sessions cannot be reviewed')
    if not session_students(session).filter(pk=student.pk).exists():
        raise ValueError('Student is not enrolled in this class')
    scheduled = get_session_scheduled_time(session)
    if outcome == 'checked_in':
        try:
            check_in = dt.time.fromisoformat(check_in_time)
        except (ValueError, TypeError):
            raise ValueError('Enter a valid local check-in time')
        if check_in.tzinfo is not None:
            raise ValueError('Use local time without a timezone')
        timing = calculate_attendance_status(scheduled, check_in)
    elif outcome == 'absent':
        check_in = None
        timing = {'status': 'absent', 'attendance_code': 'ABSENT', 'attendance_label': 'ABSENT',
                  'attendance_periods': session_period_count(session), 'late_minutes': 0}
    else:
        raise ValueError('Choose checked_in or absent')
    record = AttendanceRecord.objects.filter(session=session, student=student).first()
    before = snapshot(record)
    if record is None:
        record = AttendanceRecord(session=session, student=student, date=session.date,
                                  attendance_id=next_attendance_id(session.date))
    for key, value in timing.items():
        setattr(record, key, value)
    record.time_in = check_in
    if outcome == 'absent':
        record.time_out = None
    record.scheduled_time = scheduled
    record.method = 'MANUAL_REVIEW'
    record.notes = reason.strip()
    record.device_id = 'STAFF-REVIEW'
    record.confidence = 0
    record.save()
    after = snapshot(record)
    if before != after:
        AttendanceAuditLog.objects.create(record=record, changed_by=user, reason=reason.strip(), before=before, after=after)
    transaction.on_commit(lambda: rebuild_attendance_archive(record), robust=True)
    return record
