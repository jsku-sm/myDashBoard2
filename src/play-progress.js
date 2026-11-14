export const PLAY_TOPICS = ['함수의 뜻', '정의역과 치역', '합성함수', '역함수', '유리함수', '무리함수'];
const iso = () => new Date().toISOString();
const finite = n => Number.isFinite(n) ? Math.max(0, n) : 0;

export function playProgress(state) {
  if (!state.playLab) {
    const stages = {};
    const passed = Object.fromEntries(Object.entries(state.quizAnswers || {}).filter(([key, value]) => /^[0-5]$/.test(key) && value.correct).map(([key, value]) => [key, { at: value.at || iso(), migrated: true }]));
    if (Object.keys(passed).length) stages[1] = { passed, completedAt: Object.keys(passed).length === 6 ? iso() : null };
    state.playLab = { version: 1, learnerId: globalThis.crypto?.randomUUID?.() || `learner-${Date.now()}-${Math.random().toString(36).slice(2)}`, quiz: { stages, masteredAt: null }, games: {}, skills: {}, awards: {}, events: [], updatedAt: iso() };
    if (stages[1]?.completedAt) state.playLab.awards['quiz:1'] = { points: 100, at: stages[1].completedAt };
  }
  return state.playLab;
}
export function unlockedQuizLevel(state) {
  const p = playProgress(state);
  for (let level = 1; level <= 5; level++) if (!p.quiz.stages[level]?.completedAt) return level;
  return 5;
}
export const learningPoints = state => Object.values(playProgress(state).awards).reduce((sum, award) => sum + finite(award.points), 0);
function award(p, key, points, at) {
  if (p.awards[key]) return 0;
  p.awards[key] = { points, at }; return points;
}
function evidence(p, event) {
  p.events.push(event); if (p.events.length > 300) p.events.splice(0, p.events.length - 300);
  p.updatedAt = event.at;
}
function skill(p, title, correct, hint = false) {
  const s = p.skills[title] ||= { correct: 0, errors: 0, hints: 0 };
  if (hint) s.hints++; else if (correct) s.correct++; else s.errors++;
}
export function recordQuizOpen(state, level, topic, at = iso()) {
  if (level < 1 || level > unlockedQuizLevel(state) || topic < 0 || topic > 5) return false;
  const p = playProgress(state);
  p.quiz.startedAt ||= at; p.quiz.lastAt = at; p.quiz.activeLevel = level; p.quiz.activeTopic = topic; p.updatedAt = at;
  return true;
}
export function recordQuizAttempt(state, { level, topic, question, selected, correct, seconds = 0, at = iso() }) {
  const p = playProgress(state);
  if (!Number.isInteger(level) || level < 1 || level > unlockedQuizLevel(state) || !Number.isInteger(topic) || topic < 0 || topic > 5) return { accepted: false, points: 0 };
  const stage = p.quiz.stages[level] ||= { passed: {}, completedAt: null };
  stage.attempts = (stage.attempts || 0) + 1; stage.errors = (stage.errors || 0) + (correct ? 0 : 1); stage.seconds = (stage.seconds || 0) + finite(seconds);
  if (correct && !stage.passed[topic]) stage.passed[topic] = { at, attempts: stage.attempts };
  skill(p, PLAY_TOPICS[topic], correct);
  evidence(p, { type: correct ? 'quiz-correct' : 'quiz-error', activity: '개념 퀴즈', level, skill: PLAY_TOPICS[topic], question: String(question).slice(0, 500), selected: String(selected).slice(0, 200), seconds: finite(seconds), at });
  let points = 0, completed = false, mastered = false;
  if (!stage.completedAt && Object.keys(stage.passed).length === 6) {
    stage.completedAt = at; completed = true; points += award(p, `quiz:${level}`, level * 100, at);
    if (level === 5) { p.quiz.masteredAt = at; mastered = true; points += award(p, 'quiz:master', 300, at); }
  }
  return { accepted: true, points, completed, mastered, nextLevel: Math.min(5, level + 1) };
}

export function recordGameEvent(state, event) {
  const p = playProgress(state), at = event.at || iso();
  const g = p.games[event.game] ||= { title: event.title || event.game, starts: 0, clears: 0, wins: 0, errors: 0, successes: 0, hints: 0, seconds: 0, status: 'ready' };
  if (event.type === 'start' && g.runId !== event.runId) { g.starts++; g.runId = event.runId; g.runElapsed = 0; g.status = 'playing'; }
  if (g.runId !== event.runId) return { points: 0 };
  g.seconds += Math.max(0, finite(event.elapsed) - finite(g.runElapsed)); g.runElapsed = Math.max(finite(g.runElapsed), finite(event.elapsed));
  g.stage = event.stage || g.stage || 1; g.stageCount = event.stageCount || g.stageCount || 3;
  g.lastAt = at; g.lastSkill = event.skill || g.lastSkill || g.title;
  if (event.type === 'pause' || event.type === 'leave') g.status = 'paused';
  if (event.type === 'wait') g.status = 'between';
  if (event.type === 'resume' || event.type === 'heartbeat') g.status = 'playing';
  if (event.type === 'error') { g.errors++; skill(p, g.lastSkill, false); }
  if (event.type === 'success') { g.successes++; skill(p, g.lastSkill, true); }
  if (event.type === 'hint') { g.hints++; skill(p, g.lastSkill, false, true); }
  let points = 0;
  if (event.type === 'clear') {
    points = award(p, `game:${event.game}:${event.runId}:${event.stage}`, Math.round(300 / g.stageCount * (event.mode === 'challenge' ? 1.2 : 1)), at);
    if (points) { g.clears++; g.lastClearAt = at; }
  }
  if (event.type === 'win' && g.finishedRun !== event.runId) { g.wins++; g.finishedRun = event.runId; g.status = 'complete'; }
  if (event.type === 'retry') g.status = 'retry';
  g.lastMessage = event.message || g.lastMessage || '';
  if (event.type !== 'heartbeat') evidence(p, { type: `game-${event.type}`, activity: g.title, level: g.stage, skill: g.lastSkill, question: String(event.question || '').slice(0, 500), message: String(event.message || '').slice(0, 500), points, at });
  else p.updatedAt = at;
  return { points };
}

export function playSummary(state, now = Date.now()) {
  const p = playProgress(state), games = Object.values(p.games), skills = Object.entries(p.skills);
  const strengths = skills.filter(([, s]) => s.correct >= 3 && s.correct / Math.max(1, s.correct + s.errors) >= .75).sort((a, b) => b[1].correct - a[1].correct);
  const needsHelp = skills.filter(([, s]) => s.errors >= 2 && s.errors >= s.correct || s.hints >= 3).sort((a, b) => b[1].errors - a[1].errors);
  const active = games.find(g => g.status === 'playing' && now - Date.parse(g.lastAt) < 90000);
  const recent = [...games].sort((a, b) => (b.lastAt || '').localeCompare(a.lastAt || ''))[0];
  const quizEvents = p.events.filter(e => e.type.startsWith('quiz-'));
  const lastQuiz = quizEvents.at(-1), latest = [recent?.lastAt, lastQuiz?.at].filter(Boolean).sort().at(-1);
  const quizDate = [lastQuiz?.at, p.quiz.lastAt].filter(Boolean).sort().at(-1);
  const quizRecent = quizDate && (!recent || quizDate > recent.lastAt);
  const stages = Object.values(p.quiz.stages).filter(s => s.completedAt).length;
  return { points: learningPoints(state), games, strengths, needsHelp, stages, mastered: !!p.quiz.masteredAt, participated: !!(games.some(g => g.starts) || p.quiz.startedAt || quizEvents.length || stages),
    status: active ? '플레이 중' : quizRecent ? p.quiz.masteredAt ? '마스터 완료' : '퀴즈 학습' : recent ? ({ paused: '일시정지', between: '다음 단계 대기', retry: '재도전 필요', complete: '게임 완료', playing: '최근 플레이' })[recent.status] || '탐구 중' : stages ? '퀴즈 학습' : '참여 전',
    current: quizRecent ? `개념 퀴즈 · ${p.quiz.activeLevel || lastQuiz?.level || 1}단계 · ${PLAY_TOPICS[p.quiz.activeTopic] || lastQuiz?.skill || ''}` : recent ? `${recent.title} · ${recent.stage}/${recent.stageCount}단계` : stages ? `개념 퀴즈 · ${unlockedQuizLevel(state)}단계` : '아직 시작하지 않았어요', latest: [latest, quizDate].filter(Boolean).sort().at(-1) };
}
export function rankLearners(entries) {
  const rows = entries.map(entry => ({ ...entry, summary: playSummary(entry.state), points: learningPoints(entry.state) })).sort((a, b) => b.points - a.points || a.name.localeCompare(b.name, 'ko'));
  let rank = 0, previous = null;
  rows.forEach((row, i) => { if (row.points !== previous) rank = i + 1; row.rank = rank; previous = row.points; });
  return rows;
}
export function createPlayReport(state, profile) {
  return { app: 'goodssaem-play-lab', version: 1, exportedAt: iso(), learner: { id: playProgress(state).learnerId, name: state.studentName || profile.name, className: profile.className }, playLab: structuredClone(playProgress(state)) };
}
export function parsePlayReport(text) {
  if (text.length > 2000000) throw Error('2MB 이하의 학습 기록 파일을 선택해 주세요.');
  const report = JSON.parse(text);
  if (['id', 'name', 'className'].some(key => typeof report.learner?.[key] !== 'string' || !report.learner[key].trim() || report.learner[key].length > 150)) throw Error('학생 이름과 학급 정보가 올바르지 않아요.');
  if (report.app !== 'goodssaem-play-lab' || report.version !== 1 || !report.learner?.id || !report.learner?.name || !report.learner?.className || report.playLab?.version !== 1 || !report.playLab?.quiz?.stages || !report.playLab?.awards || !report.playLab?.games || !report.playLab?.skills || !Array.isArray(report.playLab?.events) || report.playLab.learnerId !== report.learner.id) throw Error('MATH PLAY LAB 학습 기록 파일이 아니에요.');
  if (!Number.isFinite(Date.parse(report.playLab.updatedAt)) || report.playLab.events.length > 300 || Object.values(report.playLab.awards).some(a => !Number.isFinite(a.points) || a.points < 0 || a.points > 1000)) throw Error('학습 기록의 점수 또는 날짜를 확인해 주세요.');
  if (Object.entries(report.playLab.quiz.stages).some(([level, s]) => !/^[1-5]$/.test(level) || !s.passed || Object.keys(s.passed).some(t => !/^[0-5]$/.test(t)))) throw Error('단계 기록이 올바르지 않아요.');
  if (Object.values(report.playLab.skills).some(s => !s || ['correct', 'errors', 'hints'].some(k => !Number.isFinite(s[k]) || s[k] < 0)) || Object.values(report.playLab.games).some(g => !g || ['starts', 'clears', 'wins', 'errors', 'successes', 'hints', 'seconds'].some(k => !Number.isFinite(g[k]) || g[k] < 0)) || report.playLab.events.some(e => !e || typeof e.type !== 'string' || !Number.isFinite(Date.parse(e.at)))) throw Error('학습 활동 기록이 올바르지 않아요.');
  return report;
}
export function mergePlayReports(reports, incoming) {
  const index = reports.findIndex(r => r.learner.id === incoming.learner.id);
  if (index >= 0 && reports[index].playLab.updatedAt >= incoming.playLab.updatedAt) return false;
  if (index >= 0) reports[index] = incoming; else reports.push(incoming);
  return true;
}
