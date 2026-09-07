"""풍파 가설 검증 — 바람이 불면 SAR 개방수면이 줄어 보이는가.

    python scripts/run_wind_check.py --top 6

관측 시각의 ERA5 10 m 풍속을 붙여, 풍속과 개방수면율의 관계를 봅니다.

분석 설계
    - **개방수면 구간만** 봅니다. 식생피복 구간은 수면적이 식생에 지배되므로 섞으면 안 됩니다.
    - **겨울(12~3월)을 따로** 봅니다. 식생이 없어 수면적이 거의 일정해야 하는 시기이므로,
      여기서 나타나는 요동은 실제 수면 변화가 아니라 판독 요인일 가능성이 큽니다.
    - 습지별로 봅니다. 습지 크기가 다른 것을 한데 섞으면 상관이 희석됩니다.

결과: data/interim/wind.jsonl (원자료) / web/data/wind_check.json (보고서)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import ee  # noqa: E402
from shapely.geometry import mapping  # noqa: E402

from nie.config import INTERIM, WEB_DATA  # noqa: E402
from nie.rs import gee, wind  # noqa: E402
from nie.validate import accuracy  # noqa: E402
from nie.validate.accuracy import _pearson  # noqa: E402
from nie.wetlands import aggregate, registry  # noqa: E402

CKPT = INTERIM / "wind.jsonl"
WINTER = {12, 1, 2, 3}


def load_ckpt() -> dict:
    if not CKPT.exists():
        return {}
    out = {}
    for line in CKPT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[(r["wid"], r["year"])] = r["wind"]
    return out


def geometry_index():
    idx = {}
    for src in ("ecobank", "osm"):
        try:
            g = registry.load(source=src, min_area_ha=0)
        except FileNotFoundError:
            continue
        for wid, geom in zip(g.wid, g.geometry):
            idx.setdefault(wid, geom)
    return idx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="_merged.jsonl")
    ap.add_argument("--top", type=int, default=6)
    args = ap.parse_args()

    raw = {(r["wid"], r["year"]): r for r in aggregate.load_records(INTERIM / args.source)}
    years = [aggregate.wetland_year(r) for r in raw.values()]
    ok = [y for y in years if y and y["has_open_water"]]

    wids, seen = [], set()
    for y in sorted(ok, key=lambda x: -x["area_ha"]):
        if y["wid"] not in seen:
            seen.add(y["wid"]); wids.append(y["wid"])
    wids = wids[: args.top]
    targets = [y for y in ok if y["wid"] in wids]
    print(f"대상 습지 {len(wids)}개소 · 습지-연도 {len(targets)}건")

    gee.init()
    geoms = geometry_index()
    ckpt = load_ckpt()
    if ckpt:
        print(f"이어받기: {len(ckpt)}건 건너뜁니다.")

    for i, y in enumerate(targets, 1):
        key = (y["wid"], y["year"])
        if key in ckpt:
            continue
        shape = geoms.get(y["wid"])
        if shape is None:
            print(f"  ! {y['wid']} 도형 없음"); continue
        scenes = raw[key].get("scenes", [])
        try:
            pt = ee.Geometry(mapping(shape.centroid))
            got = wind.attach(scenes, pt)
        except Exception as exc:
            print(f"  ! {y['wid']} {y['year']} 실패: {str(exc)[:100]}"); continue
        with CKPT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"wid": y["wid"], "year": y["year"], "wind": got},
                                ensure_ascii=False) + "\n")
        ckpt[key] = got
        print(f"[{i}/{len(targets)}] {y.get('name') or y['wid']} {y['year']} 풍속 {len(got)}건", flush=True)
        time.sleep(0.3)

    # --- 분석 -------------------------------------------------------------
    per_wetland = {}
    for y in targets:
        w = ckpt.get((y["wid"], y["year"]))
        if not w:
            continue
        rec = per_wetland.setdefault(y["wid"], {"name": y.get("name"), "area_ha": y["area_ha"], "obs": []})
        for o in y["observations"]:
            ws = w.get(o["date"])
            if ws is None:
                continue
            rec["obs"].append({
                "date": o["date"], "month": int(o["date"][5:7]),
                "open_ratio": o["open_ratio"], "open_ha": o["open_ha"],
                "vv_db": o["vv_db"], "state": o["state"], "wind_ms": ws,
            })

    def stats(obs):
        if len(obs) < 5:
            return {"n": len(obs)}
        wnd = [o["wind_ms"] for o in obs]
        ratio = [o["open_ratio"] for o in obs]
        r = _pearson(wnd, ratio)
        lo = [o["open_ratio"] for o in obs if o["wind_ms"] < 3.0]
        hi = [o["open_ratio"] for o in obs if o["wind_ms"] >= 5.0]
        return {
            "n": len(obs),
            "wind_mean_ms": round(sum(wnd) / len(wnd), 2),
            "wind_max_ms": round(max(wnd), 2),
            "pearson_r_wind_vs_openratio": round(r, 3) if r is not None else None,
            "open_ratio_low_wind": round(sum(lo) / len(lo), 4) if lo else None,
            "n_low_wind": len(lo),
            "open_ratio_high_wind": round(sum(hi) / len(hi), 4) if hi else None,
            "n_high_wind": len(hi),
        }

    report = {"by_wetland": {}, "winter_only": {}, "all_open": None}
    all_open, all_winter = [], []
    for wid, rec in per_wetland.items():
        op = [o for o in rec["obs"] if o["state"] == "open"]
        wi = [o for o in op if o["month"] in WINTER]
        all_open.extend(op); all_winter.extend(wi)
        # 바람 말고 다른 원인은 없는가 — 면적이 평균 후방산란의 재진술인지 함께 봅니다.
        dom = accuracy.backscatter_dominance(op)
        partial = None
        if len(op) >= 8:
            partial = accuracy.partial_correlation(
                [o["wind_ms"] for o in op], [o["open_ratio"] for o in op], [o["vv_db"] for o in op]
            )
        report["by_wetland"][wid] = {
            "name": rec["name"], "area_ha": rec["area_ha"],
            "open": stats(op), "winter_open": stats(wi),
            "backscatter_dominance": dom,
            "partial_r_wind_controlling_vv": round(partial, 3) if partial is not None else None,
        }
    report["all_open"] = stats(all_open)
    report["winter_only"] = stats(all_winter)
    report["note"] = (
        "ERA5_LAND 11 km 격자의 지역 풍속입니다. 국지 돌풍은 잡지 못합니다. "
        "음의 상관은 바람이 셀수록 개방수면이 좁게 판독됨을 뜻합니다. "
        "여러 습지를 한데 묶은 상관은 습지 간 차이가 만든 허상일 수 있으므로 "
        "습지별 값(by_wetland)을 먼저 보십시오."
    )

    out = WEB_DATA / "wind_check.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n=== 개방수면 구간 전체 n={report['all_open'].get('n')} "
          f"r={report['all_open'].get('pearson_r_wind_vs_openratio')} ===")
    print(f"=== 겨울(12~3월) n={report['winter_only'].get('n')} "
          f"r={report['winter_only'].get('pearson_r_wind_vs_openratio')} ===")
    print(f"{'습지':18s} {'n':>4s} {'r(풍속)':>8s} {'편상관':>7s} {'r2(평균VV)':>10s}")
    for wid, v in report["by_wetland"].items():
        nm = v["name"] or ("무명 " + wid[-6:])
        o, d = v["open"], v["backscatter_dominance"]
        print(f"  {nm[:16]:18s} {o.get('n', 0):>4} "
              f"{str(o.get('pearson_r_wind_vs_openratio')):>8s} "
              f"{str(v.get('partial_r_wind_controlling_vv')):>7s} "
              f"{str(d.get('r2_explained_by_mean_vv')):>10s}")
    print("저장:", out)


if __name__ == "__main__":
    main()
