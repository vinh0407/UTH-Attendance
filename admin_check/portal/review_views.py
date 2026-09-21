import json

from .enrollment import session_students
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from .attendance_review import correct_attendance, snapshot
from .models import AttendanceSession
from .views import admin_api_required


@admin_api_required
@require_POST
def correct(request, session_id, student_id):
    session = get_object_or_404(AttendanceSession, pk=session_id)
    student = get_object_or_404(session_students(session), pk=student_id)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('Expected a JSON object')
        record = correct_attendance(session=session, student=student, user=request.user,
                                    outcome=data.get('outcome'), check_in_time=data.get('check_in_time'),
                                    reason=data.get('reason'))
    except (ValueError, TypeError) as error:
        return JsonResponse({'success': False, 'error': str(error)}, status=400)
    return JsonResponse({'success': True, 'data': snapshot(record)})


@admin_api_required
@require_GET
def report(request, session_id):
    session = get_object_or_404(AttendanceSession.objects.select_related('schedule__classroom'), pk=session_id)
    records = {record.student_id: record for record in session.session_records.prefetch_related('audit_logs__changed_by')}
    students = []
    for student in session_students(session):
        record = records.get(student.pk)
        students.append({
            'id': student.pk, 'student_id': student.student_id, 'name': student.full_name,
            'record': snapshot(record),
            'similarity': round(record.confidence * 100, 1) if record and record.method == 'FACIAL_RECOGNITION' else None,
            'audit': [{
                'by': log.changed_by.get_username() if log.changed_by else 'Deleted staff account',
                'at': log.changed_at.isoformat(), 'reason': log.reason,
                'before': log.before, 'after': log.after,
            } for log in record.audit_logs.all()] if record else [],
        })
    response = JsonResponse({'success': True, 'data': {
        'status': session.status, 'students': students,
        'summary': {'total': len(students), 'checked_in': sum(
            1 for student in students if student['record'].get('status') in ('present', 'late'))},
    }})
    response['Cache-Control'] = 'private, no-store'
    return response
