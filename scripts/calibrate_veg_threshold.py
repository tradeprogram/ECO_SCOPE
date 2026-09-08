"""식생피복 판정 임계(VV_VEG_DB)를 습지유형별로 다시 산출합니다.

    python scripts/calibrate_veg_threshold.py

현행 -13 dB 는 파일럿 1개소(우포늪 2024)에서 눈으로 갈라 정한 값입니다.
1개소에서 나온 값을 전국에 쓰고 있으므로, 다른 습지·다른 유형에서도 성립하는지
확인해야 합니다.

방법
    개방수면이 사라진 관측(covered)만 모읍니다. 이때 VV 가 높으면 식생이 덮은
    것이고, 낮으면 산란체가 없는 것(건조 의심)이라는 게 현행 가정입니다.
    이 가정을 **광학으로 판정**합니다 — 같은 시기 Sentinel-2 의 NDVI 는
    SAR 과 물리 원리가 다른 독립 관측입니다.

        식생 있음   NDVI >= NDVI_VEG
        식생 없음   NDVI <= NDVI_BARE
        사이 구간은 판정하지 않고 버립니다(경계가 모호한 표본이 임계를 흐립니다).

    두 부류를 가장 잘 가르는 VV 임계를 Youden's J (민감도+특이도-1) 로 찾습니다.

읽는 법
    유형별 최적값이 서로, 그리고 -13 과 크게 다르지 않다면 현행 값을 유지할 근거가
    됩니다. 크게 갈린다면 유형별 값을 써야 합니다. 표본이 적은 유형은 값을 내지
    않습니다 — 적은 표본에서 나온 최적값은 그 표본의 우연을 외운 것입니다.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from bisect import bisect_left
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from nie.config import INTERIM              # noqa: E402
from nie.wetlands import aggregate, registry  # noqa: E402

PAIR_DAYS = 3          # SAR 과 광학의 허용 시간차
NDVI_VEG = 0.40
NDVI_BARE = 0.15
MIN_CLASS = 20         # 각 부류 최소 표본
CLOUD_MAX = 20.0
VALID_MIN = 0.80
DAY_MS = 86_400_000


def load_optical() -> dict[tuple[str, int], list[dict]]:
    """습지-연도별 광학 관측. 두 곳에 흩어져 있어 합쳐 씁니다.

    `_merged.jsonl` 의 `optical` 은 판독 배치가 함께 받은 것이고,
    `validation_optical.jsonl` 은 정확도 검증용으로 따로 받은 것입니다.
    후자가 습지 수가 더 많습니다. 같은 습지-연도면 관측이 많은 쪽을 씁니다.
    """
    out: dict[tuple[str, int], list[dict]] = {}
    for name in ("_merged.jsonl", "validation_optical.jsonl"):
        path = INTERIM / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            opt = r.get("optical") or []
            if not opt:
                continue
            key = (r["wid"], r["year"])
            if len(opt) > len(out.get(key, [])):
                out[key] = opt
    return out


def pairs_for(rec: dict, optical: list[dict]) -> list[tuple[float, float, int]]:
    """(vv_mean_db, ndvi, month) — 개방수면이 사라진 관측에 한해."""
    opt = [o for o in optical
           if o.get("ndvi") is not None
           and (o.get("cloud_pct") or 0) <= CLOUD_MAX
           and (o.get("valid_frac") or 0) >= VALID_MIN]
    if not opt:
        return []
    opt.sort(key=lambda o: o["acq_millis"])
    times = [o["acq_millis"] for o in opt]

    wy = aggregate.wetland_year(rec)
    if not wy or not wy["has_open_water"]:
        return []
    # covered 관측 = 개방수면이 기준선의 30% 아래로 내려간 관측.
    # 현행 판정은 이 안에서 VV 로 식생/건조를 가릅니다. 그 갈림을 검사합니다.
    covered = [o for o in wy["observations"]
               if o["state"] in ("veg_covered", "dry_suspect")]
    if not covered:
        return []

    out = []
    for o in covered:
        t = int(dt.datetime.fromisoformat(o["date"])
                .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        i = bisect_left(times, t)
        best = None
        for j in (i - 1, i, i + 1):
            if 0 <= j < len(opt):
                gap = abs(times[j] - t)
                if gap <= PAIR_DAYS * DAY_MS and (best is None or gap < best[0]):
                    best = (gap, opt[j])
        if best:
            out.append((o["vv_db"], best[1]["ndvi"], int(o["date"][5:7])))
    return out


def youden(pos: list[float], neg: list[float]) -> tuple[float, float, float, float]:
    """pos(식생) 를 위로, neg(비식생) 를 아래로 가르는 최적 VV 임계.

    반환: (임계 dB, J, 민감도, 특이도)
    """
    cands = sorted({round(v, 1) for v in pos + neg})
    best = (0.0, -1.0, 0.0, 0.0)
    for t in cands:
        sens = sum(1 for v in pos if v > t) / len(pos)
        spec = sum(1 for v in neg if v <= t) / len(neg)
        j = sens + spec - 1
        if j > best[1]:
            best = (t, j, sens, spec)
    return best


def quantiles(xs: list[float], qs=(0.05, 0.5, 0.95)) -> list[float]:
    s = sorted(xs)
    return [s[min(len(s) - 1, int(q * len(s)))] for q in qs]


GROW = range(5, 10)          # 5~9월. 이 시기 낮은 NDVI 는 '식생 없음' 으로 읽을 수 있다


def report(tag: str, pos: list[float], neg: list[float]) -> dict | None:
    if len(pos) < MIN_CLASS or len(neg) < MIN_CLASS:
        print("%-12s 표본 부족 (식생 %d / 비식생 %d)" % (tag, len(pos), len(neg)))
        return None
    t, j, sens, spec = youden(pos, neg)
    cur = aggregate.VV_VEG_DB
    csens = sum(1 for v in pos if v > cur) / len(pos)
    cspec = sum(1 for v in neg if v <= cur) / len(neg)
    pq, nq = quantiles(pos), quantiles(neg)
    print("%-12s 식생 %3d / 비식생 %3d" % (tag, len(pos), len(neg)))
    print("             VV 5/50/95   식생 %6.1f %6.1f %6.1f  ·  비식생 %6.1f %6.1f %6.1f dB"
          % (pq[0], pq[1], pq[2], nq[0], nq[1], nq[2]))
    print("             최적 %+.1f dB  J=%.3f (민감도 %.2f 특이도 %.2f)"
          % (t, j, sens, spec))
    print("             현행 %+.1f dB  J=%.3f (민감도 %.2f 특이도 %.2f)"
          % (cur, csens + cspec - 1, csens, cspec))
    return {"tag": tag, "n_veg": len(pos), "n_bare": len(neg),
            "best_db": t, "j": round(j, 4), "sens": round(sens, 4), "spec": round(spec, 4),
            "current_j": round(csens + cspec - 1, 4),
            "current_sens": round(csens, 4), "current_spec": round(cspec, 4),
            "veg_vv_q": [round(x, 2) for x in pq], "bare_vv_q": [round(x, 2) for x in nq]}


def main() -> None:
    types = {w["wid"]: (w.get("wetland_type") or "미상") for _, w in registry.load().iterrows()}
    optical = load_optical()
    src = INTERIM / "_merged.jsonl"
    if not src.exists():
        raise SystemExit(f"{src} 가 없습니다. scripts/build_web_data.py 를 먼저 돌리십시오.")

    all_pairs: list[tuple[str, float, float, int]] = []   # (wid, vv, ndvi, month)
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        opt = optical.get((rec["wid"], rec["year"]))
        if not opt:
            continue
        for vv, ndvi, mon in pairs_for(rec, opt):
            all_pairs.append((rec["wid"], vv, ndvi, mon))

    wids = {w for w, *_ in all_pairs}
    print(f"대상: 습지 {len(wids)}개소 · 짝지음 {len(all_pairs)}건 (±{PAIR_DAYS}일)")
    print(f"식생 NDVI >= {NDVI_VEG} / 비식생 NDVI <= {NDVI_BARE}, 사이는 제외")
    print()

    def split(rows):
        p = [vv for _, vv, nd, _ in rows if nd >= NDVI_VEG]
        n = [vv for _, vv, nd, _ in rows if nd <= NDVI_BARE]
        return p, n

    results = []
    print("── 전체 ──")
    r = report("전 기간", *split(all_pairs))
    if r: results.append(r)
    print()
    print("── 생장기(5~9월)만 ──")
    print("  겨울의 낮은 NDVI 는 마른 갈대일 수 있습니다. 마른 갈대는 광학으로는")
    print("  식생이 아니지만 SAR 로는 여전히 산란체입니다. 이 구간을 빼고 다시 봅니다.")
    grow = [x for x in all_pairs if x[3] in GROW]
    r = report("생장기", *split(grow))
    if r: results.append(r)
    print()

    # 임계를 어디에 두느냐 이전의 물음: VV 가 녹색도에 대해 정보를 갖고 있는가.
    # 상관이 0 이면 어떤 임계를 골라도 가를 수 없다.
    def pearson(xs, ys):
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        sxx = sum((a - mx) ** 2 for a in xs) ** 0.5
        syy = sum((b - my) ** 2 for b in ys) ** 0.5
        return sxy / (sxx * syy) if sxx and syy else 0.0

    print("── VV 와 NDVI 의 관계 (개방수면 소실 관측 안에서) ──")
    corr = {}
    for tag, rows in (("전 기간", all_pairs), ("생장기", grow)):
        if len(rows) < 10:
            print("  %-8s 표본 부족" % tag); continue
        r = pearson([x[1] for x in rows], [x[2] for x in rows])
        corr[tag] = round(r, 4)
        print("  %-8s n=%3d  r = %+.3f" % (tag, len(rows), r))
    print("  임계를 논하기 전에, 이 상관이 0 에 가까우면 VV 로는 가를 수 없습니다.")
    print()

    # 개방수면이 사라졌을 때 실제로 무엇이 있었는가 — 광학이 답한다.
    print("── 개방수면이 사라진 관측의 광학 구성 ──")
    comp = {}
    for tag, rows in (("전 기간", all_pairs), ("생장기(5~9월)", grow),
                      ("비생장기", [x for x in all_pairs if x[3] not in GROW])):
        if not rows:
            continue
        veg = sum(1 for x in rows if x[2] >= NDVI_VEG)
        bare = sum(1 for x in rows if x[2] <= NDVI_BARE)
        mid = len(rows) - veg - bare
        comp[tag] = {"n": len(rows), "veg": veg, "mid": mid, "bare": bare}
        print("  %-14s n=%3d  식생 %3d (%2.0f%%) · 중간 %3d · 비식생 %3d (%2.0f%%)"
              % (tag, len(rows), veg, 100 * veg / len(rows), mid, bare, 100 * bare / len(rows)))
    print()

    print("── 유형별(전 기간) ──")
    by_type: dict[str, list] = {}
    for w, vv, nd, mon in all_pairs:
        by_type.setdefault(types.get(w, "미상"), []).append((w, vv, nd, mon))
    per_type = []
    for name, rows in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        pos, neg = split(rows)
        n_w = len({w for w, *_ in rows})
        if len(pos) < MIN_CLASS or len(neg) < MIN_CLASS:
            print("  %-12s 습지 %d · 식생 %d / 비식생 %d — 표본 부족"
                  % (name, n_w, len(pos), len(neg)))
            continue
        t, j, sens, spec = youden(pos, neg)
        per_type.append({"type": name, "wetlands": n_w, "n_veg": len(pos),
                         "n_bare": len(neg), "best_db": t, "j": round(j, 4)})
        print("  %-12s 습지 %d · 식생 %d / 비식생 %d · 최적 %+.1f dB · J=%.3f"
              % (name, n_w, len(pos), len(neg), t, j))

    out = INTERIM.parent / "processed" / "veg_threshold_calibration.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "pair_days": PAIR_DAYS, "ndvi_veg": NDVI_VEG, "ndvi_bare": NDVI_BARE,
        "cloud_max": CLOUD_MAX, "valid_min": VALID_MIN,
        "wetlands": len(wids), "pairs": len(all_pairs),
        "current_db": aggregate.VV_VEG_DB,
        "splits": results, "by_type": per_type,
        "vv_ndvi_corr": corr, "covered_composition": comp,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("기록:", out)


if __name__ == "__main__":
    main()
