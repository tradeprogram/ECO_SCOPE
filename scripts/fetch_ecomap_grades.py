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


def summarize(wid: str, name, geom_5186, pad_m: float = 200.0) -> dict:
    """습지 경계 안의 생태자연도 등급별 면적 점유율."""
    minx, miny, maxx, maxy = geom_5186.bounds
    fc = client.wfs((minx - pad_m, miny - pad_m, maxx + pad_m, maxy + pad_m))
    feats = fc.get("features", [])
    if not feats:
        return {"wid": wid, "name": name, "status": "no_data", "grades": {}}

    total = geom_5186.area
    grades: dict[str, float] = {}
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
        grades[client.grade_of(props)] = grades.get(client.grade_of(props), 0.0) + part.area
        if props.get("precise_smld_ttle"):
            smld_titles.add(str(props["precise_smld_ttle"]))
        if props.get("plnt_cln_ttle"):
            key = str(props["plnt_cln_ttle"])
            plant_titles[key] = plant_titles.get(key, 0.0) + part.area

    covered = sum(grades.values())
    return {
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
