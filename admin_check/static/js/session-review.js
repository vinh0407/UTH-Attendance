(() => {
  'use strict';
  const root = document.getElementById('session-review');
  if (!root) return;
  const byId = id => document.getElementById(id);
  const dialog = byId('review-dialog');
  const form = byId('review-form');
  const endpoint = `/api/session/${root.dataset.sessionId}/review/`;
  let selected = null;
  let saving = false;
  let loading = false;
  let lastSnapshot = '';

  function cell(row, text) {
    const td = document.createElement('td');
    td.textContent = text;
    row.append(td);
    return td;
  }

  function edit(student) {
    selected = student;
    form.reset();
    byId('review-student').textContent = `${student.student_id} · ${student.name}`;
    byId('review-outcome').value = student.record.attendance_code === 'ABSENT' ? 'absent' : 'checked_in';
    byId('review-time').value = student.record.check_in_time || '';
    byId('review-error').textContent = '';
    updateTime();
    dialog.showModal();
    byId('review-outcome').focus();
  }

  function render(data) {
    const fragment = document.createDocumentFragment();
    for (const student of data.students) {
      const row = document.createElement('tr');
      cell(row, `${student.student_id} · ${student.name}`);
      cell(row, student.record.attendance_label || 'Not checked in');
      cell(row, student.record.check_in_time || '—');
      cell(row, student.record.late_minutes == null ? '—' : `${student.record.late_minutes} min`);
      cell(row, student.record.attendance_periods == null ? '—' : String(student.record.attendance_periods));
      cell(row, student.record.device_id || '—');
      cell(row, student.similarity == null ? '—' : `${student.similarity.toFixed(1)} / 100`);
      const history = cell(row, student.record.method || '—');
      if (student.audit.length) {
        history.textContent = '';
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = `${student.audit.length} correction(s)`;
        const list = document.createElement('ol');
        for (const audit of student.audit) {
          const item = document.createElement('li');
          item.textContent = `${audit.before.attendance_label || 'No record'} → ${audit.after.attendance_label}. ${audit.reason} — ${audit.by}, ${new Date(audit.at).toLocaleString()}`;
          list.append(item);
        }
        details.append(summary, list);
        history.append(details);
      }
      const action = cell(row, '');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'button button-secondary';
      button.textContent = 'Correct';
      button.setAttribute('aria-label', `Correct attendance for ${student.name}`);
      button.disabled = ['cancelled', 'postponed'].includes(data.status);
      button.addEventListener('click', () => edit(student));
      action.append(button);
      fragment.append(row);
    }
    if (!data.students.length) {
      const row = document.createElement('tr');
      const empty = cell(row, 'No students are enrolled in this class.');
      empty.colSpan = 9;
      empty.className = 'review-empty';
      fragment.append(row);
    }
    byId('review-rows').replaceChildren(fragment);
    const count = byId('session-present-count');
    if (count) count.textContent = data.summary.checked_in;
  }

  async function refresh() {
    if (loading || saving || dialog.open || document.hidden) return;
    loading = true;
    try {
      const response = await fetch(endpoint, {headers: {Accept: 'application/json'}, cache: 'no-store'});
      if (!response.ok) throw new Error('Unable to update records. Check your connection or sign in again.');
      const payload = await response.json();
      const signature = JSON.stringify(payload.data);
      if (signature !== lastSnapshot) { render(payload.data); lastSnapshot = signature; }
      byId('review-status').textContent = `${payload.data.summary.checked_in} present / late of ${payload.data.summary.total} students · Updates every 5 seconds`;
    } catch (error) { byId('review-status').textContent = error.message; }
    finally { loading = false; }
  }

  function updateTime() {
    const absent = byId('review-outcome').value === 'absent';
    byId('review-time').disabled = absent;
    byId('review-time').required = !absent;
  }
  const close = () => { if (!saving) dialog.close(); };
  byId('review-close').addEventListener('click', close);
  byId('review-cancel').addEventListener('click', close);
  dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
  byId('review-outcome').addEventListener('change', updateTime);
  byId('review-refresh').addEventListener('click', refresh);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (saving || !selected || !form.reportValidity()) return;
    saving = true;
    byId('review-save').disabled = true;
    byId('review-error').textContent = '';
    try {
      const response = await fetch(`${endpoint}${selected.id}/`, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.elements.csrfmiddlewaretoken.value},
        body: JSON.stringify({outcome: byId('review-outcome').value, check_in_time: byId('review-time').value, reason: byId('review-reason').value}),
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) throw new Error(payload.error || 'Unable to save correction.');
      dialog.close();
    } catch (error) { byId('review-error').textContent = error.message; }
    finally { saving = false; byId('review-save').disabled = false; }
    if (!dialog.open) await refresh();
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  refresh();
  setInterval(refresh, 5000);
})();
