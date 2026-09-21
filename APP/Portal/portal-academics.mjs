import {esc,normalize,dateLabel} from './portal-utils.mjs';
import {facultyDetails} from './portal-faculty.mjs';
const $=id=>document.getElementById(id);
let academicData=null, registrationSemester=null,reviewSemester=null,classId='',classPage=1,classRows=[],directoryToken=0,mutationBusy=false,searchTimer;
let api,refresh,notify;
const days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
export const academicQuery=()=>reviewSemester===null?'':'?semester='+encodeURIComponent(reviewSemester);
export const academicMutationBusy=()=>mutationBusy;
export function resetAcademics(){clearTimeout(searchTimer);academicData=null;registrationSemester=reviewSemester=null;classId='';classPage=1;classRows=[];directoryToken++;$('classmatesList').innerHTML='';$('classmateDialog').close();$('classSearch').value='';$('offeringSearch').value='';$('registrationStatus').hidden=true;}
function options(terms,selected){return terms.length?terms.map(t=>`<option value="${esc(t.code)}" ${t.code===selected?'selected':''}>${esc(t.name)}</option>`).join(''):'<option value="">No terms available</option>';}
export function renderAcademics(data){
 academicData=data;
 if(!data.semesters.some(t=>t.code===registrationSemester))registrationSemester=data.selected_semester;
 reviewSemester=data.selected_semester;
 $('registrationSemester').innerHTML=options(data.semesters,registrationSemester);
 $('scholarshipSemester').innerHTML=options(data.semesters,reviewSemester);
 renderOfferings();renderReview('scholarship',data.review);renderReview('graduation',data.review);
 const existing=classId;
 if(!data.classes.some(c=>String(c.id)===classId))classId=String(data.classes[0]?.id||'');
 $('classFilter').innerHTML=data.classes.length?data.classes.map(c=>`<option value="${c.id}">${esc(c.class_id)} · ${esc(c.name)}</option>`).join(''):'<option value="">No classes available</option>';
 $('classFilter').value=classId;
 if(existing!==classId)classPage=1;
 if(location.hash==='#classmates')loadClassmates();
}
function renderOfferings(){
 if(!academicData)return;
 const rows=academicData.offerings.filter(o=>o.semester===registrationSemester);
 $('registrationCredits').textContent=(academicData.enrolled_credits_by_semester?.[registrationSemester]||0)+' credits';
 const query=normalize($('offeringSearch').value);
 const visible=rows.filter(o=>normalize(o.subject_id+' '+o.subject_name+' '+o.teacher_contact.name).includes(query));
 $('offeringList').innerHTML=visible.length?visible.map(o=>{
  const canRegister=o.is_open&&o.seats_left>0;
  const button=o.registered?(o.registration_id?`<button type="button" class="button secondary" data-cancel="${o.registration_id}" ${mutationBusy||!o.is_open?'disabled':''}>Cancel Registration</button>`:'<span class="badge success">Enrolled</span>'):`<button type="button" class="button primary" data-register="${o.id}" ${!canRegister||mutationBusy?'disabled':''}>${!o.is_open?'Registration closed':o.seats_left===0?'Full':'Enroll in Course'}</button>`;
  return `<article class="card offering-card" data-offering="${o.id}"><div class="section-heading"><span class="eyebrow">${esc(o.subject_id)} · ${o.credits} CREDITS</span><span class="badge ${o.registered?'success':'neutral'}">${o.registered?'Enrolled':o.seats_left+' spots left'}</span></div><h2>${esc(o.subject_name)}</h2><p class="muted offering-class">${esc(o.class_code)} · ${esc(o.class_name)}</p><div class="offering-schedule"><span><i class="ph ph-calendar-blank" aria-hidden="true"></i>${days[o.day_of_week]} · ${esc(o.time_range)}</span><span><i class="ph ph-map-pin" aria-hidden="true"></i>${esc(o.room||'Room not assigned')} · Periods ${o.start_period}–${o.end_period}</span></div>${facultyDetails(o.teacher_contact)}${o.prerequisites.length?'<p class="footnote">Prerequisites: '+esc(o.prerequisites.join(', '))+'</p>':''}<div class="offering-action"><span>Deadline: <strong>${dateLabel(o.closes_on)}</strong></span>${button}</div></article>`;
 }).join(''):'<div class="card empty-state"><i class="ph ph-notebook" aria-hidden="true"></i><h3>No matching course offerings</h3><p>Try switching semester or searching with different keywords.</p></div>';
}
function renderReview(kind,review){
 const result=review[kind],root=$(kind+'Review');
 const statuses={eligible:['Eligible (Reference)','success','ph-check-circle'],not_eligible:['Not Eligible Yet','warning','ph-info'],incomplete:['Incomplete Data','neutral','ph-hourglass'],unconfigured:['Criteria Not Configured','neutral','ph-sliders-horizontal']};
 const [title,tone,icon]=statuses[result.status];
 const demo=review.policy?.is_demo;
 const lead=kind==='scholarship'?'Scholarship Evaluation':'Graduation Review Progress';
 const achieved=result.criteria.filter(c=>c.status==='pass').length;
 let progress='';
 if(kind==='graduation'&&result.required_credits){const percent=Math.min(100,result.earned_credits/result.required_credits*100);progress=`<div class="graduation-progress"><div><strong>${result.earned_credits}<span> / ${result.required_credits} credits</span></strong><span>${Math.round(percent)}%</span></div><progress value="${result.earned_credits}" max="${result.required_credits}" aria-label="Accumulated credits"></progress><p>Only passed courses counted; duplicate credits from retakes are excluded.</p></div>`;}
 root.innerHTML=`<section class="card review-summary ${tone}"><div class="review-icon"><i class="ph ${icon}" aria-hidden="true"></i></div><div><span class="eyebrow">${lead}</span><h2>${title}</h2><p>${review.policy?esc(review.policy.name):'The university has not assigned criteria to your profile yet.'}</p></div><span class="review-count">${achieved}/${result.criteria.length}<small>criteria met</small></span></section><div class="policy-notice"><i class="ph ph-info" aria-hidden="true"></i><p><strong>${demo?'Demo Criteria · Reference Only':'Reference Result'}</strong> ${kind==='scholarship'?'This is an eligibility check, not an official scholarship award or quota decision.':'This result does not replace the official graduation award decision by the university.'} GPA is calculated weighted by credits on a 10-point scale.</p></div>${progress}<section class="card criteria-card"><div class="section-heading"><h2>Requirements Checklist</h2></div>${result.criteria.length?result.criteria.map(c=>`<article class="criterion-row"><span class="criterion-icon ${c.status}"><i class="ph ${c.status==='pass'?'ph-check':c.status==='fail'?'ph-x':'ph-minus'}" aria-hidden="true"></i></span><div class="criterion-main"><h3>${esc(c.label)}</h3><p>Requirement: ${esc(c.required)}</p></div><div class="criterion-result"><strong>${esc(c.actual??'No data')}</strong><span class="badge ${c.status==='pass'?'success':c.status==='fail'?'warning':'neutral'}">${c.status==='pass'?'Passed':c.status==='fail'?'Not Passed':'Pending'}</span></div></article>`).join(''):'<div class="empty-state"><h3>No criteria set</h3><p>Contact the academic office to update your record.</p></div>'}</section><p class="footnote">Certificate and extracurricular training records are managed by the university. Contact the responsible department if data needs review.</p>`;
}
export async function loadClassmates(){
 const token=++directoryToken;
 if(!classId){$('classmatesList').innerHTML='<div class="card empty-state"><h3>No class assigned</h3><p>Classes will appear when you are assigned or enroll in courses.</p></div>';$('classmatesStatus').textContent='';$('classPage').textContent='';$('classPrev').disabled=$('classNext').disabled=true;return;}
 $('classmatesStatus').textContent='Loading class roster…';
 try{
  const result=await api('/api/student/me/classmates/?class_id='+encodeURIComponent(classId)+'&page='+classPage+'&q='+encodeURIComponent($('classSearch').value.trim()));
  if(token!==directoryToken)return;
  const page=result.data;classRows=page.students;
  $('classmatesStatus').textContent=page.total+' students · '+page.class_name;
  $('classmatesList').innerHTML=classRows.length?classRows.map(s=>`<article class="card classmate-card"><span class="avatar">${esc(s.full_name.trim().split(/\s+/).slice(-2).map(w=>w[0]).join(''))}</span><div><h2>${esc(s.full_name)}</h2><p>${esc(s.student_id)} · ${esc(s.class_name)}</p></div><button class="icon-button" type="button" data-student="${esc(s.student_id)}" aria-label="View profile of ${esc(s.full_name)}"><i class="ph ph-arrow-up-right" aria-hidden="true"></i></button></article>`).join(''):'<div class="card empty-state"><h3>No students found</h3><p>Try searching with a different name or student ID.</p></div>';
  $('classPage').textContent='Page '+page.page;$('classPrev').disabled=page.page<=1;$('classNext').disabled=!page.has_next;
 }catch(error){if(token===directoryToken){classRows=[];$('classmatesList').innerHTML='';$('classmatesStatus').textContent=error.message;$('classPrev').disabled=$('classNext').disabled=true;}}
}
export function initAcademicInteractions({request,refreshData,toast}){
 api=request;refresh=refreshData;notify=toast;
 $('registrationSemester').addEventListener('change',()=>{registrationSemester=$('registrationSemester').value;renderOfferings();});
 $('offeringSearch').addEventListener('input',renderOfferings);
 $('scholarshipSemester').addEventListener('change',async()=>{reviewSemester=$('scholarshipSemester').value;$('scholarshipSemester').disabled=true;try{await refresh();}finally{$('scholarshipSemester').disabled=false;}});
 $('offeringList').addEventListener('click',async event=>{
  const button=event.target.closest('[data-register],[data-cancel]');if(!button||mutationBusy)return;
  mutationBusy=true;renderOfferings();$('registrationStatus').hidden=true;
  try{
   if(button.dataset.register)await api('/api/student/me/registrations/',{offering_id:Number(button.dataset.register)});
   else await api('/api/student/me/registrations/'+button.dataset.cancel+'/cancel/',{});
   await refresh();notify(button.dataset.register?'Enrolled successfully. Your schedule has been updated.':'Course registration cancelled.');
  }catch(error){$('registrationStatus').textContent=error.message;$('registrationStatus').hidden=false;}
  finally{mutationBusy=false;renderOfferings();}
 });
 $('classFilter').addEventListener('change',()=>{classId=$('classFilter').value;classPage=1;loadClassmates();});
 $('classSearch').addEventListener('input',()=>{classPage=1;clearTimeout(searchTimer);searchTimer=setTimeout(loadClassmates,250);});
 $('classPrev').addEventListener('click',()=>{classPage=Math.max(1,classPage-1);loadClassmates();});
 $('classNext').addEventListener('click',()=>{classPage++;loadClassmates();});
 $('classmatesList').addEventListener('click',event=>{
  const button=event.target.closest('[data-student]');if(!button)return;
  const student=classRows.find(s=>s.student_id===button.dataset.student);if(!student)return;
  $('classmateDetail').innerHTML=`<span class="eyebrow">BASIC INFORMATION</span><h3>${esc(student.full_name)}</h3><dl class="profile-ledger"><div><dt>Student ID</dt><dd>${esc(student.student_id)}</dd></div><div><dt>Class</dt><dd>${esc(student.class_name)}</dd></div></dl><p class="footnote">Academic and personal contact details remain private.</p>`;
  $('classmateDialog').showModal();
 });
 $('closeClassmate').addEventListener('click',()=>$('classmateDialog').close());
}
