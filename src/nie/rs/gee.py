"""Google Earth Engine 공통 헬퍼.

**시간은 UTC다.** Sentinel-1 한반도 통과는 06:0x / 18:0x KST 근처이므로,
KST 날짜로 필터를 걸면 경계일 영상이 통째로 빠진다. 날짜를 다룰 때는
반드시 `kst_window()` 를 거칠 것.

**컴퓨트 예산 주의.** 이 프로젝트의 GEE 계정은 noncommercial 제한 모드다.
전국 격자 연산은 실패한다. 습지 폴리곤(중앙값 수 ha~수 ㎢) 단위로만 reduce 하고,
`reduceRegions` 는 한 번에 200개 이하로 끊어 호출한다.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache

import ee

from ..config import EE_PROJECT, S1_SPECKLE_RADIUS_M

S1_GRD = "COPERNICUS/S1_GRD"
GSW = "JRC/GSW1_4/GlobalSurfaceWater"
COP_DEM = "COPERNICUS/DEM/GLO30_2024_1"
WORLDCOVER = "ESA/WorldCover/v200/2021"

_INITIALIZED = False


def init(project: str = EE_PROJECT) -> None:
    """멱등 초기화. 여러 모듈에서 마음대로 불러도 된다."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    ee.Initialize(project=project)
    _INITIALIZED = True


def kst_window(start_kst: str, end_kst: str) -> tuple[str, str]:
    """KST 구간 -> GEE 가 쓰는 UTC 구간."""
    fmt = "%Y-%m-%d" if len(start_kst) == 10 else "%Y-%m-%dT%H:%M"

    def to_utc(s: str) -> str:
        return (dt.datetime.strptime(s, fmt) - dt.timedelta(hours=9)).strftime("%Y-%m-%dT%H:%M")

    return to_utc(start_kst), to_utc(end_kst)


def utc_to_kst(millis: int) -> dt.datetime:
    """GEE 의 system:time_start(ms, UTC) 를 KST 로."""
    return dt.datetime.utcfromtimestamp(millis / 1000) + dt.timedelta(hours=9)


def s1_collection(
    aoi: ee.Geometry,
    start_utc: str,
    end_utc: str,
    rel_orbit: int | None = None,
    orbit_pass: str | None = None,
    speckle_m: int = S1_SPECKLE_RADIUS_M,
) -> ee.ImageCollection:
    """IW / GRD / VV+VH 이중편파 컬렉션. speckle 은 focal median 으로 완화한다.

    rel_orbit 을 지정하면 입사각·관측 geometry 가 고정되어 시계열 비교가
    성립한다. 시계열을 만들 때는 **반드시** 지정할 것.
    """
    col = (
        ee.ImageCollection(S1_GRD)
        .filterBounds(aoi)
        .filterDate(start_utc, end_utc)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    )
    if rel_orbit is not None:
        col = col.filter(ee.Filter.eq("relativeOrbitNumber_start", rel_orbit))
    if orbit_pass is not None:
        col = col.filter(ee.Filter.eq("orbitProperties_pass", orbit_pass))

    kernel = ee.Kernel.circle(speckle_m, "meters")

    def _prep(img: ee.Image) -> ee.Image:
        smooth = img.select(["VV", "VH"]).focal_median(kernel=kernel)
        return smooth.copyProperties(img, img.propertyNames())

    return col.map(_prep)


def orbit_inventory(aoi: ee.Geometry, start_utc: str, end_utc: str) -> list[dict]:
    """AOI 를 덮는 relative orbit 별 관측 횟수. 시계열용 궤도를 고를 때 쓴다."""
    col = (
        ee.ImageCollection(S1_GRD)
        .filterBounds(aoi)
        .filterDate(start_utc, end_utc)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
    )
    feats = col.aggregate_array("relativeOrbitNumber_start").getInfo()
    passes = col.aggregate_array("orbitProperties_pass").getInfo()
    tally: dict[tuple[int, str], int] = {}
    for orb, ps in zip(feats, passes):
        tally[(orb, ps)] = tally.get((orb, ps), 0) + 1
    return [
        {"rel_orbit": orb, "pass": ps, "scenes": n}
        for (orb, ps), n in sorted(tally.items(), key=lambda kv: -kv[1])
    ]


@lru_cache(maxsize=1)
def permanent_water() -> ee.Image:
    """JRC GSW 상시수역(연중 출현빈도 >=80%). 상시수면과 계절수면을 가르는 기준."""
    return ee.Image(GSW).select("occurrence").gte(80).unmask(0)


@lru_cache(maxsize=1)
def terrain_mask() -> ee.Image:
    """경사 5도 초과 지형을 뺀다. 습지 판독에서 산지 그림자를 물로 오인하는 것을 막는다."""
    dem = ee.ImageCollection(COP_DEM).select("DEM").mosaic()
    return ee.Terrain.slope(dem).lt(5)


def scene_log(aoi: ee.Geometry, start_utc: str, end_utc: str) -> list[dict]:
    """AOI 를 덮은 S1 장면 목록 (궤도·통과방향·시각·위성). getInfo 한 번.

    이걸로 '언제 볼 수 있었는가'를 연도별로 따진다. 판독보다 이게 먼저다 —
    Sentinel-1B 가 2021-12 에 고장나면서 특정 relative orbit 은 2022~2024 동안
    사실상 관측이 끊겼고, 2024-12 발사된 Sentinel-1C 가 같은 궤도면을 이어받아
    2025 부터 되살아났다. 이 사실을 모르고 시계열을 그리면 관측이 없어서 생긴
    공백을 '변화 없음'으로 읽게 된다.
    """
    col = (
        ee.ImageCollection(S1_GRD)
        .filterBounds(aoi)
        .filterDate(start_utc, end_utc)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
    )
    got = col.reduceColumns(
        ee.Reducer.toList(4),
        ["relativeOrbitNumber_start", "orbitProperties_pass", "system:time_start", "platform_number"],
    ).get("list").getInfo()
    return [
        {"rel_orbit": int(o), "pass": p, "millis": int(t), "platform": s}
        for o, p, t, s in got
    ]


def dominant_orbit_recent(
    aoi: ee.Geometry, start_utc: str, end_utc: str, recent_months: int = 24
) -> tuple[dict | None, list[dict]]:
    """시계열에 쓸 궤도를 고르고, 그 판단의 근거인 장면 목록을 같이 돌려준다.

    **최근 구간에서 고른다.** 시작 연도 기준으로 고르면 이미 끊긴 위성의 궤도를
    집는다 — 실제로 그렇게 골랐다가 2022~2024 판독이 통째로 비었다.
    최근 구간에서 살아 있는 궤도는 과거에도 대부분 존재하므로 전 기간이 이어진다.
    """
    log = scene_log(aoi, start_utc, end_utc)
    if not log:
        return None, []
    cutoff = max(s["millis"] for s in log) - recent_months * 30 * 86400 * 1000
    recent = [s for s in log if s["millis"] >= cutoff] or log

    tally: dict[tuple[int, str], int] = {}
    for s in recent:
        key = (s["rel_orbit"], s["pass"])
        tally[key] = tally.get(key, 0) + 1
    (orb, ps), n = max(tally.items(), key=lambda kv: kv[1])
    return {"rel_orbit": orb, "pass": ps, "scenes_recent": n}, log
