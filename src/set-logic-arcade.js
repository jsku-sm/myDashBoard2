import { implies, regionValue } from './set-logic-math.js';

export const NEW_ARCADE_GAMES = [
  { id: 'territory', subject: 'sets', title: '벤 영역 볼피드', genre: '영역 점령', topic: '집합 연산 · 드모르간', tag: '길을 닫아 영역 획득!', desc: '움직이는 방해꾼을 피하며 경로를 닫고, 집합 조건에 맞는 땅을 점령해요.', controls: '방향키 · 그리기 버튼 또는 Space · 안전한 길로 돌아오면 영역 점령', goal: '그리기를 켜고 안전한 테두리에서 출발해 닫힌 길을 만들어요. 방해꾼이 없는 쪽에서 식에 맞는 칸만 획득해요. 각 스테이지의 목표 영역 75%를 모으면 성공! 조건과 다른 땅을 많이 감싸면 실드가 줄어요.', lesson: '겹친 곳은 교집합, 한쪽만은 차집합, “동시에 속하지 않음”은 교집합의 여집합이에요.' },
  { id: 'set-memory', subject: 'sets', title: '집합 메모리 카드', genre: '카드 뒤집기', topic: '부분집합 · 연산 법칙', tag: '식과 뜻을 연결!', desc: '부분집합의 개수와 집합 연산의 같은 표현을 찾아 짝지어요.', controls: '카드 클릭·터치 · Tab 선택 후 Enter', goal: '수학적으로 같은 내용을 나타내는 카드 6쌍을 찾아요. 부분집합·차집합·드모르간 법칙을 연결해요. 도전 모드에서는 18번 안에 찾아야 해요.', lesson: '기호 모양이 달라도 모든 원소에서 포함 여부가 같으면 같은 집합이에요.' },
  { id: 'counter', subject: 'logic', title: '반례 헌터 갤럭시', genre: '우주 슈팅', topic: '명제 · 반례 · 모든', tag: '반례를 조준!', desc: '가정은 참인데 결론은 거짓인 수를 찾아 움직이는 우주선을 격추해요.', controls: '← → 또는 A D 이동 · Space 발사 · 터치로 이동·발사', goal: '“p이면 q”를 거짓으로 만드는 반례 x가 적힌 우주선을 맞히세요. 가정이 거짓인 수는 반례가 아니에요. 탄환을 피하며 6개 명제를 모두 검증해요.', lesson: '모든 경우가 참이라는 주장은 반례 하나로 거짓임을 보일 수 있어요. 반례는 p가 참이고 q가 거짓인 경우예요.' },
  { id: 'logic-memory', subject: 'logic', title: '논리 메모리 카드', genre: '카드 뒤집기', topic: '부정 · 대우 · 조건', tag: '말과 화살표의 연결!', desc: '모든·어떤의 부정, 대우, 필요·충분조건을 같은 의미끼리 짝지어요.', controls: '카드 클릭·터치 · Tab 선택 후 Enter', goal: '논리적으로 대응하는 카드 6쌍을 찾아요. 역과 대우의 차이, 조건의 방향과 양화사의 부정을 함께 확인해요. 도전 모드에서는 18번 안에 찾아야 해요.', lesson: '대우는 순서와 부정을 모두 바꾸고, “모든”의 부정은 “어떤 …은 아니다”로 표현해요.' }
];
export const SET_MEMORY_PAIRS = [
  { left: '원소가 3개인 집합의\n부분집합의 개수', right: '2³ = 8개', why: '각 원소마다 포함·제외의 두 가지 선택이 있으므로 2³=8개예요.' },
  { left: '원소가 3개인 집합의\n진부분집합의 개수', right: '2³ − 1 = 7개', why: '부분집합 8개에서 자기 자신 하나만 제외하면 7개예요. 공집합은 포함돼요.' },
  { left: 'A − B', right: 'A ∩ Bᶜ', why: 'A에 속하면서 B에는 속하지 않는 원소만 남기면 차집합이에요.' },
  { left: '(A ∪ B)ᶜ', right: 'Aᶜ ∩ Bᶜ', why: '어느 쪽에도 속하지 않는다는 말은 A에도 없고 B에도 없다는 뜻이에요.' },
  { left: '(A ∩ B)ᶜ', right: 'Aᶜ ∪ Bᶜ', why: '둘 다 속하는 경우가 아니라면 적어도 하나에는 속하지 않아요.' },
  { left: 'n(A∪B)', right: 'n(A)+n(B)−n(A∩B)', why: '공통 부분은 두 번 더해졌으므로 한 번 빼야 해요.' }
];
export const LOGIC_MEMORY_PAIRS = [
  { left: 'p → q의 대우', right: '¬q → ¬p', why: '가정과 결론의 순서를 바꾸고 둘 다 부정하면 대우예요.' },
  { left: '“모든 x에서 p”의 부정', right: '어떤 x에서는 ¬p', why: '“모든”을 “어떤”으로 바꾸고 조건도 부정해요.' },
  { left: '“어떤 x에서 p”의 부정', right: '모든 x에서 ¬p', why: '하나라도 존재한다는 말의 부정은 하나도 존재하지 않는다는 뜻이에요.' },
  { left: 'p는 q의 충분조건', right: 'P ⊆ Q (p ⇒ q)', why: 'p를 만족하면 q도 만족하므로 p의 진리집합이 q의 진리집합에 포함돼요.' },
  { left: 'p는 q의 필요조건', right: 'Q ⊆ P (q ⇒ p)', why: 'q이려면 p가 꼭 필요해요. 화살표는 q에서 p로 향해요.' },
  { left: 'p → q의 반례', right: 'p는 참, q는 거짓', why: '가정을 만족하지만 결론을 만족하지 않는 구체적인 예가 반례예요.' }
];
export const COUNTER_ROUNDS = [
  { prompt: 'x²=4이면 x=2이다. 반례 x는?', p: x => x * x === 4, q: x => x === 2, answer: -2, choices: [-2, 2, 0, 3], why: 'x=−2이면 x²=4는 참이고 x=2는 거짓이므로 반례예요.' },
  { prompt: 'x가 4의 배수이면 8의 배수이다. 반례 x는?', p: x => x % 4 === 0, q: x => x % 8 === 0, answer: 4, choices: [4, 8, 16, 3], why: '4는 4의 배수지만 8의 배수는 아니에요. 가정이 참·결론이 거짓이에요.' },
  { prompt: 'x²−x=0이면 x=1이다. 반례 x는?', p: x => x * x - x === 0, q: x => x === 1, answer: 0, choices: [0, 1, 2, -1], why: 'x=0은 방정식 x²−x=0을 만족하지만 x=1은 아니므로 반례예요.' },
  { prompt: 'x<1이면 x²<1이다. 반례 x는?', p: x => x < 1, q: x => x * x < 1, answer: -2, choices: [-2, 0, .5, 2], why: 'x=−2는 1보다 작지만 제곱은 4이므로 결론이 거짓이에요.' },
  { prompt: 'x²>0이면 x>0이다. 반례 x는?', p: x => x * x > 0, q: x => x > 0, answer: -1, choices: [-1, 0, 1, 2], why: '음수도 제곱하면 양수예요. x=−1은 가정이 참이면서 결론이 거짓이에요.' },
  { prompt: 'x²−4x=0이면 x=4이다. 반례 x는?', p: x => x * x - 4 * x === 0, q: x => x === 4, answer: 0, choices: [0, 4, 1, -1], why: '해는 0과 4예요. 해 0을 빠뜨렸으므로 x=0이 반례예요.' }
];

export const TERRITORY_LEVELS = [
  { expression: ['intersect', 'A', 'B'], label: 'A ∩ B', hint: '두 원의 겹친 곳을 감싸요. 공통 영역을 나누어 조금씩 점령할 수도 있어요.', why: '교집합은 A와 B에 동시에 속하는 원소들의 영역이에요.' },
  { expression: ['diff', 'A', 'B'], label: 'A − B = A ∩ Bᶜ', hint: '왼쪽 원 A 안이면서 오른쪽 원 B 바깥인 곳이 목표예요.', why: '차집합은 A에 속하고 B에는 속하지 않는 영역이에요.' },
  { expression: ['not', ['intersect', 'A', 'B']], label: '(A ∩ B)ᶜ = Aᶜ ∪ Bᶜ', hint: '겹친 곳을 제외한 모든 곳이 목표예요. 원 바깥도 전체집합 U 안에 있어요.', why: '교집합의 여집합은 적어도 한 집합에는 속하지 않는 모든 원소예요. 드모르간의 법칙이에요.' }
];
const COLS = 18, ROWS = 12, CELL = 32, LEFT = 112, TOP = 45;
const index = (c, r) => r * COLS + c;
const territoryLevel = s => (s.content?.territoryLevels || TERRITORY_LEVELS)[s.round];
export const territoryMask = (c, r) => (Math.hypot(c - 6.5, r - 5.5) < 4.2 ? 1 : 0) | (Math.hypot(c - 10.5, r - 5.5) < 4.2 ? 2 : 0);
export function setupTerritory(s) {
  const level = territoryLevel(s);
  s.land = Array.from({ length: COLS * ROWS }, (_, i) => {
    const c = i % COLS, r = Math.floor(i / COLS), border = c === 0 || c === COLS - 1 || r === 0 || r === ROWS - 1;
    return { safe: border, owned: false, target: !border && regionValue(level.expression, territoryMask(c, r)) };
  });
  s.position = { col: 0, row: 6 }; s.trail = []; s.trailStart = { ...s.position }; s.paint = false; s.moveCooldown = 0; s.landTime = 0;
  s.enemy = { x: 13.4, y: 2.4, vx: s.difficulty === 'challenge' ? 2.6 : 1.3, vy: s.difficulty === 'challenge' ? 2.2 : 1.05 };
  s.message = '그리기를 켠 뒤 테두리에서 출발하세요. 안전한 길로 돌아오면 경로가 닫혀요.'; s.feedback = '';
}
export const territoryProgress = s => s.land.filter(cell => cell.owned && cell.target).length / s.land.filter(cell => cell.target).length;
function resetTrail(s) { s.position = { ...s.trailStart }; s.trail = []; s.paint = false; }
export function closeTerritory(s, events) {
  const boundary = new Set(s.trail), reachable = new Set(), queue = [];
  let seed = index(Math.round(s.enemy.x), Math.round(s.enemy.y));
  if (s.land[seed]?.safe || boundary.has(seed)) seed = s.land.findIndex((cell, i) => !cell.safe && !boundary.has(i));
  if (seed >= 0) { reachable.add(seed); queue.push(seed); }
  while (queue.length) {
    const i = queue.pop(), col = i % COLS, row = Math.floor(i / COLS);
    for (const [dc, dr] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      const c = col + dc, r = row + dr, next = index(c, r);
      if (c < 0 || c >= COLS || r < 0 || r >= ROWS || s.land[next].safe || boundary.has(next) || reachable.has(next)) continue;
      reachable.add(next); queue.push(next);
    }
  }
  const captured = s.land.map((cell, i) => !cell.safe && !reachable.has(i) ? i : -1).filter(i => i >= 0);
  let gained = 0, wrong = 0;
  for (const i of captured) {
    if (s.land[i].target) { if (!s.land[i].owned) gained++; s.land[i].owned = true; s.land[i].safe = true; }
    else if (!boundary.has(i)) wrong++;
  }
  for (const i of s.trail) s.land[i].safe = true; // thin roads stay traversable; only target land counts as owned.
  s.score += Math.max(0, gained * 12 - wrong * 2); s.trail = []; s.paint = false;
  const text = `목표 ${gained}칸 획득! 조건에 맞지 않는 ${wrong}칸은 점령하지 않았어요. ${territoryLevel(s).why}`;
  if (wrong > gained * 2 + 4 || !gained) { events.loseLife('목표가 아닌 영역을 크게 감쌌어요. ' + territoryLevel(s).hint); }
  else { events.sound?.('capture'); events.feedback(text, 'ok'); }
  if (s.phase === 'playing' && territoryProgress(s) >= .75) events.stageClear(`${territoryLevel(s).label} 영역의 ${Math.round(territoryProgress(s) * 100)}%를 점령했어요. ${territoryLevel(s).why}`);
}
export function moveTerritory(s, direction, events) {
  if (s.phase !== 'playing' || s.moveCooldown > 0) return;
  const delta = ({ left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] })[direction]; if (!delta) return;
  s.moveCooldown = .105;
  const col = s.position.col + delta[0], row = s.position.row + delta[1];
  if (col < 0 || col >= COLS || row < 0 || row >= ROWS) return;
  const next = index(col, row), cell = s.land[next];
  if (!cell.safe && !s.paint) { events.feedback('먼저 그리기 버튼을 켜고 안전한 길에서 출발해요.'); return; }
  if (!cell.safe) {
    if (s.trail.includes(next)) { resetTrail(s); events.loseLife('내가 그린 경로와 부딪혔어요. 길이 서로 겹치지 않게 닫아 보세요.'); return; }
    if (!s.trail.length) s.trailStart = { ...s.position };
    s.trail.push(next);
  }
  s.position = { col, row };
  events.sound?.('step');
  if (cell.safe && s.trail.length) closeTerritory(s, events);
}
export function updateTerritory(s, dt, keys, events) {
  s.moveCooldown = Math.max(0, s.moveCooldown - dt); s.landTime += dt;
  const direction = keys.has('arrowleft') || keys.has('a') ? 'left' : keys.has('arrowright') || keys.has('d') ? 'right' : keys.has('arrowup') || keys.has('w') ? 'up' : keys.has('arrowdown') || keys.has('s') ? 'down' : null;
  if (direction) moveTerritory(s, direction, events);
  if (s.phase !== 'playing') return;
  const enemy = s.enemy;
  const nx = enemy.x + enemy.vx * dt, ny = enemy.y + enemy.vy * dt;
  if (nx < .7 || nx > COLS - 1.7 || s.land[index(Math.round(nx), Math.round(enemy.y))]?.safe) enemy.vx *= -1; else enemy.x = nx;
  if (ny < .7 || ny > ROWS - 1.7 || s.land[index(Math.round(enemy.x), Math.round(ny))]?.safe) enemy.vy *= -1; else enemy.y = ny;
  if (s.trail.some(i => Math.hypot(i % COLS - enemy.x, Math.floor(i / COLS) - enemy.y) < .55)) { resetTrail(s); events.loseLife('방해꾼이 완성 전 경로에 닿았어요. 짧은 경로를 나누어 닫아 보세요.'); }
  const limit = s.difficulty === 'challenge' ? 65 : 120;
  if (s.landTime > limit && s.phase === 'playing') events.finish(false, `${limit}초의 스테이지 탐구 시간이 지났어요. 목표 식의 영역을 먼저 살피고 다시 도전해요.`);
}
export function drawTerritory(ctx, s) {
  const text = (label, x, y, size, color = '#adc8d2') => { ctx.font = `600 ${size}px -apple-system, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = color; ctx.fillText(label, x, y); };
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
    const i = index(c, r), cell = s.land[i], mask = territoryMask(c, r);
    ctx.fillStyle = cell.owned ? '#489c83' : cell.safe ? '#52677e' : mask === 3 ? '#384760' : mask === 1 ? '#203e46' : mask === 2 ? '#34354e' : '#182d3d';
    ctx.fillRect(LEFT + c * CELL + 1, TOP + r * CELL + 1, CELL - 2, CELL - 2);
    if (cell.safe && !cell.owned && c > 0 && c < COLS - 1 && r > 0 && r < ROWS - 1) { ctx.fillStyle = '#adbfca'; ctx.fillRect(LEFT + c * CELL + 13, TOP + r * CELL + 13, 6, 6); }
    if (s.trail.includes(i)) { ctx.fillStyle = '#f0c47d'; ctx.fillRect(LEFT + c * CELL + 7, TOP + r * CELL + 7, CELL - 14, CELL - 14); }
  }
  [6.5, 10.5].forEach((col, i) => { ctx.beginPath(); ctx.arc(LEFT + (col + .5) * CELL, TOP + 6 * CELL, 4.2 * CELL, 0, Math.PI * 2); ctx.lineWidth = 2; ctx.strokeStyle = i ? '#b8a2e07c' : '#87d5b97c'; ctx.stroke(); text(i ? 'B' : 'A', LEFT + (col + .5) * CELL, TOP + 52, 18, i ? '#c4b1e1' : '#9ee2c8'); });
  const x = LEFT + (s.position.col + .5) * CELL, y = TOP + (s.position.row + .5) * CELL;
  ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.fillStyle = '#b1f1d1'; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = '#fff6d2'; ctx.stroke();
  const ex = LEFT + (s.enemy.x + .5) * CELL, ey = TOP + (s.enemy.y + .5) * CELL;
  ctx.beginPath(); ctx.arc(ex, ey, 10, 0, Math.PI * 2); ctx.fillStyle = '#f3a39a'; ctx.fill(); text('×', ex, ey, 15, '#683a44');
  text('U', 90, 62, 17); text(`목표 영역 ${Math.round(territoryProgress(s) * 100)}% / 75%`, 400, 456, 15, '#9bd9c1');
  text(s.paint ? '그리는 중 · 안전한 길로 돌아오세요' : '안전한 길 · 그리기를 켜고 출발하세요', 400, 483, 12, s.paint ? '#f0c47d' : '#a4b9c9');
}
