"""Pure validation, scoring and reports. Scores are computed on the server."""
from copy import deepcopy
import math

MODES = {
    "treasure": {"name": "보물상자 탐험", "icon": "🧰", "color": "#f3b541", "tag": "선택 · 행운",
                 "description": "정답을 맞히면 상자 3개 중 하나를 열어요. 숨겨진 코인을 모아 보세요!",
                 "rules": "정답 100점 + 상자 보너스 20·50·100점. 오답은 0점. 정답 수와 순위는 따로 기록해요."},
    "race": {"name": "우주 레이스", "icon": "🚀", "color": "#b393ff", "tag": "연속 정답 · 도전",
             "description": "정답으로 우주선을 전진시키고, 연속 정답으로 부스터를 켜요.",
             "rules": "정답 100점 + 연속 정답 보너스 10~50점. 오답이면 연속 기록이 초기화돼요. 속도 점수는 없어요."},
    "fishing": {"name": "바다 낚시왕", "icon": "🐠", "color": "#48d5d0", "tag": "전략 · 수집",
                "description": "정답을 맞힌 뒤 낚시터를 골라요. 잔잔한 바다 또는 깊은 바다?",
                "rules": "정답 100점. 얕은 바다는 +30점, 깊은 바다는 +0 또는 +80점(각 50%). 오답은 0점이에요."},
    "team": {"name": "팀 에너지 대결", "icon": "⚡", "color": "#ff8caa", "tag": "협력 · 함께",
             "description": "두 팀이 함께 에너지를 모아요. 한 사람의 정답이 우리 팀의 힘이 됩니다.",
             "rules": "자동 균형 배정 2팀. 정답당 100점. 팀원 수가 달라도 공정하도록 팀 평균 점수로 겨뤄요."},
    "practice": {"name": "차근차근 연습", "icon": "🌱", "color": "#a2d881", "tag": "개인 연습 · 복습",
                 "description": "나의 속도로 한 문제씩 확인해요. 친구의 순위 없이 내 결과에 집중해요.",
                 "rules": "정답당 100점. 학생 화면에는 친구 순위를 공개하지 않아요. 교사는 전체 결과를 확인할 수 있어요."},
}

class ReviewError(ValueError):
    pass


def validate_questions(values):
    if not isinstance(values, list) or not 1 <= len(values) <= 20:
        raise ReviewError("문제는 1~20개로 구성해 주세요.")
    result, seen = [], set()
    for i, q in enumerate(values):
        if not isinstance(q, dict):
            raise ReviewError("문제 형식을 확인해 주세요.")
        prompt = str(q.get("prompt", "")).strip()
        options = q.get("options")
        answer = q.get("answer")
        explanation = str(q.get("explanation", "")).strip()
        if not prompt or len(prompt) > 1800 or prompt in seen:
            raise ReviewError(f"{i+1}번: 문제 내용이 비어 있거나 중복·길이 초과입니다.")
        if (not isinstance(options, list) or not 2 <= len(options) <= 5
                or not all(isinstance(x, str) and 0 < len(x.strip()) <= 800 for x in options)):
            raise ReviewError(f"{i+1}번: 보기 2~5개를 입력해 주세요.")
        options = [x.strip() for x in options]
        if len(set(options)) != len(options) or type(answer) is not int or not 0 <= answer < len(options):
            raise ReviewError(f"{i+1}번: 보기 중복 또는 정답 번호를 확인해 주세요.")
        if not explanation or len(explanation) > 3000:
            raise ReviewError(f"{i+1}번: 해설을 1~3000자로 입력해 주세요.")
        seen.add(prompt)
        result.append(dict(id=f"q{i+1}", prompt=prompt, options=options, answer=answer,
                           explanation=explanation, concept=str(q.get("concept", "복습"))[:100],
                           source=str(q.get("source", "교사 작성"))[:500]))
    return result


def summary(attempt, questions):
    answers = attempt.get("answers", [])
    correct = sum(a["correct"] for a in answers)
    return {"answered": len(answers), "correct": correct, "wrong": len(answers)-correct,
            "unanswered": len(questions)-len(answers), "total": len(questions),
            "accuracy": round(correct/len(answers)*100, 1) if answers else 0,
            "score": sum(a["points"] for a in answers), "complete": len(answers) == len(questions)}


def reward_options(mode, randomizer):
    if mode == "treasure":
        values = [20, 50, 100]
        randomizer.shuffle(values)
        return values
    if mode == "fishing":
        return [30, randomizer.choice([0, 80])]
    return []


def answer_record(mode, questions, answers, index, choice, now, randomizer):
    if type(index) is not int or index != len(answers) or not 0 <= index < len(questions):
        raise ReviewError("이미 제출했거나 다른 문제입니다. 현재 문제를 확인해 주세요.")
    q = questions[index]
    if type(choice) is not int or not 0 <= choice < len(q["options"]):
        raise ReviewError("보기 중 하나를 선택해 주세요.")
    if answers and answers[-1].get("reward_pending"):
        raise ReviewError("먼저 보상을 선택해 주세요.")
    correct = choice == q["answer"]
    streak = 1
    for a in reversed(answers):
        if not a["correct"]:
            break
        streak += 1
    points = (100 + (min(streak, 5)*10 if mode == "race" else 0)) if correct else 0
    rewards = reward_options(mode, randomizer) if correct else []
    return dict(qid=q["id"], index=index, choice=choice, correct=correct, points=points, at=now,
                reward_pending=bool(rewards), reward_options=rewards, reward_choice=None, bonus=0)


def claim_reward(answer, choice):
    choices = answer.get("reward_options", [])
    if not answer.get("reward_pending"):
        return False  # idempotent retries cannot mint more points
    if type(choice) is not int or not 0 <= choice < len(choices):
        raise ReviewError("보상 중 하나를 골라 주세요.")
    answer.update(reward_choice=choice, bonus=choices[choice], points=answer["points"]+choices[choice], reward_pending=False)
    return True


def report(questions, attempts):
    rows = []
    for a in attempts:
        row = {k: a[k] for k in ("student_id", "name", "class", "alias", "team")}
        row.update(summary(a, questions))
        rows.append(row)
    rows.sort(key=lambda r: (-r["score"], -r["correct"], r["alias"]))
    prior, rank = None, 0
    for i, row in enumerate(rows):
        key = (row["score"], row["correct"])
        if key != prior:
            rank = i+1
        row["rank"], prior = rank, key
    stats = []
    for i, q in enumerate(questions):
        answers = [x for a in attempts for x in a["answers"] if x["qid"] == q["id"]]
        correct = sum(a["correct"] for a in answers)
        counts = [sum(a["choice"] == c for a in answers) for c in range(len(q["options"]))]
        stats.append(dict(qid=q["id"], number=i+1, prompt=q["prompt"], answered=len(answers), correct=correct,
                          wrong=len(answers)-correct, unanswered=len(attempts)-len(answers), choices=counts,
                          wrong_rate=round((len(answers)-correct)/len(answers)*100, 1) if answers else 0))
    teams = []
    for team in ("핑크 팀", "민트 팀"):
        members = [r for r in rows if r["team"] == team]
        if members:
            teams.append(dict(name=team, members=len(members), score=round(sum(r["score"] for r in members)/len(members), 1),
                              correct=sum(r["correct"] for r in members)))
    teams.sort(key=lambda r: -r["score"])
    return dict(rows=rows, questions=stats, teams=teams, participants=len(rows),
                answered=sum(r["answered"] for r in rows), correct=sum(r["correct"] for r in rows),
                wrong=sum(r["wrong"] for r in rows), completed=sum(r["complete"] for r in rows))
