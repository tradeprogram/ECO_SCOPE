"""판독 자료 질의응답 — Vercel Python Function.

원칙: **화면이 이미 읽은 판독 결과 안에서만 답한다.**
프런트가 질문과 함께 근거 묶음(evidence)을 보내오고, 여기서는 그것을 그대로
프롬프트에 넣는다. 모델이 자료 밖의 사실을 만들어내지 못하도록,
자료에 없으면 없다고 말하라고 명시한다.

키가 없거나 모델 호출이 실패하면 502 를 돌려준다. 프런트는 그 경우
화면 자료만으로 답하는 로컬 응답기로 내려간다 — 조용히 지어내지 않는다.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
API_KEY = os.environ.get("GEMINI_API_KEY")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

MAX_QUESTION = 500
TIMEOUT_S = 25

SYSTEM = """너는 '에코스코프'의 판독 자료 해설자다. 국립생태원 내륙습지의
Sentinel-1 SAR 개방수면 판독 결과를 읽고 담당자에게 설명한다.

지켜야 할 것:
1. 아래 <자료> 안에 있는 수치만 쓴다. 자료에 없는 값은 지어내지 말고 "자료에 없다"고 말한다.
2. 수치를 말할 때는 단위와 날짜를 붙인다.
3. 이 판독이 말할 수 없는 것을 묻거든 분명히 못 한다고 답한다:
   - 수위(깊이)는 재지 않는다. 개방수면의 넓이만 본다.
   - 식생 하부 침수는 판정하지 않는다. 오탐이 심해 근거가 서지 않는다.
   - has_open_water 가 false 인 습지에는 개방수면 지표를 적용하지 않는다.
   - confidence 가 low 인 습지-연도의 수치로 결론을 내면 안 된다.
4. 개방수면적이 줄었다고 곧바로 '물이 말랐다'고 하지 마라. 같은 시기 VV 평균이
   올라갔다면 물은 그대로 있고 수생식물이 수면을 덮은 것이다. optical 의 NDVI 가
   함께 올랐다면 그 해석이 광학으로도 확인된 것이다.
5. 한국어로, 담당자에게 보고하듯 간결하게. 3~6문장. 과장하지 않는다.
"""


def _answer(question: str, evidence: dict) -> str:
    prompt = (
        f"{SYSTEM}\n\n<자료>\n"
        + json.dumps(evidence, ensure_ascii=False)
        + f"\n</자료>\n\n<질문>\n{question}\n</질문>\n\n답:"
    )
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700},
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
        raise RuntimeError("모델이 후보를 돌려주지 않았다")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("빈 응답")
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
            self._send(400, {"error": "본문을 JSON 으로 읽지 못했다"})
            return

        question = (data.get("question") or "").strip()[:MAX_QUESTION]
        evidence = data.get("evidence") or {}
        if not question:
            self._send(400, {"error": "질문이 비어 있다"})
            return
        if not API_KEY:
            self._send(502, {"error": "GEMINI_API_KEY 가 설정되지 않았다"})
            return

        try:
            self._send(200, {"answer": _answer(question, evidence), "model": MODEL})
        except urllib.error.HTTPError as exc:
            self._send(502, {"error": f"모델 호출 실패 {exc.code}"})
        except Exception as exc:
            self._send(502, {"error": f"모델 호출 실패: {type(exc).__name__}"})
