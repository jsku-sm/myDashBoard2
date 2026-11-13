import { COMMON2_GAMES, common2Art } from './common2-data.js';
import { escapeHTML as esc, icon, actionButton as button } from './ui.js';
import { compileFormula, shuffle, clamp, number, valueMission, createDomainMaze, trajectory } from './arcade-math.js';

import { NEW_ARCADE_GAMES, setupTerritory, territoryProgress, moveTerritory, updateTerritory, drawTerritory } from './set-logic-arcade.js';

import { ROOT_GAMES, tileNumber } from './root-arcade-data.js';
import { ARCADE_THEMES, createArcadeAudio, ARCADE_AUDIO_KEY } from './arcade-audio.js';
import { createVariantPicker } from './practice-random.js';
import { createArcadeContent, GAME_VARIANTS } from './arcade-generator.js';
import { recordGameEvent } from './play-progress.js';

const W = 800, H = 500;
export const GAMES = [
  { id: 'bubble', title: '함수 버블팝', genre: '버블슈터', topic: '함숫값 · 역함수', tag: '조준하고 팡!', desc: '함숫값을 계산하고 정답 버블을 맞혀요. 연결된 버블이 한꺼번에 팡!', controls: '마우스로 조준 후 클릭 · ← → 조준 · Space 발사', goal: '정답 버블을 맞혀 모든 버블을 없애세요. 같은 값으로 연결된 버블과 천장에 연결되지 않은 버블이 함께 사라져요.', lesson: '계산한 출력값이 바로 조준할 목표예요. 함숫값, 역함수, 합성함수를 번갈아 만나 봐요.' },
  { id: 'invaders', title: '합성함수 갤럭시', genre: '우주 슈팅', topic: '합성함수 · 역함수', tag: '계산하고 발사!', desc: '움직이는 정답 우주선을 격추해요. 적의 탄환을 피하며 지구를 지켜요.', controls: '← → 또는 A D 이동 · Space 발사 · 화면 터치로 이동·발사', goal: '현재 문제의 답이 적힌 우주선을 6번 맞히세요. 다른 우주선이나 적의 탄환에 닿으면 실드가 줄어요.', lesson: '합성함수는 안쪽부터 계산하고, 역함수는 출력을 만드는 입력을 찾아요.' },
  { id: 'maze', title: '정의역 미로 탈출', genre: '미로 탐험', topic: '유리함수 · 무리함수', tag: '조건을 찾아 탈출!', desc: '정의역에 속하는 숫자 발판만 밟고, 열쇠 3개를 모아 출구로 가요.', controls: '방향키 또는 W A S D · 화면의 방향 버튼', goal: '각 칸의 수를 x에 넣어도 식이 정의되는지 판단하세요. 안전한 길로 열쇠 3개를 모으면 출구가 열려요. 총 3개 미로에 도전해요.', lesson: '분모는 0이 될 수 없고, 제곱근 안의 수는 0 이상이어야 해요.' },
  { id: 'marble', title: '그래프 마블 슬라이드', genre: '그래프 퍼즐', topic: '함수식 · 계수 · 그래프', tag: '내가 그린 길 위로!', desc: '함수식을 직접 입력하고 계수를 조절해, 구슬이 별을 모으는 길을 만들어요.', controls: '함수식 입력 · a, b, c 슬라이더 · 구슬 굴리기', goal: '구슬은 표시된 출발점에서 중력에 따라 굴러가요. 별 3개를 모두 지나 도착점으로 이어지는 내리막을 만드세요. 총 3개 코스예요.', lesson: '식을 바꾸면 길이 바뀌어요. 기울기, y절편, 이차항의 계수와 루트 그래프를 탐구해요.' },
  { id: 'shot', title: '포물선 버드', genre: '탄도 퍼즐', topic: '이차함수 · 포물선', tag: '각도와 속력의 실험!', desc: '발사 각도와 속력을 바꾸어 벽을 넘고, 포물선 궤적으로 목표를 맞혀요.', controls: '각도·속력 슬라이더 · 화면에서 각도 조준 · 발사', goal: '예측선을 살피고 각도와 속력을 조절해 목표를 맞히세요. 벽에 부딪히지 않도록 높이도 고려해요. 총 3개 스테이지예요.', lesson: '중력이 일정할 때 탄도는 아래로 열린 포물선이에요. 각도와 속력이 이차함수의 계수를 바꿔요.' },
  { id: 'memory', title: '함수 메모리 카드', genre: '카드 뒤집기', topic: '그래프 · 정의역 · 함수', tag: '기억하고 연결!', desc: '매번 새로운 식과 그래프, 정의역, 계산 결과를 짝지으며 개념을 연결해요.', controls: '카드 클릭·터치 · Tab으로 카드 선택 후 Enter', goal: '카드 2장을 뒤집어 수학적으로 연결되는 짝을 찾으세요. 6쌍을 모두 찾으면 성공! 도전 모드에서는 18번 안에 찾아야 해요.', lesson: '그림, 식, 조건은 같은 함수를 표현하는 여러 방법이에요. 짝의 이유도 함께 확인해요.' }
];
GAMES.push(...NEW_ARCADE_GAMES, ...ROOT_GAMES, ...COMMON2_GAMES);
const marbleGame = id => ['marble','root-marble'].includes(id);
const mazeGame = id => ['maze','root-maze'].includes(id);
const memoryGame = id => ['memory', 'set-memory', 'logic-memory'].includes(id);
const shooterGame = id => ['invaders', 'counter'].includes(id);
const gameById = id => GAMES.find(g => g.id === id);
const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

export function gameArt(id) {
  if (COMMON2_GAMES.some(g => g.id === id)) return common2Art(id);
  const rootRailArt=id==='root-marble',rootMazeArt=id==='root-maze';
  if(id==='root-marble')id='marble';
  if(id==='root-maze')id='maze';
  const memoryLabels=id==='set-memory'?['∩','?','∪','?']:id==='logic-memory'?['⇒','?','¬','?']:['f(x)','?','↗','?'];
  if (id === 'counter') id = 'invaders';
  if (memoryGame(id)) id = 'memory';
  const start = '<svg viewBox="0 0 320 150" aria-hidden="true" fill="none">';
  const grid = '<path d="M20 30H300M20 60H300M20 90H300M20 120H300M50 10V140M100 10V140M150 10V140M200 10V140M250 10V140" stroke="currentColor" opacity=".10"/>';
  const text = (x, y, t) => `<text x="${x}" y="${y}" fill="currentColor" text-anchor="middle" font-family="sans-serif" font-size="15" font-weight="700">${t}</text>`;
  let content = '';
  if (id === 'bubble') content = [0, 1, 2].map(r => [0, 1, 2, 3, 4, 5].map(c => `<circle cx="${58 + c * 40 + r % 2 * 20}" cy="${29 + r * 34}" r="17" fill="currentColor" opacity="${.12 + (c % 3) * .12}"/>${text(58 + c * 40 + r % 2 * 20, 34 + r * 34, [3, 5, 7][Math.floor(c / 2)])}`).join('')).join('') + '<path d="m160 140 29-34" stroke="currentColor" stroke-width="3" stroke-dasharray="4 5"/><circle cx="160" cy="137" r="11" fill="currentColor"/>';
  if (id === 'invaders') content = [72, 160, 248].map((x, i) => `<path d="m${x - 18} 47 6-12h24l6 12v14h-8v-8h-20v8h-8Z" fill="currentColor" opacity="${i === 1 ? .9 : .35}"/>${text(x, 86, [6, 9, 12][i])}`).join('') + '<path d="m160 112-15 24h30Z" fill="currentColor"/><path d="M160 104V94M151 145v-6m18 6v-6" stroke="currentColor" stroke-width="3"/>';
  if (id === 'maze') content = '<path d="M55 122V25h210v97H95V65h130v26h-80" stroke="currentColor" stroke-width="10" opacity=".22"/><path d="M71 123V42h177v63H113V82h88" stroke="currentColor" stroke-width="2" stroke-dasharray="4 6"/><circle cx="71" cy="123" r="10" fill="currentColor"/>' + text(112, 35, rootMazeArt?'x ≥ 7/2':'x ≠ 2') + text(205, 88, '✦');
  if (id === 'marble') content = '<path d="M35 28C100 40 124 125 282 121" stroke="currentColor" stroke-width="4"/><circle cx="87" cy="46" r="11" fill="currentColor"/>' + text(135, 75, '✦') + text(204, 114, '✦') + text(183, 31, rootRailArt?'y = a√(x-b) + c':'y = ax² + bx + c') + '<path d="M280 106v24m0-24 16 6-16 5" stroke="currentColor" stroke-width="2"/>';
  if (id === 'shot') content = '<path d="M35 127Q160-80 282 115" stroke="currentColor" stroke-width="3" stroke-dasharray="6 6"/><circle cx="99" cy="49" r="12" fill="currentColor"/><path d="m37 131-6-19m6 19 10-17M180 130V91h19v39" stroke="currentColor" stroke-width="5" opacity=".55"/><circle cx="281" cy="115" r="15" stroke="currentColor" stroke-width="4"/>' + text(231, 37, '45°');
  if (id === 'territory') content = '<rect x="45" y="20" width="230" height="110" rx="7" stroke="currentColor" opacity=".3"/><circle cx="135" cy="75" r="42" stroke="currentColor" opacity=".45"/><circle cx="185" cy="75" r="42" fill="currentColor" opacity=".15"/><path d="M45 109h74V41h80v89" stroke="currentColor" stroke-width="3" stroke-dasharray="4 4"/><circle cx="199" cy="130" r="7" fill="currentColor"/>';
  if (id === 'memory') content = [0, 1, 2, 3].map((i) => `<rect x="${42 + i * 61}" y="${i % 2 ? 40 : 26}" width="52" height="78" rx="9" fill="currentColor" opacity="${i % 2 ? '.12' : '.25'}"/>${text(68 + i * 61, i % 2 ? 87 : 73, memoryLabels[i])}`).join('');
  return `${start}${grid}${content}</svg>`;
}

function cardGraph(model) {
  const line = model.kind === 'line';
  const fn = line ? x => model.a * x + model.b : x => (x - model.h) ** 2 + model.k;
  const points = line ? [[0, model.b], [1, model.a + model.b]] : [[model.h, model.k], [model.h + 1, model.k + 1]];
  const xmin = Math.min(-2, ...points.map(p => p[0] - 1)), xmax = Math.max(3, ...points.map(p => p[0] + 1));
  const ymin = Math.min(-2, ...points.map(p => p[1] - 2)), ymax = Math.max(5, ...points.map(p => p[1] + 2));
  const px = x => 9 + (x - xmin) / (xmax - xmin) * 110, py = y => 87 - (y - ymin) / (ymax - ymin) * 77;
  let path = '';
  for (let x = xmin; x <= xmax; x += .04) path += `${path ? 'L' : 'M'}${px(x).toFixed(1)} ${py(fn(x)).toFixed(1)} `;
  const description = points.map(([x, y]) => `(${x},${y})`).join('과 ');
  return `<svg class="arc-card-graph" viewBox="0 0 130 100" role="img" aria-label="${esc(description)}을 지나는 ${line ? '직선' : '포물선'}"><path d="M8 ${py(0)}H126M${px(0)} 4V96" stroke="#9aaec1"/><path d="${path}" fill="none" stroke="#38bdaa" stroke-width="2.5"/>${points.map(([x, y]) => `<circle cx="${px(x)}" cy="${py(y)}" r="3" fill="#efb45b"/><text x="${Math.min(93, px(x) + 4)}" y="${py(y) - 7}" fill="#d8e8ee" font-size="9">(${x},${y})</text>`).join('')}</svg>`;
}

export function createMathArcade(api) {
  const nextVariant = createVariantPicker();
  const marbleLevels = (s = session) => s.content.marbleLevels;
  const domainLevels = (s = session) => s.content.domainLevels;
  const shotLevels = (s = session) => s.content.shotLevels;
  const memoryPairs = (s = session) => s.content.pairs;
  const territoryLevels = (s = session) => s.content.territoryLevels;
  let selected = null, difficulty = 'relaxed', session = null, sessionOwner = null, gameCategory = 'all';
  let root = null, canvas = null, ctx = null, frame = 0, last = 0, controller = null;
  const keys = new Set();
  const records = () => api.state.arcadeRecords || {};
  const audio = createArcadeAudio({ onChange: syncSoundControls });

  function soundPanel() {
    return `<section class="arc-audio" aria-label="게임 소리 설정"><div class="arc-audio-title"><strong>♫ 게임 사운드</strong><small id="arc-audio-theme"></small></div><div class="arc-audio-controls"><button type="button" data-action="arcade-audio-music" data-audio-channel="music"></button><button type="button" data-action="arcade-audio-effects" data-audio-channel="effects"></button><label class="arc-audio-volume" for="arc-audio-volume"><span>음량 <output id="arc-audio-level"></output></span><input id="arc-audio-volume" data-arc-volume type="range" min="0" max="100" step="1" aria-label="게임 전체 음량"/></label><button type="button" data-action="arcade-audio-enable" hidden>소리 켜기</button></div></section>`;
  }
  function syncSoundControls() {
    if (!root) return;
    const settings = audio.settings, status = audio.status;
    for (const channel of ['music', 'effects']) {
      const control = root.querySelector(`[data-audio-channel="${channel}"]`);
      if (!control) continue;
      const label = channel === 'music' ? '음악' : '효과음';
      control.textContent = `${label} ${settings[channel] ? '켜짐' : '꺼짐'}`;
      control.setAttribute('aria-pressed', String(settings[channel]));
      control.setAttribute('aria-label', `${channel === 'music' ? '배경음악' : label} ${settings[channel] ? '끄기' : '켜기'}`);
      control.disabled = !status.supported;
    }
    const volume = root.querySelector('#arc-audio-volume'), level = root.querySelector('#arc-audio-level');
    if (volume) { volume.value = Math.round(settings.volume * 100); volume.disabled = !status.supported; }
    if (level) level.textContent = `${Math.round(settings.volume * 100)}%`;
    const title = root.querySelector('#arc-audio-theme');
    if (title) title.textContent = !status.supported ? '이 브라우저에서는 소리를 지원하지 않아요.' : selected ? ARCADE_THEMES[selected].name : '게임마다 다른 음악 · 설정 자동 저장';
    const enable = root.querySelector('[data-action="arcade-audio-enable"]');
    if (enable) enable.hidden = !status.supported || status.ready || session?.phase !== 'playing' || !settings.volume || (!settings.music && !settings.effects);
  }
  function startSound() {
    const current = session;
    void audio.unlock().then(ok => { if (ok && session === current && current.phase === 'playing') audio.cue('start'); });
  }

  function progressStageCount(){return shooterGame(selected)||memoryGame(selected)?6:3;}
  function report(type, extra={}) {
    const s=session;
    if(!s||sessionOwner!==api.state||(!s.analyticsStarted&&type!=='start'))return {points:0};
    if(type==='start')s.analyticsStarted=true;
    const prompt=s.mission?.prompt || (mazeGame(selected)?domainLevels()[s.round].formula:marbleGame(selected)?`y = ${s.expression}`:selected==='territory'?territoryLevels()[s.round].label:selected==='shot'?`목표 (${number(shotLevels()[s.round].target.x)}, ${number(shotLevels()[s.round].target.y)})`:'수학 개념 짝 찾기');
    const result=recordGameEvent(api.state,{game:selected,title:gameById(selected).title,runId:s.runId,type,elapsed:s.elapsed,stage:Math.min(progressStageCount(),memoryGame(selected)?Math.max(1,s.matched.length):selected==='bubble'?Math.max(1,s.bubbleStages):s.round+1),stageCount:progressStageCount(),mode:s.difficulty,skill:s.mission?.topic||gameById(selected).topic,question:prompt,...extra});
    if(result.points){s.lastAward=`이번 단계 +${result.points} LP`;const rank=api.rankSummary?.();if(rank)s.lastAward+=` · 나의 랭킹 ${rank.rank}위 · ${rank.points} LP`;const box=root?.querySelector('#arc-ranking');if(box)box.innerHTML=api.rankHTML?.()||'';}
    api.onEvent?.({game:selected,runId:s.runId,type,elapsed:s.elapsed,stage:Math.min(progressStageCount(),memoryGame(selected)?Math.max(1,s.matched.length):selected==='bubble'?Math.max(1,s.bubbleStages):s.round+1),stageCount:progressStageCount(),mode:s.difficulty,skill:s.mission?.topic||gameById(selected).topic,question:prompt,score:s.score,...extra});
    api.save();return result;
  }
  const rankGain=()=>session?.lastAward?`<p class="arc-rank-gain" role="status">${esc(session.lastAward)}</p>`:'';
  function lobby() {
    const values = Object.values(records());
    return `<section class="arc-lobby"><div class="arc-lobby-bar"><div><h3>오늘은 어떤 방식으로 탐구할까요?</h3><p>게임 카드를 선택하면 조작법과 학습 목표를 볼 수 있어요.</p></div><div class="arc-record-chip">${icon('growth')} 클리어 ${values.filter(v => v.wins > 0).length} / ${GAMES.length} <span>·</span> 총 ${values.reduce((n, v) => n + (v.wins || 0), 0)}회 성공</div></div><div class="arc-game-filters">${[['all','전체'],['function','함수'],['sets','집합'],['logic','명제']].map(([id,label])=>button(label,'arcade-filter',gameCategory===id?'soft small':'light small',`data-filter="${id}"`)).join('')}</div><div class="arc-game-grid">${GAMES.filter(g=>gameCategory==='all'||(g.subject||'function')===gameCategory).map((g, i) => {
      const record = records()[g.id];
      return `<button class="arc-game-card" data-game="${g.id}" data-action="arcade-open" data-id="${g.id}"><div class="arc-card-art"><span class="arc-card-number">${String(i + 1).padStart(2,'0')}</span><span class="arc-genre">${g.genre}</span>${gameArt(g.id)}</div><div class="arc-card-body"><span class="arc-topic">${g.topic}</span><h3>${g.title}</h3><p>${g.desc}</p><div class="arc-card-footer"><span>${record?.wins ? `★ 최고 ${record.bestScore}점 · ${record.wins}회 성공` : g.tag}</span><span class="arc-card-arrow">${icon('arrow')}</span></div></div></button>`;
    }).join('')}</div><p class="arc-save-note">${icon('lock')} 기록은 현재 브라우저의 학생 프로필에 저장돼요. 개념 퀴즈와 별도로 성장해요.</p></section>`;
  }

  function newSession() {
    sessionOwner = api.state;
    const s = { runId:crypto.randomUUID(), analyticsStarted:false, lastHeartbeat:0, bubbleStages:0, id: selected, phase: 'ready', difficulty, score: 0, hearts: 5, round: 0, hits: 0, mistakes: 0, shots: 0, elapsed: 0, lessons: [], message: '조작법을 확인하고 시작해 보세요.', feedback: '', hint: false, saved: false, particles: [], feedbackTime: 0 };
    s.content = createArcadeContent(selected, nextVariant(`game:${selected}`, GAME_VARIANTS[selected]));
    if (selected === 'bubble') {
      s.bubbles = [];
      for (let r = 0; r < 4; r++) for (let c = 0; c < 9; c++) s.bubbles.push({ x: 166 + c * 52 + r % 2 * 26, y: 60 + r * 45, value: (Math.floor(c / 3) + Math.floor(r / 2)) % 5 + 1 + s.content.variant % 6 });
      s.angle = -Math.PI / 2; s.ball = null; s.mission = bubbleMission(s); s.message = '먼저 함숫값을 계산해요. 그 값의 버블을 조준해 발사하세요.';
    }
    if (shooterGame(selected)) { s.player = 400; s.bullets = []; s.enemyBullets = []; s.cooldown = 0; s.enemyTimer = 0; s.invulnerable = 0; nextWave(s); }
    if (mazeGame(selected)) { s.hearts = 6; setupMaze(s); }
    if (selected === 'territory') { s.hearts = 6; setupTerritory(s); }
    if (marbleGame(selected)) setupMarble(s);
    if (selected === 'shot') setupShot(s);
    if (memoryGame(selected)) {
      s.cards = shuffle(memoryPairs(s).flatMap((_, pair) => [{ pair, side: 'left' }, { pair, side: 'right' }]));
      s.open = []; s.matched = []; s.turns = 0; s.revealUntil = 0; s.message = '카드 두 장을 뒤집고, 수학적으로 연결되는 짝을 찾아요.';
    }
    return s;
  }

  function bubbleMission(s) {
    const bottom = s.bubbles.filter(b => !s.bubbles.some(other => other.y > b.y && Math.abs(other.x - b.x) < 28));
    return valueMission(bottom[Math.floor(Math.random() * bottom.length)]?.value || 1, s.hits, s.content.variant);
  }
  function nextWave(s) {
    const counter = selected === 'counter' ? s.content.counterRounds[s.round] : null;
    const answer = counter ? counter.answer : 1 + Math.floor(Math.random() * 12);
    s.mission = counter ? { ...counter, topic: '반례 찾기', hint: '가정 p가 참이고 결론 q가 거짓인 수를 찾아요. 가정이 거짓인 수는 반례가 아니에요.' } : valueMission(answer, s.round + 2, s.content.variant);
    const options = shuffle(counter ? counter.choices : [answer, answer + 2, answer - 1, answer + 4]);
    s.aliens = options.map((value, i) => ({ x: 180 + i * 145, y: 105, base: 180 + i * 145, value }));
    s.waveTime = 0; s.bullets = []; s.enemyBullets = []; s.enemyTimer = 0;
    s.message = counter ? '반례 우주선을 조준하세요. 가정은 참이고 결론은 거짓인지 모두 확인해요.' : '정답 우주선을 조준해요. 탄환과 우주선을 피하며 이동하세요.';
  }
  function setupMaze(s) {
    s.cells = createDomainMaze(domainLevels(s)[s.round]); s.position = { col: 1, row: 5 };
    s.mazeKeys = [{ col: 1, row: 1 }, { col: 4, row: 3 }, { col: 7, row: 5 }]; s.collected = []; s.steps = 0; s.moveCooldown = 0;
    s.message = '숫자가 정의역에 속하는지 확인해 이동해요. 열쇠 3개를 모으면 출구가 열려요.'; s.feedback = '';
  }
  function setupMarble(s) {
    const level = marbleLevels(s)[s.round];
    s.expression = level.expression; s.parameters = { ...level.initial }; s.formula = compileFormula(s.expression); s.formulaError = '';
    s.stars = [3, 6, 9].map(x => ({ x, y: level.fn(x) + .22, collected: false }));
    s.goal = { x: 11, y: level.fn(11) + .22 }; s.ball = null; s.trace = []; s.starPoints = 0;
    s.message = `함수식을 쓰거나 계수를 조절해요. 구슬은 (0, ${number(level.start)})에서 출발해요.`; s.feedback = '';
  }
  function setupShot(s) {
    s.angle = 45; s.speed = 11; s.ball = null; s.trace = []; s.message = '각도와 속력을 조절하고 예측선과 목표를 비교해요.'; s.feedback = '';
  }

  function markup() {
    if (sessionOwner !== api.state) { selected = null; session = null; }
    return `<div id="math-arcade">${soundPanel()}<div id="arc-ranking">${api.rankHTML?.()||''}</div>${selected ? stage() : lobby()}</div>`;
  }
  function modeDescriptions() {
    if (memoryGame(selected)) return ['횟수 제한 없음','18번 안에 짝 찾기'];
    if (selected === 'counter') return ['여유 있는 속도','빠른 우주선과 탄환'];
    if (mazeGame(selected)) return ['통과 조건 표시','식에서 조건 찾기'];
    if (marbleGame(selected)) return ['별의 좌표 표시','눈금으로 좌표 읽기'];
    if (selected === 'territory') return ['느린 방해꾼 · 120초','빠른 방해꾼 · 65초'];
    return ({
      bubble: ['긴 조준선', '짧은 조준선'], invaders: ['여유 있는 속도', '빠른 우주선과 탄환'],
      maze: ['통과 조건 표시', '식에서 조건 찾기'], marble: ['별의 좌표 표시', '눈금으로 좌표 읽기'],
      shot: ['전체 예측선', '짧은 예측선'], memory: ['횟수 제한 없음', '18번 안에 짝 찾기']
    })[selected];
  }
  function stage() {
    const g = gameById(selected), s = session;
    return `<section class="arc-stage" data-game="${selected}"><div class="arc-stage-heading"><button class="text-button" data-action="arcade-lobby">← 게임 목록</button><div><span class="arc-topic">${g.genre} · ${g.topic}</span><h2>${g.title}</h2></div><button class="btn light small" data-action="arcade-restart">${icon('reset')} 처음부터</button></div><div class="arc-play-layout"><div class="arc-play-main"><div class="arc-machine"><div class="arc-hud"><span><i class="arc-live-dot"></i> <b id="arc-stage-label">${stageLabel()}</b></span><div><span>점수 <b id="arc-score">${s.score}</b></span><span id="arc-lives">${livesText()}</span><button class="arc-pause" data-action="arcade-pause" ${['ready', 'won', 'lost', 'between'].includes(s.phase) ? 'disabled' : ''} aria-label="일시정지">Ⅱ</button></div></div><div class="arc-mission" id="arc-mission">${missionHTML()}</div><div class="arc-board-wrap">${memoryGame(selected) ? `<div class="arc-memory-board" aria-label="수학 개념 짝 찾기 카드">${memoryHTML()}</div>` : `<canvas id="arc-canvas" width="800" height="500" tabindex="0" aria-label="${esc(g.title)} 게임 화면. ${esc(g.controls)}"></canvas>`}<div id="arc-overlay">${overlayHTML()}</div></div><div class="arc-bottom-line"><span>${icon('settings')} ${g.controls}</span><span id="arc-time">00:00</span></div></div><div class="arc-touch-controls">${touchControls()}</div><div class="arc-feedback" id="arc-feedback" role="status" aria-live="polite">${esc(s.message)}</div></div><aside class="arc-toolbox"><section class="panel"><span class="arc-eyebrow">HOW TO PLAY</span><h3>플레이 속 수학</h3><p>${g.goal}</p>${s.phase === 'ready' ? `<label class="arc-mode-label" for="arc-difficulty">플레이 모드</label><select id="arc-difficulty" class="field" data-arc-input="difficulty"><option value="relaxed" ${difficulty === 'relaxed' ? 'selected' : ''}>천천히 탐구 · ${modeDescriptions()[0]}</option><option value="challenge" ${difficulty === 'challenge' ? 'selected' : ''}>도전 · ${modeDescriptions()[1]}</option></select>` : `<span class="arc-mode-badge">${s.difficulty === 'relaxed' ? '천천히 탐구' : '도전 모드'}</span>`}</section>${toolsHTML()}<section class="panel arc-discovery"><span class="eyeline">${icon('spark')} 발견 노트</span><p>${g.lesson}</p><div id="arc-lessons">${lessonsHTML()}</div><button class="btn light small block" data-action="arcade-hint">${icon('book')} ${s.hint ? '힌트 접기' : '생각의 힌트'}</button><p class="arc-hint" id="arc-hint" ${s.hint ? '' : 'hidden'}>${esc(hintText())}</p></section></aside></div></section>`;
  }
  function stageLabel() {
    const s = session;
    if (selected === 'territory') return `STAGE ${s.round+1} / 3 · ${Math.round(territoryProgress(s)*100)}%`;
    if (selected === 'bubble') return `남은 버블 ${s.bubbles.length}`;
    if (shooterGame(selected)) return `WAVE ${Math.min(s.round + 1, 6)} / 6`;
    if (memoryGame(selected)) return `${s.matched.length} / 6쌍 · ${s.turns}${s.difficulty === 'challenge' ? ' / 18' : ''}번 시도`;
    return `STAGE ${s.round + 1} / 3`;
  }
  function livesText() { return memoryGame(selected) ? '✦ 짝 찾기' : `♥ ${session.hearts}`; }
  function missionHTML() {
    const s = session;
    if (['bubble', 'invaders', 'counter'].includes(selected)) return `<span>${s.mission.topic}</span><strong>${esc(s.mission.prompt)}</strong>`;
    if (selected === 'territory') return `<span>점령할 집합</span><strong>${territoryLevels(s)[s.round].label}</strong><small>목표 영역 75% · ${Math.max(0,Math.ceil((session.difficulty==='challenge'?65:120)-s.landTime))}초</small>`;
    if (mazeGame(selected)) return `<span>통과 조건</span><strong>${domainLevels()[s.round].formula}</strong><small>${s.difficulty === 'relaxed' ? `${domainLevels()[s.round].rule} · ` : ''}열쇠 ${s.collected.length} / 3 · 출구 ↗</small>`;
    if (marbleGame(selected)) return `<span>${marbleLevels()[s.round].name}</span><strong id="arc-formula-label">y = ${esc(s.expression)}</strong><small>별 ${s.stars.filter(star => star.collected).length} / 3</small>`;
    if (selected === 'shot') return `<span>${shotLevels(s)[s.round].name}</span><strong>목표 (${number(shotLevels(s)[s.round].target.x)}, ${number(shotLevels(s)[s.round].target.y)}) m</strong><small>중력 9.8 m/s²</small>`;
    return '<span>수학적 연결</span><strong>식 ↔ 그래프 · 식 ↔ 정의역 · 계산 ↔ 결과</strong>';
  }
  function toolsHTML() {
    const s = session;
    if (marbleGame(selected)) return `<section class="panel arc-formula-tools"><label class="field-label" for="arc-expression">직접 만드는 함수식</label><div class="arc-expression-line"><span>y =</span><input class="field" id="arc-expression" data-arc-input="expression" value="${esc(s.expression)}" maxlength="160" spellcheck="false" autocomplete="off" aria-describedby="arc-expression-help arc-expression-error"/></div><small id="arc-expression-help">x, a, b, c · + − * / ^ · sqrt(x), abs(x)<br/>${selected==='root-marble'?'예: −1.5*sqrt(x)+6, a*sqrt(x-b)+c':'예: −0.4x+6, a*x^2+b*x+c'}</small><p id="arc-expression-error" class="arc-input-error" role="status">${esc(s.formulaError)}</p>${[['a', -2, 2, .01], ['b', -3, 3, .05], ['c', -2, 9, .05]].map(([key, min, max, step]) => slider(key, `계수 ${key}`, s.parameters[key], min, max, step)).join('')}<button class="btn teal block" data-action="arcade-launch" ${s.ball || s.formulaError || s.phase !== 'playing' ? 'disabled' : ''}>${icon('arrow')} 구슬 굴리기</button><p class="arc-tool-note">별과 도착점의 좌표를 보고, 함숫값을 비교해 보세요. 입력식에 없는 상수는 그래프를 바꾸지 않아요. 구슬이 굴러가는 동안에는 길을 바꿀 수 없어요.</p></section>`;
    if (selected === 'shot') return `<section class="panel">${slider('angle', '발사 각도 θ (°)', s.angle, 15, 75, 1)}${slider('speed', '처음 속력 v (m/s)', s.speed, 7, 16, .1)}<div class="arc-equation" id="arc-shot-equation">${shotEquation()}</div><button class="btn teal block" data-action="arcade-launch" ${s.ball || s.phase !== 'playing' ? 'disabled' : ''}>${icon('target')} 발사!</button><p class="arc-tool-note">발사점 (1, 1) · X = x − 1<br/>점선은 현재 설정의 예측 궤적이에요.</p></section>`;
    return '';
  }
  function slider(key, label, value, min, max, step) { return `<label class="arc-slider"><span>${label}<output id="arc-value-${key}" for="arc-input-${key}">${number(value)}</output></span><input id="arc-input-${key}" type="range" data-arc-input="${key}" min="${min}" max="${max}" step="${step}" value="${value}" ${session.ball ? 'disabled' : ''}/></label>`; }
  function shotEquation() {
    const { angle, speed } = session, rad = angle * Math.PI / 180;
    return `<span>지금의 포물선</span><strong>y = −${number(9.8 / (2 * speed ** 2 * Math.cos(rad) ** 2))}X²<br/>+ ${number(Math.tan(rad))}X + 1</strong><small>y = 1 + tan(θ)X − 9.8X² / (2v²cos²θ)</small>`;
  }
  function touchControls() {
    if (mazeGame(selected) || selected === 'territory') return `<div class="arc-dpad">${[['up', '↑', '위로'], ['left', '←', '왼쪽으로'], ['down', '↓', '아래로'], ['right', '→', '오른쪽으로']].map(([dir, label, name]) => `<button data-action="arcade-move" data-dir="${dir}" aria-label="${name} 이동">${label}</button>`).join('')}</div>${selected==='territory'?`<button class="arc-paint-button" data-action="arcade-paint">${session.paint?'그리기 켜짐 · 길 닫기':'그리기 켜기'}</button>`:'<span>숫자를 확인하고 한 칸씩 이동해요.</span>'}`;
    if (['bubble', 'invaders', 'counter'].includes(selected)) return `<button data-arc-hold="left" aria-label="왼쪽 ${selected === 'bubble' ? '조준' : '이동'}">←</button><button class="arc-fire-button" data-action="arcade-fire">${icon('target')} 발사</button><button data-arc-hold="right" aria-label="오른쪽 ${selected === 'bubble' ? '조준' : '이동'}">→</button>`;
    return '';
  }
  function memoryHTML() {
    const s = session;
    return s.cards.map((card, i) => {
      const matched = s.matched.includes(card.pair), open = matched || s.open.includes(i), pair = memoryPairs(s)[card.pair];
      return `<button class="arc-memory-card ${open ? 'is-open' : ''} ${matched ? 'is-matched' : ''}" data-action="arcade-card" data-index="${i}" aria-label="${open ? esc(pair[card.side]) : `카드 ${i + 1} 뒤집기`}" aria-pressed="${open}" ${matched ? 'disabled' : ''}><span class="arc-card-back" aria-hidden="true"><b>ƒ</b><small>${String(i + 1).padStart(2, '0')}</small></span><span class="arc-card-front" ${open ? '' : 'aria-hidden="true"'}>${card.side === 'right' && pair.graph ? cardGraph(pair.graph) : ''}<span>${esc(pair[card.side]).replace(/\n/g, '<br/>')}</span>${matched ? '<i>✓ 연결 성공</i>' : ''}</span></button>`;
    }).join('');
  }
  function overlayHTML() {
    const s = session, g = gameById(selected);
    if (s.phase === 'playing') return '';
    if (s.phase === 'ready') return `<div class="arc-overlay-card"><span class="arc-overlay-icon">${icon(marbleGame(selected) ? 'graph' : 'target')}</span><span class="arc-eyebrow">READY TO DISCOVER?</span><h3>${g.title}</h3><p>${g.goal}</p>${button('플레이 시작 '+icon('arrow'), 'arcade-start', 'teal')}<small>${g.controls}</small></div>`;
    if (s.phase === 'paused') return `<div class="arc-overlay-card"><span class="arc-eyebrow">TAKE YOUR TIME</span><h3>잠깐 쉬어 가요</h3><p>준비되면 이어서 탐구해요.<br/>게임 시간도 함께 멈췄어요.</p>${button('이어서 플레이', 'arcade-resume', 'teal')}</div>`;
    if (s.phase === 'between') return `<div class="arc-overlay-card"><span class="arc-eyebrow">STAGE CLEAR</span><h3>다음 길도 만들어 볼까요?</h3><p>${esc(s.feedback)}</p>${rankGain()}${button('다음 스테이지 '+icon('arrow'), 'arcade-next', 'teal')}</div>`;
    return `<div class="arc-overlay-card arc-result"><span class="arc-eyebrow">${s.phase === 'won' ? 'MISSION COMPLETE' : 'TRY & DISCOVER'}</span><div class="arc-result-stars">${s.phase === 'won' ? '★'.repeat(starCount()) + '☆'.repeat(3 - starCount()) : '✦'}</div><h3>${s.phase === 'won' ? '플레이가 발견이 되었어요!' : '다시 도전하면 보여요'}</h3><p>${esc(s.feedback)}</p>${rankGain()}<div class="arc-result-stats"><span><b>${s.score}</b>점수</span><span><b>${formatTime(s.elapsed)}</b>탐구 시간</span><span><b>${s.hits}</b>성공한 연결</span></div><small>이 학생 프로필에 결과가 저장되었어요.</small><div class="row">${button('다시 도전', 'arcade-restart', 'teal')}${button('다른 게임', 'arcade-lobby', 'light')}</div></div>`;
  }
  function hintText() {
    const s = session;
    if (['bubble', 'invaders', 'counter'].includes(selected)) return s.mission.hint;
    if (selected === 'territory') return territoryLevels()[session.round].hint;
    if (memoryGame(selected) && selected !== 'memory') return gameById(selected).lesson;
    if (mazeGame(selected)) return `통과 조건은 ${domainLevels()[s.round].rule}. ${domainLevels()[s.round].why(domainLevels()[s.round].illegal[0])}`;
    if (marbleGame(selected)) return marbleLevels()[s.round].hint;
    if (selected === 'shot') return shotLevels(s)[s.round].hint;
    return '식과 그래프는 기울기와 꼭짓점을 비교해요. 정의역은 분모가 0인지, 루트 안이 음수인지 확인해요. 합성함수는 안쪽부터 계산해요.';
  }
  function lessonsHTML() { return session.lessons.slice(-3).reverse().map(text => `<div class="arc-lesson">✓ ${esc(text)}</div>`).join(''); }
  function formatTime(seconds) { return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`; }
  function starCount() { return session.mistakes <= 1 ? 3 : session.mistakes <= 4 ? 2 : 1; }

  function refresh() {
    if (!root) return;
    stopLoop();
    audio.setScene(selected, session?.phase || 'idle');
    root.innerHTML = soundPanel() + `<div id="arc-ranking">${api.rankHTML?.()||''}</div>` + (selected ? stage() : lobby());
    syncSoundControls();
    canvas = root.querySelector('#arc-canvas'); ctx = canvas?.getContext('2d');
    if (canvas && ctx) {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = W * ratio; canvas.height = H * ratio; ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    }
    last = 0;
    if (selected) {
      syncTools(); draw(); updateHUD();
      if (session.phase === 'playing') frame = requestAnimationFrame(loop);
      else if(!document.querySelector('.modal,.focus-overlay')) root.querySelector('#arc-overlay [data-action]')?.focus({ preventScroll: true });
    }
    window.dispatchEvent(new window.Event('goodmath:layout'));
  }
  function updateHUD() {
    if (!root || !selected) return;
    const set = (id, value) => { const el = root.querySelector(`#${id}`); if (el && el.textContent !== String(value)) el.textContent = value; };
    if(selected==='territory'){const paint=root.querySelector('[data-action="arcade-paint"]');if(paint){paint.textContent=session.paint?'그리기 켜짐 · 길 닫기':'그리기 켜기';paint.setAttribute('aria-pressed',String(session.paint));}}
    set('arc-score', session.score); set('arc-stage-label', stageLabel()); set('arc-lives', livesText()); set('arc-time', formatTime(session.elapsed));
  }
  function feedback(message, tone = '') {
    session.message = message;
    const box = root?.querySelector('#arc-feedback');
    if (box) { box.textContent = message; box.dataset.tone = tone; }
  }
  function remember(text) {
    if (!session.lessons.includes(text)) session.lessons.push(text);
    const box = root?.querySelector('#arc-lessons'); if (box) box.innerHTML = lessonsHTML();
  }
  function updateMission() {
    const box = root?.querySelector('#arc-mission'); if (box) {const html=missionHTML();if(box.innerHTML!==html)box.innerHTML=html;}
    const hint = root?.querySelector('#arc-hint'); if (hint) hint.textContent = hintText();
  }
  function finish(won, message) {
    const s = session;
    if (s.saved) return;
    s.phase = won ? 'won' : 'lost'; s.feedback = message; s.saved = true; keys.clear();
    const old = records()[selected] || {};
    api.state.arcadeRecords = { ...records(), [selected]: { plays: (old.plays || 0) + 1, wins: (old.wins || 0) + (won ? 1 : 0), bestScore: Math.max(old.bestScore || 0, s.score), bestStars: Math.max(old.bestStars || 0, won ? starCount() : 0), lastPlayed: new Date().toISOString(), lastResult: won ? 'clear' : 'retry', lastSummary: message, lastScore: s.score, lastMode: s.difficulty, discoveries: s.lessons.slice(-6) } };
    report(won?'win':'retry',{message});api.save(); refresh(); audio.cue(won ? 'win' : 'lose');
  }
  function loseLife(message) {
    session.hearts--; session.mistakes++; feedback(message, 'try');
    audio.cue('damage');report('error',{message});
    if (session.hearts <= 0) finish(false, `${message} 힌트를 읽고 다시 실험해 보세요.`);
  }
  function stageClear(text) {
    report('success',{message:text});report('clear',{stage:session.round+1,message:text});
    session.hits++; session.score += 200; remember(text); session.feedback = text;
    if (session.round === 2) finish(true, text); else { session.phase = 'between'; report('wait'); keys.clear(); refresh(); audio.cue('stage'); }
  }

  function stopLoop() { cancelAnimationFrame(frame); frame = 0; keys.clear(); }
  function unmount() {
    stopLoop(); controller?.abort(); controller = null;
    audio.stop();
    if (session?.phase === 'playing') {report('leave');session.phase = 'paused';}
    else if(session?.phase==='between')report('leave');
    root = null; canvas = null; ctx = null;
  }
  function mount() {
    root = document.getElementById('math-arcade'); if (!root) return;
    try { const settings=JSON.parse(localStorage.getItem(ARCADE_AUDIO_KEY));if(settings)audio.updateSettings(settings); } catch { /* Keep the current sound setting. */ }
    controller?.abort(); controller = new AbortController();
    const options = { signal: controller.signal };
    root.addEventListener('input', input, options);
    root.addEventListener('pointerdown', pointerDown, options);
    root.addEventListener('pointermove', pointerMove, options);
    root.addEventListener('pointerup', releasePointer, options); root.addEventListener('pointercancel', releasePointer, options);
    window.addEventListener('pointerup', releasePointer, options);
    document.addEventListener('keydown', keyDown, options);
    document.addEventListener('keyup', e => keys.delete(e.key.toLowerCase()), options);
    document.addEventListener('visibilitychange', () => { if (document.hidden) { pause(); audio.stop(); } }, options);
    window.addEventListener('blur', () => { pause(); audio.stop(); }, options);
    window.addEventListener('pagehide', () => { pause(); audio.stop(); }, options);
    refresh();
  }
  function pause() {
    if (session?.phase !== 'playing') return;
    report('pause');session.phase = 'paused'; keys.clear(); refresh();
  }
  function action(name, el) {
    if (!name.startsWith('arcade-')) return false;
    if (name === 'arcade-audio-enable') { audio.setScene(selected, session?.phase || 'idle'); void audio.unlock(); return true; }
    if (name === 'arcade-audio-music' || name === 'arcade-audio-effects') {
      const channel = name === 'arcade-audio-music' ? 'music' : 'effects';
      audio.updateSettings({ [channel]: !audio.settings[channel] });
      if (session?.phase === 'playing') { audio.setScene(selected, session.phase); void audio.unlock(); }
      return true;
    }
    if (name === 'arcade-open') { if (!gameById(el.dataset.id)) return true; selected = el.dataset.id; session = newSession(); refresh(); root.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}); return true; }
    if (name === 'arcade-filter') { gameCategory=el.dataset.filter; refresh(); return true; }
    if (name === 'arcade-lobby') { if(['playing','between'].includes(session?.phase))report('leave');selected = null; session = null; refresh(); return true; }
    if (!session) return true;
    if (name === 'arcade-restart') { if(['playing','between'].includes(session.phase))report('leave');session = newSession(); refresh(); }
    if (name === 'arcade-start' && session.phase === 'ready') { session.phase = 'playing'; report('start');refresh(); startSound(); canvas?.focus({ preventScroll: true }); }
    if (name === 'arcade-resume' && session.phase === 'paused') { session.phase = 'playing'; report('resume');refresh(); startSound(); canvas?.focus({ preventScroll: true }); }
    if (name === 'arcade-pause') pause();
    if (name === 'arcade-hint') { session.hint = !session.hint;if(session.hint)report('hint'); const hint = root.querySelector('#arc-hint'); hint.hidden = !session.hint; el.innerHTML = `${icon('book')} ${session.hint ? '힌트 접기' : '생각의 힌트'}`; }
    if (name === 'arcade-next' && session.phase === 'between') {
      session.round++; session.phase = 'playing'; session.hint = false;
      if (mazeGame(selected)) setupMaze(session);
      if (selected === 'territory') setupTerritory(session);
      if (marbleGame(selected)) setupMarble(session);
      if (selected === 'shot') setupShot(session);
      report('resume');refresh(); startSound();
    }
    if (name === 'arcade-fire') fire();
    if (name === 'arcade-move') { if(selected==='territory') moveTerritory(session,el.dataset.dir,territoryEvents()); else moveMaze(el.dataset.dir); }
    if (name === 'arcade-paint') togglePaint();
    if (name === 'arcade-launch') launch();
    if (name === 'arcade-card') flipCard(Number(el.dataset.index));
    return true;
  }

  function input(event) {
    if (event.target.hasAttribute('data-arc-volume')) {
      audio.updateSettings({ volume: Number(event.target.value) / 100 });
      if (session?.phase === 'playing') void audio.unlock();
      return;
    }
    const field = event.target.dataset.arcInput, s = session;
    if (!field || !s) return;
    if (field === 'difficulty' && s.phase === 'ready') { difficulty = event.target.value; s.difficulty = difficulty; updateMission(); draw(); return; }
    if (s.ball || !['ready', 'playing'].includes(s.phase)) return;
    if (marbleGame(selected)) {
      if (field === 'expression') {
        s.expression = event.target.value;
        try { s.formula = compileFormula(s.expression); s.formulaError = ''; }
        catch (error) { s.formula = null; s.formulaError = error.message; }
        root.querySelector('#arc-expression-error').textContent = s.formulaError;
        root.querySelector('#arc-formula-label').textContent = `y = ${s.expression}`;
      } else if (['a', 'b', 'c'].includes(field)) s.parameters[field] = Number(event.target.value);
      s.trace = []; s.stars.forEach(star => { star.collected = false; }); updateMission();
    } else if (selected === 'shot' && ['angle', 'speed'].includes(field)) {
      s[field] = Number(event.target.value); root.querySelector('#arc-shot-equation').innerHTML = shotEquation();
    }
    const output = root.querySelector(`#arc-value-${field}`); if (output) output.textContent = number(Number(event.target.value));
    if (s.phase === 'playing' && field !== 'expression') audio.cue('tune');
    syncTools(); draw();
  }
  function syncTools() {
    const s = session;
    root?.querySelectorAll('[data-arc-input]').forEach(el => {
      if (el.dataset.arcInput !== 'difficulty') el.disabled = !!s.ball || !['ready', 'playing'].includes(s.phase);
    });
    const launchButton = root?.querySelector('[data-action="arcade-launch"]');
    if (launchButton) launchButton.disabled = !!s.ball || !!s.formulaError || s.phase !== 'playing';
  }
  function keyDown(event) {
    if (!selected || event.target.closest('input, textarea, select, .modal, .focus-overlay')) return;
    if (document.querySelector('.modal,.focus-overlay')) return;
    if (event.key === 'Escape' || event.key.toLowerCase() === 'p') { if (session.phase === 'playing') { event.preventDefault(); pause(); } return; }
    if (session.phase !== 'playing') return;
    const key = event.key.toLowerCase();
    if (!['arrowleft', 'arrowright', 'arrowup', 'arrowdown', 'a', 'd', 'w', 's', ' '].includes(key)) return;
    if (memoryGame(selected) || marbleGame(selected) || selected==='shot') return;
    if (selected==='territory') { if(key===' '&&event.target.closest('button'))return;event.preventDefault();keys.add(key);if(key===' '&&!event.repeat)togglePaint();return; }
    // Let keyboard users activate the focused button with Space normally.
    if (key === ' ' && event.target.closest('button')) return;
    event.preventDefault(); keys.add(key);
    if (mazeGame(selected)) moveMaze(({ arrowleft: 'left', a: 'left', arrowright: 'right', d: 'right', arrowup: 'up', w: 'up', arrowdown: 'down', s: 'down' })[key]);
    if (key === ' ' && !event.repeat) fire();
  }
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return { x: (event.clientX - rect.left) * W / rect.width, y: (event.clientY - rect.top) * H / rect.height };
  }
  function pointerDown(event) {
    const hold = event.target.closest('[data-arc-hold]');
    if (hold && session?.phase === 'playing') { event.preventDefault(); keys.add(hold.dataset.arcHold === 'left' ? 'arrowleft' : 'arrowright'); hold.setPointerCapture(event.pointerId); return; }
    if (event.target !== canvas || session?.phase !== 'playing' || (event.button !== 0 && event.pointerType === 'mouse')) return;
    event.preventDefault(); canvas.focus({ preventScroll: true }); canvas.setPointerCapture(event.pointerId);
    aim(point(event));
    if (selected === 'bubble' || shooterGame(selected)) fire();
  }
  function pointerMove(event) {
    if (event.target !== canvas || session?.phase !== 'playing') return;
    if (selected === 'bubble' || event.buttons || canvas.hasPointerCapture(event.pointerId)) aim(point(event));
  }
  function releasePointer() { keys.delete('arrowleft'); keys.delete('arrowright'); }
  function aim(p) {
    const s = session;
    if (selected === 'bubble') s.angle = clamp(Math.atan2(p.y - 454, p.x - 400), -2.85, -.29);
    if (shooterGame(selected)) s.player = clamp(p.x, 38, W - 38);
    if (selected === 'shot' && !s.ball) {
      const origin = worldPoint(1, 1, 'shot');
      s.angle = Math.round(clamp(Math.atan2(origin.y - p.y, p.x - origin.x) * 180 / Math.PI, 15, 75));
      root.querySelector('#arc-input-angle').value = s.angle; root.querySelector('#arc-value-angle').textContent = s.angle;
      root.querySelector('#arc-shot-equation').innerHTML = shotEquation();
    }
  }
  function fire() {
    const s = session;
    if (!s || s.phase !== 'playing') return;
    if (selected === 'bubble' && !s.ball && s.feedbackTime <= 0) { const speed = s.difficulty === 'challenge' ? 640 : 520; s.ball = { x: 400, y: 454, vx: Math.cos(s.angle) * speed, vy: Math.sin(s.angle) * speed }; s.shots++; audio.cue('shoot'); }
    if (shooterGame(selected) && s.cooldown <= 0 && s.feedbackTime <= 0) { s.bullets.push({ x: s.player, y: 438 }); s.cooldown = .3; s.shots++; audio.cue('shoot'); }
  }
  function moveMaze(direction) {
    const s = session;
    if (!mazeGame(selected) || s.phase !== 'playing' || s.moveCooldown > 0 || !direction) return;
    const [dx, dy] = ({ left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] })[direction] || [0, 0];
    const col = s.position.col + dx, row = s.position.row + dy, cell = s.cells[row * 9 + col];
    s.moveCooldown = .13;
    if (!cell || cell.wall) { audio.cue('bump'); feedback('막힌 벽이에요. 숫자가 있는 다른 길을 살펴보세요.'); return; }
    const domain = domainLevels()[s.round];
    if (!domain.valid(cell.value)) {
      cell.revealed = true; s.moveCooldown = .45;
      loseLife(`${domain.why(cell.value)} 이 칸은 지나갈 수 없어요.`); return;
    }
    s.position = { col, row }; s.steps++;
    const keyIndex = s.mazeKeys.findIndex(key => key.col === col && key.row === row);
    if (keyIndex >= 0 && !s.collected.includes(keyIndex)) { audio.cue('collect'); s.collected.push(keyIndex); s.score += 60; feedback(`열쇠 ${s.collected.length} / 3! x=${tileNumber(cell.value)}은 ${domain.rule}을 만족해요.`, 'ok'); }
    else { audio.cue('step'); feedback(`x=${tileNumber(cell.value)}: 통과! ${domain.why(cell.value)}`, 'ok'); }
    if (col === 7 && row === 1) {
      if (s.collected.length === 3) { stageClear(`${domain.formula}의 정의역은 ${domain.rule}. ${s.steps}번 이동해 안전하게 탈출했어요.`); return; }
      feedback(`출구를 열려면 열쇠가 ${3 - s.collected.length}개 더 필요해요.`);
    }
    updateMission();
  }
  function launch() {
    const s = session;
    if (s.phase !== 'playing' || s.ball) return;
    if (marbleGame(selected)) {
      if (!s.formula || s.formulaError) return;
      s.stars.forEach(star => { star.collected = false; });
      s.ball = { x: 0, y: marbleLevels()[s.round].start + .26, vx: .65, vy: 0, onTrack: false, age: 0 };
      audio.cue('roll');
      feedback('구슬이 출발했어요. 길의 기울기와 구슬의 속도를 관찰해요.');
    } else if (selected === 'shot') {
      s.ball = { x: 1, y: 1, age: 0 }; audio.cue('launch'); feedback('발사! 예측한 포물선과 실제 궤적을 비교해 보세요.');
    } else return;
    s.shots++; s.trace = []; syncTools(); updateMission();
    if (!document.body.classList.contains('lab-playing') && window.innerWidth <= 1150) canvas?.scrollIntoView({block:'center',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
  }
  function flipCard(index) {
    const s = session;
    if (!memoryGame(selected) || s.phase !== 'playing' || !s.cards[index] || s.open.length === 2 || s.open.includes(index) || s.matched.includes(s.cards[index].pair)) return;
    s.open.push(index);
    audio.cue('flip');
    if (s.open.length === 2) {
      s.turns++;
      const first = s.cards[s.open[0]], second = s.cards[s.open[1]];
      if (first.pair === second.pair) {
        s.matched.push(first.pair); s.open = []; s.hits++; s.score += 100;
        const why = memoryPairs(s)[first.pair].why; remember(why); feedback(`연결 성공! ${why}`, 'ok');
        audio.cue('match');report('success',{question:memoryPairs(s)[first.pair].left,message:why});report('clear',{stage:s.matched.length,question:memoryPairs(s)[first.pair].left,message:why});
        if (s.matched.length === memoryPairs(s).length) { s.score += Math.max(0, 24 - s.turns) * 10; finish(true, `6쌍을 ${s.turns}번 만에 연결했어요. ${gameById(selected).lesson}`); return; }
      } else {
        s.mistakes++; s.revealUntil = s.elapsed + 1.7;
        audio.cue('miss');report('error',{question:s.open.map(i=>memoryPairs(s)[s.cards[i].pair][s.cards[i].side]).join(' ↔ '),message:'수학적으로 연결되지 않는 두 카드를 선택했어요.'});
        feedback('아직 짝이 아니에요. 식의 특징, 그래프 모양과 계산 결과를 기억해 두세요.', 'try');
      }
    }
    updateMemory(); updateHUD();
    if (s.difficulty === 'challenge' && s.turns >= 18 && s.open.length === 0) finish(false, '18번의 기회를 사용했어요. 발견 노트를 읽고 다시 연결해 보세요.');
  }
  function updateMemory() {
    const s = session;
    root?.querySelectorAll('.arc-memory-card').forEach((el, i) => {
      const card = s.cards[i], pair = memoryPairs(s)[card.pair], matched = s.matched.includes(card.pair), open = matched || s.open.includes(i);
      el.classList.toggle('is-open', open); el.classList.toggle('is-matched', matched); el.disabled = matched;
      el.setAttribute('aria-pressed', String(open)); el.setAttribute('aria-label', open ? pair[card.side] : `카드 ${i + 1} 뒤집기`);
      el.querySelector('.arc-card-front').setAttribute('aria-hidden', String(!open));
      if (matched && !el.querySelector('i')) el.querySelector('.arc-card-front').insertAdjacentHTML('beforeend', '<i>✓ 연결 성공</i>');
    });
  }

  function loop(timestamp) {
    if (!root?.isConnected || !selected) return;
    const dt = last ? Math.min((timestamp - last) / 1000, .04) : 0; last = timestamp;
    const s = session;
    if (s.phase === 'playing') {
      s.elapsed += dt; s.feedbackTime = Math.max(0, s.feedbackTime - dt);
      if (selected === 'bubble') updateBubble(dt);
      if (shooterGame(selected)) updateInvaders(dt);
      if (selected === 'territory') { updateTerritory(s,dt,keys,territoryEvents()); if(s.phase==='playing')updateMission(); }
      if (mazeGame(selected)) s.moveCooldown = Math.max(0, s.moveCooldown - dt);
      if (marbleGame(selected)) updateMarble(dt);
      if (selected === 'shot') updateShot(dt);
      if (memoryGame(selected) && s.open.length === 2 && s.elapsed >= s.revealUntil) {
        s.open = []; updateMemory();
        if (s.difficulty === 'challenge' && s.turns >= 18) finish(false, '18번의 기회를 사용했어요. 식과 그래프의 특징을 기억하며 다시 도전해요.');
      }
      if(s.phase==='playing'&&s.elapsed-s.lastHeartbeat>=15){s.lastHeartbeat=s.elapsed;report('heartbeat');}
      s.particles = s.particles.filter(p => p.life > 0);
      s.particles.forEach(p => { p.x += p.vx * dt; p.y += p.vy * dt; p.vy += 180 * dt; p.life -= dt; });
    }
    draw(); updateHUD();
    // refresh() can schedule a new frame when a game ends during this tick.
    if (frame) cancelAnimationFrame(frame);
    frame = s.phase === 'playing' ? requestAnimationFrame(loop) : 0;
  }
  function burst(x, y, color = '#6be0c5') {
    for (let i = 0; i < 12; i++) session.particles.push({ x, y, vx: (Math.random() - .5) * 250, vy: (Math.random() - .65) * 230, life: .5 + Math.random() * .4, color });
  }
  function updateBubble(dt) {
    const s = session;
    if (keys.has('arrowleft') || keys.has('a')) s.angle = clamp(s.angle - dt * 1.5, -2.85, -.29);
    if (keys.has('arrowright') || keys.has('d')) s.angle = clamp(s.angle + dt * 1.5, -2.85, -.29);
    const ball = s.ball; if (!ball) return;
    ball.x += ball.vx * dt; ball.y += ball.vy * dt;
    if (ball.x < 140 || ball.x > 660) { ball.x = clamp(ball.x, 140, 660); ball.vx *= -1; audio.cue('bump'); }
    const hit = s.bubbles.find(b => distance(b, ball) <= 38);
    if (hit || ball.y < 29) {
      s.ball = null;
      if (hit?.value === s.mission.answer) {
        const connected = new Set([hit]); const queue = [hit];
        while (queue.length) {
          const b = queue.pop();
          for (const other of s.bubbles) if (!connected.has(other) && other.value === hit.value && distance(b, other) < 56) { connected.add(other); queue.push(other); }
        }
        s.bubbles = s.bubbles.filter(b => !connected.has(b));
        const anchored = new Set(s.bubbles.filter(b => b.y <= 65)), search = [...anchored];
        while (search.length) {
          const b = search.pop();
          for (const other of s.bubbles) if (!anchored.has(other) && distance(b, other) < 56) { anchored.add(other); search.push(other); }
        }
        const dropped = s.bubbles.filter(b => !anchored.has(b));
        s.bubbles = s.bubbles.filter(b => anchored.has(b));
        [...connected, ...dropped].forEach(b => burst(b.x, b.y));
        s.hits++; s.score += (connected.size + dropped.length) * 25;
        audio.cue('pop');report('success',{message:s.mission.why});
        const milestone=Math.floor((36-s.bubbles.length)/12);while(s.bubbleStages<Math.min(3,milestone)){s.bubbleStages++;report('clear',{stage:s.bubbleStages,message:s.mission.why});}
        remember(s.mission.why); feedback(`팡! ${connected.size + dropped.length}개 제거. ${s.mission.why}`, 'ok');
        if (!s.bubbles.length) { finish(true, `${s.shots}번 발사해 모든 버블을 없앴어요. 함숫값을 구해 목표를 찾고, 같은 값의 연결도 발견했어요.`); return; }
      } else {
        // The missed shot sticks to the nearest free lattice position, as in a bubble shooter.
        const candidates = [];
        for (let r = 0; r < 8; r++) for (let c = 0; c < 9; c++) {
          const p = { x: 166 + c * 52 + r % 2 * 26, y: 60 + r * 45, value: s.mission.answer };
          if (!s.bubbles.some(b => distance(b, p) < 35) && (!hit ? r === 0 : distance(hit, p) < 56)) candidates.push(p);
        }
        candidates.sort((a, b) => distance(a, ball) - distance(b, ball));
        if (candidates[0]) s.bubbles.push(candidates[0]);
        const why = s.mission.why; remember(why); loseLife(`${hit ? `${hit.value} 버블에 닿았어요.` : '천장에 닿았어요.'} ${why}`);
        if (s.phase !== 'playing') return;
        if (s.bubbles.some(b => b.y > 365)) { finish(false, '버블이 발사대 가까이 내려왔어요. 함숫값을 구하고 같은 숫자가 모인 곳을 조준해 보세요.'); return; }
      }
      s.feedbackTime = .8; s.mission = bubbleMission(s); updateMission();
    }
  }
  function updateInvaders(dt) {
    const s = session;
    s.cooldown = Math.max(0, s.cooldown - dt); s.invulnerable = Math.max(0, s.invulnerable - dt);
    if (keys.has('arrowleft') || keys.has('a')) s.player = clamp(s.player - dt * 350, 38, 762);
    if (keys.has('arrowright') || keys.has('d')) s.player = clamp(s.player + dt * 350, 38, 762);
    if (keys.has(' ')) fire();
    s.waveTime += dt;
    const fast = s.difficulty === 'challenge';
    s.aliens.forEach((alien, i) => { alien.x = alien.base + Math.sin(s.waveTime * (fast ? 1.8 : .9)) * 65; alien.y = 85 + s.waveTime * (fast ? 12 : 5) + Math.sin(s.waveTime * 2 + i) * 13; });
    s.enemyTimer += dt;
    if (s.enemyTimer > (fast ? 1.2 : 2.8) && s.feedbackTime <= 0) {
      s.enemyTimer = 0; const alien = s.aliens[Math.floor(Math.random() * s.aliens.length)];
      if (alien) s.enemyBullets.push({ x: alien.x, y: alien.y + 26 });
    }
    for (const bullet of s.bullets) {
      bullet.y -= dt * 610;
      const hit = s.aliens.find(alien => Math.abs(alien.x - bullet.x) < 34 && Math.abs(alien.y - bullet.y) < 28);
      if (!hit || bullet.dead) continue;
      bullet.dead = true;
      if (hit.value === s.mission.answer) {
        audio.cue('hit');report('success',{message:s.mission.why});report('clear',{stage:s.round+1,message:s.mission.why});
        burst(hit.x, hit.y); s.hits++; s.score += 150; remember(s.mission.why); feedback(`명중! ${s.mission.why}`, 'ok');
        s.round++;
        if (s.round === 6) { finish(true, selected==='counter'?'반례 우주선 6대를 찾았어요. 반례는 가정이 참이면서 결론이 거짓인 경우라는 것을 활용했어요.':'정답 우주선 6대를 격추했어요. 합성함수의 계산 순서와 역함수의 의미를 활용했어요.'); return; }
        nextWave(s); s.feedbackTime = .7; updateMission(); return;
      }
      if (s.invulnerable <= 0) { s.invulnerable = .7; loseLife(`${hit.value}는 이번 답이 아니에요. ${s.mission.hint}`); if (s.phase !== 'playing') return; }
    }
    s.bullets = s.bullets.filter(b => b.y > -10 && !b.dead);
    for (const bullet of s.enemyBullets) {
      bullet.y += dt * (fast ? 240 : 145);
      if (s.invulnerable <= 0 && Math.abs(bullet.x - s.player) < 22 && Math.abs(bullet.y - 451) < 22) { bullet.y = H + 20; s.invulnerable = 1.2; loseLife('적의 탄환에 맞았어요. 좌우로 이동하며 정답 우주선을 조준해요.'); if (s.phase !== 'playing') return; }
    }
    s.enemyBullets = s.enemyBullets.filter(b => b.y < H + 10);
    if (s.aliens.some(a => a.y > 400)) finish(false, '우주선이 지구에 도착했어요. 힌트에서 계산 순서를 확인하고 다시 출격해요.');
  }
  function trackHeight(x) { return session.formula ? session.formula(x, session.parameters) : NaN; }
  function missMarble(message) {
    session.ball = null; session.score -= session.starPoints; session.starPoints = 0; loseLife(message);
    if (session.phase === 'playing') { syncTools(); updateMission(); }
  }
  function updateMarble(dt) {
    const s = session, ball = s.ball; if (!ball) return;
    // Small physics steps keep the ball from tunnelling through a steep student curve.
    const steps = Math.max(1, Math.ceil(dt / .008)), step = dt / steps;
    for (let i = 0; i < steps; i++) {
      ball.age += step;
      const before = { x: ball.x, y: ball.y }, radius = .22;
      if (ball.onTrack) {
        const y = trackHeight(ball.x), left = trackHeight(Math.max(0, ball.x - .01)), right = trackHeight(ball.x + .01);
        const slope = (right - left) / (ball.x < .01 ? .01 : .02);
        if (!Number.isFinite(y) || !Number.isFinite(slope)) { ball.onTrack = false; ball.vy = 0; }
        else {
          ball.vx += (-6 * slope / (1 + slope ** 2) - .045 * ball.vx) * step;
          ball.x += ball.vx * step; const next = trackHeight(ball.x);
          if (Number.isFinite(next) && Math.abs(next - y) < .7) ball.y = next + radius;
          else { ball.onTrack = false; ball.vy = slope * ball.vx; }
          if (ball.vx < .02 && ball.age > 1) { missMarble('길이 평평하거나 오르막이라 멈췄어요. 오른쪽으로 내려가는 기울기를 만들어 보세요.'); return; }
        }
      } else {
        ball.vy -= 6 * step; ball.x += ball.vx * step; ball.y += ball.vy * step;
        const track = trackHeight(ball.x) + radius, previous = trackHeight(before.x) + radius;
        if (Number.isFinite(track) && Number.isFinite(previous) && ball.vy <= 0 && before.y >= previous - .015 && ball.y <= track && Math.abs(track - previous) < .7) {
          ball.y = track; ball.onTrack = true;
        }
      }
      for (const star of s.stars) if (!star.collected && distance(ball, star) < .5) { audio.cue('collect'); star.collected = true; s.score += 30; s.starPoints += 30; feedback(`별 ${s.stars.filter(item => item.collected).length} / 3! x=${star.x}에서 그래프 높이는 약 ${number(trackHeight(star.x))}예요.`, 'ok'); updateMission(); }
      if (distance(ball, s.goal) < .52) {
        s.ball = null;
        if (s.stars.every(star => star.collected)) {
          const parameters = Object.keys(s.parameters).filter(key => new RegExp(`\\b${key}\\b`).test(s.expression)).map(key => `${key}=${number(s.parameters[key])}`).join(', ');
          stageClear(`y = ${s.expression}${parameters ? ` (${parameters})` : ''}로 연결했어요. ${marbleLevels()[s.round].lesson}`); return;
        }
        missMarble('도착점에 닿았지만 놓친 별이 있어요. 별의 좌표에서 함숫값을 다시 비교해요.'); return;
      }
      if (ball.x > 12.5 || ball.x < -.8 || ball.y < -.7 || ball.y > 10 || ball.age > 20) { missMarble('구슬이 길을 벗어났어요. 출발 높이와 별의 좌표에 맞도록 식과 계수를 바꿔 보세요.'); return; }
    }
    s.trace.push({ x: ball.x, y: ball.y }); if (s.trace.length > 1600) s.trace.shift();
  }
  function updateShot(dt) {
    const s = session, ball = s.ball; if (!ball) return;
    const level = shotLevels(s)[s.round], rad = s.angle * Math.PI / 180;
    const steps = Math.max(1, Math.ceil(dt / .008)), step = dt / steps;
    for (let i = 0; i < steps; i++) {
      ball.age += step; ball.x = 1 + s.speed * Math.cos(rad) * ball.age; ball.y = 1 + s.speed * Math.sin(rad) * ball.age - 4.9 * ball.age ** 2;
      if (distance(ball, level.target) < .55) {
        s.ball = null; s.score += 100;
        stageClear(`각도 ${s.angle}°, 속력 ${number(s.speed)} m/s로 목표에 명중했어요. 포물선의 이차항 계수는 음수이고, 각도와 속력에 따라 궤적이 달라져요.`); return;
      }
      const wallHit = level.wall && Math.abs(ball.x - level.wall.x) < .37 && ball.y <= level.wall.height + .17;
      if (wallHit || ball.y < .15 || ball.x > 17 || ball.age > 6) {
        const atTarget = trajectory(level.target.x, s.angle, s.speed), difference = atTarget - level.target.y;
        s.ball = null;
        loseLife(wallHit ? `벽에 닿았어요. x=${level.wall.x}에서 높이가 ${level.wall.height} m보다 높아야 해요. 각도와 속력을 조절해요.` : `목표 x=${level.target.x}에서 예상 높이는 ${number(atTarget)} m예요. 목표보다 ${number(Math.abs(difference))} m ${difference > 0 ? '높아요' : '낮아요'}. 궤적을 조절해요.`);
        if (s.phase === 'playing') syncTools(); return;
      }
    }
    s.trace.push({ x: ball.x, y: ball.y });
  }
  function rounded(x, y, width, height, radius, fill, stroke) {
    ctx.beginPath(); ctx.roundRect(x, y, width, height, radius);
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
  }
  function circle(x, y, radius, fill, stroke, width = 1) {
    ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2);
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.lineWidth = width; ctx.strokeStyle = stroke; ctx.stroke(); }
  }
  function label(text, x, y, size = 14, color = '#b6c7d7', align = 'center', weight = 500) {
    ctx.fillStyle = color; ctx.font = `${weight} ${size}px -apple-system, "Apple SD Gothic Neo", sans-serif`; ctx.textAlign = align; ctx.textBaseline = 'middle'; ctx.fillText(text, x, y);
  }
  function line(x1, y1, x2, y2, color, width = 1) {
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.strokeStyle = color; ctx.lineWidth = width; ctx.stroke();
  }
  function star(x, y, radius, color = '#ffd076') {
    ctx.beginPath();
    for (let i = 0; i < 10; i++) { const r = i % 2 ? radius * .45 : radius, a = i * Math.PI / 5 - Math.PI / 2; const px = x + Math.cos(a) * r, py = y + Math.sin(a) * r; if (!i) ctx.moveTo(px, py); else ctx.lineTo(px, py); }
    ctx.closePath(); ctx.fillStyle = color; ctx.fill();
  }
  function draw() {
    if (!ctx || !selected || !session) return;
    ctx.clearRect(0, 0, W, H);
    const bg = ctx.createLinearGradient(0, 0, W, H); bg.addColorStop(0, '#15283b'); bg.addColorStop(1, '#101b2c'); ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
    if (selected === 'bubble') drawBubble();
    if (shooterGame(selected)) drawInvaders();
    if (mazeGame(selected)) drawMaze();
    if (selected === 'territory') drawTerritory(ctx,session);
    if (marbleGame(selected)) drawMarble();
    if (selected === 'shot') drawShot();
    for (const p of session.particles) { ctx.globalAlpha = Math.max(0, p.life); circle(p.x, p.y, 3.5, p.color); }
    ctx.globalAlpha = 1;
  }
  function drawBubble() {
    const s = session;
    rounded(124, 20, 552, 398, 20, '#102235', '#355066');
    ctx.save(); ctx.setLineDash([5, 7]); line(134, 387, 666, 387, '#845568'); ctx.restore();
    label('버블이 이 선에 닿기 전에 제거해요', 400, 404, 12, '#a3b0c2');
    const palette = ['#70dcca', '#b8a1ff', '#ffbd83', '#81bdff', '#f3a6c8'];
    for (const b of s.bubbles) {
      const color = palette[(Math.abs(b.value) - 1) % palette.length];
      ctx.shadowColor = `${color}44`; ctx.shadowBlur = 12; circle(b.x, b.y, 24, `${color}28`, `${color}aa`, 1.5); ctx.shadowBlur = 0;
      circle(b.x - 7, b.y - 9, 4, '#ffffff40'); label(b.value, b.x, b.y + 1, 21, color, 'center', 750);
    }
    if (!s.ball) {
      ctx.save(); ctx.setLineDash([4, 8]);
      let x = 400, y = 454, vx = Math.cos(s.angle), vy = Math.sin(s.angle);
      ctx.beginPath(); ctx.moveTo(x, y);
      for (let i = 0; i < (s.difficulty === 'challenge' ? 10 : 28); i++) { x += vx * 9; y += vy * 9; if (x < 140 || x > 660) { x = clamp(x, 140, 660); vx *= -1; } ctx.lineTo(x, y); }
      ctx.strokeStyle = '#75dbc58c'; ctx.lineWidth = 2; ctx.stroke(); ctx.restore();
    }
    line(400, 454, 400 + Math.cos(s.angle) * 40, 454 + Math.sin(s.angle) * 40, '#66d8be', 12);
    circle(400, 454, 23, '#326e6b', '#8de0ce', 2); label('ƒ', 400, 455, 24, '#effff8', 'center', 800);
    if (s.ball) { ctx.shadowColor = '#8ce8d3'; ctx.shadowBlur = 16; circle(s.ball.x, s.ball.y, 13, '#d5fff3'); ctx.shadowBlur = 0; label('?', s.ball.x, s.ball.y + 1, 16, '#17463e', 'center', 800); }
    label('출력값을 찾아 조준해요', 400, 490, 12, '#8fabbf');
    label('벽에', 80, 203, 13, '#7e9ab0'); label('튕겨요 ↗', 80, 224, 13, '#7e9ab0');
  }
  function drawInvaders() {
    const s = session;
    for (let i = 0; i < 65; i++) { const x = (i * 137 + 27) % W, y = (i * 71 + s.elapsed * (i % 3 + 1) * 7) % H; circle(x, y, i % 3 === 0 ? 1.4 : .8, '#abc4e05c'); }
    ctx.save(); ctx.setLineDash([7, 8]); line(25, 409, 775, 409, '#65728977'); ctx.restore();
    label('지구 방어선', 745, 424, 12, '#a6b1c4', 'right');
    const pixels = ['001000100', '000101000', '001111100', '011010110', '111111111', '101111101', '101000101', '000101000'];
    s.aliens.forEach((alien, i) => {
      const color = ['#9bafff', '#77dfc7', '#ffc288', '#f3a3c3'][i];
      pixels.forEach((row, r) => [...row].forEach((v, c) => { if (v === '1') { ctx.fillStyle = color; ctx.fillRect(alien.x - 27 + c * 6, alien.y - 25 + r * 5, 5, 4); } }));
      rounded(alien.x - 24, alien.y + 20, 48, 29, 7, `${color}22`, `${color}55`); label(alien.value, alien.x, alien.y + 35, 19, color, 'center', 750);
    });
    for (const b of s.bullets) rounded(b.x - 2, b.y - 13, 4, 18, 2, '#91ffe0');
    for (const b of s.enemyBullets) rounded(b.x - 3, b.y - 5, 6, 15, 3, '#ff9c98');
    ctx.globalAlpha = s.invulnerable > 0 ? .45 + .35 * Math.sin(s.elapsed * 25) : 1;
    const x = s.player, y = 450;
    ctx.beginPath(); ctx.moveTo(x, y - 25); ctx.lineTo(x + 24, y + 17); ctx.lineTo(x + 7, y + 10); ctx.lineTo(x, y + 17); ctx.lineTo(x - 7, y + 10); ctx.lineTo(x - 24, y + 17); ctx.closePath(); ctx.fillStyle = '#bde8df'; ctx.fill();
    line(x, y - 12, x, y + 6, '#4ac0a8', 4); ctx.globalAlpha = 1;
    if (s.phase === 'playing') { ctx.fillStyle = '#f8bf78'; ctx.fillRect(x - 4, y + 20, 8, 9 + Math.sin(s.elapsed * 30) * 4); }
  }
  function drawMaze() {
    const s = session, size = 64, left = 112, top = 26;
    for (const cell of s.cells) {
      const x = left + cell.col * size, y = top + cell.row * size;
      if (cell.wall) { rounded(x + 2, y + 2, size - 4, size - 4, 7, '#253b51', '#31485e'); rounded(x + 8, y + 8, size - 16, 6, 3, '#2d465f'); continue; }
      const current = s.position.col === cell.col && s.position.row === cell.row;
      rounded(x + 3, y + 3, size - 6, size - 6, 8, cell.revealed ? '#703c4a' : current ? '#265d63' : '#192f42', cell.revealed ? '#d78294' : current ? '#75e2c5' : '#355066');
      label(tileNumber(cell.value), x + 32, y + 25, 19, cell.revealed ? '#ffc3c8' : '#c1d4df', 'center', 700);
      const keyIndex = s.mazeKeys.findIndex(k => k.col === cell.col && k.row === cell.row);
      if (keyIndex >= 0 && !s.collected.includes(keyIndex)) { circle(x + 25, y + 45, 5, null, '#ffd078', 2.5); line(x + 30, y + 45, x + 42, y + 45, '#ffd078', 3); line(x + 39, y + 45, x + 39, y + 50, '#ffd078', 3); }
      if (cell.col === 7 && cell.row === 1) label(s.collected.length === 3 ? '출구 ↗' : '잠김 ▣', x + 32, y + 46, 12, s.collected.length === 3 ? '#8ef3ce' : '#d8b7e9');
      if (cell.revealed) label('통과 불가', x + 32, y + 47, 11, '#ffc3c8');
      if (current) { circle(x + 32, y + 46, 10, '#78e1c4', '#d3fff2', 2); circle(x + 29, y + 44, 1.6, '#193e44'); circle(x + 35, y + 44, 1.6, '#193e44'); }
    }
    label('START', 80, 379, 11, '#78e1c4'); label('→', 80, 400, 20, '#78e1c4');
    label(`${s.steps}걸음`, 400, 487, 12, '#9bb1c5');
  }
  function worldBounds(type = selected) { return type === 'shot' ? { xmin: 0, xmax: 17, ymin: 0, ymax: 10 } : { xmin: -1, xmax: 13, ymin: -1, ymax: 9 }; }
  function worldPoint(x, y, type = selected) {
    const b = worldBounds(type); return { x: 58 + (x - b.xmin) / (b.xmax - b.xmin) * 694, y: 453 - (y - b.ymin) / (b.ymax - b.ymin) * 421 };
  }
  function plotGrid() {
    const b = worldBounds();
    for (let x = Math.ceil(b.xmin); x <= b.xmax; x++) { const p = worldPoint(x, 0); line(p.x, 32, p.x, 453, '#3a52633d'); if (x >= 0) label(x, p.x, 471, 11, '#89a2b6'); }
    for (let y = Math.max(0, Math.ceil(b.ymin)); y <= b.ymax; y++) { const p = worldPoint(0, y); line(58, p.y, 752, p.y, '#3a52633d'); label(y, 42, p.y, 11, '#89a2b6'); }
    const zero = worldPoint(0, 0); line(58, zero.y, 760, zero.y, '#6a8a9d', 1.5); line(zero.x, 24, zero.x, 453, '#6a8a9d', 1.5);
    label('x', 771, zero.y, 14, '#a3c7cf'); label('y', zero.x, 16, 14, '#a3c7cf');
  }
  function curve(fn, color, width = 3, dashed = false, maxX = 12) {
    ctx.save(); ctx.beginPath(); ctx.rect(58, 32, 694, 421); ctx.clip(); ctx.beginPath();
    let connected = false, previous = 0;
    for (let x = selected === 'shot' ? 1 : 0; x <= maxX; x += .025) {
      const y = fn(x), p = worldPoint(x, y);
      if (!Number.isFinite(y) || y > 30 || y < -30) { connected = false; continue; }
      if (connected && Math.abs(y - previous) < 1) ctx.lineTo(p.x, p.y); else ctx.moveTo(p.x, p.y);
      previous = y; connected = true;
    }
    if (dashed) ctx.setLineDash([5, 7]); ctx.lineWidth = width; ctx.strokeStyle = color; ctx.stroke(); ctx.restore();
  }
  function trace() {
    const points = session.trace; if (points.length < 2) return;
    ctx.save(); ctx.beginPath(); ctx.rect(58, 32, 694, 421); ctx.clip(); ctx.beginPath();
    points.forEach((point, i) => { const p = worldPoint(point.x, point.y); if (!i) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); });
    ctx.setLineDash([3, 5]); ctx.strokeStyle = '#ffd18b88'; ctx.lineWidth = 2; ctx.stroke(); ctx.restore();
  }
  function drawMarble() {
    const s = session; plotGrid();
    if (s.formula) { curve(trackHeight, '#60ddbf', 4); curve(x => trackHeight(x) - .12, '#60ddbf22', 7); }
    trace();
    const start = worldPoint(0, marbleLevels()[s.round].start);
    rounded(start.x - 17, start.y + 4, 34, 10, 3, '#b9a0f7'); label(`(0, ${number(marbleLevels()[s.round].start)})`, start.x + 15, start.y - 29, 12, '#ccbcff', 'left');
    for (const item of s.stars) {
      const p = worldPoint(item.x, item.y); circle(p.x, p.y, 21, item.collected ? '#63d9b211' : '#f7cc7310');
      star(p.x, p.y, item.collected ? 10 : 13, item.collected ? '#466a67' : '#ffd078');
      if (s.difficulty === 'relaxed') label(`(${item.x}, ${number(item.y - .22)})`, p.x, p.y + 31, 11, item.collected ? '#6a9c94' : '#c5bd9d');
    }
    const goal = worldPoint(s.goal.x, s.goal.y);
    circle(goal.x, goal.y, 20, '#70d6c51c', '#74dfbe', 2); label('✓', goal.x, goal.y, 23, '#81eac6'); label(s.difficulty === 'relaxed' ? `도착 (${s.goal.x}, ${number(s.goal.y - .22)})` : '도착', goal.x - 3, goal.y + 35, 11, '#b9d8c8');
    const ball = s.ball || { x: 0, y: marbleLevels()[s.round].start + .26 }, p = worldPoint(ball.x, ball.y);
    ctx.shadowColor = '#fff2b8'; ctx.shadowBlur = 15; circle(p.x, p.y, 10, '#ffe8a6', '#fff5d6', 1.5); ctx.shadowBlur = 0; circle(p.x - 3, p.y - 3, 3, '#fffbea');
  }
  function drawShot() {
    const s = session, level = shotLevels(s)[s.round]; plotGrid();
    const ground = worldPoint(0, .1); rounded(58, ground.y, 694, 7, 2, '#437966');
    curve(x => trajectory(x, s.angle, s.speed), '#8cc9c48a', 2, true, s.difficulty === 'challenge' ? 6 : 17);
    trace();
    if (level.wall) {
      const p = worldPoint(level.wall.x, level.wall.height), bottom = worldPoint(level.wall.x, 0);
      rounded(p.x - 13, p.y, 26, bottom.y - p.y, 3, '#68738e', '#8a96b5');
      for (let y = p.y + 13; y < bottom.y; y += 18) line(p.x - 12, y, p.x + 12, y, '#939db655');
      label(`${level.wall.height} m`, p.x, p.y - 16, 12, '#d0c2ed');
    }
    const origin = worldPoint(1, 1), target = worldPoint(level.target.x, level.target.y);
    line(origin.x - 10, origin.y + 5, origin.x - 8, origin.y + 34, '#bc9d7d', 6); line(origin.x + 10, origin.y + 5, origin.x + 8, origin.y + 34, '#bc9d7d', 6);
    circle(target.x, target.y, 22, '#66d9bb22', '#86e8cc', 2); circle(target.x, target.y, 13, '#66d9bb33', '#86e8cc', 1); circle(target.x, target.y, 4, '#9de5d2');
    label(`(${number(level.target.x)}, ${number(level.target.y)})`, target.x, target.y - 37, 12, '#b8e3d5');
    const ball = s.ball ? worldPoint(s.ball.x, s.ball.y) : origin;
    circle(ball.x, ball.y, 12, '#f6b887', '#ffe3b3', 1.5); circle(ball.x + 3, ball.y - 4, 2, '#3f3542');
    ctx.beginPath(); ctx.moveTo(ball.x + 10, ball.y - 1); ctx.lineTo(ball.x + 19, ball.y + 2); ctx.lineTo(ball.x + 10, ball.y + 5); ctx.fillStyle = '#f6d87e'; ctx.fill();
    if (!s.ball) {
      const rad = s.angle * Math.PI / 180; line(origin.x, origin.y, origin.x + Math.cos(rad) * 48, origin.y - Math.sin(rad) * 48, '#f6d092', 2);
      label(`${s.angle}°`, origin.x + 50, origin.y - 12, 12, '#f3d5a3');
    }
  }

  function territoryEvents(){return {loseLife,feedback,stageClear,finish,sound: name => audio.cue(name)};}
  function togglePaint(){
    if(selected!=='territory'||session.phase!=='playing')return;
    if(session.trail.length){feedback('안전한 길로 돌아와 경로를 먼저 닫아 주세요.');return;}
    session.paint=!session.paint;
    audio.cue('paint');
    const control=root?.querySelector('[data-action="arcade-paint"]');if(control)control.textContent=session.paint?'그리기 켜짐 · 길 닫기':'그리기 켜기';
    feedback(session.paint?'그리기가 켜졌어요. 안전한 길에서 출발해 다시 안전한 길로 돌아오세요.':'안전한 길에서 이동할 수 있어요.');
  }
  function open(id){if(!gameById(id))return;selected=id;session=newSession();refresh();}
  return { html: markup, mount, unmount, action, open };
}
