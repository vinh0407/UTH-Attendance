import {renderAcademics,initAcademicInteractions,academicQuery,resetAcademics,loadClassmates,academicMutationBusy} from './portal-academics.mjs';
import {fillAttendanceSemesters,renderCourseAttendance} from './portal-quota.mjs';
import {renderHome,renderSchedule,renderAttendance,renderGrades,initGradeCalculator,renderLeaveRequests} from './portal-render.mjs';
const $=id=>document.getElementById(id);
const names={home:'Overview',schedule:'Schedule',attendance:'Attendance',grades:'Academic Results',subjects:'Courses',profile:'My Profile',registration:'Course Registration',scholarship:'Scholarship',graduation:'Graduation Review',classmates:'My Class',leaves:'Leave Application'};
let data=null,selectedDay='all',limit=20,generation=0,toastTimer,attendanceSemester=null,loading=false,loadPromise=null;
function toast(message){$('toast').textContent=message;$('toast').classList.add('is-visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('is-visible'),4000);}
async function request(path,body){
 const csrf=document.cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('csrftoken='))?.slice(10)||'';
 const response=await fetch((window.PORTAL_API_BASE||'')+path,{method:body?'POST':'GET',credentials:'include',headers:{Accept:'application/json',...(body?{'Content-Type':'application/json','X-CSRFToken':decodeURIComponent(csrf)}:{})},...(body?{body:JSON.stringify(body)}:{})});
 let payload={};try{payload=await response.json();}catch{}
 if(!response.ok||payload.success===false){const error=new Error(payload.error||'Could not connect to server. Please try again.');error.status=response.status;throw error;}return payload;
}
function showLogin(message=''){
 generation++;data=null;resetAcademics();$('portalShell').hidden=true;$('authGate').hidden=false;$('loginError').textContent=message;$('loginError').hidden=!message;
 $('attendanceSearch').value='';$('attendanceFilter').value='all';$('semesterFilter').value='all';selectedDay='all';limit=20;attendanceSemester=null;
 document.title='Student Sign In · UTH';
}
function route(focus=false){
 if(!data)return;
 const key=location.hash.slice(1),active=names[key]?key:'home';
 document.querySelectorAll('.page').forEach(e=>e.hidden=e.id!=='page-'+active);
 document.querySelectorAll('[data-route]').forEach(e=>{const isActive=e.dataset.route===active||(['subjects','registration','scholarship','graduation','classmates','leaves'].includes(active)&&e.closest('.bottom-nav')&&e.dataset.route==='grades');e.classList.toggle('is-active',!!isActive);if(isActive)e.setAttribute('aria-current','page');else e.removeAttribute('aria-current');});
 $('pageLabel').textContent=names[active];document.title=names[active]+' · UTH';
 if(focus&&active==='classmates')loadClassmates();
 if(active==='leaves')loadLeaves();
 if(focus){window.scrollTo({top:0,behavior:'instant'});$('page-'+active).querySelector('h1')?.focus({preventScroll:true});}
}
function render(){attendanceSemester=fillAttendanceSemesters(data,attendanceSemester);renderHome(data);renderSchedule(data,selectedDay);renderCourseAttendance(data,attendanceSemester);renderAttendance(data,limit,attendanceSemester);renderGrades(data);renderAcademics(data.academics);populateLeaveSubjects();route();}
function load(){if(loadPromise)return loadPromise;loadPromise=fetchData().finally(()=>{loadPromise=null;});return loadPromise;}
async function fetchData(){
 if(loading)return; loading=true;
 const token=++generation,button=$('refreshButton');button.disabled=true;$('syncStatus').textContent='Updating data…';
 try{const [result,academicResult]=await Promise.all([request('/api/student/me/dashboard/'),request('/api/student/me/academics/'+academicQuery())]);if(token!==generation)return;data={...result.data,academics:academicResult.data};render();$('authGate').hidden=true;$('portalShell').hidden=false;$('syncStatus').textContent='Updated at '+new Intl.DateTimeFormat('en-US',{hour:'2-digit',minute:'2-digit'}).format(new Date());}
 catch(error){if(token!==generation)return;if(error.status===401)showLogin(data?'Session expired. Please sign in again.':'');else if(data){$('syncStatus').textContent='Data not updated. Please try again.';toast('Could not refresh. You are viewing previously cached data.');}else showLogin('Could not load data. Please sign in again.');}
 finally{button.disabled=false;loading=false;}
}
$('studentLoginForm').addEventListener('submit',async event=>{
 event.preventDefault();$('loginSubmit').disabled=true;$('loginError').hidden=true;
 try{await request('/api/student/login/',{student_id:$('loginStudentId').value.trim(),class_name:$('loginClassName').value.trim()});await load();}
 catch(error){$('loginError').textContent=error.message;$('loginError').hidden=false;}
 finally{$('loginSubmit').disabled=false;}
});
$('refreshButton').addEventListener('click',load);
window.addEventListener('hashchange',()=>route(true));
$('dayPicker').addEventListener('click',event=>{const button=event.target.closest('[data-day]');if(button&&data){selectedDay=button.dataset.day;renderSchedule(data,selectedDay);}});
$('scheduleToday').addEventListener('click',()=>{if(data){selectedDay=data.date;renderSchedule(data,selectedDay);$('dayPicker').querySelector('.is-active')?.scrollIntoView({block:'nearest',inline:'center'});}});
for(const id of ['attendanceSearch','attendanceFilter'])$(id).addEventListener(id==='attendanceSearch'?'input':'change',()=>{limit=20;if(data)renderAttendance(data,limit,attendanceSemester);});
$('moreAttendance').addEventListener('click',()=>{limit+=20;if(data)renderAttendance(data,limit,attendanceSemester);});
$('attendanceSemester').addEventListener('change',()=>{attendanceSemester=$('attendanceSemester').value;limit=20;if(data){renderCourseAttendance(data,attendanceSemester);renderAttendance(data,limit,attendanceSemester);}});
$('semesterFilter').addEventListener('change',()=>{if(data)renderGrades(data);});
function theme(value){document.documentElement.dataset.theme=value;const dark=value==='dark';$('themeLabel').textContent=dark?'Dark':'Light';$('themeToggle').setAttribute('aria-label',dark?'Switch to light theme':'Switch to dark theme');$('themeToggle').setAttribute('aria-pressed',String(dark));}
try{theme(localStorage.getItem('uth-student-theme')==='dark'?'dark':'light');}catch{theme('light');}
$('themeToggle').addEventListener('click',()=>{const value=document.documentElement.dataset.theme==='dark'?'light':'dark';theme(value);try{localStorage.setItem('uth-student-theme',value);}catch{}});
$('logoutButton').addEventListener('click',async()=>{
 $('logoutButton').disabled=true;
 try{await request('/api/student/logout/',{});showLogin();$('studentLoginForm').reset();location.hash='home';$('loginStudentId').focus();}
 catch{toast('Could not log out. Check connection and try again.');}
 finally{$('logoutButton').disabled=false;}
});
const passForm = $('changePasswordForm');
if (passForm) {
 passForm.addEventListener('submit', async event => {
  event.preventDefault();
  const oldPass = $('oldPassword').value;
  const newPass = $('newPassword').value;
  const confirmPass = $('confirmPassword').value;
  const statusEl = $('changePasswordStatus');
  const btn = $('btnChangePassword');

  statusEl.hidden = true;
  if (newPass !== confirmPass) {
    statusEl.textContent = 'New password confirmation does not match.';
    statusEl.hidden = false;
    return;
  }
  btn.disabled = true;
  try {
    const res = await request('/api/student/me/change-password/', { old_password: oldPass, new_password: newPass });
    passForm.reset();
    toast(res.message || 'Password changed successfully.');
  } catch (err) {
    statusEl.textContent = err.message || 'Could not change password. Please try again.';
    statusEl.hidden = false;
  } finally {
    btn.disabled = false;
  }
 });
}

function populateLeaveSubjects() {
  const select = $('leaveSubject');
  if (!select || !data) return;
  const currentVal = select.value;
  const subjects = data.subjects || [];
  select.innerHTML = '<option value="">-- All sessions on this day --</option>' +
    subjects.map(s => `<option value="${s.subject_id}">${s.subject_name} (${s.subject_id})</option>`).join('');
  if ([...select.options].some(o => o.value === currentVal)) select.value = currentVal;
}

let leavesLoading = false;
async function loadLeaves() {
  if (leavesLoading) return;
  leavesLoading = true;
  const container = $('leaveRequestsList');
  if (container) container.innerHTML = '<p class="muted" style="font-size:0.85rem;">Loading leave requests...</p>';
  try {
    const res = await request('/api/student/me/leave-requests/');
    renderLeaveRequests(res.data || []);
  } catch (err) {
    if (container) container.innerHTML = '<p class="form-error">' + (err.message || 'Could not load leave requests.') + '</p>';
  } finally {
    leavesLoading = false;
  }
}

const leaveForm = $('createLeaveForm');
if (leaveForm) {
  leaveForm.addEventListener('submit', async event => {
    event.preventDefault();
    const btn = $('btnSubmitLeave');
    const statusEl = $('createLeaveStatus');
    if (statusEl) statusEl.hidden = true;
    if (btn) btn.disabled = true;

    const payload = {
      date: $('leaveDate').value,
      subject_id: $('leaveSubject').value,
      reason: $('leaveReason').value.trim(),
      evidence_url: $('leaveEvidence').value.trim()
    };

    try {
      const res = await request('/api/student/me/leave-requests/create/', payload);
      leaveForm.reset();
      toast(res.message || 'Leave request submitted successfully.');
      await loadLeaves();
    } catch (err) {
      if (statusEl) {
        statusEl.textContent = err.message || 'Could not submit leave request. Please try again.';
        statusEl.hidden = false;
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  });
}

initAcademicInteractions({request,refreshData:async()=>{if(loadPromise)await loadPromise;await load();},toast});
initGradeCalculator(()=>data);
// Register PWA Service Worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  });
}
// Updates the derived outcome and in-page notices after a staff member finalizes a session.
setInterval(()=>{if(data&&!document.hidden&&!academicMutationBusy())load();},30000);
document.addEventListener('visibilitychange',()=>{if(data&&!document.hidden&&!academicMutationBusy())load();});
load();
