import {facultyDetails} from './portal-faculty.mjs';
import {esc} from './portal-utils.mjs';

export function courseStatus(course) {
  if (course.attendance_outcome === 'unassigned') return ['Unassigned term', 'neutral'];
  if (course.alert_badge) return [course.alert_badge.text, course.alert_badge.color];
  if (course.attendance_outcome === 'failed') return ['BARRED FROM EXAM', 'danger'];
  if (course.attendance_outcome === 'warning') return ['AT RISK OF BARRING', 'warning'];
  return [course.remaining_absences + ' absence(s) remaining', course.remaining_absences === 1 ? 'warning' : 'success'];
}

export function quotaCard(course) {
  const [label, tone] = courseStatus(course);
  const remaining = course.remaining_absences;
  const fraction = (remaining ?? '—') + '/' + course.absence_limit;
  const progress = (remaining / course.absence_limit) * 100;
  return `<article class="card quota-card ${tone}" data-subject="${esc(course.subject_id)}">
    <div class="quota-card-heading"><span class="eyebrow">${esc(course.subject_id)}</span><span class="badge ${tone}">${esc(label)}</span></div>
    <h3>${esc(course.subject_name)}</h3><p class="quota-teacher">${esc(course.teacher || 'Instructor not assigned')}</p>
    <div class="quota-card-body"><div class="quota-ring" role="img" aria-label="${remaining === null ? 'Unassigned term' : `${remaining} of ${course.absence_limit} absences remaining`}" style="--quota-progress:${progress}%;"><div><strong>${fraction}</strong><span>REMAINING</span></div></div>
    <dl class="quota-ledger"><div><dt>Absences</dt><dd>${course.absent_sessions} <small>sessions</small></dd></div><div><dt>Excused</dt><dd>${course.excused_sessions || 0} <small>sessions</small></dd></div><div><dt>Max allowed</dt><dd>${course.absence_limit} <small>sessions</small></dd></div></dl></div>
    <div class="quota-card-footer"><span>${course.counted_sessions} recorded sessions</span><span>${esc(course.semester_name)}</span></div>
    ${course.alert_badge && course.danger_level !== 'safe' ? `<p class="quota-consequence" style="color:var(--color-${course.alert_badge.color === 'danger' ? 'danger' : 'warning'}, #ef4444);font-weight:600;">${esc(course.alert_badge.detail)}</p>` : ''}
    ${course.attendance_outcome === 'warning' && !course.alert_badge ? '<p class="quota-consequence">You must attend all remaining classes.</p>' : course.attendance_outcome === 'failed' && !course.alert_badge ? '<p class="quota-consequence">Exceeded allowed absences limit. Contact your instructor if attendance is incorrect.</p>' : ''}
    ${course.attendance_outcome === 'unassigned' ? '<p class="quota-consequence">Assign schedule to a semester to calculate absence quota accurately.</p>' : ''}
    ${facultyDetails(course.teacher_contact, course.teacher)}
  </article>`;
}

export function renderCourseAttendance(data, semester) {
  const courses = (data.course_attendance || []).filter(course => course.semester === semester);
  const notices = (data.attendance_notifications || []).filter(notice => notice.semester === semester);
  const term = (data.semesters || []).find(item => item.code === semester);
  document.getElementById('quotaSemesterTitle').textContent = (term?.name || 'Unassigned term') + ' · ' + courses.length + ' courses';
  document.getElementById('attendanceCourses').innerHTML = courses.length ? courses.map(quotaCard).join('') : '<div class="card empty-state"><i class="ph ph-books" aria-hidden="true"></i><h3>No courses in this term</h3><p>Courses will appear when the schedule is updated.</p></div>';
  const notifications = document.getElementById('attendanceNotifications');
  const markup = notices.map(notice => `<article class="quota-notice ${notice.severity === 'failed' ? 'danger' : 'warning'}"><i class="ph ${notice.severity === 'failed' ? 'ph-x-circle' : 'ph-warning-circle'}" aria-hidden="true"></i><div><strong>${esc(notice.subject_name)}</strong><p>${esc(notice.message)}</p></div></article>`).join('');
  // Do not re-announce unchanged notifications during background refresh.
  if (notifications.innerHTML !== markup) notifications.innerHTML = markup;
  notifications.hidden = !notices.length;
}

export function fillAttendanceSemesters(data, selected) {
  const select = document.getElementById('attendanceSemester');
  select.innerHTML = data.semesters.length ? data.semesters.map(term => `<option value="${esc(term.code)}">${esc(term.name)}</option>`).join('') : '<option value="">No terms available</option>';
  const value = data.semesters.some(term => term.code === selected) ? selected : data.selected_semester;
  select.value = value;
  return value;
}
