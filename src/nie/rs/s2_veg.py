"""Sentinel-2 식생지수 — SAR 판독의 교차검증용.

SAR 개방수면적이 여름에 급감할 때 원인은 둘 중 하나다.
    (a) 물이 실제로 빠졌다            -> 광학에서도 물·식생 모두 줄고 나지가 는다
    (b) 수생식물이 수면을 덮었다      -> 광학에서 NDVI 가 오르고 NDWI 가 떨어진다
둘을 가르지 못하면 '개방수면 감소'를 해석할 수 없다. 그래서 같은 폴리곤·같은 기간의
S2 NDVI/NDWI 를 붙여 둔다.

구름은 SCL(장면분류)로 거른다. 구름이 걷힌 날이 없으면 그 달은 값이 없는 것으로 둔다 —
비어 있는 것을 채우지 않는다.
"""

from __future__ import annotations

import ee

from . import gee

S2_SR = "COPERNICUS/S2_SR_HARMONIZED"
# SCL 에서 살릴 클래스: 4 식생, 5 나지, 6 물, 7 저확률구름, 11 눈
SCL_KEEP = [4, 5, 6, 7, 11]


def _mask_clouds(img: ee.Image) -> ee.Image:
    scl = img.select("SCL")
    keep = ee.Image(0)
    for cls in SCL_KEEP:
        keep = keep.Or(scl.eq(cls))
    return img.updateMask(keep)


def s2_collection(aoi: ee.Geometry, start_utc: str, end_utc: str, max_cloud: int = 60) -> ee.ImageCollection:
    return (
        ee.ImageCollection(S2_SR)
        .filterBounds(aoi)
        .filterDate(start_utc, end_utc)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
        .map(_mask_clouds)
    )


def indices(img: ee.Image) -> ee.Image:
    """NDVI(식생), NDWI(McFeeters, 개방수면), NDVI 로 본 부엽·정수식물 신호."""
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("ndvi")
    ndwi = img.normalizedDifference(["B3", "B8"]).rename("ndwi")
    return ndvi.addBands(ndwi)


def wetland_timeseries(
    geom: ee.Geometry,
    start_utc: str,
    end_utc: str,
    min_valid_frac: float = 0.4,
) -> list[dict]:
    """습지별 NDVI/NDWI 시계열. getInfo 한 번.

    min_valid_frac 미만으로 유효화소가 남은 장면은 구름에 먹힌 것으로 보고 버린다.
    """
    col = s2_collection(geom, start_utc, end_utc)

    def per_scene(img: ee.Image) -> ee.Feature:
        idx = indices(img)
        stats = idx.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=20,
            maxPixels=1e9,
            bestEffort=True,
        )
        valid = (
            idx.select("ndvi").mask()
            .reduceRegion(ee.Reducer.mean(), geom, 20, maxPixels=1e9, bestEffort=True)
            .get("ndvi")
        )
        return ee.Feature(
            None,
            {
                "acq_millis": img.get("system:time_start"),
                "ndvi": stats.get("ndvi"),
                "ndwi": stats.get("ndwi"),
                "valid_frac": valid,
                "cloud_pct": img.get("CLOUDY_PIXEL_PERCENTAGE"),
            },
        )

    fc = ee.FeatureCollection(col.map(per_scene)).filter(
        ee.Filter.gte("valid_frac", min_valid_frac)
    )
    return [f["properties"] for f in fc.getInfo().get("features", [])]
