"""에코뱅크 WMS 프록시 — Vercel Python Function.

**인증키를 브라우저에 노출하지 않기 위한 것입니다.**
에코뱅크 WMS 는 serviceKey 를 URL 쿼리로 받으므로, 화면에서 타일 주소를 직접 물리면
개발자 도구에 키가 그대로 드러납니다. 화면은 이 프록시만 부르고, 키는 서버 환경변수에
둡니다.

요청
    GET /map/wms?layer=<레이어명>&bbox=<minx,miny,maxx,maxy>&width=&height=

    layer  ALLOWED 에 있는 이름만 허용합니다. 임의 경로 통과를 막기 위함입니다.
    bbox   EPSG:5186 (Korea 2000 / Central Belt 2010) 미터 좌표 4개.

응답
    image/png. 키가 없거나 오류면 502 와 함께 JSON 사유를 돌려줍니다.
    화면은 그 경우 해당 레이어를 감추고 나머지로 동작합니다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nie.ecobank import client  # noqa: E402

# 화면에 얹을 수 있는 레이어만 열어 둡니다.
ALLOWED = {
    "생태계정밀조사_식생_면",
    "자연환경조사_식생_면",
    "생태계정밀조사_조사지역_면",
    "습지_내륙_면",
    "습지_생물상_조사_점",
}

MAX_PX = 1024
CACHE_S = 3600


class handler(BaseHTTPRequestHandler):  # noqa: N801  (Vercel 규약)
    def _fail(self, code: int, reason: str) -> None:
        raw = json.dumps({"error": reason}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        q = parse_qs(urlparse(self.path).query)

        layer = (q.get("layer") or [""])[0]
        if layer not in ALLOWED:
            self._fail(400, f"허용되지 않은 레이어입니다: {layer or '(없음)'}")
            return

        try:
            bbox = tuple(float(v) for v in (q.get("bbox") or [""])[0].split(","))
            if len(bbox) != 4:
                raise ValueError
        except ValueError:
            self._fail(400, "bbox 는 EPSG:5186 좌표 4개여야 합니다 (minx,miny,maxx,maxy)")
            return

        try:
            width = min(int((q.get("width") or ["512"])[0]), MAX_PX)
            height = min(int((q.get("height") or ["512"])[0]), MAX_PX)
        except ValueError:
            self._fail(400, "width/height 는 정수여야 합니다")
            return

        if not client.available():
            self._fail(502, "에코뱅크 인증키가 설정되지 않았습니다")
            return

        try:
            png = client.wms_image(layer, bbox, width=width, height=height)  # type: ignore[arg-type]
        except urllib.error.HTTPError as exc:
            self._fail(502, f"에코뱅크 응답 오류 (HTTP {exc.code})")
            return
        except Exception as exc:
            self._fail(502, f"에코뱅크 요청 실패 ({type(exc).__name__})")
            return

        if not png.startswith(b"\x89PNG"):
            # 오류 시 XML 이 돌아옵니다. 이미지가 아니면 이미지인 척하지 않습니다.
            self._fail(502, "에코뱅크가 이미지가 아닌 응답을 돌려주었습니다")
            return

        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.send_header("Cache-Control", f"public, max-age={CACHE_S}")
        self.end_headers()
        self.wfile.write(png)


# 로컬에서 단독 실행할 때: python api/ecomap.py 8788
if __name__ == "__main__":
    from http.server import HTTPServer

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
    print(f"에코뱅크 WMS 프록시: http://localhost:{port}/map/wms?layer=...&bbox=...")
    HTTPServer(("127.0.0.1", port), handler).serve_forever()
