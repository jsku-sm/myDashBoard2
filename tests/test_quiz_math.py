"""Independent expected values for 112 parameterized concept families.

Checks numeric/algebraic/logic answer labels, not teacher-edited free-form items.
Uses no runtime, network, curriculum service, or external model.
"""
from fractions import Fraction
import math
import random
import pytest
from quiz_core import bank


class TraceRandom(random.Random):
    def __init__(self, seed):
        super().__init__(seed); self.draws=[]
    def randint(self,a,b):
        value=super().randint(a,b); self.draws.append(value); return value


def oracle(subject,unit,k,d):
    a,b,c,x,y=d[:5]
    if subject=='공통수학1':
        if unit==0: return [a+c,a*c,b-a,sum([a*x**2,b*x,c]),a+b,b+2,a+b][k]
        if unit==1: return [c**2+a*c+b,c,c,sum([a,b,c,a+b]),-(a+b),(-c)**2+a*(-c)+b,b][k]
        if unit==2: return [b,a,a,c,b,a,a][k]
        if unit==3:
            if k==0:
                z=complex(0,1)**d[5]
                return {1+0j:'1',-1+0j:'-1',1j:'i',-1j:'-i'}[z]
            return [None,a+c,(a+complex(0,b))*(a-complex(0,b)),a+b,b**2-4*a*c,a*b,a+b][k]
        if unit==4: return [a,b,b,a,1,a**2+b,a][k]
        if unit==5: return [c,f'x > -{b}',len(list(range(-a+1,a))),a,3,a+b,len(list(range(-a+1,a)))][k]
        if unit==6:
            if k==2: return sum(d[5]-1 for _ in range(d[5]))
            if k==3:
                # Independent enumeration of unordered subsets.
                from itertools import combinations
                return sum(1 for _ in combinations(range(d[5]),d[6]))
            if k==4:
                from itertools import permutations
                return sum(1 for _ in permutations(range(d[5]),d[6]))
            return [a*b,a+b,None,None,None,(a+2)*(a+1),a+2][k]
        if unit==7: return [c,a+c,c*b,sum(v*w for v,w in zip([a,b],[c,2])),a*b,a,b][k]
    if unit==0: return [a,(x+(x+2*a))//2,(y+(y+2*b))//2,a,int(math.hypot(3*a,4*a)),2,3*b][k]
    if unit==1: return [a,b,Fraction(a*b,a),a,Fraction(-1,a),y-a*x,a][k]
    if unit==2: return [a,c,c*c,b,1,0,c+c][k]
    if unit==3: return [f'({x}, {-a})',f'({-a}, {y})',f'({-a}, {-b})',x+a,y,a+c,a+(a-x)][k]
    if unit==4:
        if k in (3,5):
            from itertools import combinations
            count=sum(sum(1 for _ in combinations(range(d[5]),size)) for size in range(d[5]+1))
            return count if k==3 else count-1
        return [a+b+c,b,a,None,1,None,0][k]
    if unit==5: return [f'x ≤ {a}',f'x>{a}이면 x>{a+b}이다',f'x≤{a}이면 x≤{a+b}이다',
                       '충분조건이지만 필요조건은 아니다',f'x≠{a} 그리고 x≠{a+1}',-a,
                       f'어떤 실수 x에 대해 x²≤{a}이다'][k]
    if unit==6: return [a*c+b,b*c+a,c,max(a*v+b for v in (1,2,3)),(c+a)-b,a+b,c][k]
    if unit==7: return [b,c,Fraction(a,1)+c,a,b,int(math.sqrt(c*c))+b,b][k]
    raise AssertionError('Missing oracle')


@pytest.mark.parametrize('subject',bank.SUBJECTS)
@pytest.mark.parametrize('unit',range(8))
@pytest.mark.parametrize('family',range(7))
def test_all_answer_families_with_independent_values(subject,unit,family):
    for seed in range(24):
        r=TraceRandom(103*seed+family)
        q=bank._candidate(subject,unit,family,r,span=15)
        expected=oracle(subject,unit,family,r.draws)
        if isinstance(expected,complex):
            assert abs(expected.imag)<1e-9
            expected=int(expected.real)
        label=bank.text(expected)
        assert len(q['options'])==4 and len(set(q['options']))==4
        assert q['options'].count(label)==1
        assert q['options'][q['answer']]==label, q['prompt']
