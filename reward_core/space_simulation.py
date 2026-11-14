"""Space Guardian v2. Integer rules mirrored by the browser, including pickups."""


def initial_space(s):
    s.update(rules_version=2, x=360, energy=100, shield_until=0, power_until=0, respawn_until=0,
             hurt_until=0, next_shot=0, next_enemy=1, shot_count=0, kills=0, deaths=0, pickups=0,
             drop_count=0, last_pickup='', pickup_until=0, enemy_bullets=[], drops=[], bursts=[])


def burst(s, x, y, kind):
    s['bursts'].append(dict(x=x, y=y, kind=kind, born=s['t']))


def near(a, b, radius):
    return (a['x']-b['x'])**2+(a['y']-b['y'])**2 < radius*radius


def damage(s, amount):
    t = s['t']
    if t < s['safe'] or t < s['respawn_until']: return
    if t < s['shield_until']:
        burst(s, s['x'], s['y'], 'shield'); s['safe'] = t+4; return
    s['energy'] = max(0, s['energy']-amount); s['hits'] += 1; s['combo'] = 0
    s['safe'] = t+16; s['hurt_until'] = t+5
    burst(s, s['x'], s['y'], 'damage')
    if not s['energy']:
        s['deaths'] += 1; s['respawn_until'] = t+30; s['safe'] = t+70; s['enemy_bullets'] = []


def step_space(s, keys, rand, score):
    t = s['t']; s['level'] = 1+min(2, t//600)
    s['bursts'] = [b for b in s['bursts'] if t-b['born'] < 12]
    if not s['energy'] and t >= s['respawn_until']:
        s.update(energy=100, x=360, y=340); burst(s, s['x'], s['y'], 'shield')
    ready = t >= s['respawn_until']
    if ready:
        s['x'] = max(30, min(690, s['x']+(int(bool(keys & 2))-int(bool(keys & 1)))*10))
        s['y'] = max(180, min(385, s['y']+(int(bool(keys & 8))-int(bool(keys & 4)))*8))
        if keys & 16 and t >= s['next_shot']:
            for vx in ([-3, 0, 3] if t < s['power_until'] else [0]):
                s['bullets'].append(dict(x=s['x'], y=s['y']-24, vx=vx, dead=False))
            s['shot_count'] += 1; s['next_shot'] = t+5
    if t >= s['next_enemy']:
        bomber = rand(s, 3) == 0
        s['objects'].append(dict(x=55+rand(s,610), y=-28, vx=2 if rand(s,2) else -2,
                                 kind='bomber' if bomber else 'fighter', hp=3 if bomber else 2,
                                 born=t, fire_at=t+40, dead=False))
        s['next_enemy'] = t+60-s['level']*10
    if t % 55 == 20:
        s['objects'].append(dict(x=35+rand(s,650), y=-25, vx=0, kind='rock', hp=1, born=t, fire_at=0, dead=False))
    if t % 160 == 60:
        kind = ['heal','shield','triple','star'][s['drop_count'] % 4]; s['drop_count'] += 1
        s['drops'].append(dict(x=65+rand(s,590), y=45, kind=kind, dead=False))
    for o in s['objects']:
        o['x'] += o['vx']
        if o['x'] < 30 or o['x'] > 690: o['vx'] *= -1
        o['y'] += 4 if o['kind'] == 'rock' else (2 if o['y'] < 80 or t-o['born'] > 180 else 0)
        if o['kind'] != 'rock' and 35 <= o['y'] < 190 and t >= o['fire_at']:
            bomb = o['kind'] == 'bomber'; vx = max(-3, min(3, (s['x']-o['x'])//70))
            s['enemy_bullets'].append(dict(x=o['x'], y=o['y']+20, vx=vx, vy=4 if bomb else 6,
                                           kind='bomb' if bomb else 'laser', dead=False))
            if s['level'] == 3 and not bomb:
                s['enemy_bullets'].append(dict(x=o['x'], y=o['y']+20, vx=vx-2 if vx>0 else vx+2, vy=6, kind='laser', dead=False))
            o['fire_at'] = t+70-s['level']*10
    for b in s['bullets']:
        b['x'] += b['vx']; b['y'] -= 14
        for o in s['objects']:
            if not b['dead'] and not o['dead'] and near(b,o,27):
                b['dead'] = True; o['hp'] -= 1; burst(s,b['x'],b['y'],'hit')
                if o['hp'] <= 0:
                    o['dead'] = True; s['kills'] += 1
                    score(s,40 if o['kind']=='bomber' else 30 if o['kind']=='fighter' else 15)
                    burst(s,o['x'],o['y'],'explode')
                    if s['kills'] % 4 == 0: s['drops'].append(dict(x=o['x'],y=o['y'],kind='star',dead=False))
        for shot in s['enemy_bullets']:
            if not b['dead'] and not shot['dead'] and shot['kind']=='bomb' and near(b,shot,17):
                b['dead'] = True; shot['dead'] = True; score(s,8); burst(s,shot['x'],shot['y'],'explode')
    for item in s['drops']:
        item['y'] += 2
        if ready and near(item,s,32):
            item['dead'] = True; s['pickups'] += 1; s['last_pickup'] = item['kind']; s['pickup_until'] = t+45
            if item['kind'] == 'heal': s['energy'] = min(100,s['energy']+30)
            if item['kind'] == 'shield': s['shield_until'] = t+120
            if item['kind'] == 'triple': s['power_until'] = t+160
            score(s,60 if item['kind']=='star' else 15); burst(s,item['x'],item['y'],'pickup')
    for shot in s['enemy_bullets']:
        shot['x'] += shot['vx']; shot['y'] += shot['vy']
        if not shot['dead'] and ready and near(shot,s,29 if shot['kind']=='bomb' else 23):
            shot['dead'] = True; damage(s,25 if shot['kind']=='bomb' else 12)
    for o in s['objects']:
        if not o['dead'] and ready and near(o,s,38):
            o['dead'] = True; damage(s,20); burst(s,o['x'],o['y'],'explode')
    s['bullets'] = [b for b in s['bullets'] if not b['dead'] and b['y']>-30 and -20<b['x']<740]
    s['enemy_bullets'] = [b for b in s['enemy_bullets'] if not b['dead'] and b['y']<460 and -30<b['x']<750]
    s['objects'] = [o for o in s['objects'] if not o['dead'] and o['y']<460]
    s['drops'] = [o for o in s['drops'] if not o['dead'] and o['y']<460]
