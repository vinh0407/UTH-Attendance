const API = window.KIOSK_API_BASE || '';
const KIOSK_KEY = window.KIOSK_API_KEY || 'development-kiosk-key-change-before-deployment';
const kioskHeaders = extra => ({ 'X-Kiosk-Key': KIOSK_KEY, ...extra });
const el = id => document.getElementById(id);
const video = el('camera');
const overlay = el('overlay');
const frame = el('camera-frame');
const state = { camera: null, session: null, sending: false, timer: null, resetTimer: null, lastResult: null };
const deviceId = new URLSearchParams(window.location.search).get('device_id') || localStorage.getItem('kiosk_device_id') || 'KIOSK-LOCAL';
el('device-label').textContent = deviceId;

function setStatus(kind, title, copy, label = 'Ready to check in', icon = '◎') {
  clearTimeout(state.resetTimer);
  el('state-icon').textContent = icon;
  el('state-label').textContent = label;
  el('state-title').innerHTML = title;
  el('state-copy').textContent = copy;
  frame.dataset.state = kind;
  el('student-result').hidden = true;
}

function setConnection(kind, label) {
  el('connection-dot').dataset.state = kind;
  el('connection-label').textContent = label;
}

function showResult(face, duplicate = false) {
  clearTimeout(state.resetTimer);
  el('student-result').hidden = false;
  const code = face.attendance_code || '';
  const labelByCode = {ON_TIME:'ON TIME',LATE_LEVEL_1:'LATE — LEVEL 1',LATE_ONE_PERIOD:'LATE — 1 PERIOD',ABSENT_TWO_PERIODS:'ABSENT — 2 PERIODS',ABSENT:'ABSENT',WRONG_CLASS:'WRONG CLASS'};
  const attendanceLabel = labelByCode[code] || (face.status === 'late' ? 'LATE' : face.status === 'absent' ? 'ABSENT' : 'ON TIME');
  const wrongClass = face.status === 'wrong_class' || code === 'WRONG_CLASS';
  el('result-label').textContent = wrongClass ? 'ATTENDANCE NOT RECORDED' : (duplicate ? 'ALREADY CHECKED IN' : (code === 'ON_TIME' ? 'ATTENDANCE CONFIRMED' : 'ATTENDANCE RESULT'));
  el('student-name').textContent = face.name || '—';
  el('student-id').textContent = face.student_id || '—';
  el('attendance-time').textContent = face.time_in || new Date().toLocaleTimeString('vi-VN', { hour12:false });
  el('state-icon').textContent = wrongClass ? '!' : (duplicate ? '↺' : '✓');
  el('state-label').textContent = wrongClass ? 'WRONG CLASS' : (duplicate ? 'EXISTING RECORD' : 'CONFIRMED');
  el('state-title').innerHTML = wrongClass ? 'You are in the<br>wrong class' : (duplicate ? 'Already<br>checked in' : `${attendanceLabel.replace(' — ', '<br>— ')}`);
  el('state-copy').textContent = wrongClass ? 'Your face was recognized, but you are not enrolled in this class session.' : (duplicate ? 'Your original check-in remains unchanged. No duplicate was created.' : (face.late_minutes ? `${face.late_minutes} minutes late.` : 'Your attendance has been recorded.'));
  state.resetTimer = setTimeout(() => setStatus('idle', 'Place your face<br>inside the guide', 'Look straight at the camera. Recognition starts automatically.'), 4200);
}

async function loadSession() {
  try {
    const requestedSession = new URLSearchParams(window.location.search).get('session_id');
    const response = requestedSession
      ? await fetch(`${API}/api/session/${encodeURIComponent(requestedSession)}/roster/`, { headers: kioskHeaders({ Accept:'application/json' }) })
      : await fetch(`${API}/api/sessions/today/`, { headers: kioskHeaders({ Accept:'application/json' }) });
    if (!response.ok) throw new Error('session');
    const payload = await response.json();
    const session = requestedSession
      ? (payload.session ? {
          ...payload.session,
          subject: payload.session.subject_name,
          classroom: payload.session.classroom,
        } : null)
      : (payload.data || []).find(item => item.status === 'active');
    state.session = session || null;
    if (!session) {
      el('session-label').textContent = 'No active session';
      setStatus('blocked', 'Attendance session<br>is not open', 'Please contact your lecturer to start the session.', 'SESSION INACTIVE', '—');
      el('retry-session').hidden = false;
      setConnection('offline', 'Waiting for session');
      return;
    }
    el('session-label').textContent = `SESSION ${session.session_id || `#${session.id}`}`;
    el('class-name').textContent = session.classroom || '—';
    el('subject-name').textContent = session.subject || '—';
    el('room-name').textContent = session.room || '—';
    setStatus('idle', 'Place your face<br>inside the guide', 'Look straight at the camera. Recognition starts automatically.');
    el('retry-session').hidden = true;
    setConnection('online', 'Connected');
  } catch (error) {
    state.session = null;
    setConnection('offline', 'Disconnected');
    setStatus('blocked', 'Unable to load<br>session', 'Check the server connection and try again.', 'BACKEND ERROR', '!');
    el('retry-session').hidden = false;
  }
}

async function startCamera() {
  // Browsers only expose the camera API on secure contexts. `localhost` and
  // `127.0.0.1` are treated as secure for local development, but a LAN URL
  // such as `http://192.168.x.x:8000` must be served over HTTPS.
  const localHost = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);
  if (!window.isSecureContext && !localHost) {
    return cameraFailed('Camera requires HTTPS on a network address. Open http://127.0.0.1:8000/kiosk/ on this computer, or use an HTTPS URL for other devices.');
  }
  if (!navigator.mediaDevices?.getUserMedia) return cameraFailed('This browser does not provide camera access. Use a current Chrome, Edge, or Firefox browser.');
  try {
    if (state.camera) state.camera.getTracks().forEach(track => track.stop());
    state.camera = await navigator.mediaDevices.getUserMedia({ video: { facingMode:'user', width:{ideal:1280}, height:{ideal:720} }, audio:false });
    video.srcObject = state.camera;
    el('camera-error').hidden = true;
    el('system-label').textContent = 'Camera ready';
    await video.play();
    resizeOverlay();
  } catch (error) {
    const message = error?.name === 'NotAllowedError'
      ? 'Camera permission was blocked. Allow camera access for this site, then press Retry camera.'
      : error?.name === 'NotFoundError'
        ? 'No camera was found. Connect a camera and close apps that may be using it.'
        : 'Unable to connect to the camera. Check browser permissions and Windows camera privacy settings.';
    cameraFailed(message);
  }
}

function cameraFailed(message = 'Unable to connect to the camera. Check browser permissions.') {
  el('camera-error').hidden = false;
  const copy = el('camera-error-copy');
  if (copy) copy.textContent = message;
  el('system-label').textContent = 'Camera unavailable';
  setStatus('error', 'Camera<br>unavailable', message, 'CAMERA ERROR', '!');
}

function resizeOverlay() { overlay.width = video.videoWidth || 1280; overlay.height = video.videoHeight || 720; }
function drawDetections(faces) {
  const ctx = overlay.getContext('2d'); ctx.clearRect(0,0,overlay.width,overlay.height);
  // The API receives a 640px-wide sample; map its coordinates back to the video.
  const sourceWidth = 640;
  const sourceHeight = Math.round(640 * (video.videoHeight || 720) / (video.videoWidth || 1280));
  const scaleX = overlay.width / sourceWidth;
  const scaleY = overlay.height / sourceHeight;
  faces.forEach(face => { if (!face.bbox || face.bbox.length < 4) return; const [x1,y1,x2,y2] = face.bbox; const known = face.name && face.name !== 'Unknown'; ctx.strokeStyle = known ? '#b8ef76' : '#ff806f'; ctx.lineWidth = Math.max(3, overlay.width / 420); ctx.strokeRect(x1*scaleX,y1*scaleY,(x2-x1)*scaleX,(y2-y1)*scaleY); });
}

async function recognize() {
  if (document.hidden || state.sending || !state.session || !video.videoWidth || video.readyState < 2) return;
  state.sending = true; const started = performance.now();
  try {
    const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = Math.round(640 * video.videoHeight / video.videoWidth); canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
    const response = await fetch(`${API}/api/recognize-face/`, { method:'POST', headers:kioskHeaders({'Content-Type':'application/json'}), body:JSON.stringify({ image:canvas.toDataURL('image/jpeg', .76), session_id:state.session.session_id || state.session.id, device_id:deviceId }) });
    const payload = await response.json(); el('latency-label').textContent = `${Math.round(performance.now()-started)} ms`;
    if (!response.ok || !payload.success) {
      const error = new Error(payload.error || `Server returned ${response.status}`);
      error.status = response.status;
      error.code = payload.code || '';
      throw error;
    }
    setConnection('online', 'Connected');
    const faces = payload.data?.recognized || []; drawDetections(faces);
    if (faces.length > 1) return setStatus('multiple', 'Please keep only<br>one person in frame', 'Wait until there is only one face inside the guide.', 'MULTIPLE FACES', '!');
    if (!faces.length) return setStatus('idle', 'Place your face<br>inside the guide', 'Look straight at the camera. Recognition starts automatically.');
    const face = faces[0];
    if (face.name === 'Unknown') return setStatus('unknown', 'Adjust your<br>position', face.quality?.message || 'Look straight at the camera.', 'FACE CHECK', '!');
    if (face.status === 'verifying') {
      const progress = face.verification || {};
      return setStatus('recognizing', 'Hold still<br>for verification', `${progress.hits || 0} of ${progress.required || 3} clear frames confirmed. Keep looking at the camera.`, 'VERIFYING', '…');
    }
    if (face.status === 'wrong_class' || face.attendance_code === 'WRONG_CLASS') return showResult(face, false);
    setStatus('recognizing', 'Verifying your<br>attendance', 'Checking your record against the current class session.', 'RECOGNIZING', '…');
    if (!face.attendance_code) return setStatus('unknown', 'Unable to confirm<br>identity', 'Please contact your lecturer.', 'NOT RECORDED', '!');
    showResult(face, Boolean(face.already_checked_in));
  } catch (error) {
    console.error('Kiosk recognition failed', error);
    const authFailure = error?.status === 401;
    const copy = authFailure
      ? 'Kiosk authentication failed. Reload the page or verify the kiosk key.'
      : (error?.message && error.message !== 'recognition'
          ? `Server could not confirm attendance: ${error.message}`
          : 'The server could not confirm attendance. Try again.');
    setConnection('offline', authFailure ? 'Authentication error' : 'Sync error');
    setStatus('error', 'Unable to<br>sync', copy, authFailure ? 'KIOSK AUTH ERROR' : 'SYNC ERROR', '!');
  }
  finally { state.sending = false; }
}

function clock() { const now = new Date(); el('clock').textContent = now.toLocaleTimeString('vi-VN',{hour12:false}); el('clock').dateTime = now.toISOString(); }
window.addEventListener('resize', resizeOverlay);
el('retry-camera').addEventListener('click', startCamera);
el('retry-session').addEventListener('click', loadSession);
document.addEventListener('visibilitychange', () => { if (!document.hidden && !state.timer) state.timer = setInterval(recognize, 900); });
clock(); setInterval(clock, 1000); loadSession(); startCamera(); state.timer = setInterval(recognize, 900);
