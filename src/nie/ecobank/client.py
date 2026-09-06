"""국립생태원 생태자연도 오픈API 어댑터.

공공데이터포털 `국립생태원_생태자연도 서비스` (B553084/ecoapi/EcologyzmpService).
WMS(지도 타일) / WFS(피처) / 속성조회 세 오퍼레이션을 감싼다.
인증키는 자동승인이며 개발계정 일 10,000회다.

**키는 서버에만 둔다.** WMS URL 에 ServiceKey 가 그대로 들어가므로 브라우저에
직접 물리면 키가 새어나간다. 화면은 반드시 api/ecomap 프록시를 거치게 할 것.

키가 없으면 이 모듈은 예외를 던지지 않고 `available() == False` 를 돌려준다.
화면은 그 경우 생태자연도 레이어를 감추고 나머지로 동작한다.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from ..config import CACHE, DATA_GO_KR_KEY, ECOBANK_API_KEY

BASE = "https://apis.data.go.kr/B553084/ecoapi/EcologyzmpService"
OP_WMS = "wms/getEcologyzmpWMS"
OP_WFS = "wfs/getEcologyzmpWFS"
OP_ATTR = "attr/getEcologyzmpAttr"

# 생태자연도 좌표계는 EPSG:5186 (Korea 2000 / Central Belt 2010)
SRS = "EPSG:5186"

TIMEOUT_S = 30


def api_key() -> str | None:
    """생태자연도는 공공데이터포털 키로 부른다. 에코뱅크 자체 키가 있으면 그것도 받는다."""
    return DATA_GO_KR_KEY or ECOBANK_API_KEY


def available() -> bool:
    return api_key() is not None


def _request(operation: str, params: dict, as_json: bool = True) -> bytes | dict:
    key = api_key()
    if key is None:
        raise RuntimeError(
            "생태자연도 API 키가 없다. .env 에 DATA_GO_KR_KEY 를 넣을 것 "
            "(공공데이터포털 > 국립생태원_생태자연도 서비스, 자동승인)."
        )
    query = {"ServiceKey": key, **params}
    url = f"{BASE}/{operation}?{urllib.parse.urlencode(query, safe='%,:')}"
    req = urllib.request.Request(url, headers={"User-Agent": "nie-eco-platform/0.1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        payload = resp.read()
    if not as_json:
        return payload
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # 오류 시 포털이 XML 을 준다. 원문을 그대로 올려 보내 진단 가능하게.
        return {"_raw": payload[:2000].decode("utf-8", errors="replace")}


def wms_image(bbox: tuple[float, float, float, float], width: int = 512, height: int = 512,
              layers: str = "", transparent: bool = True) -> bytes:
    """생태자연도 WMS 타일(PNG). bbox 는 EPSG:5186 (minx, miny, maxx, maxy)."""
    return _request(  # type: ignore[return-value]
        OP_WMS,
        {
            "srs": SRS,
            "bbox": ",".join(str(v) for v in bbox),
            "width": width,
            "height": height,
            "layers": layers,
            "format": "image/png",
            "transparent": str(transparent).lower(),
        },
        as_json=False,
    )


def wfs_features(bbox: tuple[float, float, float, float], max_features: int = 500) -> dict:
    """생태자연도 WFS 피처. bbox 는 EPSG:5186."""
    return _request(  # type: ignore[return-value]
        OP_WFS,
        {
            "srs": SRS,
            "bbox": ",".join(str(v) for v in bbox),
            "maxFeatures": max_features,
            "typeName": "",
            "format": "json",
        },
    )


def attributes(x: float, y: float) -> dict:
    """한 지점의 생태자연도 등급 속성. 좌표는 EPSG:5186."""
    return _request(OP_ATTR, {"srs": SRS, "x": x, "y": y, "format": "json"})  # type: ignore[return-value]


def cached(name: str, producer, ttl_note: str = "") -> dict:
    """응답을 data/cache 에 남긴다. 키가 끊겨도 화면이 죽지 않게 하기 위한 것."""
    path: Path = CACHE / f"ecobank_{name}.json"
    try:
        payload = producer()
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload
    except Exception as exc:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_stale"] = True
            data["_error"] = str(exc)[:200]
            return data
        raise
