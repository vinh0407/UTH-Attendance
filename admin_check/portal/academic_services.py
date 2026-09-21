"""Student registration and transparent, configurable academic review (10-point scale)."""
from decimal import Decimal
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import (AttendanceRecord, CourseOffering, CourseRegistration, Grade, Student,
                     StudentAcademicProfile, TermAssessment)
from .enrollment import student_schedules, schedule_students
from .student_attendance import student_course_attendance




def profile_policy(student):
    profile = StudentAcademicProfile.objects.select_related('policy').filter(student=student).first()
    return profile, profile.policy if profile else None


def final_grade_attempts(student):
    outcomes = {(c['subject_id'],c['semester']):c for c in student_course_attendance(student,timezone.localdate())['courses']}
    return [(g, outcomes.get((g.subject.code,g.semester),{}).get('attendance_outcome') == 'failed')
            for g in Grade.objects.filter(student=student,assessment_type='TOTAL',score__gte=0,score__lte=10).select_related('subject')]


def _passed_subjects(student, pass_score):
    return {g.subject_id for g, failed in final_grade_attempts(student) if not failed and g.score >= pass_score}


@transaction.atomic
def register_course(student, offering_id):
    Student.objects.select_for_update().get(pk=student.pk)
    # A write lock also serializes seat allocation on SQLite (where select_for_update is a no-op).
    if not CourseOffering.objects.filter(pk=offering_id).update(revision=F('revision')+1):
        raise ValueError('Course offering not found. (Không tìm thấy lớp học phần.)')
    offering = CourseOffering.objects.select_related('schedule__subject','schedule__semester').get(pk=offering_id)
    existing = CourseRegistration.objects.filter(student=student,offering=offering).first()
    if existing and existing.status == 'registered':
        return existing
    today=timezone.localdate()
    schedule=offering.schedule
    if not offering.is_open or not offering.opens_on <= today <= offering.closes_on or not schedule.is_active:
        raise ValueError('Outside course registration period. (Ngoài thời gian đăng ký học phần.)')
    if not schedule.semester_id or schedule.semester.ends_on < today:
        raise ValueError('Semester is invalid or already ended. (Học kỳ chưa hợp lệ hoặc đã kết thúc.)')
    current=list(student_schedules(student).filter(semester=schedule.semester).select_related('subject'))
    if any(s.subject_id == schedule.subject_id for s in current):
        raise ValueError('You have already enrolled or registered for this course this semester. (Bạn đã học hoặc đăng ký môn này trong học kỳ.)')
    if schedule_students(schedule).count() >= offering.capacity:
        raise ValueError('Course offering is full. (Lớp học phần đã hết chỗ.)')
    if any(s.day_of_week==schedule.day_of_week and s.start_period<=schedule.end_period and s.end_period>=schedule.start_period for s in current if s.is_active):
        raise ValueError('Course schedule conflicts with an enrolled class. (Học phần trùng lịch với môn đã đăng ký.)')
    _,policy=profile_policy(student)
    pass_score=policy.pass_score if policy else Decimal('5')
    prerequisites=set(offering.prerequisites.values_list('pk',flat=True))
    if prerequisites - _passed_subjects(student,pass_score):
        raise ValueError('Prerequisite courses have not been met. (Bạn chưa đạt các học phần tiên quyết.)')
    credits={s.subject_id:s.subject.credits for s in current}
    if sum(credits.values())+schedule.subject.credits > (policy.max_term_credits if policy else 24):
        raise ValueError('Maximum term credit limit exceeded. (Vượt số tín chỉ tối đa được đăng ký trong kỳ.)')
    if existing:
        existing.status='registered';existing.save(update_fields=['status','updated_at'])
        return existing
    return CourseRegistration.objects.create(student=student,offering=offering)


@transaction.atomic
def cancel_registration(student, registration_id):
    Student.objects.select_for_update().get(pk=student.pk)
    registration=CourseRegistration.objects.select_related('offering__schedule').filter(pk=registration_id,student=student).first()
    if not registration:
        raise ValueError('Registration record not found. (Không tìm thấy đăng ký của bạn.)')
    CourseOffering.objects.filter(pk=registration.offering_id).update(revision=F('revision')+1)
    offering=registration.offering
    if registration.status=='cancelled': return registration
    if not offering.opens_on <= timezone.localdate() <= offering.closes_on or not offering.is_open:
        raise ValueError('Course cancellation period has expired. (Đã hết thời gian hủy đăng ký.)')
    if AttendanceRecord.objects.filter(student=student,session__schedule=offering.schedule).exists():
        raise ValueError('Attendance already recorded for this course. Contact Academic Affairs. (Học phần đã có điểm danh, cần liên hệ phòng đào tạo.)')
    if Grade.objects.filter(student=student,subject=offering.schedule.subject,semester=offering.schedule.semester.code).exists():
        raise ValueError('Grades already recorded for this course. Contact Academic Affairs. (Học phần đã có điểm, cần liên hệ phòng đào tạo.)')
    registration.status='cancelled';registration.save(update_fields=['status','updated_at'])
    return registration


def criterion(key,label,actual,required,passed):
    return {'key':key,'label':label,'actual':actual,'required':required,'status':'missing' if passed is None else 'pass' if passed else 'fail'}


def review_status(criteria):
    if any(c['status']=='fail' for c in criteria): return 'not_eligible'
    if any(c['status']=='missing' for c in criteria): return 'incomplete'
    return 'eligible'


def score_to_scale4_and_letter(score_10):
    """Convert 10-point scale to Letter Grade and 4-point GPA."""
    if score_10 is None:
        return {'letter': None, 'gpa': None, 'rank': None}
    s = float(score_10)
    if s >= 9.0:
        return {'letter': 'A+', 'gpa': 4.0, 'rank': 'Excellent'}
    if s >= 8.5:
        return {'letter': 'A', 'gpa': 3.7, 'rank': 'Very Good'}
    if s >= 8.0:
        return {'letter': 'B+', 'gpa': 3.5, 'rank': 'Good'}
    if s >= 7.0:
        return {'letter': 'B', 'gpa': 3.0, 'rank': 'Above Average'}
    if s >= 6.5:
        return {'letter': 'C+', 'gpa': 2.5, 'rank': 'Average'}
    if s >= 5.5:
        return {'letter': 'C', 'gpa': 2.0, 'rank': 'Pass'}
    if s >= 5.0:
        return {'letter': 'D+', 'gpa': 1.5, 'rank': 'Conditional Pass'}
    if s >= 4.0:
        return {'letter': 'D', 'gpa': 1.0, 'rank': 'Pass'}
    return {'letter': 'F', 'gpa': 0.0, 'rank': 'Poor'}


def academic_classification(gpa_4):
    """Academic classification based on 4-point scale GPA."""
    if gpa_4 is None:
        return 'Unranked'
    g = float(gpa_4)
    if g >= 3.6:
        return 'Excellent'
    if g >= 3.2:
        return 'Very Good'
    if g >= 2.5:
        return 'Good'
    if g >= 2.0:
        return 'Average'
    if g >= 1.0:
        return 'Weak'
    return 'Poor'


def weighted_average(grades):
    credits=sum(g.subject.credits for g in grades)
    return round(float(sum(g.score*g.subject.credits for g in grades)/credits),2) if credits else None


def academic_review(student, semester):
    profile,policy=profile_policy(student)
    if not policy:
        return {'policy':None,'semester':semester,'scholarship':{'status':'unconfigured','criteria':[]},'graduation':{'status':'unconfigured','criteria':[],'earned_credits':0}}
    attempts=final_grade_attempts(student)
    term_attempts=[(g,failed) for g,failed in attempts if g.semester==semester]
    term_grades=[g for g,_ in term_attempts]
    courses=student_course_attendance(student,timezone.localdate())['courses']
    term_courses=[c for c in courses if c['semester']==semester]
    graded_codes={g.subject.code for g in term_grades}
    missing_grades=not term_courses or any(c['subject_id'] not in graded_codes for c in term_courses)
    completed_credits=sum(g.subject.credits for g in term_grades)
    average=weighted_average(term_grades)
    failed_course=any(failed or g.score<policy.pass_score for g,failed in term_attempts) or any(c['attendance_outcome']=='failed' for c in term_courses)
    conduct=TermAssessment.objects.filter(student=student,semester__code=semester).first()
    conduct_score=conduct.conduct_score if conduct else None
    scholarship=[
        criterion('finals','All finals graded in semester','Pending' if missing_grades else 'Completed','Completed',None if missing_grades else True),
        criterion('average','Credit-weighted average (Scale 10)',average,float(policy.min_scholarship_average),None if missing_grades or average is None else average>=float(policy.min_scholarship_average)),
        criterion('credits','Credits with final grade',completed_credits,policy.min_scholarship_credits,None if missing_grades else completed_credits>=policy.min_scholarship_credits),
        criterion('conduct','Conduct score',conduct_score,policy.min_conduct_score,None if conduct_score is None else conduct_score>=policy.min_conduct_score),
        criterion('failures','No failed courses in semester','Failed courses exist' if failed_course else 'No failures recorded','None',False if failed_course else None if missing_grades else True),
    ]
    best={}
    for grade,failed in attempts:
        if not failed and grade.score>=policy.pass_score and (grade.subject_id not in best or grade.score>best[grade.subject_id].score):
            best[grade.subject_id]=grade
    earned=sum(g.subject.credits for g in best.values())
    cumulative=weighted_average(list(best.values()))
    required=list(policy.required_subjects.all())
    missing_required=[s.name for s in required if s.pk not in best]
    graduation=[
        criterion('credits','Cumulative credits earned (no duplicate retakes)',earned,policy.graduation_credits,earned>=policy.graduation_credits),
        criterion('average','Cumulative average of passed courses (Scale 10)',cumulative,float(policy.min_graduation_average),None if cumulative is None else cumulative>=float(policy.min_graduation_average)),
        criterion('required','Required curriculum courses',', '.join(missing_required) if missing_required else 'All required courses completed','Completed',not missing_required),
    ]
    for enabled,field,label in [('require_english','english_certified','English Language Proficiency'),('require_physical_education','physical_education_completed','Physical Education'),('require_defense','defense_completed','National Defense Education'),('require_financial_clearance','financial_clearance','Financial Clearance')]:
        if getattr(policy,enabled):
            value=getattr(profile,field)
            graduation.append(criterion(field,label,'Confirmed' if value else 'Pending' if value is False else None,'Confirmed',value))
    return {'policy':{'name':policy.name,'is_demo':policy.is_demo,'scale':10,'pass_score':float(policy.pass_score),'max_term_credits':policy.max_term_credits},'semester':semester,
            'scholarship':{'status':review_status(scholarship),'criteria':scholarship,'average':average,'credits':completed_credits},
            'graduation':{'status':review_status(graduation),'criteria':graduation,'earned_credits':earned,'required_credits':policy.graduation_credits,'average':cumulative}}
