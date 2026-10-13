"""Validated graph captures and audio submissions."""
import base64
import copy
import io
import json
import wave

from .ai import normalized_image
from .storage import AppError

MODES = {"writing": "직접 쓰며 풀기", "quiz": "퀴즈", "graph": "데스모스 그래프"}


def activity_mode(task):
    if "데스모스" in task.get("title", "") or "desmos" in task.get("title", "").lower():
        return "graph"
    return task.get("mode", "writing")


def validated_graph(value):
    if not isinstance(value, dict) or not value.get("ready"):
        raise AppError("그래프가 답안에 반영될 때까지 기다리거나 ‘현재 그래프 반영’을 눌러주세요.")
    state, expressions = value.get("state"), value.get("expressions")
    if not isinstance(state, dict) or not isinstance(expressions, list) or not expressions:
        raise AppError("그래프에 수식을 하나 이상 입력하세요.")
    if len(expressions) > 100 or any(not isinstance(e, dict) for e in expressions):
        raise AppError("그래프 수식을 확인하세요.")
    state_expressions = state.get("expressions")
    saved = state_expressions.get("list") if isinstance(state_expressions, dict) else None
    if not isinstance(saved, list) or any(not isinstance(e, dict) for e in saved):
        raise AppError("그래프 저장 상태를 다시 반영해주세요.")

    def expression_content(expression):
        identity = expression.get("id")
        latex = expression.get("latex", "")
        if not isinstance(identity, str) or not identity or not isinstance(latex, str):
            raise AppError("그래프 수식을 확인하세요.")
        return (identity, expression.get("type", "expression"), latex, expression.get("columns"))

    saved_math = [e for e in saved if (isinstance(e.get("latex"), str) and e["latex"].strip())
                  or e.get("type") == "table"]
    if ([expression_content(e) for e in expressions] != [expression_content(e) for e in saved_math] or
            len({e.get("id") for e in expressions}) != len(expressions)):
        raise AppError("그래프 수식과 저장 상태가 다릅니다. 현재 그래프를 다시 반영해주세요.")
    if not any((isinstance(e.get("latex"), str) and e["latex"].strip()) or
               (e.get("type") == "table" and isinstance(e.get("columns"), list) and e["columns"])
               for e in expressions):
        raise AppError("그래프에 수식을 하나 이상 입력하세요.")
    try:
        serialized = json.dumps(dict(state=state, expressions=expressions), allow_nan=False)
    except (ValueError, TypeError):
        raise AppError("그래프 저장 형식을 확인하세요.") from None
    if len(serialized.encode()) > 500000:
        raise AppError("그래프가 너무 큽니다. 수식과 표의 개수를 줄여주세요.")
    image = value.get("image", "")
    if not isinstance(image, str) or not image.startswith("data:image/png;base64,") or len(image) > 16000000:
        raise AppError("그래프 이미지를 다시 반영해주세요.")
    try:
        capture = normalized_image(base64.b64decode(image.split(",", 1)[1], validate=True))
    except ValueError:
        raise AppError("그래프 이미지를 읽지 못했습니다.") from None
    return dict(state=copy.deepcopy(state), expressions=copy.deepcopy(expressions)), capture


def validate_audio(raw):
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        raise AppError("녹음 파일을 읽지 못했습니다. 다시 녹음하세요.")
    raw = bytes(raw)
    if len(raw) > 10000000:
        raise AppError("음성은 2분 이내로 녹음하세요.")
    try:
        with wave.open(io.BytesIO(raw), "rb") as audio:
            frames, rate = audio.getnframes(), audio.getframerate()
            if not 8000 <= rate <= 192000 or audio.getnchannels() not in (1, 2):
                raise AppError("녹음 파일의 음성 형식을 확인하세요. 다시 녹음하세요.")
            seconds = frames / rate
            if seconds <= 0 or seconds > 125:
                raise AppError("음성은 2분 이내로 녹음하세요.")
            expected_bytes = frames * audio.getnchannels() * audio.getsampwidth()
            if len(audio.readframes(frames)) != expected_bytes:
                raise AppError("녹음 파일이 완전히 저장되지 않았습니다. 다시 녹음하세요.")
    except (wave.Error, EOFError, ZeroDivisionError, ValueError):
        raise AppError("녹음 파일을 읽지 못했습니다. 다시 녹음하세요.") from None
    return raw
