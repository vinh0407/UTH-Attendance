import {esc} from './portal-utils.mjs';
export function facultyDetails(contact = {}, fallback = '') {
  const name=contact.name || fallback || 'Instructor not assigned';
  const email=contact.email || '';
  const phone=contact.phone || '';
  const emailValue=email?`<a href="mailto:${esc(encodeURIComponent(email))}">${esc(email)}</a>`:'Not updated';
  const phoneValue=/^\+?[0-9 ()-]+$/.test(phone)&&!phone.startsWith('000')?`<a href="tel:${esc(phone.replace(/[ ()-]/g,''))}">${esc(phone)}</a>`:esc(phone||'Not updated');
  return `<details class="faculty-details"><summary><i class="ph ph-chalkboard-teacher" aria-hidden="true"></i><span>Instructor Info<strong>${esc(name)}</strong></span><i class="ph ph-caret-down" aria-hidden="true"></i></summary><dl><div><dt>Full Name</dt><dd>${esc(name)}</dd></div><div><dt>Department</dt><dd>${esc(contact.department||'Not updated')}</dd></div><div><dt>Email</dt><dd>${emailValue}</dd></div><div><dt>Phone</dt><dd>${phoneValue}</dd></div><div><dt>Office</dt><dd>${esc(contact.office||'Not updated')}</dd></div></dl>${contact.bio?`<p>${esc(contact.bio)}</p>`:''}</details>`;
}
