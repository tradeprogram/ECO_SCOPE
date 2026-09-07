"""SAR 관측 시각의 지상 풍속 — 풍파에 의한 개방수면 과소판독을 검증하기 위한 것.

배경
    잔잔한 수면은 레이더를 경면반사시켜 후방산란이 급락하므로 개방수면 판독이 성립합니다.
    그런데 바람이 불면 수면이 거칠어져 후방산란이 올라가고, 임계값(-16 dB) 위로 올라간
    화소는 물이 아닌 것으로 판정됩니다. 즉 **바람이 불면 수면이 줄어든 것처럼 보입니다.**

    실제로 우포늪 겨울 판독이 주 단위로 2배씩 요동쳤고, 같은 기간 광학은 거의 고정이었습니다.
    이 모듈은 그 요동이 바람으로 설명되는지 확인하기 위해 관측 시각의 풍속을 붙입니다.

자료
    ECMWF/ERA5_LAND/HOURLY 의 10 m 바람 u·v 성분. 풍속 = sqrt(u^2 + v^2).
    격자가 약 11 km 라 국지 돌풍은 못 잡습니다. 지역 규모의 바람 상태를 보는 용도입니다.
"""

from __future__ import annotations

import ee

from . import gee

ERA5_LAND_HOURLY = "ECMWF/ERA5_LAND/HOURLY"


def wind_at_times(
    point: ee.Geometry,
    times_millis: list[int],
    buffer_m: int = 15_000,
) -> list[dict]:
    """주어진 시각들의 10 m 풍속(m/s). getInfo 는 한 번만 부릅니다.

    ERA5_LAND 는 육상 자료라 수면 위 격자가 비어 있을 수 있습니다.
    습지 중심을 넉넉히 버퍼해 육상 격자가 함께 들어오게 합니다.
    """
    region = point.buffer(buffer_m)

    def one(t):
        t = ee.Number(t)
        img = (
            ee.ImageCollection(ERA5_LAND_HOURLY)
            .filterDate(ee.Date(t).advance(-1, "hour"), ee.Date(t).advance(1, "hour"))
            .first()
        )
        u = ee.Image(img).select("u_component_of_wind_10m")
        v = ee.Image(img).select("v_component_of_wind_10m")
        speed = u.pow(2).add(v.pow(2)).sqrt().rename("wind")
        val = speed.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=11_000, bestEffort=True
        ).get("wind")
        return ee.Feature(None, {"acq_millis": t, "wind_ms": val})

    fc = ee.FeatureCollection(ee.List(times_millis).map(one))
    return [f["properties"] for f in fc.getInfo().get("features", [])]


def attach(observations: list[dict], point: ee.Geometry) -> dict[str, float]:
    """관측 목록에 붙일 {날짜: 풍속} 사전. 관측이 없으면 빈 사전."""
    if not observations:
        return {}
    times = [o["acq_millis"] for o in observations if o.get("acq_millis")]
    if not times:
        return {}
    out = {}
    for rec in wind_at_times(point, times):
        if rec.get("wind_ms") is None:
            continue
        date = gee.utc_to_kst(int(rec["acq_millis"])).date().isoformat()
        out[date] = round(float(rec["wind_ms"]), 2)
    return out
