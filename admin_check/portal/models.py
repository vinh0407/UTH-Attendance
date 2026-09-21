from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password, check_password


class Student(models.Model):
    """Model lưu thông tin sinh viên"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    student_id = models.CharField(max_length=20, unique=True, verbose_name="Student ID")
    full_name = models.CharField(max_length=100, verbose_name="Full name")
    email = models.EmailField(blank=True, verbose_name="Email")
    class_name = models.CharField(max_length=50, blank=True, verbose_name="Class")
    password_hash = models.CharField(max_length=128, blank=True, default='', verbose_name="Password hash")
    face_encoding = models.BinaryField(null=True, blank=True, verbose_name="Face encoding data")
    face_image = models.ImageField(upload_to='faces/', null=True, blank=True, verbose_name="Face image")
    is_registered = models.BooleanField(default=False, verbose_name="Face registered")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student"
        verbose_name_plural = "Students"
        ordering = ['student_id']

    def __str__(self):
        return f"{self.student_id} - {self.full_name}"

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)
        if self.user:
            self.user.set_password(raw_password)
            self.user.save(update_fields=['password'])

    def check_password(self, raw_password):
        if not self.password_hash:
            if self.user and self.user.has_usable_password():
                return self.user.check_password(raw_password)
            return False
        return check_password(raw_password, self.password_hash)


class Subject(models.Model):
    """Model lưu thông tin môn học"""
    code = models.CharField(max_length=20, unique=True, verbose_name="Subject code")
    name = models.CharField(max_length=100, verbose_name="Subject name")
    teacher = models.CharField(max_length=100, blank=True, verbose_name="Teacher")
    teacher_email = models.EmailField(blank=True)
    teacher_phone = models.CharField(max_length=30, blank=True)
    teacher_department = models.CharField(max_length=150, blank=True)
    teacher_office = models.CharField(max_length=100, blank=True)
    teacher_bio = models.TextField(blank=True)
    credits = models.IntegerField(default=3, verbose_name="Credits")
    weight_cc = models.DecimalField(max_digits=4, decimal_places=2, default=0.10, verbose_name="Attendance Weight")
    weight_gk = models.DecimalField(max_digits=4, decimal_places=2, default=0.30, verbose_name="Midterm Weight")
    weight_ck = models.DecimalField(max_digits=4, decimal_places=2, default=0.60, verbose_name="Final Weight")
    bonus_method = models.CharField(max_length=20, default='DIRECT', verbose_name="Bonus Method")
    
    class Meta:
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class ClassRoom(models.Model):
    """Model lưu thông tin lớp học"""
    class_id = models.CharField(max_length=20, unique=True, verbose_name="Class ID")
    name = models.CharField(max_length=100, verbose_name="Class name")
    department = models.CharField(max_length=100, blank=True, verbose_name="Department")
    students = models.ManyToManyField(Student, related_name='classrooms', blank=True, verbose_name="Students")
    
    class Meta:
        verbose_name = "Class"
        verbose_name_plural = "Classes"
    
    def __str__(self):
        return f"{self.class_id} - {self.name}"


class AcademicTerm(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    starts_on = models.DateField()
    ends_on = models.DateField()

    class Meta:
        ordering = ['-starts_on', 'code']
        constraints = [models.CheckConstraint(condition=models.Q(ends_on__gte=models.F('starts_on')), name='valid_academic_term_dates')]

    def __str__(self):
        return self.name


class Schedule(models.Model):
    """Model lưu thời khóa biểu - Buổi học"""
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    PERIOD_CHOICES = [
        (1, 'Period 1 (7:00 - 7:50)'),
        (2, 'Period 2 (7:50 - 8:40)'),
        (3, 'Period 3 (8:50 - 9:40)'),
        (4, 'Period 4 (9:40 - 10:30)'),
        (5, 'Period 5 (10:40 - 11:30)'),
        (6, 'Period 6 (13:00 - 13:50)'),
        (7, 'Period 7 (13:50 - 14:40)'),
        (8, 'Period 8 (14:50 - 15:40)'),
        (9, 'Period 9 (15:40 - 16:30)'),
        (10, 'Period 10 (16:40 - 17:30)'),
    ]
    
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, verbose_name="Subject")
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, verbose_name="Class")
    day_of_week = models.IntegerField(choices=DAY_CHOICES, verbose_name="Day")
    start_period = models.IntegerField(choices=PERIOD_CHOICES, verbose_name="Start period")
    end_period = models.IntegerField(choices=PERIOD_CHOICES, verbose_name="End period")
    room = models.CharField(max_length=50, blank=True, verbose_name="Room")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    semester = models.ForeignKey(AcademicTerm, null=True, blank=True, on_delete=models.PROTECT, verbose_name='Semester')
    
    class Meta:
        verbose_name = "Schedule"
        verbose_name_plural = "Schedules"
        ordering = ['day_of_week', 'start_period']
    
    def __str__(self):
        return f"{self.subject.name} - {self.classroom.name} - {self.get_day_of_week_display()}"
    
    def get_time_range(self):
        """Trả về khoảng thời gian của buổi học"""
        period_times = {
            1: ('7:00', '7:50'),
            2: ('7:50', '8:40'),
            3: ('8:50', '9:40'),
            4: ('9:40', '10:30'),
            5: ('10:40', '11:30'),
            6: ('13:00', '13:50'),
            7: ('13:50', '14:40'),
            8: ('14:50', '15:40'),
            9: ('15:40', '16:30'),
            10: ('16:40', '17:30'),
        }
        start = period_times.get(self.start_period, ('', ''))[0]
        end = period_times.get(self.end_period, ('', ''))[1]
        return f"{start} - {end}"


class AttendanceSession(models.Model):
    """Model lưu buổi điểm danh - Mỗi buổi học cụ thể có 1 ID riêng"""
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('postponed', 'Postponed'),
    ]
    
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, verbose_name="Schedule")
    external_session_id = models.CharField(max_length=80, unique=True, null=True, blank=True, verbose_name="External session ID")
    date = models.DateField(verbose_name="Class date")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled', verbose_name="Status")
    start_time = models.DateTimeField(null=True, blank=True, verbose_name="Attendance start time")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="Attendance end time")
    notes = models.TextField(blank=True, verbose_name="Notes")
    postponed_to = models.DateField(null=True, blank=True, verbose_name="Postponed to")
    postponed_reason = models.CharField(max_length=240, blank=True, verbose_name="Postponement reason")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Attendance session"
        verbose_name_plural = "Attendance sessions"
        ordering = ['-date', '-created_at']
        unique_together = ['schedule', 'date']
    
    def __str__(self):
        return f"#{self.id} - {self.schedule.subject.name} - {self.schedule.classroom.name} - {self.date}"
    
    def get_present_count(self):
        return self.session_records.filter(status='present').count()
    
    def get_total_students(self):
        from .enrollment import session_students
        return session_students(self).count()


class AttendanceRecord(models.Model):
    """Model lưu lịch sử điểm danh - Liên kết với buổi điểm danh"""
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('late', 'Late'),
        ('absent', 'Absent'),
        ('excused', 'Excused'),
    ]

    attendance_id = models.CharField(max_length=40, unique=True, null=True, blank=True, verbose_name="Attendance ID")
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='session_records', null=True, blank=True, verbose_name="Attendance session")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(verbose_name="Date")
    time_in = models.TimeField(null=True, blank=True, verbose_name="Check-in time")
    time_out = models.TimeField(null=True, blank=True, verbose_name="Check-out time")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='present', verbose_name="Status")
    confidence = models.FloatField(default=0.0, verbose_name="Recognition confidence (%)")
    camera_id = models.CharField(max_length=50, blank=True, verbose_name="Camera ID")
    scheduled_time = models.TimeField(null=True, blank=True, verbose_name="Scheduled time")
    late_minutes = models.PositiveIntegerField(default=0, verbose_name="Late minutes")
    attendance_code = models.CharField(max_length=40, blank=True, verbose_name="Status code")
    attendance_label = models.CharField(max_length=80, blank=True, verbose_name="Status label")
    attendance_periods = models.PositiveIntegerField(null=True, blank=True, verbose_name="Counted periods")
    method = models.CharField(max_length=40, default='FACIAL_RECOGNITION', verbose_name="Method")
    device_id = models.CharField(max_length=80, blank=True, verbose_name="Device")
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Attendance record"
        verbose_name_plural = "Attendance records"
        ordering = ['-date', '-time_in']
        constraints = [
            models.UniqueConstraint(fields=['session', 'student'], name='uniq_attendance_session_student'),
        ]

    def __str__(self):
        session_info = f" - Session #{self.session.id}" if self.session else ""
        return f"{self.student.full_name} - {self.date}{session_info} - {self.get_status_display()}"


class AttendanceAuditLog(models.Model):
    record = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE, related_name='audit_logs')
    changed_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    changed_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=500)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)

    class Meta:
        ordering = ['-changed_at', '-pk']


class RecognitionWindow(models.Model):
    """Short-lived confirmation state shared across Django workers."""
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE)
    device_id = models.CharField(max_length=80)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    frame_hashes = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'device_id'], name='uniq_recognition_device_session')]


class Grade(models.Model):
    """Điểm thành phần của sinh viên theo học phần và học kỳ."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='grades')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='grades')
    semester = models.CharField(max_length=30, default='', blank=True)
    assessment_type = models.CharField(max_length=40, default='TOTAL')
    score = models.DecimalField(max_digits=5, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['subject__code', 'assessment_type']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'subject', 'semester', 'assessment_type'],
                name='uniq_grade_student_subject_semester_type',
            ),
        ]

    def __str__(self):
        return f"{self.student.student_id} - {self.subject.code} - {self.assessment_type}: {self.score}"


class GradeAuditLog(models.Model):
    """Lưu lịch sử thay đổi điểm số phục vụ đối soát và khiếu nại."""
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name='audit_logs')
    changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    changed_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=500, blank=True, default='')
    before_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    after_score = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        verbose_name = "Grade audit log"
        verbose_name_plural = "Grade audit logs"
        ordering = ['-changed_at', '-pk']

    def __str__(self):
        return f"{self.grade} -> {self.after_score} ({self.changed_at})"


class LeaveRequest(models.Model):
    """Đơn xin nghỉ phép trực tuyến của sinh viên."""
    STATUS_CHOICES = [
        ('pending', 'Chờ duyệt'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='leave_requests')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='leave_requests', null=True, blank=True)
    session = models.ForeignKey(AttendanceSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='leave_requests')
    date = models.DateField(verbose_name="Ngày xin nghỉ")
    reason = models.TextField(verbose_name="Lý do xin nghỉ")
    evidence_url = models.CharField(max_length=500, blank=True, default='', verbose_name="Minh chứng / Ghi chú giấy tờ")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_leaves')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Leave request"
        verbose_name_plural = "Leave requests"
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return f"{self.student.full_name} - {self.date} ({self.get_status_display()})"


class Camera(models.Model):
    """Model quản lý camera"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('maintenance', 'Maintenance'),
    ]

    camera_id = models.CharField(max_length=50, unique=True, verbose_name="Camera ID")
    name = models.CharField(max_length=100, verbose_name="Camera name")
    location = models.CharField(max_length=200, verbose_name="Location")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP address")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Status")
    last_active = models.DateTimeField(null=True, blank=True, verbose_name="Last active")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Camera"
        verbose_name_plural = "Cameras"

    def __str__(self):
        return f"{self.name} ({self.camera_id})"


class SystemStats(models.Model):
    """Model lưu thống kê hệ thống"""
    date = models.DateField(unique=True, verbose_name="Date")
    total_students = models.IntegerField(default=0, verbose_name="Total students")
    attendance_rate = models.FloatField(default=0.0, verbose_name="Attendance rate (%)")
    avg_scan_time = models.FloatField(default=0.0, verbose_name="Average scan time (s)")
    total_scans = models.IntegerField(default=0, verbose_name="Total scans")

    class Meta:
        verbose_name = "System statistics"
        verbose_name_plural = "System statistics"
        ordering = ['-date']

    def __str__(self):
        return f"Stats - {self.date}"

class AcademicPolicy(models.Model):
    name = models.CharField(max_length=150)
    is_demo = models.BooleanField(default=True)
    pass_score = models.DecimalField(max_digits=4, decimal_places=2, default=5)
    min_scholarship_average = models.DecimalField(max_digits=4, decimal_places=2, default=8)
    min_scholarship_credits = models.PositiveSmallIntegerField(default=12)
    min_conduct_score = models.PositiveSmallIntegerField(default=80)
    graduation_credits = models.PositiveSmallIntegerField(default=120)
    min_graduation_average = models.DecimalField(max_digits=4, decimal_places=2, default=5)
    max_term_credits = models.PositiveSmallIntegerField(default=24)
    required_subjects = models.ManyToManyField(Subject, blank=True)
    require_english = models.BooleanField(default=True)
    require_physical_education = models.BooleanField(default=True)
    require_defense = models.BooleanField(default=True)
    require_financial_clearance = models.BooleanField(default=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(pass_score__gte=0, pass_score__lte=10, min_scholarship_average__gte=0, min_scholarship_average__lte=10, min_graduation_average__gte=0, min_graduation_average__lte=10, min_conduct_score__lte=100), name='valid_academic_policy_scores')]

    def __str__(self):
        return self.name


class StudentAcademicProfile(models.Model):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='academic_profile')
    policy = models.ForeignKey(AcademicPolicy, on_delete=models.PROTECT, null=True, blank=True)
    english_certified = models.BooleanField(null=True, blank=True)
    physical_education_completed = models.BooleanField(null=True, blank=True)
    defense_completed = models.BooleanField(null=True, blank=True)
    financial_clearance = models.BooleanField(null=True, blank=True)

    def __str__(self):
        return str(self.student)


class TermAssessment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    semester = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT)
    conduct_score = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'semester'], name='unique_student_term_assessment'), models.CheckConstraint(condition=models.Q(conduct_score__lte=100) | models.Q(conduct_score__isnull=True), name='valid_conduct_score')]


class CourseOffering(models.Model):
    schedule = models.OneToOneField(Schedule, on_delete=models.PROTECT, related_name='offering')
    capacity = models.PositiveSmallIntegerField(default=40)
    opens_on = models.DateField()
    closes_on = models.DateField()
    is_open = models.BooleanField(default=True)
    prerequisites = models.ManyToManyField(Subject, blank=True, related_name='required_for_offerings')
    revision = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(closes_on__gte=models.F('opens_on')), name='valid_registration_window'), models.CheckConstraint(condition=models.Q(capacity__gte=1), name='positive_offering_capacity')]

    def __str__(self):
        return str(self.schedule)


class CourseRegistration(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='course_registrations')
    offering = models.ForeignKey(CourseOffering, on_delete=models.PROTECT, related_name='registrations')
    status = models.CharField(max_length=20, choices=[('registered', 'Registered'), ('cancelled', 'Cancelled')], default='registered')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'offering'], name='unique_student_offering')]
