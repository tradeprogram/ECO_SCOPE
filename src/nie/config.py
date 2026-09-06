"""경로·환경변수 한 곳 모음.

.env 는 저장소 루트에 둔다. 키가 없어도 import 는 실패하지 않는다 —
키가 필요한 시점에 각 모듈이 스스로 판단해 공개 대체 경로로 내려간다.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "data"
AOI = DATA / "aoi"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
WEB_DATA = ROOT / "web" / "data"
CACHE = DATA / "cache"

for _p in (AOI, RAW, INTERIM, PROCESSED, WEB_DATA, CACHE):
    _p.mkdir(parents=True, exist_ok=True)


def _load_dotenv() -> None:
    """의존성 없이 .env 를 읽는다. 이미 설정된 환경변수는 덮지 않는다."""
    for name in (".env.local", ".env"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# --- Google Earth Engine ---
EE_PROJECT = os.environ.get("EE_PROJECT", "gen-lang-client-0419682396")

# --- 에코뱅크 / 공공데이터포털 ---
# 발급 전에는 None. 이 값이 None 이면 각 클라이언트가 캐시·공개자료로 대체한다.
ECOBANK_API_KEY = os.environ.get("ECOBANK_API_KEY") or None
DATA_GO_KR_KEY = os.environ.get("DATA_GO_KR_KEY") or None
KMA_API_KEY = os.environ.get("KMA_API_KEY") or None

# --- 질의응답 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or None
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# --- 판독 파라미터 (한 곳에서 관리, 문서와 코드가 갈라지지 않게) ---
S1_SPECKLE_RADIUS_M = 50      # focal median 반경
WATER_VV_DB_MAX = -16.0       # 개방수면 VV 상한 (dB) — 초기값, 보정 대상
MIN_WETLAND_AREA_HA = 1.0     # 이 미만 습지는 10m 격자로 면적을 논하지 않는다
S1_PIXEL_M = 10
