from django.urls import path
from . import views
from . import extra_views
from . import recognition_views
from . import review_views
from . import academic_views

app_name = 'portal'

urlpatterns = [
    # Main pages
    path('', views.home, name='home'),
    path('student-portal/', views.student_portal, name='student_portal'),
    path('student-portal/<path:path>', views.student_portal_asset, name='student_portal_asset'),
    path('kiosk/', views.attendance_kiosk, name='attendance_kiosk'),
    path('kiosk/<path:path>', views.attendance_kiosk_asset, name='attendance_kiosk_asset'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('register/', views.register_face, name='register'),
    path('static/<path:path>', views.static_asset, name='static_asset'),

    # Thoi khoa bieu va Diem danh theo buoi
    path('schedule/', views.schedule_view, name='schedule'),
    path('session/start/<int:schedule_id>/', views.start_attendance_session, name='start_session'),
    path('session/<int:session_id>/', views.attendance_session, name='attendance_session'),
    path('session/<int:session_id>/end/', views.end_attendance_session, name='end_session'),
    path('api/session/<int:session_id>/finalize/', views.api_finalize_session, name='api_finalize_session'),
    path('api/session/<int:session_id>/review/', review_views.report, name='api_session_review'),
    path('api/session/<int:session_id>/review/<int:student_id>/', review_views.correct, name='api_correct_attendance'),

    # API Endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/record-attendance/', views.api_record_attendance, name='api_record_attendance'),
    path('api/students/', views.api_students, name='api_students'),
    path('api/attendance/today/', views.api_attendance_today, name='api_attendance_today'),

    # Face Recognition APIs
    path('api/face-engine/status/', views.api_face_engine_status, name='api_face_engine_status'),
    path('api/register-face/', views.api_register_face, name='api_register_face'),
    path('api/recognize-face/', recognition_views.recognize, name='api_recognize_face'),
    path('api/registered-faces/', views.api_registered_faces, name='api_registered_faces'),

    # Schedule & Session APIs
    path('api/schedules/', views.api_schedules, name='api_schedules'),
    path('api/sessions/today/', views.api_sessions_today, name='api_sessions_today'),
    path('api/session/<int:session_id>/attendance/', views.api_session_attendance, name='api_session_attendance'),
    path('api/session/<int:session_id>/roster/', views.api_session_roster, name='api_session_roster'),
    path('api/session/<int:session_id>/export.csv', views.api_export_session_csv, name='api_export_session_csv'),
    path('api/attendance/import.csv', views.api_import_attendance_csv, name='api_import_attendance_csv'),
    path('api/session/record/', views.api_record_session_attendance, name='api_record_session_attendance'),
    path('api/session/create/', views.api_create_session, name='api_create_session'),
    path('api/classes/create/', views.api_create_class, name='api_create_class'),
    path('api/subjects/create/', views.api_create_subject, name='api_create_subject'),
    path('api/schedules/create/', views.api_create_schedule, name='api_create_schedule'),
    path('api/session/<int:session_id>/postpone/', views.api_postpone_session, name='api_postpone_session'),
    path('api/export/all.csv', views.api_export_all_csv, name='api_export_all_csv'),

    # Authenticated student portal APIs
    path('api/student/login/', views.api_student_login, name='api_student_login'),
    path('api/student/logout/', views.api_student_logout, name='api_student_logout'),
    path('api/student/me/change-password/', views.api_student_change_password, name='api_student_change_password'),
    path('api/student/me/dashboard/', views.api_student_dashboard, name='api_student_dashboard'),
    path('api/student/me/profile/', views.api_student_profile, name='api_student_profile'),
    path('api/student/me/schedule/today/', views.api_student_schedule_today, name='api_student_schedule_today'),
    path('api/student/me/attendance/', views.api_student_attendance, name='api_student_attendance'),
    path('api/student/me/attendance/summary/', views.api_student_attendance_summary, name='api_student_attendance_summary'),
    path('api/student/me/grades/', views.api_student_grades, name='api_student_grades'),
    path('api/student/me/subjects/summary/', views.api_student_subject_summary, name='api_student_subject_summary'),
    path('api/student/me/leave-requests/', views.api_student_leave_requests, name='api_student_leave_requests'),
    path('api/student/me/leave-requests/create/', views.api_student_create_leave_request, name='api_student_create_leave_request'),

    path('api/student/me/academics/', academic_views.academics),
    path('api/student/me/registrations/', academic_views.registrations),
    path('api/student/me/registrations/<int:registration_id>/cancel/', academic_views.cancel),
    path('api/student/me/classmates/', academic_views.classmates),

    # Admin APIs
    path('api/admin/grades/update/', views.api_admin_update_grade, name='api_admin_update_grade'),
    path('api/admin/grades/template.csv', views.api_admin_grade_template_csv, name='api_admin_grade_template_csv'),
    path('api/admin/grades/import.csv', views.api_admin_import_grades_csv, name='api_admin_import_grades_csv'),
    path('api/admin/leave-requests/', views.api_admin_leave_requests, name='api_admin_leave_requests'),
    path('api/admin/leave-requests/<int:request_id>/review/', views.api_admin_review_leave_request, name='api_admin_review_leave_request'),
    path('api/delete-student/<int:student_id>/', views.api_delete_student, name='api_delete_student'),
    path('api/update-student/<int:student_id>/', views.api_update_student, name='api_update_student'),

    # === TEST & SYNC Utilities ===
    # Dong bo face_database.pkl -> Django Student DB
    path('api/sync-faces/', extra_views.api_sync_faces, name='api_sync_faces'),
    # Test nhan dien anh va ghi diem danh (POST multipart voi field 'image')
    path('api/test-image/', extra_views.api_test_image, name='api_test_image'),
]
