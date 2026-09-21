"""Read-only weekly timetable that includes concrete session overrides."""
import datetime as dt

from .faculty import teacher_details
from .models import AttendanceSession
from .enrollment import student_schedules


def weekly_timetable(student, schedules, today):
    start = today - dt.timedelta(days=today.weekday())
    end = start + dt.timedelta(days=6)
    sessions = AttendanceSession.objects.filter(
        schedule__in=student_schedules(student), date__range=(start, end),
    ).select_related('schedule__subject', 'schedule__classroom').distinct()
    by_key = {(session.schedule_id, session.date): session for session in sessions}
    entries = {(schedule.pk, start + dt.timedelta(days=schedule.day_of_week)): schedule for schedule in schedules}
    entries.update({key: session.schedule for key, session in by_key.items()})
    result = []
    for (schedule_id, day), schedule in entries.items():
        session = by_key.get((schedule_id, day))
        result.append({
            'schedule_id': schedule_id, 'date': day.isoformat(), 'day_of_week': day.weekday(),
            'subject_id': schedule.subject.code, 'subject_name': schedule.subject.name,
            'teacher': schedule.subject.teacher, 'teacher_contact': teacher_details(schedule.subject), 'class_id': schedule.classroom.class_id,
            'classroom': schedule.classroom.name, 'room': schedule.room,
            'start_period': schedule.start_period, 'end_period': schedule.end_period,
            'time_range': schedule.get_time_range(),
            'session_status': session.status if session else 'scheduled',
            'postponed_to': session.postponed_to.isoformat() if session and session.postponed_to else None,
            'postponed_reason': session.postponed_reason if session else '',
        })
    return sorted(result, key=lambda item: (item['date'], item['start_period'], item['subject_id']))
