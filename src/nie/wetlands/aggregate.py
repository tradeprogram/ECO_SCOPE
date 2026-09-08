"""판독 원자료(JSONL) -> 습지별 지표.

이 파일이 '수치의 유일한 출처'다. 웹 화면도 제안서도 여기를 거쳐 나온다.
같은 숫자가 두 곳에서 다르게 계산되는 일을 막기 위한 것이다.

**주지표는 고정임계(-16 dB)다.** 처음에는 장면별 Otsu 를 주지표로 썼으나, 파일럿에서
대면적·이질 폴리곤(간척지 등)의 판독창이 물/뭍 이봉을 만들지 못해 임계값이
-14.9 ~ -19.4 dB 로 요동쳤고 같은 습지·같은 달의 면적이 39~123 ha 로 갈렸다.
IW VV 개방수면의 물리 범위는 안정적이므로 고정임계를 주지표로 두고,
Otsu 는 **민감도 검사**로만 남긴다. 둘이 크게 갈리는 습지-연도는 confidence="low".

지표 정의
    open_ratio      개방수면율 = 개방수면적 / 습지면적
    baseline        그 습지·그 해 open_ratio 의 90퍼센타일 (최대 개방 상태)
    covered         open_ratio < COVER_RATIO x baseline  (개방수면이 사라진 관측)
    covered_share   covered 관측 비중 — **주지표**
    veg_covered     covered 이면서 VV 평균 > VV_VEG_DB   (식생 추정, 실험적)
    dry_suspect     covered 이면서 VV 평균 <= VV_VEG_DB  (산란체 없음 추정, 실험적)

VV_VEG_DB = -13 은 파일럿(우포늪 2024)에서 왔다. 개방수면 관측의 VV 평균은
-16~-22 dB, 식생피복 관측은 -8.8~-12 dB 로 갈렸고 그 사이가 비어 있었다.

**전국 자료로 이 임계를 검사했고, 갈라지지 않았다.**
    습지 17개소·짝지음 173건에서 covered 관측의 VV 를 같은 시기 Sentinel-2 NDVI 와
    대조했다(scripts/calibrate_veg_threshold.py).
        VV 와 NDVI 의 상관   전 기간 r=+0.14 / 생장기 r=-0.13 — 부호가 뒤집힌다
        -13.0 dB 의 성능     민감도 0.98 / **특이도 0.10** / Youden J 0.085
                            식생이 없는 관측의 90% 도 '식생피복'으로 간다
        최적 임계            -13.0 dB. 파일럿 값과 같지만, 같다는 사실에 의미가 없다.
                            어느 지점에서 잘라도 J 가 이 수준이기 때문이다.
    두 분포가 거의 포개진다 — 식생 5/50/95 = -12.8/-11.2/-9.9,
    비식생 -13.7/-10.7/-9.7 dB. covered 안에서 VV 는 녹색도에 대한 정보를 갖고 있지
    않다. 실제 판정 결과도 covered 의 93.8% 가 veg_covered 다 — 거의 상수 분류기다.

**그래서 주지표는 veg_cover_share 가 아니라 covered_share 다.**
    측정된 것은 '개방수면이 사라졌다'까지이고, 그 원인이 식생인지는 SAR 단독으로
    판정할 수 없다. veg_covered / dry_suspect 는 원자료에 남기되 실험적 구분으로
    표시하고, 화면과 제안서는 covered_share 를 쓴다.

    다만 원인을 아주 모르는 것은 아니다. 계절이 VV 보다 잘 예측한다 —
    생장기(5~9월) covered 관측의 광학 구성은 식생 55% / 비식생 15%, 비생장기는
    14% / 28% 로 뒤집힌다. 집계 수준에서는 '여름철 소실은 대개 식생'이라고 말할 수 있다.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

COVER_RATIO = 0.30
VV_VEG_DB = -13.0
MIN_OBS_FOR_YEAR = 8      # 이보다 적으면 그 해 지표를 내지 않는다

# 개방수면 지표를 적용할 수 있는 습지인지의 문턱.
# 연중 최대 개방수면율이 이보다 낮으면 그 습지는 SAR 로 볼 개방수면이 사실상 없다
# (삼림습지·초본습지·이탄지 등). baseline 이 0 에 가까운데 비율로 '피복'을 판정하면
# 0 을 0 으로 나누는 꼴이 되어 아무 의미 없는 수치가 나온다. 그래서 아예 분리한다.
MIN_BASELINE_RATIO = 0.05
MIN_OPEN_HA = 1.0

# 적응임계와 고정임계가 이만큼(최대 개방수면적 대비) 벌어지면 신뢰도를 낮춘다.
CONF_DISAGREE_FRAC = 0.20


def _kst(millis: int) -> dt.date:
    return (dt.datetime.utcfromtimestamp(millis / 1000) + dt.timedelta(hours=9)).date()


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    s = sorted(values)
    idx = (len(s) - 1) * q
    lo, hi = math.floor(idx), math.ceil(idx)
    if lo == hi:
        return s[int(idx)]
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def load_records(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def wetland_year(rec: dict, force_open_water: bool | None = None) -> dict | None:
    """한 습지·한 해의 지표. 관측이 모자라면 None.

    같은 날 두 장면이 오는 습지가 있다 — 한 궤도의 인접 프레임 경계에 걸친 경우다.
    그대로 세면 연 54회처럼 재방문 주기가 실제의 두 배로 부풀려진다. 날짜로 묶어
    평균 내고 **1회로 센다.**
    """
    scenes = [
        s for s in rec.get("scenes", [])
        if s.get("frac_otsu") is not None and s.get("vv_mean_db") is not None
    ]
    if rec.get("status") != "ok" or len(scenes) < MIN_OBS_FOR_YEAR:
        return None

    area_ha = rec["area_ha"]

    by_date: dict[str, list[dict]] = {}
    for s in scenes:
        by_date.setdefault(_kst(s["acq_millis"]).isoformat(), []).append(s)

    obs = []
    n_merged = 0
    for date in sorted(by_date):
        group = by_date[date]
        if len(group) > 1:
            n_merged += 1
        mean = lambda k: sum(float(g[k]) for g in group) / len(group)  # noqa: E731
        ratio = mean("frac_fixed")          # 주지표: 고정임계
        ratio_alt = mean("frac_otsu")       # 민감도: 장면별 Otsu
        obs.append(
            {
                "date": date,
                "frames": len(group),
                "open_ratio": round(ratio, 4),
                "open_ha": round(ratio * area_ha, 2),
                "open_ha_alt": round(ratio_alt * area_ha, 2),
                "vv_db": round(mean("vv_mean_db"), 2),
                "thr_db": round(mean("thr_otsu_db"), 2),
            }
        )

    if len(obs) < MIN_OBS_FOR_YEAR:
        return None

    ratios = [o["open_ratio"] for o in obs]
    baseline = _percentile(ratios, 0.90)
    open_ha_max = _percentile([o["open_ha"] for o in obs], 0.90)

    # 이 습지에 개방수면 지표를 쓸 수 있는가.
    # force_open_water 가 주어지면 그 판정을 따릅니다 — 습지 단위 판정을 위한 것입니다.
    # 이 성질은 습지의 것이지 연도의 것이 아니므로, 연도별로 뒤집히면 안 됩니다.
    has_open_water = (
        force_open_water
        if force_open_water is not None
        else (baseline >= MIN_BASELINE_RATIO and open_ha_max >= MIN_OPEN_HA)
    )

    cut = COVER_RATIO * baseline
    n_veg = n_dry = 0
    for o in obs:
        if not has_open_water:
            o["state"] = "no_open_water"
            continue
        o["state"] = "open"
        if o["open_ratio"] < cut:
            if o["vv_db"] > VV_VEG_DB:
                o["state"] = "veg_covered"
                n_veg += 1
            else:
                o["state"] = "dry_suspect"
                n_dry += 1

    disagree = max((abs(o["open_ha"] - o["open_ha_alt"]) for o in obs), default=0.0)
    conf_low = has_open_water and open_ha_max > 0 and disagree > CONF_DISAGREE_FRAC * open_ha_max

    return {
        "wid": rec["wid"],
        "name": rec.get("name"),
        "year": rec["year"],
        "area_ha": round(area_ha, 2),
        "rel_orbit": rec.get("rel_orbit"),
        "orbit_pass": rec.get("orbit_pass"),
        "n_obs": len(obs),
        "n_dates_multiframe": n_merged,
        "revisit_days": round(365 / len(obs), 1),
        "has_open_water": has_open_water,
        "confidence": "low" if conf_low else "high",
        "open_ha_max": round(open_ha_max, 2),
        "open_ha_med": round(_percentile([o["open_ha"] for o in obs], 0.50), 2),
        "open_ha_min": round(min(o["open_ha"] for o in obs), 2),
        "open_ratio_baseline": round(baseline, 4),
        "n_covered": n_veg + n_dry,
        # 주지표. 측정된 것은 여기까지다 — 개방수면이 사라진 관측이 얼마나 되는가.
        "covered_share": round((n_veg + n_dry) / len(obs), 3) if has_open_water else None,
        # 아래 둘은 실험적 구분이다. VV 로는 원인을 가르지 못한다는 것을 확인했다.
        # 파일 머리말의 '전국 자료로 이 임계를 검사했고' 항을 보라.
        "n_veg_covered": n_veg,
        "n_dry_suspect": n_dry,
        "veg_cover_share": round(n_veg / len(obs), 3) if has_open_water else None,
        "thr_disagree_ha_max": round(disagree, 2),
        "observations": obs,
        "optical": _optical(rec),
    }


def _optical(rec: dict) -> list[dict]:
    """Sentinel-2 교차검증 자료. 수집하지 않았으면 빈 목록."""
    out = []
    for o in rec.get("optical", []) or []:
        if o.get("ndvi") is None:
            continue
        out.append(
            {
                "date": _kst(o["acq_millis"]).isoformat(),
                "ndvi": round(float(o["ndvi"]), 3),
                "ndwi": round(float(o["ndwi"]), 3) if o.get("ndwi") is not None else None,
                "valid_frac": round(float(o.get("valid_frac", 0)), 2),
            }
        )
    return sorted(out, key=lambda x: x["date"])


def summarize(path: Path) -> dict:
    """전국 집계. 헤드라인 수치는 전부 여기서 나옵니다.

    **개방수면 지표 적용 여부는 습지 단위로 판정합니다.**
    연도별로 판정하면 기준선이 문턱(5%) 근처인 습지에서 적용·비적용이 해마다 뒤집혀,
    식생피복 비중이 0% 와 79% 를 오가는 것처럼 보입니다. 실제로 복정습지에서 그런
    현상이 나왔습니다. 습지에 SAR 로 볼 개방수면이 있는지는 그 습지의 성질이지
    연도의 성질이 아니므로, 전 기간을 함께 보고 한 번만 판정합니다.
    """
    recs = load_records(path)
    years = sorted({r["year"] for r in recs})

    # 1차: 연도별로 계산해 습지별 최대 기준선을 구합니다.
    first_pass = [(r, wetland_year(r)) for r in recs]
    peak: dict[str, tuple[float, float]] = {}
    for _, y in first_pass:
        if not y:
            continue
        b, a = peak.get(y["wid"], (0.0, 0.0))
        peak[y["wid"]] = (max(b, y["open_ratio_baseline"]), max(a, y["open_ha_max"]))

    open_water_wids = {
        wid for wid, (b, a) in peak.items()
        if b >= MIN_BASELINE_RATIO and a >= MIN_OPEN_HA
    }

    # 2차: 습지 단위 판정을 적용해 다시 계산합니다.
    per_year = [
        wetland_year(r, force_open_water=(r["wid"] in open_water_wids)) for r in recs
    ]
    ok = [x for x in per_year if x]

    n_scene_total = sum(x["n_obs"] for x in ok)
    wids = sorted({x["wid"] for x in ok})
    open_wy = [x for x in ok if x["has_open_water"]]
    covered = [x for x in open_wy if x["n_covered"] > 0]
    high_conf = [x for x in open_wy if x["confidence"] == "high"]

    return {
        "generated_utc": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source_file": path.name,
        "years": years,
        "n_wetlands": len(wids),
        "n_wetland_years": len(ok),
        "n_wetland_years_dropped": len(per_year) - len(ok),
        "n_observations": n_scene_total,
        "mean_obs_per_wetland_year": round(n_scene_total / len(ok), 1) if ok else 0,
        "mean_revisit_days": round(sum(x["revisit_days"] for x in ok) / len(ok), 1) if ok else None,
        # 개방수면 지표를 적용할 수 있는 습지와 그렇지 않은 습지를 나눠서 센다
        "n_wetlands_open_water": len({x["wid"] for x in open_wy}),
        "n_wetlands_no_open_water": len(wids) - len({x["wid"] for x in open_wy}),
        "n_wetland_years_high_conf": len(high_conf),
        "n_wetlands_with_cover_loss": len({x["wid"] for x in covered}),
        "thr_disagree_ha_p90": round(_percentile([x["thr_disagree_ha_max"] for x in open_wy], 0.9), 2) if open_wy else None,
        "wetland_years": ok,
    }
