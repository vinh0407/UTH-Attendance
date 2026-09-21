"""Enrollment shared by schedules, registration, face recognition and attendance."""
from django.db.models import Q
from .models import Schedule, Student


def student_schedules(student):
    return Schedule.objects.filter(Q(classroom__students=student) | Q(offering__registrations__student=student, offering__registrations__status='registered')).distinct()


def schedule_students(schedule):
    return Student.objects.filter(Q(classrooms=schedule.classroom_id) | Q(course_registrations__offering__schedule=schedule, course_registrations__status='registered')).distinct()


def session_students(session):
    return schedule_students(session.schedule)
