import json
from django.db import OperationalError, IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from .models import AcademicTerm, ClassRoom, CourseOffering, CourseRegistration, Student
from .views import student_api_required
from .enrollment import student_schedules, schedule_students
from .academic_services import academic_review, register_course, cancel_registration
from .faculty import teacher_details


def private_json(data, status=200):
    response=JsonResponse({'success':True,'data':data},status=status)
    response['Cache-Control']='private, no-store'
    return response


def student_classes(student):
    return ClassRoom.objects.filter(Q(students=student) | Q(schedule__offering__registrations__student=student,schedule__offering__registrations__status='registered')).distinct()


@student_api_required
@require_GET
def academics(request):
    student=request.portal_student
    today=timezone.localdate()
    terms=list(AcademicTerm.objects.all())
    selected=request.GET.get('semester')
    if selected is None:
        current=next((t for t in terms if t.starts_on<=today<=t.ends_on),terms[0] if terms else None)
        selected=current.code if current else ''
    if selected and not any(t.code==selected for t in terms):
        return JsonResponse({'success':False,'error':'Invalid semester.'},status=400)
    enrolled=list(student_schedules(student).select_related('subject','semester'))
    enrolled_ids={s.pk for s in enrolled}
    credit_groups={}
    for schedule in enrolled:
        if schedule.semester_id:
            credit_groups.setdefault(schedule.semester.code,{})[schedule.subject_id]=schedule.subject.credits
    credits_by_semester={code:sum(subjects.values()) for code,subjects in credit_groups.items()}
    registered={(r.offering_id):r for r in CourseRegistration.objects.filter(student=student,status='registered')}
    offerings=[]
    for offering in CourseOffering.objects.select_related('schedule__subject','schedule__classroom','schedule__semester').prefetch_related('prerequisites').filter(schedule__semester__isnull=False).order_by('-schedule__semester__starts_on','schedule__subject__code')[:200]:
        schedule=offering.schedule
        registration=registered.get(offering.pk)
        seats=max(0,offering.capacity-schedule_students(schedule).count())
        open_now=offering.is_open and schedule.is_active and offering.opens_on<=today<=offering.closes_on and schedule.semester.ends_on>=today
        offerings.append({'id':offering.pk,'subject_id':schedule.subject.code,'subject_name':schedule.subject.name,'credits':schedule.subject.credits,
            'semester':schedule.semester.code,'semester_name':schedule.semester.name,'class_name':schedule.classroom.name,'class_code':schedule.classroom.class_id,
            'day_of_week':schedule.day_of_week,'start_period':schedule.start_period,'end_period':schedule.end_period,'time_range':schedule.get_time_range(),'room':schedule.room,
            'capacity':offering.capacity,'seats_left':seats,'opens_on':str(offering.opens_on),'closes_on':str(offering.closes_on),'is_open':open_now,
            'registered':schedule.pk in enrolled_ids,'registration_id':registration.pk if registration else None,
            'teacher_contact':teacher_details(schedule.subject),'prerequisites':[s.name for s in offering.prerequisites.all()]})
    review=academic_review(student,selected)
    return private_json({'semesters':[{'code':t.code,'name':t.name} for t in terms], 'selected_semester':selected,
        'offerings':offerings,'review':review,'classes':list(student_classes(student).values('id','class_id','name')),
        'enrolled_credits':credits_by_semester.get(selected,0),'enrolled_credits_by_semester':credits_by_semester})


@student_api_required
@require_POST
def registrations(request):
    try:
        payload=json.loads(request.body)
        if not isinstance(payload,dict) or isinstance(payload.get('offering_id'),bool): raise ValueError('Invalid registration payload.')
        registration=register_course(request.portal_student,int(payload.get('offering_id')))
    except (ValueError,TypeError) as error:
        return JsonResponse({'success':False,'error':str(error) or 'Invalid registration request.'},status=400)
    except (OperationalError,IntegrityError):
        return JsonResponse({'success':False,'error':'Course offering is currently being updated. Please try again.'},status=409)
    return private_json({'id':registration.pk,'status':registration.status},status=201)


@student_api_required
@require_POST
def cancel(request, registration_id):
    try:
        registration=cancel_registration(request.portal_student,registration_id)
    except ValueError as error:
        return JsonResponse({'success':False,'error':str(error)},status=400)
    except (OperationalError,IntegrityError):
        return JsonResponse({'success':False,'error':'Course offering is currently being updated. Please try again.'},status=409)
    return private_json({'id':registration.pk,'status':registration.status})


@student_api_required
@require_GET
def classmates(request):
    try:
        class_id=int(request.GET.get('class_id','0'))
        page=max(1,int(request.GET.get('page','1')))
    except ValueError:
        return JsonResponse({'success':False,'error':'Invalid class ID or page number.'},status=400)
    classroom=student_classes(request.portal_student).filter(pk=class_id).first()
    if classroom is None:
        return JsonResponse({'success':False,'error':'You can only view classmates for classes you are currently enrolled in.'},status=403)
    students=Student.objects.filter(Q(classrooms=classroom) | Q(course_registrations__offering__schedule__classroom=classroom,course_registrations__status='registered')).distinct()
    query=request.GET.get('q','').strip()[:100]
    if query: students=students.filter(Q(full_name__icontains=query)|Q(student_id__icontains=query))
    count=students.count()
    rows=[{'student_id':s.student_id,'full_name':s.full_name,'class_name':s.class_name or classroom.class_id} for s in students.order_by('student_id')[(page-1)*30:page*30]]
    return private_json({'class_name':classroom.name,'students':rows,'total':count,'page':page,'has_next':page*30<count})
