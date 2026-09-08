"""국립생태원 생태자연도 오픈API 어댑터 (공공데이터포털).

엔드포인트
    https://apis.data.go.kr/B553084/ecoapi/EcologyzmpService
    인증키는 `serviceKey` 파라미터로 전달합니다. 일 10,000회.

세 오퍼레이션 중 **WFS 만 씁니다.**
    실측에서 WMS(`/wms/getEcologyzmpWMS`)와 속성조회(`/attr/getEcologyzmpAttr`)는
    15~29초 만에 게이트웨이 HTTP_ERROR(reasonCode 04)로 떨어졌습니다.
    같은 키로 WFS 는 1.3초에 응답하므로 키 문제가 아니라 해당 백엔드의 문제입니다.
    WFS 로 벡터를 직접 받으면 래스터 타일보다 오히려 다루기 좋습니다 —
    등급별로 색을 입혀 화면에 그릴 수 있고, 면적 집계도 됩니다.

응답 스키마(주요 필드)
    eczm_grad          생태자연도 등급 (1 / 2 / 3 / 별도관리지역)
    vtn_evl_grad       식생 평가등급
    smld_evl_grad      습지 평가등급          <- 본 과업과 직결
    tpgrph_evl_grad    지형 평가등급
    amplt_evl_grad     동물 평가등급
    plnt_cln_ttle      식물 군락 명칭
    precise_smld_ttle  정밀 습지 명칭         <- 본 과업과 직결
    frph_agcl_code     임상영급 코드
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from ..config import DATA_GO_KR_KEY

BASE = "https://apis.data.go.kr/B553084/ecoapi/EcologyzmpService"
UA = "nie-ecoscope/0.1 (National Institute of Ecology idea contest prototype)"

SRS = "EPSG:5186"
MAX_FEATURES = 500
TIMEOUT_S = 90

# 생태자연도 등급 표기. 자료의 eczm_grad 값을 그대로 키로 씁니다.
#
# 코드 9 는 제공기관 문서에 설명이 없어 자료로 확인했습니다. 실측한 세 지역 824피처에서
# eczm_grad=9 인 24건은 식생·습지·지형·동물 평가등급이 **모두 비어 있었고**,
# 1·2·3 등급과 병렬로 존재했습니다. 생태자연도의 구분이 1/2/3등급과 별도관리지역
# 네 가지이고 별도관리지역은 평가등급을 매기지 않으므로 9 를 별도관리지역으로 봅니다.
# **자료로부터 추정한 것이며 제공기관 정의를 확인한 것은 아닙니다.**
GRADE_LABELS = {
    "1": "1등급",
    "2": "2등급",
    "3": "3등급",
    "9": "별도관리지역(추정)",
}


def available() -> bool:
    return DATA_GO_KR_KEY is not None


def wfs(bbox: tuple[float, float, float, float],
        max_features: int = MAX_FEATURES,
        retries: int = 2) -> dict:
    """지정 범위의 생태자연도 피처(GeoJSON). bbox 는 EPSG:5186 (minx,miny,maxx,maxy).

    반환 딕셔너리에 `_truncated` 를 실어 보냅니다. maxFeatures 에 닿았다면
    그 범위의 자료를 다 받지 못한 것이므로, 집계에 쓰기 전에 확인해야 합니다.
    """
    if DATA_GO_KR_KEY is None:
        raise RuntimeError(
            "생태자연도 인증키가 없습니다. .env 에 DATA_GO_KR_KEY 를 설정하십시오."
        )
    query = {
        "serviceKey": DATA_GO_KR_KEY,
        "srs": SRS,
        "bbox": ",".join(f"{v:.1f}" for v in bbox),
        "maxFeatures": max_features,
        "outputFormat": "application/json",
    }
    url = f"{BASE}/wfs/getEcologyzmpWFS?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})

    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                raw = resp.read()
            break
        except Exception as exc:
            last = exc
            if attempt < retries:
                time.sleep(3 * attempt)
    else:
        raise RuntimeError(f"생태자연도 WFS 요청 실패: {last}")

    text = raw.decode("utf-8", "replace").lstrip()
    if not text.startswith("{"):
        # 게이트웨이 오류는 XML/JSON 봉투로 옵니다. 원문을 그대로 올려 진단이 되게 합니다.
        raise RuntimeError(f"GeoJSON 이 아닌 응답: {text[:250]}")

    payload = json.loads(text)
    feats = payload.get("features", [])
    payload["_truncated"] = len(feats) >= max_features
    return payload


def grade_of(props: dict) -> str:
    """피처의 생태자연도 등급 문자열. 값이 없으면 '미상'."""
    raw = props.get("eczm_grad")
    if raw is None or str(raw).strip() == "":
        return "미상"
    return GRADE_LABELS.get(str(raw).strip(), f"기타({raw})")
