export const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const dateLabel = value => value ? new Intl.DateTimeFormat('en-US', {month:'short',day:'numeric',year:'numeric'}).format(new Date(value+'T12:00:00')) : '—';
export const normalize = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase();
export function nextLesson(rows, minutes) {
  return rows.filter(r => !['cancelled','postponed','completed'].includes(r.session_status)).map(r => {
    const times = (r.time_range || '').match(/\d{1,2}:\d{2}/g) || [];
    const toMinutes = t => t ? Number(t.split(':')[0])*60+Number(t.split(':')[1]) : -1;
    return {...r, start:toMinutes(times[0]), end:toMinutes(times[1])};
  }).filter(r => r.end > minutes).sort((a,b)=>a.start-b.start)[0] || null;
}
export function weekDates(today) {
 const d=new Date(today+'T12:00:00'); d.setDate(d.getDate()-((d.getDay()+6)%7));
 return Array.from({length:7},(_,i)=>{const t=new Date(d);t.setDate(t.getDate()+i);return [t.getFullYear(),String(t.getMonth()+1).padStart(2,'0'),String(t.getDate()).padStart(2,'0')].join('-');});
}
export const attendanceLabel = r => ({
  ON_TIME: 'On time',
  LATE_LEVEL_1: 'Late',
  LATE_ONE_PERIOD: 'Late · 1 period',
  ABSENT_TWO_PERIODS: '2 periods counted',
  ABSENT: 'Absent',
  EXCUSED: 'Excused absence'
}[r.attendance_code] || {
  present: 'On time',
  late: 'Late',
  absent: 'Absent',
  excused: 'Excused absence'
}[r.status] || 'Unknown');
export const tone = r => ({present:'success',late:'warning',absent:'danger',excused:'neutral'}[r.status] || 'neutral');
