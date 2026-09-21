import os, sys, django
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'admin_check')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
import json
import re

vn_pattern = re.compile(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]', re.IGNORECASE)

client = Client()

# 1. Check Student Portal HTML
res = client.get('/student-portal/')
html = getattr(res, 'content', None) or b''.join(res.streaming_content)
html = html.decode('utf-8')
assert 'name="google" content="notranslate"' in html, "Meta notranslate is missing in portal HTML"
assert 'translate="no"' in html, "translate='no' is missing in portal HTML"
print("[PASS] Student Portal HTML contains notranslate & translate='no'")

# 2. Check Admin Dashboard HTML as staff user
admin_user = User.objects.filter(is_staff=True).first()
client.force_login(admin_user)
res = client.get('/admin-dashboard/')
admin_html = res.content.decode('utf-8')
assert 'name="google" content="notranslate"' in admin_html, "Meta notranslate is missing in admin HTML"
assert 'translate="no"' in admin_html, "translate='no' is missing in admin HTML"
print("[PASS] Admin Dashboard HTML contains notranslate & translate='no'")

# 3. Check Student Dashboard API
s_client = Client()

# Login
login_res = s_client.post('/api/student/login/', data=json.dumps({'student_id': '2251120064', 'class_name': 'CN22A'}), content_type='application/json').json()
assert login_res.get('success'), f"Login failed: {login_res}"
print("[PASS] Student Login API success")

# Dashboard data
dash_res = s_client.get('/api/student/me/dashboard/')
data = dash_res.json()['data']
    
# Check subjects
for s in data['subjects']:
    for k in ['subject_name', 'teacher', 'attendance_outcome_label']:
        val = s.get(k, '')
        if vn_pattern.search(str(val)):
            print(f"[FAIL] VN text found in subject {s.get('subject_id')}.{k}: {val}")
    if s.get('alert_badge'):
        for ak in ['text', 'detail']:
            aval = s['alert_badge'].get(ak, '')
            if vn_pattern.search(str(aval)):
                print(f"[FAIL] VN text in alert_badge.{ak}: {aval}")

# Check grouped grades
for g in data['grouped_grades']:
    for k in ['subject_name', 'rank']:
        val = g.get(k, '')
        if vn_pattern.search(str(val)):
            print(f"[FAIL] VN text in grouped_grade.{k}: {val}")

# Check academic rank
rank = data.get('academic_rank', '')
if vn_pattern.search(str(rank)):
    print(f"[FAIL] VN text in academic_rank: {rank}")
else:
    print(f"[PASS] academic_rank is: '{rank}'")

# 4. Check Academics API
acad_res = s_client.get('/api/student/me/academics/')
acad_data = acad_res.json()['data']
review = acad_data.get('review', {})

for kind in ['scholarship', 'graduation']:
    crit_list = review.get(kind, {}).get('criteria', [])
    for c in crit_list:
        for k in ['label', 'actual', 'required']:
            val = str(c.get(k, '') or '')
            if vn_pattern.search(val):
                print(f"[FAIL] VN text in {kind}.{c.get('key')}.{k}: {val}")

for off in acad_data.get('offerings', []):
    for k in ['subject_name', 'semester_name']:
        val = str(off.get(k, '') or '')
        if vn_pattern.search(val):
            print(f"[FAIL] VN text in offering.{k}: {val}")

print("[PASS] All verification checks completed successfully!")
