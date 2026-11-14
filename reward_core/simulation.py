"""Deterministic 20 Hz games. The server replays inputs, never client scores.

Integer coordinates and a 32-bit PRNG keep Python and JavaScript in agreement.
Inputs: left=1, right=2, up/jump=4, down=8, space-v2 fire=16.
Ticks are bounded by server time. Saved legacy rounds retain their old rules.
"""
from .catalog import GAMES
from .space_simulation import initial_space, step_space

HZ = 20


def rand(s, n):
    s['rng'] = (1664525 * s['rng'] + 1013904223) % 4294967296
    return s['rng'] % n


def score(s, points):
    s['combo'] += 1
    s['best_combo'] = max(s['best_combo'], s['combo'])
    s['score'] += points + min(10, s['combo'] // 3)


def hit(s):
    if s['t'] < s['safe']: return
    s['hits'] += 1; s['combo'] = 0; s['safe'] = s['t'] + 24


def blocks(s):
    s['objects'] = [dict(x=65+c*85, y=60+r*29, w=76, h=21, kind='block') for r in range(5) for c in range(7)]


def maze(s):
    w, h = 13, 7
    cells = [1] * (w*h); cells[w+1] = 0
    stack = [(1, 1)]
    while stack:
        x, y = stack[-1]
        options = [(x+dx, y+dy, dx, dy) for dx, dy in [(2,0),(-2,0),(0,2),(0,-2)]
                   if 0 < x+dx < w-1 and 0 < y+dy < h-1 and cells[(y+dy)*w+x+dx] == 1]
        if not options: stack.pop(); continue
        nx, ny, dx, dy = options[rand(s, len(options))]
        cells[(y+dy//2)*w+x+dx//2] = 0; cells[ny*w+nx] = 0
        stack.append((nx, ny))
    free = [i for i, cell in enumerate(cells) if not cell and i not in (14, 76)]
    for i in range(len(free)-1, 0, -1):
        j = rand(s, i+1); free[i], free[j] = free[j], free[i]
    s.update(cells=cells, treasures=free[:6], key_cell=free[6], traps=free[7:9], key=False, x=1, y=1)


def initial(game, seed):
    if game not in GAMES: raise ValueError('게임을 선택해 주세요.')
    s = dict(game=game, rng=int(seed) % 4294967296, t=0, prev=0, score=0, combo=0, best_combo=0,
             hits=0, safe=0, x=140, y=340, vy=0, grounded=True, objects=[], bullets=[],
             lane=1, boost=0, bx=360, by=315, vx=5, bvy=-7, level=1)
    if game == 'space': initial_space(s)
    if game == 'blocks': s['x'] = 360; blocks(s)
    if game == 'maze': maze(s)
    return s


def step(s, keys):
    s['t'] += 1
    t = s['t']; g = s['game']
    dx = int(bool(keys & 2)) - int(bool(keys & 1))
    jump = bool(keys & 4) and not bool(s['prev'] & 4)
    if g == 'jump':
        s['x'] = max(35, min(300, s['x'] + dx*7))
        old_y = s['y']
        if jump and s['grounded']: s['vy'] = -18
        s['vy'] = min(18, s['vy']+1); s['y'] += s['vy']; s['grounded'] = False
        if s['y'] >= 340: s.update(y=340, vy=0, grounded=True)
        if t % 34 == 1:
            kind = 'platform' if rand(s, 3) else 'spike'
            height = 35+rand(s, 3)*30
            s['objects'].append(dict(kind=kind, x=740, y=340-height, w=70, h=height, touched=False))
            s['objects'].append(dict(kind='star', x=770, y=300-height, w=18, h=18, touched=False))
        for o in s['objects']:
            o['x'] -= 5
            if o['kind'] == 'platform' and s['vy'] >= 0 and old_y <= o['y'] <= s['y'] and abs(s['x']-(o['x']+35)) < 47:
                s.update(y=o['y'], vy=0, grounded=True)
            if o['kind'] == 'star' and abs(s['x']-o['x']) < 28 and abs(s['y']-20-o['y']) < 28:
                score(s, 15); o['x'] = -100
            if o['kind'] in ('spike','platform') and abs(s['x']-(o['x']+35)) < 44 and s['y'] > o['y']+5:
                hit(s); o['touched'] = True
            if o['kind'] != 'star' and not o['touched'] and o['x']+70 < s['x']-15:
                score(s, 5); o['touched'] = True
        s['objects'] = [o for o in s['objects'] if o['x'] > -100]
    elif g == 'kart':
        if dx and (not s['prev'] & (1|2) or t % 6 == 0): s['lane'] = max(0, min(2, s['lane']+dx))
        s['x'] = 210+s['lane']*150
        if t % 16 == 1:
            s['objects'].append(dict(lane=rand(s, 3), y=-30, kind=['coin','car','boost'][rand(s, 3)], touched=False))
        for o in s['objects']:
            o['y'] += 7 if t < s['boost'] else 5
            if o['lane'] == s['lane'] and abs(o['y']-340) < 32:
                if o['kind'] == 'car': hit(s)
                else:
                    score(s, 20 if o['kind'] == 'boost' else 10)
                    if o['kind'] == 'boost': s['boost'] = t+45
                o['y'] = 500; o['touched'] = True
            elif o['kind'] == 'car' and o['y'] > 380 and not o['touched']:
                score(s, 5); o['touched'] = True
        if t % 20 == 0: s['score'] += 2
        s['objects'] = [o for o in s['objects'] if o['y'] < 480]
    elif g == 'space' and s.get('rules_version', 1) >= 2:
        step_space(s, keys, rand, score)
    elif g == 'space':
        s['x'] = max(30, min(690, s['x']+dx*10))
        dy = int(bool(keys & 8)) - int(bool(keys & 4))
        s['y'] = max(180, min(385, s['y']+dy*8))
        if t % 5 == 0: s['bullets'].append(dict(x=s['x'], y=s['y']-10))
        if t % 14 == 1: s['objects'].append(dict(x=30+rand(s, 660), y=-20, kind='rock', dead=False))
        for b in s['bullets']: b['y'] -= 15
        for o in s['objects']:
            o['y'] += 4
            for b in s['bullets']:
                if not o['dead'] and b['y'] > -50 and abs(b['x']-o['x']) < 25 and abs(b['y']-o['y']) < 25:
                    o['dead'] = True; b['y'] = -100; score(s, 20)
            if not o['dead'] and abs(s['x']-o['x']) < 35 and abs(s['y']-o['y']) < 30:
                hit(s); o['dead'] = True
        s['bullets'] = [b for b in s['bullets'] if b['y'] > -20]
        s['objects'] = [o for o in s['objects'] if not o['dead'] and o['y'] < 460]
    elif g == 'blocks':
        s['x'] = max(65, min(655, s['x']+dx*14))
        s['bx'] += s['vx']; s['by'] += s['bvy']
        if s['bx'] < 15 or s['bx'] > 705: s['vx'] *= -1; s['bx'] = max(15, min(705, s['bx']))
        if s['by'] < 25: s['bvy'] = abs(s['bvy'])
        if s['bvy'] > 0 and 345 <= s['by'] <= 365 and abs(s['bx']-s['x']) <= 70:
            s['bvy'] = -7; s['vx'] = max(-9, min(9, (s['bx']-s['x'])//7)) or 3
        for o in s['objects']:
            if o['x']-8 <= s['bx'] <= o['x']+o['w']+8 and o['y']-8 <= s['by'] <= o['y']+o['h']+8:
                s['bvy'] *= -1; s['objects'].remove(o); score(s, 10); break
        if s['by'] > 420:
            hit(s); s.update(bx=s['x'], by=315, vx=5 if rand(s, 2) else -5, bvy=-7)
        if not s['objects']: s['level'] += 1; score(s, 100); blocks(s)
    elif g == 'maze':
        if keys and (keys != s['prev'] or t % 4 == 0):
            dy = int(bool(keys & 8))-int(bool(keys & 4))
            nx, ny = s['x']+dx, s['y']+(dy if dx == 0 else 0)
            if 0 <= nx < 13 and 0 <= ny < 7 and not s['cells'][ny*13+nx]: s.update(x=nx, y=ny)
        cell = s['y']*13+s['x']
        if cell in s['treasures']: s['treasures'].remove(cell); score(s, 20)
        if cell == s['key_cell'] and not s['key']: s['key'] = True; score(s, 30)
        if cell in s['traps'] and (t//20) % 3 == 0 and t >= s['safe']:
            hit(s); s.update(x=1, y=1)
        if cell == 76 and s['key']:
            score(s, 100); s['level'] += 1; maze(s)
    s['prev'] = keys
    return s


def input_limit(s):
    return 31 if s['game'] == 'space' and s.get('rules_version', 1) >= 2 else 15


def replay(s, inputs):
    if not isinstance(inputs, list) or len(inputs) > 1800 or any(type(k) is not int or not 0 <= k <= input_limit(s) for k in inputs):
        raise ValueError('게임 입력을 확인해 주세요.')
    for keys in inputs: step(s, keys)
    return s
