"""Durable CSV archive for attendance events.

The database remains the source of truth.  This module mirrors each committed
record into the requested date/subject folder so the school can consume the
history with Excel or another local tool.
"""

from __future__ import annotations

import csv
import re
import os
import tempfile
from pathlib import Path

from django.conf import settings


ARCHIVE_COLUMNS = [
    'attendance_id', 'session_id', 'student_id', 'student_name', 'subject_id',
    'subject_name', 'date', 'scheduled_time', 'check_in_time', 'late_minutes',
    'status', 'attendance_periods', 'method', 'device_id',
]


def _safe_folder(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value or '').strip())
    return value.rstrip('. ') or 'Unknown'


def _session_id(session):
    if not session:
        return ''
    from .attendance_service import session_external_id
    return session_external_id(session)


def row_for_record(record):
    session = record.session
    schedule = session.schedule if session else None
    subject = schedule.subject if schedule else None
    status = record.attendance_code or str(record.status or '').upper()
    return {
        'attendance_id': record.attendance_id or '',
        'session_id': _session_id(session),
        'student_id': record.student.student_id,
        'student_name': record.student.full_name,
        'subject_id': subject.code if subject else '',
        'subject_name': subject.name if subject else '',
        'date': record.date.isoformat(),
        'scheduled_time': record.scheduled_time.strftime('%H:%M:%S') if record.scheduled_time else '',
        'check_in_time': record.time_in.strftime('%H:%M:%S') if record.time_in else '',
        'late_minutes': record.late_minutes,
        'status': status,
        'attendance_periods': '' if record.attendance_periods is None else record.attendance_periods,
        'method': record.method or '',
        'device_id': record.device_id or '',
    }


def archive_attendance_record(record):
    """Append one record idempotently to ``DD_MM_YYYY/subject/attendance.csv``."""
    base = Path(settings.ATTENDANCE_HISTORY_DIR)
    subject_name = record.session.schedule.subject.name if record.session_id else 'Unknown'
    target_dir = base / record.date.strftime('%d_%m_%Y') / _safe_folder(subject_name)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / 'attendance.csv'
    row = row_for_record(record)

    existing_ids = set()
    if target.exists():
        try:
            with target.open('r', encoding='utf-8-sig', newline='') as stream:
                existing_ids = {r.get('attendance_id', '') for r in csv.DictReader(stream)}
        except (OSError, UnicodeError, csv.Error):
            existing_ids = set()
    if row['attendance_id'] and row['attendance_id'] in existing_ids:
        return target

    # Write through a temporary file when creating the archive, preventing a
    # half-written header if the process is interrupted.
    needs_header = not target.exists() or target.stat().st_size == 0
    with target.open('a', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=ARCHIVE_COLUMNS)
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
    return target


def rebuild_attendance_archive(record):
    """Rebuild the affected CSV from committed data after a staff correction."""
    from .models import AttendanceRecord
    folder = _safe_folder(record.session.schedule.subject.name if record.session_id else 'Unknown')
    directory = Path(settings.ATTENDANCE_HISTORY_DIR) / record.date.strftime('%d_%m_%Y') / folder
    directory.mkdir(parents=True, exist_ok=True)
    records = AttendanceRecord.objects.filter(date=record.date).select_related('student', 'session__schedule__subject').order_by('pk')
    rows = [row_for_record(item) for item in records if _safe_folder(
        item.session.schedule.subject.name if item.session_id else 'Unknown') == folder]
    descriptor, temporary = tempfile.mkstemp(prefix='.attendance-', suffix='.csv', dir=directory)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=ARCHIVE_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, directory / 'attendance.csv')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
