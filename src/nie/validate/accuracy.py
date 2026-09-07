"""SAR 개방수면 판독의 정확도 산출.

현장 실측 자료가 없으므로 **독립 센서와의 일치도**로 정확도를 대신합니다.
같은 습지·같은 시기를 Sentinel-1(레이더)과 Sentinel-2(광학)가 각각 관측했을 때,
두 센서가 산출한 개방수면적이 얼마나 일치하는지를 봅니다.

이것이 '정답과의 오차'가 아니라 '두 관측의 불일치'라는 점을 분명히 해 둡니다.
두 센서가 같은 값을 낸다고 그 값이 참이라는 보장은 없습니다. 다만 서로 다른
물리(후방산란 / 분광반사)를 쓰는 두 관측이 일치하면, 어느 한쪽의 계통 오차일
가능성은 크게 줄어듭니다.

산출을 하나의 숫자로 뭉개지 않는 이유
--------------------------------------
1. **상태별로 나눕니다.** 식생이 수면을 덮은 시기에는 두 센서가 모두 0 에 가까운
   값을 냅니다. 그 구간을 섞으면 '잘 맞는다'는 착시가 생깁니다. 판정이 실제로
   시험되는 곳은 개방수면 구간입니다.
2. **시간차를 나눕니다.** 두 위성이 같은 날 지나지 않으므로 ±N 일로 짝을 짓는데,
   그 사이에 실제로 수면이 변했을 수 있습니다. 불일치가 판독 오차인지 시간차인지
   구분하려면 시간차별로 따로 봐야 합니다.
3. **임계값 민감도를 함께 냅니다.** SAR 은 고정임계 −16 dB, 광학은 NDWI > 0 을
   주지표로 쓰되, 각각의 대안 임계로도 계산해 결과가 임계 선택에 얼마나 흔들리는지
   같이 보고합니다.
"""

from __future__ import annotations

import datetime as dt
import math

# 수면이 '있다'고 볼 최소 점유율. 이보다 작으면 두 센서 모두 없음으로 봅니다.
PRESENCE_RATIO = 0.01


def _date(iso: str) -> dt.date:
    return dt.date.fromisoformat(iso[:10])


def pair_observations(
    sar_obs: list[dict],
    opt_obs: list[dict],
    area_ha: float,
    max_offset_days: int = 3,
) -> list[dict]:
    """SAR 관측과 광학 관측을 시간차 안에서 짝짓습니다.

    한 SAR 관측에 광학이 여러 개 걸리면 **시간차가 가장 작은 것 하나**만 씁니다.
    여러 개를 다 쓰면 같은 SAR 관측이 여러 번 세어져 표본 수가 부풀려집니다.
    """
    if not sar_obs or not opt_obs:
        return []

    opt = [
        {
            "date": _date(o["date"]),
            "water_frac": o.get("water_frac"),
            "water_frac_alt": o.get("water_frac_alt"),
            "ndvi": o.get("ndvi"),
            "ndwi": o.get("ndwi"),
        }
        for o in opt_obs
        if o.get("water_frac") is not None
    ]
    if not opt:
        return []

    pairs = []
    for s in sar_obs:
        sd = _date(s["date"])
        best = min(opt, key=lambda o: abs((o["date"] - sd).days))
        offset = abs((best["date"] - sd).days)
        if offset > max_offset_days:
            continue
        pairs.append(
            {
                "date_sar": sd.isoformat(),
                "date_opt": best["date"].isoformat(),
                "offset_days": offset,
                "state": s.get("state"),
                "area_ha": area_ha,
                "sar_ha": s["open_ha"],
                "sar_ha_alt": s.get("open_ha_alt"),
                "opt_ha": round(best["water_frac"] * area_ha, 3),
                "opt_ha_alt": (
                    round(best["water_frac_alt"] * area_ha, 3)
                    if best.get("water_frac_alt") is not None
                    else None
                ),
                "vv_db": s.get("vv_db"),
                "ndvi": best.get("ndvi"),
            }
        )
    return pairs


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def metrics(pairs: list[dict], sar_key: str = "sar_ha", opt_key: str = "opt_ha") -> dict:
    """짝지은 관측의 일치도. 표본 수를 항상 함께 냅니다."""
    use = [p for p in pairs if p.get(sar_key) is not None and p.get(opt_key) is not None]
    n = len(use)
    if n == 0:
        return {"n": 0}

    diffs = [p[sar_key] - p[opt_key] for p in use]
    sar = [p[sar_key] for p in use]
    opt = [p[opt_key] for p in use]
    area = sum(p["area_ha"] for p in use) / n

    mae = sum(abs(d) for d in diffs) / n
    rmse = math.sqrt(sum(d * d for d in diffs) / n)
    bias = sum(diffs) / n
    r = _pearson(sar, opt)

    # 수면 유무에 대한 두 센서의 판정 일치 (면적 회귀보다 견고한 보조 지표)
    tt = tf = ft = ff = 0
    for p in use:
        s_w = p[sar_key] >= PRESENCE_RATIO * p["area_ha"]
        o_w = p[opt_key] >= PRESENCE_RATIO * p["area_ha"]
        if s_w and o_w:
            tt += 1
        elif s_w and not o_w:
            tf += 1
        elif o_w and not s_w:
            ft += 1
        else:
            ff += 1

    return {
        "n": n,
        "mae_ha": round(mae, 2),
        "rmse_ha": round(rmse, 2),
        "bias_ha": round(bias, 2),          # 양수면 SAR 이 광학보다 넓게 봄
        "mae_pct_of_wetland": round(100 * mae / area, 2) if area else None,
        "pearson_r": round(r, 3) if r is not None else None,
        "r2": round(r * r, 3) if r is not None else None,
        "presence_agreement": round((tt + ff) / n, 3),
        "presence_table": {"둘다_수면": tt, "SAR만": tf, "광학만": ft, "둘다_없음": ff},
        "mean_sar_ha": round(sum(sar) / n, 2),
        "mean_opt_ha": round(sum(opt) / n, 2),
    }


def report(pairs: list[dict]) -> dict:
    """층별 정확도 보고서. 전체 하나만 내지 않습니다.

    구성
        overall        전체
        by_state       개방수면 / 식생피복 / 건조의심 별
        by_offset      시간차(0일 / 1일 / 2~3일) 별
        sensitivity    임계값을 바꿨을 때
    """
    by_state: dict[str, dict] = {}
    for state in ("open", "veg_covered", "dry_suspect"):
        subset = [p for p in pairs if p.get("state") == state]
        if subset:
            by_state[state] = metrics(subset)

    by_offset: dict[str, dict] = {}
    for label, keep in (("0일", lambda o: o == 0),
                        ("1일", lambda o: o == 1),
                        ("2~3일", lambda o: 2 <= o <= 3)):
        subset = [p for p in pairs if keep(p["offset_days"])]
        if subset:
            by_offset[label] = metrics(subset)

    open_pairs = [p for p in pairs if p.get("state") == "open"]
    sensitivity = {
        "주지표 (SAR −16dB · NDWI>0)": metrics(open_pairs),
        "SAR 대안 (장면별 Otsu)": metrics(open_pairs, sar_key="sar_ha_alt"),
        "광학 대안 (NDWI>0.15)": metrics(open_pairs, opt_key="opt_ha_alt"),
    }

    return {
        "overall": metrics(pairs),
        "by_state": by_state,
        "by_offset": by_offset,
        "sensitivity_open_only": {k: v for k, v in sensitivity.items() if v.get("n")},
        "note": (
            "현장 실측이 아니라 독립 센서와의 일치도입니다. "
            "두 센서가 일치한다고 그 값이 참이라는 보장은 없습니다. "
            "식생피복 구간은 두 센서가 모두 0 에 가까워 자동으로 일치하므로, "
            "판정이 실제로 시험되는 곳은 개방수면 구간(by_state.open)입니다."
        ),
    }
