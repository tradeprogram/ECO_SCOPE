"""습지별 생태자연도 등급 구성을 산출합니다.

    python scripts/fetch_ecomap_grades.py --top 30

습지 경계로 생태자연도를 잘라, 등급별 면적 점유율을 계산합니다.
"이 습지가 생태자연도 몇 등급 지역인가" 에 답하기 위한 자료입니다.

결과: data/interim/ecomap_grades.jsonl (습지 1개소당 1줄, 이어받기 가능)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")   # 윈도우 콘솔 기본이 cp949 라 한글·기호가 깨집니다

import geopandas as gpd  # noqa: E402
from shapely.geometry import shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from nie.config import INTERIM  # noqa: E402
from nie.ecomap import client  # noqa: E402
from nie.wetlands import registry  # noqa: E402

OUT = INTERIM / "ecomap_grades.jsonl"


def done_wids() -> set[str]:
    if not OUT.exists():
        return set()
    return {
        json.loads(line)["wid"]
        for line in OUT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def collect(bbox, depth: int = 0) -> tuple[list, bool]:
    """bbox 안의 생태자연도 피처. 상한(500)에 닿으면 4분할해 다시 받습니다.

    분할하지 않으면 밀집 지역에서 조용히 잘려, 습지 일부만 덮은 결과가
    전체인 것처럼 집계됩니다.
    """
    fc = client.wfs(bbox)
    feats = fc.get("features", [])
    if not fc.get("_truncated") or depth >= 3:
        return feats, bool(fc.get("_truncated"))
    minx, miny, maxx, maxy = bbox
    mx, my = (minx + maxx) / 2, (miny + maxy) / 2
    # 사분면 경계에 걸친 피처는 여러 사분면에서 함께 돌아옵니다.
    # 그대로 더하면 같은 도형의 면적을 두 번 이상 세어 피복률이 100% 를 넘습니다.
    seen: dict[str, dict] = {}
    trunc = False
    for sub in ((minx, miny, mx, my), (mx, miny, maxx, my),
                (minx, my, mx, maxy), (mx, my, maxx, maxy)):
        sf, st = collect(sub, depth + 1)
        for f in sf:
            seen[str(f.get("id"))] = f
        trunc = trunc or st
        time.sleep(0.4)
    return list(seen.values()), trunc


def summarize(wid: str, name, geom_5186, pad_m: float = 200.0) -> dict:
    """습지 경계 안의 생태자연도 등급별 면적 점유율."""
    minx, miny, maxx, maxy = geom_5186.bounds
    feats, truncated = collect((minx - pad_m, miny - pad_m, maxx + pad_m, maxy + pad_m))
    feats = list({str(f.get("id")): f for f in feats}.values())
    fc = {"_truncated": truncated}
    if not feats:
        return {"wid": wid, "name": name, "status": "no_data", "grades": {}}

    total = geom_5186.area
    # 생태자연도 폴리곤은 서로 겹칩니다. 면적을 그냥 더하면 점유율이 100% 를 넘습니다.
    # 실측한 겹침 규모는 크지 않습니다 — 상위 8개소에서 단순합 대비 합집합이
    # 0~4%p 작았습니다(한강하구 102%→100%, 낙동강하구습지 66%→62%).
    # 크지 않아도 100% 초과는 그 자체로 자료를 못 믿게 만들므로 등급별로
    # **합집합**을 낸 뒤 습지와 교차시킵니다.
    by_grade: dict[str, list] = {}
    smld_titles: set[str] = set()
    plant_titles: dict[str, float] = {}

    for f in feats:
        try:
            g = shape(f["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            part = g.intersection(geom_5186)
        except Exception:
            continue
        if part.is_empty or part.area <= 0:
            continue
        props = f.get("properties", {})
        by_grade.setdefault(client.grade_of(props), []).append(part)
        if props.get("precise_smld_ttle"):
            smld_titles.add(str(props["precise_smld_ttle"]))
        if props.get("plnt_cln_ttle"):
            key = str(props["plnt_cln_ttle"])
            plant_titles[key] = plant_titles.get(key, 0.0) + part.area

    grades: dict[str, float] = {}
    for label, parts in by_grade.items():
        merged = unary_union(parts)
        if not merged.is_empty:
            grades[label] = merged.area
    grades = dict(sorted(grades.items(), key=lambda kv: -kv[1]))

    # 등급 간에도 겹칠 수 있으므로 전체 피복은 모든 등급의 합집합으로 따로 냅니다.
    all_parts = [g for parts in by_grade.values() for g in parts]
    covered_geom = unary_union(all_parts) if all_parts else None

    covered = covered_geom.area if covered_geom is not None else 0.0
    over = covered / total if total else 0
    return {
        "coverage_warning": "피복률이 1을 넘습니다. 계산을 확인하십시오." if over > 1.02 else None,
        "note": "등급 폴리곤은 서로 겹칠 수 있어 등급별 점유율의 합은 피복률과 다를 수 있습니다.",
        "wid": wid,
        "name": name,
        "status": "ok",
        "truncated": bool(fc.get("_truncated")),
        "coverage": round(covered / total, 4) if total else 0.0,
        "grades": {k: round(v / total, 4) for k, v in sorted(grades.items(), key=lambda kv: -kv[1])},
        "wetland_titles": sorted(smld_titles)[:5],
        "top_plant_communities": [
            k for k, _ in sorted(plant_titles.items(), key=lambda kv: -kv[1])[:3]
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30, help="면적 상위 N개소")
    ap.add_argument("--min-area", type=float, default=3.0)
    ap.add_argument("--pause", type=float, default=1.0)
    args = ap.parse_args()

    if not client.available():
        raise SystemExit("생태자연도 인증키가 없습니다. .env 의 DATA_GO_KR_KEY 를 확인하십시오.")

    wetlands = registry.load(min_area_ha=args.min_area).head(args.top).to_crs(5186)
    already = done_wids()
    print(f"대상 {len(wetlands)}개소 (완료 {len(already)}개소는 건너뜁니다)")

    for i, row in enumerate(wetlands.itertuples(), 1):
        if row.wid in already:
            continue
        try:
            rec = summarize(row.wid, row.name, row.geometry)
        except Exception as exc:
            rec = {"wid": row.wid, "name": row.name, "status": "error",
                   "error": str(exc)[:160], "grades": {}}
        with OUT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        top = next(iter(rec["grades"]), "-")
        print(f"[{i}/{len(wetlands)}] {rec.get('name') or row.wid}  {rec['status']}  주등급={top}", flush=True)
        time.sleep(args.pause)

    print("완료:", OUT)


if __name__ == "__main__":
    main()
