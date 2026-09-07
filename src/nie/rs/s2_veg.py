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


# --- SAR 판독의 정확도 산출용 ---------------------------------------------
#
# 위의 wetland_timeseries 는 지수의 '평균'만 냅니다. 평균으로는 SAR 개방수면'적'과
# 견줄 수 없으므로, 여기서는 광학으로도 같은 방식의 **수면 면적**을 냅니다.
#
# 판정: NDWI > NDWI_WATER  (McFeeters 기준. 표준값은 0 이며, 혼합화소를 고려해
# 0~0.3 을 쓰기도 합니다. SAR 쪽과 마찬가지로 고정 임계를 주지표로 두고
# 민감도 검사를 함께 냅니다.)
#
# 구름 기준을 본편보다 엄격하게 둡니다. 정확도를 재는 자리에서 구름에 먹힌 장면을
# 섞으면 그 오차가 SAR 의 오차로 둔갑합니다.

NDWI_WATER = 0.0            # 주지표
NDWI_WATER_ALT = 0.15       # 민감도 검사
VALID_FRAC_STRICT = 0.9     # 정확도 산출에 쓸 장면의 최소 유효화소 비율


def water_timeseries(
    geom: ee.Geometry,
    start_utc: str,
    end_utc: str,
    min_valid_frac: float = VALID_FRAC_STRICT,
) -> list[dict]:
    """광학 기준 개방수면 '면적 비율' 시계열. SAR 판독과 대조하기 위한 것입니다.

    반환 항목
        date          관측일 (KST)
        water_frac    NDWI > 0 화소 비율      (주지표)
        water_frac_alt NDWI > 0.15 화소 비율   (민감도)
        ndvi / ndwi   폴리곤 평균 (해석용)
        valid_frac    구름 제거 후 남은 화소 비율
    """
    col = s2_collection(geom, start_utc, end_utc)

    def per_scene(img: ee.Image) -> ee.Feature:
        idx = indices(img)
        ndwi = idx.select("ndwi")
        bands = (
            ndwi.gt(NDWI_WATER).rename("w")
            .addBands(ndwi.gt(NDWI_WATER_ALT).rename("w_alt"))
            .addBands(idx.select("ndvi"))
            .addBands(ndwi)
        )
        stats = bands.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=20,
            maxPixels=1e9,
            bestEffort=True,
        )
        valid = (
            ndwi.mask()
            .reduceRegion(ee.Reducer.mean(), geom, 20, maxPixels=1e9, bestEffort=True)
            .get("ndwi")
        )
        return ee.Feature(
            None,
            {
                "acq_millis": img.get("system:time_start"),
                "water_frac": stats.get("w"),
                "water_frac_alt": stats.get("w_alt"),
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
