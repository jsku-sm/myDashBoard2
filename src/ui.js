import katex from 'katex';
import 'katex/dist/katex.min.css';

export const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const math = (tex, displayMode = false) => katex.renderToString(tex, { throwOnError: false, displayMode, trust: false, strict: 'ignore' });
const paths = {
 home:'m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z',
 book:'M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H3V4h1Zm9 3a3 3 0 0 1 3-3h5v15h-5a3 3 0 0 0-3 2',
 sheet:'M14 2H5a1 1 0 0 0-1 1v18h16V8Zm0 0v6h6M8 12h8M8 16h6',
 graph:'M4 3v17h17M7 15l4-6 4 3 5-7',
 quiz:'m13 2-9 12h7l-1 8 10-13h-7Z',
 note:'M12 4H4v16h16v-8M9 15l1-5L19 1l4 4-9 9Z',
 chat:'M21 11a9 9 0 0 1-9 9H4l-3 2 2-7a9 9 0 1 1 18-4ZM8 10h8M8 14h5',
 growth:'M4 19h3v-5H4Zm7 0h3V9h-3Zm7 0h3V3h-3',
 arrow:'M4 12h16m-6-6 6 6-6 6',
 chevron:'m9 5 7 7-7 7',
 bell:'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
 check:'m5 12 4 4L20 5',
 clock:'M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
 target:'M22 12a10 10 0 1 1-10-10m5 1-5 9m5-9 1 5 5-1M17 12a5 5 0 1 1-5-5',
 spark:'m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3ZM20 1v4m-2-2h4',
 settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM9 2h6l1 4 4 1 2 5-3 3v5l-5 2-3-3H6l-3-5 2-4-1-4Z',
 teacher:'M3 3h18v13H9M7 8a3 3 0 1 1-6 0 3 3 0 0 1 6 0M1 21v-5a3 3 0 0 1 6 0v5m0-7 5-4',
 lock:'M6 10V7a6 6 0 0 1 12 0v3M4 10h16v12H4Zm8 5v3',
 download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
 reset:'M3 10a9 9 0 1 1 2 9M3 3v7h7',
 close:'m6 6 12 12M6 18 18 6',
 heart:'M20 5c-3-3-7 0-8 2-1-2-5-5-8-2s-2 7 8 15c10-8 11-12 8-15Z',
 eye:'M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12Zm14 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
 folder:'M2 6V3h7l3 3h10v15H2Z',
 menu:'M4 6h16M4 12h16M4 18h16',
 sun:'M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0'
};
export const icon = (name, cls = '') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.spark}"/></svg>`;
export const actionButton = (label, action, cls = '', attrs = '') => `<button type="button" class="btn ${cls}" data-action="${action}" ${attrs}>${label}</button>`;
export function toast(message) {
 let region = document.getElementById('toast');
 if (!region) { region = document.createElement('div'); region.id = 'toast'; region.setAttribute('role','status'); document.body.append(region); }
 region.textContent = message; region.classList.add('visible'); clearTimeout(toast.timer); toast.timer = setTimeout(() => region.classList.remove('visible'), 3200);
}
export const localDate = value => new Intl.DateTimeFormat('ko-KR', {month:'long',day:'numeric',timeZone:'Asia/Seoul'}).format(value ? new Date(value) : new Date());
export function saveDownload(content, filename, type='application/json') {
 const url=URL.createObjectURL(new Blob([content],{type})); const link=document.createElement('a'); link.href=url; link.download=filename; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
