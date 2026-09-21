"""Server-side multi-frame confirmation. Not an anti-spoofing/liveness model."""
from .enrollment import session_students
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .attendance_service import attendance_payload, record_attendance_event
from .models import AttendanceSession, RecognitionWindow, Student


@transaction.atomic
def process_recognition(session, results, device_id, frame_hash):
    # All requests for the session serialize on PostgreSQL. SQLite serializes
    # writes; a lock conflict must be retried by the caller, never counted twice.
    session = AttendanceSession.objects.select_for_update().select_related(
        'schedule__classroom', 'schedule__subject').get(pk=session.pk)
    now = timezone.now()
    if session.status != 'active' or session.date != timezone.localdate(now):
        raise ValueError('An active session for today is required')
    windows = RecognitionWindow.objects.filter(session=session, device_id=device_id)
    faces = [{**item, 'student_id': '', 'status': 'unknown', 'is_new_attendance': False} for item in results]
    if len(faces) != 1:
        windows.delete()
        return faces, None
    face = faces[0]
    if face.get('name') == 'Unknown' or not face.get('quality', {}).get('ok', False):
        windows.delete()
        return faces, None
    identity = face['name']
    student = Student.objects.filter(student_id=identity).first()
    if student is None:
        # Legacy name-based embeddings are accepted only for an unambiguous name.
        candidates = list(Student.objects.filter(full_name__iexact=identity)[:2])
        student = candidates[0] if len(candidates) == 1 else None
    if student is None:
        windows.delete()
        face['name'] = 'Unknown'
        return faces, None
    face.update(name=student.full_name, student_id=student.student_id, class_name=student.class_name)
    if not session_students(session).filter(pk=student.pk).exists():
        windows.delete()
        face.update(status='wrong_class', attendance_code='WRONG_CLASS', attendance_label='WRONG CLASS')
        return faces, None
    existing = session.session_records.filter(student=student).first()
    if existing is not None:
        face.update(attendance_payload(existing, already_checked_in=True), time_in=existing.time_in.isoformat() if existing.time_in else None)
        return faces, (student, existing, False)
    window = windows.first()
    if window is None or window.student_id != student.pk or (now - window.first_seen).total_seconds() > settings.FACE_CONFIRMATION_WINDOW_SECONDS:
        windows.delete()
        window = RecognitionWindow.objects.create(session=session, device_id=device_id, student=student,
                                                  first_seen=now, last_seen=now, frame_hashes=[frame_hash])
    elif frame_hash not in window.frame_hashes and (now - window.last_seen).total_seconds() >= settings.FACE_CONFIRMATION_MIN_INTERVAL_SECONDS:
        window.frame_hashes = [*window.frame_hashes, frame_hash]
        window.last_seen = now
        window.save(update_fields=['frame_hashes', 'last_seen'])
    count = len(window.frame_hashes)
    face.update(status='verifying', verification={'hits': count, 'required': settings.FACE_CONFIRMATION_FRAMES})
    if count < settings.FACE_CONFIRMATION_FRAMES:
        return faces, None
    record, created, _ = record_attendance_event(
        session=session, student=student, check_in_at=window.first_seen,
        confidence=face['confidence'] / 100., device_id=device_id,
    )
    windows.delete()
    face.update(attendance_payload(record, already_checked_in=not created),
                is_new_attendance=created, time_in=record.time_in.isoformat())
    return faces, (student, record, created)
