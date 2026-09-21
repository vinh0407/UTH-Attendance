import {facultyDetails} from './portal-faculty.mjs';
import {courseStatus, quotaCard} from './portal-quota.mjs';
import {esc,dateLabel,normalize,nextLesson,weekDates,attendanceLabel,tone} from './portal-utils.mjs';
const $=id=>document.getElementById(id);
const text=(id,value)=>$(id).textContent=value ?? '—';
const empty=(title,detail='')=>'<div class="empty-state"><i class="ph ph-calendar-blank" aria-hidden="true"></i><h3>'+esc(title)+'</h3><p>'+esc(detail)+'</p></div>';
const badge=(label,color='neutral')=>'<span class="badge '+color+'">'+esc(label)+'</span>';
function lesson(r) {
 const status={cancelled:['Cancelled','danger'],postponed:['Postponed','warning'],completed:['Completed','neutral']}[r.session_status];
 return '<article class="lesson-row"><div class="lesson-time"><strong>'+esc((r.time_range||'—').split(' - ')[0])+'</strong><small>Periods '+esc(r.start_period)+'–'+esc(r.end_period)+'</small></div><div class="lesson-info"><h3>'+esc(r.subject_name)+'</h3><p>'+esc(r.teacher||'Instructor not assigned')+'</p>'+facultyDetails(r.teacher_contact,r.teacher)+(r.postponed_to?'<p>Postponed to '+dateLabel(r.postponed_to)+'</p>':'')+(r.postponed_reason?'<p>'+esc(r.postponed_reason)+'</p>':'')+'</div><div class="lesson-meta">'+(status?badge(...status):badge(r.room?'Room '+r.room:'Room not assigned'))+'<small>'+esc(r.time_range)+'</small></div></article>';
}
export function renderHome(data) {
 const p=data.profile, rows=data.attendance||[], today=data.schedule_today||[];
 text('sidebarName',p.full_name);text('sidebarMeta',p.student_id+' · '+p.class_name);text('greetingName',p.full_name.trim().split(/\s+/).at(-1));
 text('profileName',p.full_name);text('profilePageId',p.student_id);text('profilePageClass',p.class_name);text('profilePageEmail',p.email||'Not updated');
 document.querySelectorAll('[data-avatar]').forEach(e=>e.textContent=p.full_name.trim().split(/\s+/).slice(-2).map(s=>s[0]).join(''));
 text('faceRegistration',p.is_registered?'Face registered':'Face not registered');$('faceRegistration').className='badge '+(p.is_registered?'success':'warning');
 text('todayDate',dateLabel(data.date));text('headerDate',dateLabel(data.date));text('todayCount',today.length);
 $('todaySchedule').innerHTML=today.length?today.map(lesson).join(''):empty('No classes scheduled today','You can view your schedule for other days of the week.');
 const clock=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date()).split(':');
 const minutes=Number(clock[0])*60+Number(clock[1]), next=nextLesson(today,minutes);
 text('nextLabel',next&&next.start<=minutes?'CURRENT CLASS IN PROGRESS':'UPCOMING CLASS');text('nextTag',next?'Today':'Your Free Time');
 $('nextClass').innerHTML=next?'<h2 id="nextTitle">'+esc(next.subject_name)+'</h2><p>'+esc(next.teacher||'')+'</p><div class="next-details"><span><i class="ph ph-clock" aria-hidden="true"></i> '+esc(next.time_range)+'</span><span><i class="ph ph-map-pin" aria-hidden="true"></i> '+esc(next.room||'Room not assigned')+'</span></div>':'<h2 id="nextTitle">'+(today.length?'No more classes today':'Your schedule is clear today.')+'</h2><p>Check your weekly schedule and prepare for your upcoming classes.</p>';
 const present=rows.filter(r=>r.status==='present').length, late=rows.filter(r=>r.status==='late').length, absent=rows.filter(r=>r.status==='absent').length,total=present+late+absent,rate=total?Math.round((present+late)/total*100):0;
 text('attendanceRate',total?rate+'%':'—');$('attendanceRing').style.setProperty('--progress',rate+'%');text('attendanceBasis',total?(present+late)+'/'+total+' sessions recorded':'No attendance records yet');text('summaryOnTime',present);text('summaryLate',late);text('summaryAbsent',absent);
 const currentCourses=(data.course_attendance||[]).filter(c=>c.semester===data.selected_semester);
 const failed=currentCourses.filter(c=>c.attendance_outcome==='failed');
 const warnings=currentCourses.filter(c=>c.attendance_outcome==='warning');
 $('academicNotice').innerHTML=failed.length||warnings.length?'<h3>'+failed.length+' course(s) barred · '+warnings.length+' near limit</h3><p>Review your absence count and attendance notices for this term.</p>':'<h3>'+(currentCourses.length?'Absence allowance healthy':'No courses registered')+'</h3><p>Max 3 absences per course. The 4th missed session leads to exam barring.</p>';
 $('recentAttendance').innerHTML=rows.length?[...rows].sort((a,b)=>b.date.localeCompare(a.date)).slice(0,3).map(r=>'<div class="recent-row"><span class="recent-icon"><i class="ph ph-check-square" aria-hidden="true"></i></span><div class="recent-info"><strong>'+esc(r.subject_name)+'</strong><small>'+dateLabel(r.date)+'</small></div>'+badge(attendanceLabel(r),tone(r))+'</div>').join(''):empty('No attendance records yet','Records will appear once attendance is logged.');
 $('subjectCards').innerHTML=data.subjects.length?data.subjects.map(quotaCard).join(''):empty('No courses registered');
 const semester=$('semesterFilter').value;
 $('semesterFilter').innerHTML='<option value="all">All Semesters</option>'+[...new Set(data.grades.map(r=>r.semester))].sort().map(s=>'<option value="'+esc(s)+'">'+esc(s)+'</option>').join('');
 if([...$('semesterFilter').options].some(o=>o.value===semester))$('semesterFilter').value=semester;
}
export function renderSchedule(data,selected) {
 const dates=weekDates(data.date),rows=data.schedule_week||[];
 text('weekRange','Week of '+dateLabel(dates[0])+' – '+dateLabel(dates[6]));
 $('dayPicker').innerHTML='<button type="button" class="day-button '+(selected==='all'?'is-active':'')+'" data-day="all" aria-pressed="'+(selected==='all')+'"><span>Full Week</span><strong>7 Days</strong></button>'+dates.map((d,i)=>'<button type="button" class="day-button '+(selected===d?'is-active ':'')+(d===data.date?'is-today':'')+'" data-day="'+d+'" aria-pressed="'+(selected===d)+'"><span>'+['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][i]+'</span><strong>'+d.slice(8)+'/'+d.slice(5,7)+'</strong></button>').join('');
 const active=selected==='all'?dates:[selected];
 $('weeklySchedule').innerHTML=active.map(d=>'<section class="card"><div class="section-heading"><h2>'+dateLabel(d)+(d===data.date?' · Today':'')+'</h2></div>'+ (rows.some(r=>r.date===d)?rows.filter(r=>r.date===d).map(lesson).join(''):empty('No classes scheduled'))+'</section>').join('');
}
export function renderAttendance(data,limit=20,semester=data.selected_semester) {
 const query=normalize($('attendanceSearch').value),filter=$('attendanceFilter').value;
 const rows=data.attendance.filter(r=>r.semester===semester&&(filter==='all'||r.status===filter)&&normalize(r.subject_name+' '+r.subject_id).includes(query)).sort((a,b)=>b.date.localeCompare(a.date));
 text('attendanceCount',rows.length+' results');
 $('attendanceRows').innerHTML=rows.length?rows.slice(0,limit).map(r=>'<tr><td data-label="Course"><strong>'+esc(r.subject_name)+'</strong><small>'+esc(r.subject_id)+'</small></td><td data-label="Date">'+dateLabel(r.date)+'</td><td data-label="Schedule / Arrival">'+esc(r.scheduled_time||'—')+' / '+esc(r.check_in_time||'—')+'</td><td data-label="Result">'+badge(attendanceLabel(r),tone(r))+'</td><td data-label="Absence periods">'+esc(r.attendance_periods ?? (r.status==='absent'?'Full session':0))+'</td></tr>').join(''):'<tr><td colspan="5">'+empty('No matching records found',data.attendance.length?'Try changing search keywords or filter status.':'You have no attendance records yet.')+'</td></tr>';
 $('moreAttendance').hidden=rows.length<=limit;
}
export function renderGrades(data) {
 const selected = $('semesterFilter').value;
 
 // 1. Determine grouped grades
 let groups = data.grouped_grades || [];
 if (!groups.length && data.grades) {
   const map = {};
   data.grades.forEach(r => {
     const key = r.subject_id + '_' + r.semester;
     if (!map[key]) {
       map[key] = {
         subject_id: r.subject_id,
         subject_name: r.subject_name,
         credits: 3,
         semester: r.semester,
         weights: { cc: 0.10, gk: 0.30, ck: 0.60 },
         bonus_method: 'DIRECT',
         cc: null, gk: null, ck: null, bonus: null, official_total: null, calculated_total: null
       };
     }
     const score = Number(r.score);
     const type = (r.assessment_type || '').toUpperCase();
     if (type === 'ATTENDANCE' || type === 'CC') map[key].cc = score;
     else if (type === 'MIDTERM' || type === 'GK') map[key].gk = score;
     else if (type === 'FINAL' || type === 'CK') map[key].ck = score;
     else if (type === 'BONUS' || type === 'PROCESS' || type === 'ASSIGNMENT' || type === 'QUIZ') map[key].bonus = score;
     else if (type === 'TOTAL') map[key].official_total = score;
   });
   groups = Object.values(map);
   groups.forEach(g => {
     if (g.cc !== null || g.gk !== null || g.ck !== null) {
       let calc = (g.cc || 0)*g.weights.cc + (g.gk || 0)*g.weights.gk + (g.ck || 0)*g.weights.ck;
       if (g.bonus !== null && g.bonus_method === 'DIRECT') calc += g.bonus;
       g.calculated_total = Math.round(Math.min(10, Math.max(0, calc)) * 100) / 100;
     }
   });
 }

 const filteredGroups = groups.filter(g => selected === 'all' || g.semester === selected);

  // 2. Header summary
  if ($('gradeSemesterLabel')) $('gradeSemesterLabel').textContent = selected === 'all' ? 'All Semesters' : selected;
  const totals = filteredGroups.map(g => g.official_total ?? g.calculated_total).filter(v => v !== null && v !== undefined);
  const avg = totals.length ? (totals.reduce((a,b) => a+b, 0) / totals.length).toFixed(2) : '—';
  if ($('gradeOverallGPA')) $('gradeOverallGPA').textContent = '# ' + avg + ' / 10';

  const gradedCourses = filteredGroups.filter(g => g.gpa_scale_4 !== null && g.gpa_scale_4 !== undefined);
  const totalCreds = gradedCourses.reduce((sum, g) => sum + (g.credits || 3), 0);
  const gpa4 = totalCreds ? (gradedCourses.reduce((sum, g) => sum + g.gpa_scale_4 * (g.credits || 3), 0) / totalCreds).toFixed(2) : '—';
  if ($('gradeScale4Summary')) $('gradeScale4Summary').textContent = 'GPA Scale 4.0: ' + gpa4 + ' / 4.0';
  const rank = gpa4 !== '—' ? (gpa4 >= 3.6 ? 'Excellent' : gpa4 >= 3.2 ? 'Very Good' : gpa4 >= 2.5 ? 'Good' : gpa4 >= 2.0 ? 'Average' : 'Poor') : 'Unranked';
  if ($('gradeAcademicRank')) $('gradeAcademicRank').textContent = 'Standing: ' + rank;

  // 3. Render Grade Cards Grid
  const formatVal = (val) => (val !== null && val !== undefined) ? Number(val).toFixed(2) : '<span class="score-missing">Not graded</span>';

  if ($('gradeCardsGrid')) {
    $('gradeCardsGrid').innerHTML = filteredGroups.length ? filteredGroups.map(g => {
      const course = data.course_attendance?.find(c => c.semester === g.semester && c.subject_id === g.subject_id);
      const stateBadge = course ? badge(...courseStatus(course)) : badge('In Progress', 'success');
      const finalScore = g.official_total !== null && g.official_total !== undefined ? Number(g.official_total).toFixed(2) : (g.calculated_total !== null && g.calculated_total !== undefined ? Number(g.calculated_total).toFixed(2) : '—');
      const letterBadge = g.letter_grade ? `<span class="badge ${g.letter_grade === 'F' ? 'danger' : 'success'}" style="font-size:12px;font-weight:700">${esc(g.letter_grade)} · ${Number(g.gpa_scale_4).toFixed(1)}</span>` : '';
      const examWarning = (course?.danger_level === 'barred' || course?.danger_level === 'warning')
        ? `<div style="margin-top: 8px; padding: 6px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 6px; background: ${course.danger_level === 'barred' ? 'rgba(239, 68, 68, 0.12); color: #dc2626;' : 'rgba(245, 158, 11, 0.12); color: #d97706;'}">
             <i class="ph ${course.danger_level === 'barred' ? 'ph-prohibit' : 'ph-warning'}" aria-hidden="true"></i>
             <span>${esc(course.alert_badge?.detail || (course.danger_level === 'barred' ? 'Barred from exam due to excessive absences' : 'At risk of exam barring'))}</span>
           </div>`
        : '';

      return `<article class="card subject-grade-card">
        <div class="grade-card-header">
          <div>
            <span class="eyebrow">${esc(g.subject_id)} · ${g.credits} CREDITS</span>
            <h2>${esc(g.subject_name)}</h2>
          </div>
          ${stateBadge}
        </div>
        ${examWarning}
        
        <div class="grade-components-grid">
          <div class="component-box">
            <span class="component-label">Bonus Points</span>
            <strong class="component-value">${formatVal(g.bonus)}</strong>
          </div>
          <div class="component-box">
            <span class="component-label">Attendance</span>
            <strong class="component-value">${formatVal(g.cc)}</strong>
          </div>
          <div class="component-box">
            <span class="component-label">Midterm Exam</span>
            <strong class="component-value">${formatVal(g.gk)}</strong>
          </div>
          <div class="component-box">
            <span class="component-label">Final Exam</span>
            <strong class="component-value">${formatVal(g.ck)}</strong>
          </div>
        </div>

        <div class="grade-card-footer">
          <div class="weights-note">
            <small>Weights: CC ${Math.round(g.weights.cc*100)}% · Midterm ${Math.round(g.weights.gk*100)}% · Final ${Math.round(g.weights.ck*100)}%</small>
          </div>
          <div class="total-score-badge">
            <span>Overall Score</span>
            <div style="display:flex;align-items:baseline;gap:8px;justify-content:flex-end">
              <strong># ${finalScore}</strong>
              ${letterBadge}
            </div>
          </div>
        </div>
      </article>`;
    }).join('') : empty('No academic results', 'Grades will appear once published by the university.');
  }

  // 4. Populate Subject Select in Interactive Calculator
  const calcSelect = $('calcSubjectSelect');
  if (calcSelect) {
    const currentVal = calcSelect.value;
    calcSelect.innerHTML = '<option value="custom">Custom (Manual input)</option>' + filteredGroups.map(g => 
      `<option value="${esc(g.subject_id)}">${esc(g.subject_name)} (${esc(g.subject_id)})</option>`
    ).join('');
    if ([...calcSelect.options].some(o => o.value === currentVal)) calcSelect.value = currentVal;
  }

  // 5. Render Raw Ledger Table
  const rows = data.grades.filter(r => selected === 'all' || r.semester === selected);
  const names = {MIDTERM:'Midterm', FINAL:'Final', TOTAL:'Total', ASSIGNMENT:'Assignment', QUIZ:'Quiz', PROCESS:'Process', ATTENDANCE:'Attendance', BONUS:'Bonus'};
  $('gradesRows').innerHTML = rows.length ? rows.map(r => {
    const course = data.course_attendance?.find(c => c.semester === r.semester && c.subject_id === r.subject_id);
    const state = course ? badge(...courseStatus(course)) : badge('No data');
    return '<tr><td data-label="Course"><strong>'+esc(r.subject_name)+'</strong><small>'+esc(r.subject_id)+'</small>'+facultyDetails(course?.teacher_contact,course?.teacher)+'</td><td data-label="Semester">'+esc(r.semester)+'</td><td data-label="Assessment Type">'+esc(names[r.assessment_type]||r.assessment_type)+'</td><td data-label="Score"><strong class="score">'+esc(r.score ?? 'Not graded')+'</strong></td><td data-label="Attendance">'+state+'</td></tr>';
  }).join('') : '<tr><td colspan="5">'+empty('No grades available','Grades will appear once published by the university.')+'</td></tr>';
  updateCalculator();
}

export function updateCalculator() {
  if (!$('calcCC')) return;
  const cc = parseFloat($('calcCC').value) || 0;
  const wCC = (parseFloat($('calcWeightCC').value) || 0) / 100;
  const gk = parseFloat($('calcGK').value) || 0;
  const wGK = (parseFloat($('calcWeightGK').value) || 0) / 100;
  const ck = parseFloat($('calcCK').value) || 0;
  const wCK = (parseFloat($('calcWeightCK').value) || 0) / 100;
  const bonus = parseFloat($('calcBonus').value) || 0;
  const bonusMethod = $('calcBonusMethod').value;

  const totalWeight = Math.round((wCC + wGK + wCK) * 100);
  const statusBadge = $('weightValidationStatus');
  if (statusBadge) {
    if (totalWeight === 100) {
      statusBadge.className = 'badge success';
      statusBadge.textContent = 'Valid weights · Sum equals 100%';
    } else {
      statusBadge.className = 'badge warning';
      statusBadge.textContent = `Total weights = ${totalWeight}% (Must be 100%)`;
    }
  }

  let total = cc * wCC + gk * wGK + ck * wCK;
  if (bonusMethod === 'DIRECT') {
    total += bonus;
  }
  const capped = Math.min(10, Math.max(0, total));
  if ($('calcResultScore')) {
    $('calcResultScore').textContent = '# ' + capped.toFixed(2) + ' / 10';
  }
}

export function initGradeCalculator(getData) {
  const inputs = ['calcCC', 'calcWeightCC', 'calcGK', 'calcWeightGK', 'calcCK', 'calcWeightCK', 'calcBonus', 'calcBonusMethod'];
  inputs.forEach(id => {
    const el = $(id);
    if (el) el.addEventListener('input', () => updateCalculator());
    if (el) el.addEventListener('change', () => updateCalculator());
  });

  const select = $('calcSubjectSelect');
  if (select) {
    select.addEventListener('change', () => {
      const data = getData ? getData() : null;
      if (!data) return;
      const groups = data.grouped_grades || [];
      const sub = groups.find(g => g.subject_id === select.value);
      if (sub) {
        $('calcCC').value = sub.cc !== null && sub.cc !== undefined ? sub.cc : 8.0;
        $('calcWeightCC').value = Math.round((sub.weights?.cc || 0.10) * 100);
        $('calcGK').value = sub.gk !== null && sub.gk !== undefined ? sub.gk : 7.0;
        $('calcWeightGK').value = Math.round((sub.weights?.gk || 0.30) * 100);
        $('calcCK').value = sub.ck !== null && sub.ck !== undefined ? sub.ck : 8.0;
        $('calcWeightCK').value = Math.round((sub.weights?.ck || 0.60) * 100);
        $('calcBonus').value = sub.bonus !== null && sub.bonus !== undefined ? sub.bonus : 0.5;
        $('calcBonusMethod').value = sub.bonus_method || 'DIRECT';
        updateCalculator();
      }
    });
  }

  const btnTarget = $('btnCalcTargetCK');
  if (btnTarget) {
    btnTarget.addEventListener('click', () => {
      const targetTotal = parseFloat($('calcTargetTotal').value);
      const textEl = $('targetResultText');
      if (isNaN(targetTotal) || targetTotal < 0 || targetTotal > 10) {
        if (textEl) textEl.textContent = 'Please enter a target score between 0 and 10.';
        return;
      }
      const cc = parseFloat($('calcCC').value) || 0;
      const wCC = (parseFloat($('calcWeightCC').value) || 0) / 100;
      const gk = parseFloat($('calcGK').value) || 0;
      const wGK = (parseFloat($('calcWeightGK').value) || 0) / 100;
      const wCK = (parseFloat($('calcWeightCK').value) || 0) / 100;
      const bonus = parseFloat($('calcBonus').value) || 0;
      const bonusMethod = $('calcBonusMethod').value;

      if (wCK <= 0) {
        if (textEl) textEl.textContent = 'Final exam weight must be greater than 0%.';
        return;
      }

      const currentWeightedBeforeCK = cc * wCC + gk * wGK + (bonusMethod === 'DIRECT' ? bonus : 0);
      const neededFromCK = targetTotal - currentWeightedBeforeCK;
      const requiredCK = neededFromCK / wCK;

      if (textEl) {
        if (requiredCK <= 0) {
          textEl.textContent = `Target total ${targetTotal.toFixed(1)} achieved! No further final exam score needed.`;
        } else if (requiredCK > 10) {
          textEl.textContent = `Need ${requiredCK.toFixed(2)} / 10 in final exam for target ${targetTotal.toFixed(1)} (Exceeds 10.0, very difficult).`;
        } else {
          textEl.textContent = `You need at least ${requiredCK.toFixed(2)} / 10 in final exam to achieve overall score ${targetTotal.toFixed(1)}.`;
        }
      }
    });
  }
}

export function renderLeaveRequests(leaves) {
  const container = $('leaveRequestsList');
  if (!container) return;
  if (!leaves || !leaves.length) {
    container.innerHTML = '<p class="muted" style="font-size: 0.85rem;">You have not submitted any leave requests yet.</p>';
    return;
  }
  const statusMap = {
    pending: { label: 'Pending Review', color: 'warning' },
    approved: { label: 'Approved (Excused)', color: 'success' },
    rejected: { label: 'Rejected', color: 'danger' }
  };
  container.innerHTML = leaves.map(l => {
    const st = statusMap[l.status] || { label: l.status_display || l.status, color: 'neutral' };
    return `<div class="card" style="padding: 1rem; border-left: 4px solid var(--color-${st.color === 'warning' ? 'warning' : st.color === 'success' ? 'success' : 'danger'}, #3b82f6);">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
        <div>
          <strong style="display: block; font-size: 0.95rem;">${esc(l.subject_name)}</strong>
          <small class="muted" style="display: block; margin-top: 2px;"><i class="ph ph-calendar"></i> Leave Date: ${dateLabel(l.date)} · Submitted: ${esc(l.created_at)}</small>
        </div>
        <span class="badge ${st.color}">${esc(st.label)}</span>
      </div>
      <div style="margin-top: 8px; font-size: 0.875rem;">
        <span class="muted">Reason:</span> ${esc(l.reason)}
      </div>
      ${l.evidence_url ? `<div style="margin-top: 4px; font-size: 0.8rem;"><span class="muted">Evidence:</span> ${l.evidence_url.startsWith('http') ? `<a href="${esc(l.evidence_url)}" target="_blank" rel="noopener noreferrer" style="color:var(--color-primary);">${esc(l.evidence_url)}</a>` : esc(l.evidence_url)}</div>` : ''}
      ${l.review_note ? `<div style="margin-top: 6px; padding: 6px 8px; background: rgba(0,0,0,0.03); border-radius: 4px; font-size: 0.8rem;"><span class="muted">Faculty / Staff Note:</span> <em>${esc(l.review_note)}</em></div>` : ''}
    </div>`;
  }).join('');
}
