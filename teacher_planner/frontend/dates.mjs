// UTC arithmetic preserves calendar dates regardless of browser timezone/DST.
export const iso = d => d.toISOString().slice(0,10);
export const parse = s => new Date(s+'T12:00:00Z');
export const addDays = (s,n) => {const d=parse(s);d.setUTCDate(d.getUTCDate()+n);return iso(d);};
export const weekday = s => (parse(s).getUTCDay()+6)%7;
export const weekStart = s => addDays(s,-weekday(s));
export const weekDates = s => Array.from({length:7},(_,i)=>addDays(weekStart(s),i));
export const monthDays = s => {const start=weekStart(s.slice(0,7)+'-01');return Array.from({length:42},(_,i)=>addDays(start,i));};
export const addMonths = (s,n) => {const d=parse(s.slice(0,7)+'-01');d.setUTCMonth(d.getUTCMonth()+n);return iso(d);};
export const monthLabel = s => `${Number(s.slice(0,4))}년 ${Number(s.slice(5,7))}월`;
export const dayLabel = s => `${Number(s.slice(5,7))}.${Number(s.slice(8,10))} (${['월','화','수','목','금','토','일'][weekday(s)]})`;
export const validRange = s => /^\d{4}-\d{2}-\d{2}$/.test(s) && s>='2000-01-01' && s<='2100-12-31' && !isNaN(parse(s)) && iso(parse(s))===s;
export function project(data) {
 const events=[];
 for(const r of data.lessons||[]) {
  if(r.deleted_at)continue;
  if(r.content)events.push({key:'lesson:'+r.id,kind:'lesson',type:'lesson',id:r.id,revision:r.revision,date:r.date,period:r.period,title:r.content,status:r.status,cls:r.class,subject:r.subject,row:r});
  if(r.assessment_title)events.push({key:'assessment:'+r.id,kind:'assessment',type:'assessment',id:r.id,revision:r.revision,date:r.assessment_date,period:r.assessment_period,title:r.assessment_title,status:r.assessment_status,cls:r.class,subject:r.subject,row:r});
 }
 for(const r of data.diary||[])if(!r.deleted_at)events.push({key:'diary:'+r.id,kind:'diary',type:r.kind,id:r.id,revision:r.revision,date:r.date,period:'미정',title:r.title,time:r.time,status:r.done==='1'?'완료':'예정',important:r.important==='1',row:r});
 return events.sort((a,b)=>(a.date||'9999').localeCompare(b.date||'9999')||(a.time||a.period).localeCompare(b.time||b.period)||a.id.localeCompare(b.id));
}
