"""에코스코프.agent 질의응답 — Vercel Python Function.

원칙: **화면이 이미 읽은 판독 결과의 범위에서만 답변합니다.**
프런트엔드가 질의와 함께 근거 묶음(evidence)을 전송하며, 여기서는 그것을 그대로
프롬프트에 포함시킵니다. 모델이 자료 외의 사실을 생성하지 못하도록,
자료에 없으면 없다고 답하도록 명시합니다.

인증키가 없거나 모델 호출이 실패하면 502 를 반환합니다. 프런트엔드는 그 경우
화면 자료만으로 답변하는 내장 응답기로 전환하며, 그 사실을 화면에 표시합니다.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
API_KEY = os.environ.get("GEMINI_API_KEY")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

MAX_QUESTION = 500
TIMEOUT_S = 45

SYSTEM = """당신은 국립생태원 생태정보 플랫폼 '에코스코프'의 판독 결과 해설 담당자입니다.
내륙습지의 Sentinel-1 SAR 개방수면 판독 결과를 읽고 담당자에게 설명합니다.

작성 원칙
1. 아래 <자료> 에 포함된 수치만 사용합니다. 자료에 없는 값은 추정하지 말고 "자료에 없습니다"라고 답합니다.
2. 수치를 제시할 때는 단위와 관측일자를 함께 기재합니다.
3. 본 판독으로 판단할 수 없는 사항을 질의받은 경우 명확히 불가함을 밝힙니다.
   - 수위(수심)는 측정하지 않습니다. 개방수면의 면적만 관측합니다.
   - 식생 하부 침수는 판정하지 않습니다. 오탐이 심하여 근거가 확립되지 않았습니다.
   - has_open_water 가 false 인 습지에는 개방수면 지표를 적용하지 않습니다.
   - confidence 가 low 인 습지-연도의 수치를 판단 근거로 삼아서는 안 됩니다.
4. 개방수면적이 감소하였다는 사실만으로 수량이 감소하였다고 단정하지 않습니다.
   같은 시기 VV 평균이 상승하였다면 수량은 유지된 상태에서 수생식물이 수면을 덮은 것입니다.
   optical 의 NDVI 가 함께 상승하였다면 그 해석이 광학 자료로도 확인된 것입니다.
5. 공공기관 보고 문체의 한국어로, 간결하게 3~6문장으로 작성합니다.
   존댓말을 사용하며 과장하지 않습니다.
6. 자기 역할이나 소속을 소개하지 말고 곧바로 답변 내용부터 씁니다."""


def _answer(question: str, evidence: dict) -> str:
    prompt = (
        f"{SYSTEM}\n\n<자료>\n"
        + json.dumps(evidence, ensure_ascii=False)
        + f"\n</자료>\n\n<질문>\n{question}\n</질문>\n\n답:"
    )
    # Gemini 3.x 는 사고(thinking) 토큰이 maxOutputTokens 를 함께 소진합니다.
    # 700 으로 두었더니 사고에 다 쓰이고 답변이 한 문장에서 잘렸습니다.
    # 이 용도(주어진 자료 안에서 요약)에는 깊은 사고가 필요 없으므로 낮춥니다.
    # thinkingBudget:0 은 이 모델에서 INVALID_ARGUMENT 로 거부되므로 thinkingLevel 을 씁니다.
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        ENDPOINT.format(model=MODEL),
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("모델이 응답 후보를 반환하지 않았습니다")
    first = candidates[0]
    parts = first.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError(f"빈 응답 (finishReason={first.get('finishReason')})")
    if first.get("finishReason") == "MAX_TOKENS":
        # 잘린 답을 온전한 답인 척 내보내지 않습니다.
        text += chr(10) + chr(10) + "(응답이 길이 제한에 걸려 중간에 끊겼습니다. 질문을 좁혀 다시 물어보시기 바랍니다.)"
    return text


class handler(BaseHTTPRequestHandler):  # noqa: N801  (Vercel 규약)
    def _send(self, code: int, obj: dict) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._send(400, {"error": "요청 본문을 JSON 으로 해석하지 못했습니다"})
            return

        question = (data.get("question") or "").strip()[:MAX_QUESTION]
        evidence = data.get("evidence") or {}
        if not question:
            self._send(400, {"error": "질의 내용이 비어 있습니다"})
            return
        if not API_KEY:
            self._send(502, {"error": "GEMINI_API_KEY 가 설정되지 않았습니다"})
            return

        try:
            self._send(200, {"answer": _answer(question, evidence), "model": MODEL})
        except urllib.error.HTTPError as exc:
            self._send(502, {"error": f"모델 호출에 실패하였습니다 (HTTP {exc.code})"})
        except Exception as exc:
            self._send(502, {"error": f"모델 호출에 실패하였습니다 ({type(exc).__name__})"})
