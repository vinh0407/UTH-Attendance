def teacher_details(subject):
    return {'name':subject.teacher, 'email':subject.teacher_email, 'phone':subject.teacher_phone,
            'department':subject.teacher_department, 'office':subject.teacher_office, 'bio':subject.teacher_bio}

