"""SAR 개방수면 판독의 정확도를 산출합니다.

    python scripts/run_validation.py --source _merged.jsonl --top 12

같은 습지·같은 시기를 Sentinel-1 과 Sentinel-2 가 각각 관측한 짝을 만들어
두 센서의 개방수면적 일치도를 냅니다. 현장 실측이 아니라 **독립 센서와의 일치도**입니다.

광학 수집은 GEE 호출이라 느립니다. 습지-연도 단위로 체크포인트에 적어 이어받습니다.
결과: data/interim/validation_optical.jsonl (원자료) / web/data/validation.json (보고서)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from shapely.geometry import mapping  # noqa: E402

import ee  # noqa: E402

from nie.config import INTERIM, WEB_DATA  # noqa: E402
from nie.rs import gee, s2_veg  # noqa: E402
from nie.validate import accuracy  # noqa: E402
from nie.wetlands import aggregate, registry  # noqa: E402

CKPT = INTERIM / "validation_optical.jsonl"


def load_checkpoint() -> dict[tuple[str, int], list[dict]]:
    if not CKPT.exists():
        return {}
    out = {}
    for line in CKPT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[(r["wid"], r["year"])] = r["optical"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="_merged.jsonl", help="SAR 판독 원자료")
    ap.add_argument("--top", type=int, default=12, help="개방수면 성립 습지 상위 N개소")
    ap.add_argument("--offset", type=int, default=3, help="짝짓기 허용 시간차(일)")
    args = ap.parse_args()

    recs = aggregate.load_records(INTERIM / args.source)
    years = [aggregate.wetland_year(r) for r in recs]
    ok = [y for y in years if y and y["has_open_water"]]
    if not ok:
        raise SystemExit("개방수면 판독이 성립한 습지-연도가 없습니다.")

    # 대상: 개방수면 성립 습지 중 면적 상위
    wids, seen = [], set()
    for y in sorted(ok, key=lambda x: -x["area_ha"]):
        if y["wid"] not in seen:
            seen.add(y["wid"])
            wids.append(y["wid"])
    wids = wids[: args.top]
    targets = [y for y in ok if y["wid"] in wids]
    print(f"대상 습지 {len(wids)}개소 · 습지-연도 {len(targets)}건")

    gee.init()

    # 판독 원자료가 어느 레지스트리로 만들어졌는지에 따라 wid 체계가 다릅니다.
    # (정본은 습지코드, 임시본은 osm-*) 양쪽을 모두 색인해 두고 찾습니다.
    geoms = {}
    for src in ("ecobank", "osm"):
        try:
            g = registry.load(source=src, min_area_ha=0)
        except FileNotFoundError:
            continue
        for wid, geom in zip(g.wid, g.geometry):
            geoms.setdefault(wid, geom)
    print(f"도형 색인 {len(geoms):,}개소")
    ckpt = load_checkpoint()
    if ckpt:
        print(f"이어받기: 이미 수집한 {len(ckpt)}건은 건너뜁니다.")

    for i, y in enumerate(targets, 1):
        key = (y["wid"], y["year"])
        if key in ckpt:
            continue
        try:
            shape = geoms.get(y["wid"])
            if shape is None:
                print(f"  ! {y['wid']} 도형 없음 — 건너뜁니다")
                continue
            geom = ee.Geometry(mapping(shape.simplify(0.00015)))
            start, end = gee.kst_window(f"{y['year']}-01-01", f"{y['year'] + 1}-01-01")
            opt = s2_veg.water_timeseries(geom, start, end)
            for o in opt:
                o["date"] = gee.utc_to_kst(o["acq_millis"]).date().isoformat()
            rec = {"wid": y["wid"], "year": y["year"], "optical": opt}
        except Exception as exc:
            print(f"  ! {y['wid']} {y['year']} 실패: {str(exc)[:110]}")
            continue
        with CKPT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ckpt[key] = opt
        print(f"[{i}/{len(targets)}] {y.get('name') or y['wid']} {y['year']} "
              f"유효장면 {len(opt)}건", flush=True)
        time.sleep(0.4)

    # 짝짓고 보고서를 냅니다
    pairs, per_wetland = [], {}
    for y in targets:
        opt = ckpt.get((y["wid"], y["year"]))
        if not opt:
            continue
        got = accuracy.pair_observations(y["observations"], opt, y["area_ha"], args.offset)
        pairs.extend(got)
        per_wetland.setdefault(y["wid"], {"name": y.get("name"), "pairs": []})
        per_wetland[y["wid"]]["pairs"].extend(got)

    rep = accuracy.report(pairs)
    rep["max_offset_days"] = args.offset
    rep["source"] = args.source
    rep["by_wetland"] = {
        wid: {"name": v["name"], **accuracy.metrics([p for p in v["pairs"] if p["state"] == "open"])}
        for wid, v in per_wetland.items()
    }

    # 묶은 상관은 습지 간 크기 차이에 오염됩니다. 화면이 인용할 수 있는 값은
    # 습지별 상관의 중앙값입니다.
    r2s = sorted(m["r2"] for m in rep["by_wetland"].values() if m.get("r2") is not None)
    rep["median_wetland_r2"] = (
        round(r2s[len(r2s) // 2] if len(r2s) % 2 else (r2s[len(r2s) // 2 - 1] + r2s[len(r2s) // 2]) / 2, 3)
        if r2s else None
    )
    rep["n_wetlands_validated"] = len(r2s)

    out = WEB_DATA / "validation.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    o = rep["overall"]
    print(f"\n짝지은 관측 {o['n']}건")
    op = rep["by_state"].get("open")
    if op:
        print(f"개방수면 구간 {op['n']}건 · MAE {op['mae_ha']} ha "
              f"({op['mae_pct_of_wetland']}% of 습지면적) · R² {op['r2']} "
              f"· 편향 {op['bias_ha']} ha")
    print("저장:", out)


if __name__ == "__main__":
    main()
