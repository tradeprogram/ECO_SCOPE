"""Sentinel-1 SAR 개방수면 판독 — 이 프로젝트의 코어.

왜 SAR 인가
    습지 수면적은 구름 아래에서도 변한다. 장마철·태풍기가 특히 그렇다.
    광학(Sentinel-2)은 바로 그 시기에 못 본다. SAR 은 구름을 통과한다.

왜 '개방수면'만 다루는가
    잔잔한 개방수면은 SAR 를 경면반사시켜 후방산란이 급락한다. 신호가 크고 방향이
    한쪽이라 판독이 안정적이다. 반면 식생 아래 침수(이중반사, z>0)는 논의 담수 관리
    주기와 같은 대역에서 움직여 오탐이 심하다 — 선행 프로젝트(충남 농경지)에서
    사건 17일 '전' 영상이 사건 후보다 큰 이상치를 낸 전례가 있다.
    그래서 여기서는 **개방수면적만** 산출하고, 식생 하부 침수는 판정하지 않는다.

산출물
    습지 × 관측시각 별 개방수면적(ha)과 수면율(수면적/습지면적).
    임계값은 장면마다 Otsu 로 다시 정한다 (고정 dB 임계는 계절·입사각에 흔들린다).
"""

from __future__ import annotations

import ee

from ..config import S1_PIXEL_M, WATER_VV_DB_MAX
from . import gee

# Otsu 히스토그램 파라미터
HIST_SCALE_M = 20      # 임계값 추정용. 면적 산출은 10m 로 따로 한다.
HIST_MAX_PIXELS = 1e7
# Otsu 가 물/뭍 경계가 아닌 다른 이봉(예: 여름 식생 vs 나지)에 꽂히는 일이 실제로
# 일어난다. 우포늪 2024-08 장면에서 임계값이 -10.6dB 로 밀렸다.
# IW VV 에서 잔잔한 개방수면은 -25~-15dB 대에 놓이므로 그 밖은 채택하지 않는다.
OTSU_VALID_RANGE = (-24.0, -14.0)


def otsu(histogram: ee.Dictionary) -> ee.Number:
    """히스토그램 이분화 임계값 (클래스간 분산 최대화)."""
    counts = ee.Array(ee.Dictionary(histogram).get("histogram"))
    means = ee.Array(ee.Dictionary(histogram).get("bucketMeans"))
    size = means.length().get([0])
    total = counts.reduce(ee.Reducer.sum(), [0]).get([0])
    total_sum = means.multiply(counts).reduce(ee.Reducer.sum(), [0]).get([0])
    grand_mean = total_sum.divide(total)

    def between_class_variance(i):
        a_counts = counts.slice(0, 0, i)
        a_count = a_counts.reduce(ee.Reducer.sum(), [0]).get([0])
        a_means = means.slice(0, 0, i)
        a_mean = a_means.multiply(a_counts).reduce(ee.Reducer.sum(), [0]).get([0]).divide(a_count)
        b_count = total.subtract(a_count)
        b_mean = total_sum.subtract(a_count.multiply(a_mean)).divide(b_count)
        return a_count.multiply(a_mean.subtract(grand_mean).pow(2)).add(
            b_count.multiply(b_mean.subtract(grand_mean).pow(2))
        )

    # i = 1..size-1 로 자른다. i=size 는 class B 가 비어 0으로 나눠진다.
    # sort 의 두 배열은 길이가 같아야 하므로 means 도 같은 길이로 맞춘다 —
    # 분할 i 의 임계값은 class A 의 마지막 버킷 평균, 즉 means[i-1] 이다.
    indices = ee.List.sequence(1, size.subtract(1))
    scores = ee.Array(indices.map(between_class_variance))
    candidates = means.slice(0, 0, size.subtract(1))
    return ee.Number(candidates.sort(scores).get([-1]))


def scene_threshold(image: ee.Image, region: ee.Geometry) -> ee.Number:
    """장면별 VV 임계값(dB). 물/뭍이 함께 잡히도록 습지 주변까지 넓혀서 본다."""
    hist = image.select("VV").reduceRegion(
        reducer=ee.Reducer.histogram(maxBuckets=256),
        geometry=region,
        scale=HIST_SCALE_M,
        maxPixels=HIST_MAX_PIXELS,
        bestEffort=True,
    ).get("VV")
    # 판독창에 유효 화소가 없으면 히스토그램이 비어 bucketMeans 키 자체가 없다.
    # 그대로 otsu() 에 넘기면 'Dictionary does not contain key' 로 장면이 아니라
    # **요청 전체**가 죽는다. 대면적 습지를 분기로 쪼개 받을 때 이 오류로 11개소가
    # 통째로 실패했다. 빈 히스토그램은 고정임계로 넘긴다.
    hd = ee.Dictionary(hist)
    usable = ee.Algorithms.If(
        ee.Algorithms.IsEqual(hist, None),
        False,
        hd.contains("bucketMeans"),
    )
    thr = ee.Number(ee.Algorithms.If(usable, otsu(hd), WATER_VV_DB_MAX))
    # Otsu 가 엉뚱한 곳(전부 물 / 전부 뭍이라 이봉이 아닌 장면)에 꽂히면 고정값으로 되돌린다.
    lo, hi = OTSU_VALID_RANGE
    return ee.Number(ee.Algorithms.If(thr.gte(lo).And(thr.lte(hi)), thr, WATER_VV_DB_MAX))


def water_mask(image: ee.Image, threshold_db: ee.Number) -> ee.Image:
    """개방수면 마스크. 경사지를 빼서 산지 레이더 그림자 오탐을 막는다."""
    return image.select("VV").lt(threshold_db).And(gee.terrain_mask()).rename("water")


def water_fraction(
    mask: ee.Image,
    wetlands: ee.FeatureCollection,
    scale_m: int = S1_PIXEL_M,
) -> ee.FeatureCollection:
    """습지 폴리곤별 수면 점유율(0~1). 면적은 이 값 × 폴리곤 면적으로 낸다."""
    return mask.unmask(0).reduceRegions(
        collection=wetlands,
        reducer=ee.Reducer.mean().setOutputs(["water_frac"]),
        scale=scale_m,
        tileScale=4,
    )


def scene_records(
    image: ee.Image,
    wetlands: ee.FeatureCollection,
    threshold_region: ee.Geometry,
) -> ee.FeatureCollection:
    """한 장면에 대한 습지별 판독 결과. 임계값·관측시각·궤도를 같이 실어 보낸다."""
    thr = scene_threshold(image, threshold_region)
    mask = water_mask(image, thr)
    props = {
        "acq_millis": image.get("system:time_start"),
        "rel_orbit": image.get("relativeOrbitNumber_start"),
        "orbit_pass": image.get("orbitProperties_pass"),
        "platform": image.get("platform_number"),
        "thr_db": thr,
    }
    return water_fraction(mask, wetlands).map(lambda f: f.set(props))


def wetland_timeseries(
    geom: ee.Geometry,
    start_utc: str,
    end_utc: str,
    rel_orbit: int | None = None,
    orbit_pass: str | None = None,
    buffer_m: int = 1500,
) -> list[dict]:
    """습지 하나의 개방수면적 시계열. **getInfo 는 한 번만 부른다.**

    임계값은 습지 경계를 buffer_m 만큼 넓힌 창에서 구한다. 습지 안쪽만 보면
    물이 가득한 장면에서 물/뭍 이봉이 안 만들어져 Otsu 가 무너진다.
    """
    window = geom.buffer(buffer_m)
    col = gee.s1_collection(window, start_utc, end_utc, rel_orbit, orbit_pass)

    def per_scene(img: ee.Image) -> ee.Feature:
        thr = scene_threshold(img, window)
        mask = water_mask(img, thr)
        frac = mask.unmask(0).reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=S1_PIXEL_M,
            maxPixels=1e9,
            bestEffort=True,
        ).get("water")
        return ee.Feature(
            None,
            {
                "acq_millis": img.get("system:time_start"),
                "rel_orbit": img.get("relativeOrbitNumber_start"),
                "orbit_pass": img.get("orbitProperties_pass"),
                "thr_db": thr,
                "water_frac": frac,
            },
        )

    fc = ee.FeatureCollection(col.map(per_scene))
    raw = fc.getInfo()
    return [f["properties"] for f in raw.get("features", [])]


def wetland_timeseries_dual(
    geom: ee.Geometry,
    start_utc: str,
    end_utc: str,
    rel_orbit: int | None = None,
    buffer_m: int = 1500,
) -> list[dict]:
    """적응임계(Otsu)와 고정임계를 **같은 장면에서 동시에** 낸다.

    임계 선택이 결과를 얼마나 흔드는지를 산출물에 붙여 두기 위한 것이다.
    둘이 크게 갈리는 장면은 판독을 신뢰하지 않는다.
    """
    window = geom.buffer(buffer_m)
    col = gee.s1_collection(window, start_utc, end_utc, rel_orbit)

    def per_scene(img: ee.Image) -> ee.Feature:
        thr_otsu = scene_threshold(img, window)
        thr_fixed = ee.Number(WATER_VV_DB_MAX)
        slope_ok = gee.terrain_mask()
        vv = img.select("VV")
        stats = (
            vv.lt(thr_otsu).And(slope_ok).rename("f_otsu")
            .addBands(vv.lt(thr_fixed).And(slope_ok).rename("f_fixed"))
            .unmask(0)
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=S1_PIXEL_M,
                maxPixels=1e9,
                bestEffort=True,
            )
        )
        return ee.Feature(
            None,
            {
                "acq_millis": img.get("system:time_start"),
                "rel_orbit": img.get("relativeOrbitNumber_start"),
                "orbit_pass": img.get("orbitProperties_pass"),
                "thr_otsu_db": thr_otsu,
                "thr_fixed_db": thr_fixed,
                "frac_otsu": stats.get("f_otsu"),
                "frac_fixed": stats.get("f_fixed"),
                "vv_mean_db": vv.reduceRegion(
                    ee.Reducer.mean(), geom, S1_PIXEL_M, maxPixels=1e9, bestEffort=True
                ).get("VV"),
            },
        )

    fc = ee.FeatureCollection(col.map(per_scene))
    return [f["properties"] for f in fc.getInfo().get("features", [])]
