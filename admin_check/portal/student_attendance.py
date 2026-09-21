"""Authoritative per-course absence allowance, derived from finalized sessions.

No grade is overwritten: corrected attendance immediately recomputes the outcome.
Legacy schedules remain explicitly unassigned, never guessed into a semester.
"""
from .faculty import teacher_details
from .models import AttendanceRecord, Grade, Schedule
from .enrollment import student_schedules

ABSENCE_LIMIT = 3


def student_course_attendance(student, today):
    schedules = list(student_schedules(student).select_related('subject', 'semester').distinct())
    records = list(AttendanceRecord.objects.filter(student=student, session__isnull=False).select_related('session__schedule__subject', 'session__schedule__semester'))
    grades = list(Grade.objects.filter(student=student).select_related('subject'))
    courses, terms = {}, {}

    def add_course(subject, semester='', term=None):
        key = (semester, subject.pk)
        terms.setdefault(semester, {'code': semester, 'name': term.name if term else semester or 'Chưa phân học kỳ', 'starts_on': str(term.starts_on) if term else '', 'ends_on': str(term.ends_on) if term else ''})
        return courses.setdefault(key, {
            'subject_id': subject.code, 'subject_name': subject.name, 'teacher': subject.teacher,
            'teacher_contact': teacher_details(subject), 'credits': subject.credits,
            'semester': semester, 'semester_name': terms[semester]['name'],
            'absence_limit': ABSENCE_LIMIT, 'absent_sessions': 0, 'counted_sessions': 0,
            'excused_sessions': 0,
            'absent_periods': 0, 'late_periods': 0, 'late_events': 0, 'grades': [],
        })

    for schedule in schedules:
        add_course(schedule.subject, schedule.semester.code if schedule.semester else '', schedule.semester)
    for record in records:
        schedule = record.session.schedule
        item = add_course(schedule.subject, schedule.semester.code if schedule.semester else '', schedule.semester)
        if record.session.status != 'completed':
            continue
        item['counted_sessions'] += 1
        if record.status == 'absent':
            item['absent_sessions'] += 1
            item['absent_periods'] += record.attendance_periods or 0
        elif record.status == 'late':
            item['late_events'] += 1
            item['late_periods'] += record.attendance_periods or 0
        elif record.status == 'excused':
            item['excused_sessions'] += 1
    for grade in grades:
        item = add_course(grade.subject, grade.semester)
        item['grades'].append({'semester': grade.semester, 'assessment_type': grade.assessment_type, 'score': float(grade.score)})

    notifications = []
    for item in courses.values():
        absent = item['absent_sessions']
        item['remaining_absences'] = max(0, ABSENCE_LIMIT - absent)
        outcome = 'failed' if absent > ABSENCE_LIMIT else 'warning' if absent == ABSENCE_LIMIT else 'eligible'
        if not item['semester']:
            outcome = 'unassigned'
            item['remaining_absences'] = None
        item['attendance_outcome'] = outcome
        item['exam_prohibited'] = outcome == 'failed'
        item['exam_status'] = 'FAILED_ATTENDANCE' if outcome == 'failed' else 'ELIGIBLE'

        if outcome == 'failed':
            danger_level = 'barred'
            alert_badge = {'text': 'BARRED FROM EXAM', 'color': 'danger', 'detail': f"Missed {absent} sessions (exceeded {ABSENCE_LIMIT} allowed absences)"}
        elif outcome == 'warning':
            danger_level = 'warning'
            alert_badge = {'text': 'EXAM BAR WARNING', 'color': 'warning', 'detail': f"Missed {absent}/{ABSENCE_LIMIT} allowed absences. One more absence will lead to exam barring!"}
        else:
            danger_level = 'safe'
            alert_badge = {'text': 'Eligible for Exam', 'color': 'success', 'detail': f"Missed {absent}/{ABSENCE_LIMIT} allowed absences"}

        item['danger_level'] = danger_level
        item['alert_badge'] = alert_badge

        if outcome in ('warning', 'failed'):
            notifications.append({
                'id': f"{item['semester']}:{item['subject_id']}:{outcome}",
                'semester': item['semester'], 'subject_id': item['subject_id'],
                'subject_name': item['subject_name'], 'severity': outcome,
                'message': (f"You have missed {absent} sessions in {item['subject_name']}. You are barred from taking the exam because absences exceeded {ABSENCE_LIMIT}."
                            if outcome == 'failed' else f"WARNING: You have missed {absent}/{ABSENCE_LIMIT} allowed absences in {item['subject_name']}. One more absence will result in exam barring!"),
            })
    ordered_terms = sorted(terms.values(), key=lambda t: (t['starts_on'], t['code']), reverse=True)
    current = next((t for t in ordered_terms if t['starts_on'] <= str(today) <= t['ends_on']), None)
    previous = next((t for t in ordered_terms if t['starts_on'] and t['starts_on'] <= str(today)), None)
    selected = (current or previous or (ordered_terms[0] if ordered_terms else {})).get('code', '')
    return {
        'courses': sorted(courses.values(), key=lambda c: (c['semester'], c['subject_id'])),
        'semesters': ordered_terms, 'selected_semester': selected, 'notifications': notifications,
    }
