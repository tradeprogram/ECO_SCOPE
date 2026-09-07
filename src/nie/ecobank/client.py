"""에코뱅크(국립생태원 생태정보종합은행) 오픈API 어댑터.

엔드포인트
    https://www.nie-ecobank.kr/ecoapi/{서비스}/{wms|wfs|attr}/{오퍼레이션}
    인증키는 `serviceKey` 파라미터로 전달합니다.

응답 형식
    WFS 는 기본이 GML 입니다. `outputFormat=application/json` 을 붙이면
    GeoJSON(EPSG:5186)으로 받을 수 있으므로 이 어댑터는 항상 GeoJSON 을 요청합니다.

전국 자료를 받는 방법
    WFS 로 전국을 격자 수집하는 방식은 실패했습니다. 습지 도형이 매우 상세해
    (2개소 = 109 KB) 40 km 타일에서 응답이 커지면 게이트웨이가 HTTP 500 을 돌려줍니다.
    대신 **속성 조회(attr)** 를 씁니다. 이쪽은 페이징(numOfRows / pageNo)을 지원하고
    `geom` 필드에 WKT 도형까지 함께 실어 주므로 한 경로로 전량 수집이 됩니다.

제약
    - WFS 는 bbox 가 필요하고 maxFeatures 상한이 500 입니다. 좁은 범위 조회에만 씁니다.
    - 속성 조회는 numOfRows 상한이 1000 입니다.
    - 발급받은 인증키는 **승인된 레이어에 한하여** 동작합니다.

키 취급
    인증키는 서버에만 둡니다. WMS URL 에 serviceKey 가 그대로 들어가므로
    브라우저에 직접 물리면 유출됩니다. 화면에서 쓸 때는 프록시를 거쳐야 합니다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from ..config import ECOBANK_API_KEY

BASE = "https://www.nie-ecobank.kr/ecoapi"
UA = "nie-ecoscope/0.1 (National Institute of Ecology idea contest prototype)"

# 에코뱅크 공간자료 기준 좌표계 (Korea 2000 / Central Belt 2010)
SRS = "EPSG:5186"

MAX_FEATURES = 500      # WFS 상한
MAX_ROWS = 1000         # 속성 조회 상한
TIMEOUT_S = 120

# 발급받은 레이어의 요청 URL. 이름은 에코뱅크 '소개 및 사용법' 표기를 그대로 씁니다.
LAYERS: dict[str, dict[str, str]] = {
    "습지_내륙_면": {
        "wfs": "WtlInfoService/wfs/getWtlInlandPynWFS",
        "wms": "WtlInfoService/wms/getWtlInlandPynWMS",
        "attr": "WtlInfoService/attr/getWtlInlandPynAttr",
        "geoserver": "mv_map_wtl_inland_pyn_2022",
    },
    "습지_생물상_조사_점": {
        "wfs": "WtlInfoService/wfs/getWtlBiotaExaminDtaPointWFS",
        "wms": "WtlInfoService/wms/getWtlBiotaExaminDtaPointWMS",
        "attr": "WtlInfoService/attr/getWtlBiotaExaminDtaPointAttr",
        "geoserver": "mv_dat_wtl_biota_examin_dta_point_2022",
    },
    "생태계정밀조사_조사지역_면": {
        "wfs": "EcpeInfoService/wfs/getEcsystmExaminAreaPynWFS",
        "wms": "EcpeInfoService/wms/getEcsystmExaminAreaPynWMS",
        "attr": "EcpeInfoService/attr/getEcsystmExaminAreaPynAttr",
        "geoserver": "mv_map_ecpe_ecsystm_examin_area_pyn",
    },
    "생태계정밀조사_식생_면": {
        "wfs": "EcpeInfoService/wfs/getVtnPynWFS",
        "wms": "EcpeInfoService/wms/getVtnPynWMS",
        "geoserver": "mv_map_ecpe_vtn_pyn",
    },
    "생태계정밀조사_양서파충류_점": {
        "wfs": "EcpeInfoService/wfs/getAmnrpPointWFS",
        "wms": "EcpeInfoService/wms/getAmnrpPointWMS",
        "geoserver": "mv_map_ecpe_amnrp_point",
    },
    "생태계정밀조사_저서무척추동물_점": {
        "wfs": "EcpeInfoService/wfs/getBninPointWFS",
        "wms": "EcpeInfoService/wms/getBninPointWMS",
        "geoserver": "mv_map_ecpe_bnin_point",
    },
    "생태계정밀조사_조류_점": {
        "wfs": "EcpeInfoService/wfs/getBirdsPointWFS",
        "wms": "EcpeInfoService/wms/getBirdsPointWMS",
        "geoserver": "mv_map_ecpe_birds_point",
    },
    "자연환경조사_식생_면": {
        "wfs": "NteeInfoService/wfs/getVtnPynWFS",
        "wms": "NteeInfoService/wms/getVtnPynWMS",
        "geoserver": "mv_map_ntee_vtn_pyn",
    },
    "자연환경조사_양서파충류_점": {
        "wfs": "NteeInfoService/wfs/getAmnrpPointWFS",
        "wms": "NteeInfoService/wms/getAmnrpPointWMS",
        "geoserver": "mv_map_ntee_amnrp_point",
    },
    "자연환경조사_조류_점": {
        "wfs": "NteeInfoService/wfs/getBirdsPointWFS",
        "wms": "NteeInfoService/wms/getBirdsPointWMS",
        "geoserver": "mv_map_ntee_birds_point",
    },
}

# 남한 전역 대략 범위 (EPSG:5186). 격자 분할 요청의 시작 상자입니다.
KOREA_BBOX_5186 = (40_000.0, 130_000.0, 460_000.0, 810_000.0)


def available() -> bool:
    return ECOBANK_API_KEY is not None


def _get(path: str, params: dict, retries: int = 3) -> bytes:
    if ECOBANK_API_KEY is None:
        raise RuntimeError(
            "에코뱅크 인증키가 없습니다. .env 에 ECOBANK_API_KEY 를 설정하십시오."
        )
    query = {"serviceKey": ECOBANK_API_KEY, **params}
    url = f"{BASE}/{path}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return resp.read()
        except Exception as exc:  # 게이트웨이 혼잡·일시 오류는 흔합니다.
            last = exc
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"에코뱅크 요청 실패 ({path}): {last}")


def wfs(layer: str, bbox: tuple[float, float, float, float],
        max_features: int = MAX_FEATURES) -> dict:
    """레이어의 GeoJSON FeatureCollection. bbox 는 EPSG:5186 (minx,miny,maxx,maxy)."""
    spec = LAYERS.get(layer)
    if spec is None or "wfs" not in spec:
        raise KeyError(f"WFS 요청 URL 을 모르는 레이어입니다: {layer}")
    raw = _get(
        spec["wfs"],
        {
            "bbox": ",".join(f"{v:.1f}" for v in bbox),
            "srs": SRS,
            "maxFeatures": max_features,
            "outputFormat": "application/json",
        },
    )
    text = raw.decode("utf-8", "replace").lstrip()
    if not text.startswith("{"):
        # 오류 시 XML 이 돌아옵니다. 진단이 되도록 앞부분을 그대로 올려보냅니다.
        raise RuntimeError(f"GeoJSON 이 아닌 응답 ({layer}): {text[:300]}")
    return json.loads(text)


def wms_image(layer: str, bbox: tuple[float, float, float, float],
              width: int = 512, height: int = 512, transparent: bool = True) -> bytes:
    """WMS 타일(PNG). 화면에 직접 물리지 말고 서버 프록시를 통해 사용하십시오."""
    spec = LAYERS.get(layer)
    if spec is None or "wms" not in spec:
        raise KeyError(f"WMS 요청 URL 을 모르는 레이어입니다: {layer}")
    return _get(
        spec["wms"],
        {
            "bbox": ",".join(f"{v:.1f}" for v in bbox),
            "srs": SRS,
            "width": min(width, 1024),
            "height": min(height, 1024),
            "format": "image/png",
            "transparent": str(transparent).lower(),
        },
    )


def attr_page(layer: str, page: int, rows: int = 200) -> dict:
    """속성 조회 1페이지. `geom` 에 WKT 도형이 함께 들어 있습니다."""
    spec = LAYERS.get(layer)
    if spec is None or "attr" not in spec:
        raise KeyError(f"속성 조회 URL 을 모르는 레이어입니다: {layer}")
    raw = _get(
        spec["attr"],
        {"type": "json", "numOfRows": min(rows, MAX_ROWS), "pageNo": page},
    )
    payload = json.loads(raw.decode("utf-8", "replace"))
    header = payload.get("header", {})
    if header.get("resultCode") not in ("0", "00", None):
        raise RuntimeError(f"에코뱅크 오류 응답: {header}")
    return payload.get("body", {})


def fetch_layer_attrs(
    layer: str,
    rows: int = 10,
    checkpoint: "Path | None" = None,
    passes: int = 4,
    pause_s: float = 0.8,
    progress: bool = True,
) -> tuple[list[dict], list[int]]:
    """레이어 전량을 속성 조회로 받습니다. 중간에 끊겨도 이어서 받습니다.

    **이 엔드포인트는 처리 시간 상한이 약 10초입니다.** 부하에 따라 같은 요청이
    성공하기도 실패하기도 하며, 실패는 전부 10.2초 부근에서 HTTP 500 으로 떨어집니다.
    따라서 한 번에 받으려 하지 않고, 작은 페이지로 나눈 뒤 실패한 페이지만
    여러 차례 다시 시도합니다. 진행분은 `checkpoint` JSONL 에 즉시 기록하므로
    같은 경로로 다시 실행하면 끝난 페이지를 건너뜁니다.

    반환: (수신 항목, 끝내 받지 못한 페이지 번호)
    """
    total = int(attr_page(layer, 1, 1).get("totalCount", 0))
    pages = (total + rows - 1) // rows

    done: dict[int, list[dict]] = {}
    if checkpoint is not None and checkpoint.exists():
        for line in checkpoint.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            done[rec["page"]] = rec["items"]
        if progress and done:
            print(f"  이어받기: 이미 받은 {len(done)}페이지를 건너뜁니다.")

    if progress:
        print(f"  총 {total:,}건 · {rows}건씩 {pages}페이지")

    pending = [p for p in range(1, pages + 1) if p not in done]
    for attempt in range(1, passes + 1):
        if not pending:
            break
        if progress:
            print(f"  {attempt}차 시도: {len(pending)}페이지", flush=True)
        still: list[int] = []
        for i, page in enumerate(pending, 1):
            try:
                body = attr_page(layer, page, rows)
                got = body.get("item", []) or []
                if isinstance(got, dict):
                    got = [got]
                done[page] = got
                if checkpoint is not None:
                    with checkpoint.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"page": page, "items": got}, ensure_ascii=False) + chr(10))
            except Exception:
                still.append(page)
            if progress and i % 25 == 0:
                print(f"    {i}/{len(pending)} · 누적 {sum(len(v) for v in done.values()):,}건", flush=True)
            time.sleep(pause_s)
        pending = still
        if pending:
            time.sleep(5 * attempt)   # 서버가 진정될 시간을 줍니다.

    items = [it for page in sorted(done) for it in done[page]]
    if progress:
        print(f"  수신 {len(items):,}건 / 전체 {total:,}건 · 미수신 페이지 {len(pending)}개")
    return items, pending
