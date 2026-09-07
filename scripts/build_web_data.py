"""판독 결과 -> 화면용 정적 파일.

화면은 서버 계산을 하지 않는다. 여기서 만든 파일만 읽는다.
(질의응답만 서버를 쓴다. 선행 프로젝트와 같은 구성.)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import geopandas as gpd  # noqa: E402

from nie.config import AOI, INTERIM, WEB_DATA  # noqa: E402
from nie.wetlands import aggregate, registry  # noqa: E402


def build(sources: list[str]) -> None:
    merged = INTERIM / "_merged.jsonl"

    def richness(rec: dict) -> tuple:
        """같은 (습지, 연도)가 여러 파일에 있을 때 어느 것을 쓸지 정하는 기준.

        광학 교차검증까지 수집된 기록을 우선합니다. 인자 순서에 의존하면
        --optical 없이 돌린 배치가 있는 배치를 덮어 NDVI 근거가 사라집니다.
        """
        return (
            rec.get("status") == "ok",
            bool(rec.get("optical")),
            len(rec.get("scenes", [])),
        )

    best: dict[tuple[str, int], dict] = {}
    n_files = 0
    for name in sources:
        path = INTERIM / name
        if not path.exists():
            print(f"  건너뜀 (없음): {path.name}")
            continue
        n_files += 1
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            key = (rec["wid"], rec["year"])
            if key not in best or richness(rec) > richness(best[key]):
                best[key] = rec

    lines = [json.dumps(r, ensure_ascii=False) for _, r in sorted(best.items())]
    merged.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    n_optical = sum(1 for r in best.values() if r.get("optical"))
    print(f"원자료 {n_files}개 파일 -> 습지-연도 {len(lines)}건 (광학 교차검증 {n_optical}건)")

    summary = aggregate.summarize(merged)

    # 1) 습지별 시계열 (관측 배열 포함) — 화면의 주 자료
    wetlands_out = []
    for wy in summary["wetland_years"]:
        wetlands_out.append(wy)
    (WEB_DATA / "wetland_years.json").write_text(
        json.dumps(wetlands_out, ensure_ascii=False), encoding="utf-8"
    )

    # 2) 전국 요약 — 헤더 KPI
    head = {k: v for k, v in summary.items() if k != "wetland_years"}
    (WEB_DATA / "summary.json").write_text(
        json.dumps(head, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 3) 습지 위치 (미니 지도용 대표점 + 단순화 경계)
    wids = {wy["wid"] for wy in summary["wetland_years"]}
    gdf = registry.load(min_area_ha=0)
    gdf = gdf[gdf.wid.isin(wids)].copy()
    gdf["geometry"] = gdf.geometry.simplify(0.0005)
    pts = gdf.copy()
    pts["lon"] = pts.geometry.centroid.x
    pts["lat"] = pts.geometry.centroid.y
    (WEB_DATA / "wetland_points.json").write_text(
        json.dumps(
            [
                {"wid": r.wid, "name": r["name"], "area_ha": round(r.area_ha, 1),
                 "lon": round(r.lon, 5), "lat": round(r.lat, 5)}
                for _, r in pts.iterrows()
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # 화면이 에코뱅크 WMS 를 겹쳐 부르려면 EPSG:5186 bbox 가 필요합니다.
    # 브라우저에 투영 라이브러리를 싣지 않으려고 여기서 미리 계산해 실어 보냅니다.
    b5186 = gdf.to_crs(5186).bounds.round(1)
    shapes = gdf[["wid", "name", "area_ha", "geometry"]].copy()
    shapes["bbox5186"] = [
        f"{r.minx},{r.miny},{r.maxx},{r.maxy}" for r in b5186.itertuples()
    ]
    out_shapes = WEB_DATA / "wetland_shapes.geojson"
    if out_shapes.exists():
        out_shapes.unlink()
    shapes.to_file(out_shapes, driver="GeoJSON")

    print(f"습지 {head['n_wetlands']}개소 / 습지-연도 {head['n_wetland_years']}건 "
          f"/ 관측 {head['n_observations']:,}회")
    print(f"평균 재방문 {head['mean_revisit_days']}일, "
          f"식생피복 관측된 습지 {head['n_wetlands_with_veg_cover']}개소")
    # 3.5) 관측 가능성 이력 — 궤도별 연 관측수.
    #      판독보다 이게 먼저다. 관측이 없어서 생긴 공백을 '변화 없음'으로 읽지 않기 위한 것.
    #    한 습지가 여러 배치에 걸쳐 있으면 연도 범위가 서로 다릅니다.
    #    먼저 온 것을 채택하면 1개년만 돌린 배치가 다년 배치를 덮어 이력이 잘립니다.
    #    같은 위성 카탈로그에서 나온 수치이므로 연도별로 합집합을 취합니다.
    merged_orbits: dict[str, dict] = {}
    for name in sources:
        hp = INTERIM / (Path(name).stem + "_orbits.json")
        if not hp.exists():
            continue
        for rec in json.loads(hp.read_text(encoding="utf-8")):
            cur = merged_orbits.get(rec["wid"])
            if cur is None:
                merged_orbits[rec["wid"]] = json.loads(json.dumps(rec))
                continue
            for orb, by_year in rec["by_orbit_year"].items():
                cur["by_orbit_year"].setdefault(orb, {}).update(by_year)
            # 궤도 선택은 관측 범위가 넓은 쪽 판단을 따릅니다.
            span = lambda r: sum(len(v) for v in r["by_orbit_year"].values())
            if span(rec) > span(cur):
                cur["chosen_orbit"] = rec["chosen_orbit"]
                cur["chosen_pass"] = rec.get("chosen_pass", cur.get("chosen_pass"))
    orbits = list(merged_orbits.values())
    if orbits:
        (WEB_DATA / "orbit_history.json").write_text(
            json.dumps(orbits, ensure_ascii=False), encoding="utf-8"
        )
        print(f"관측 가능성 이력 {len(orbits)}개소")

    # 미니 지도용 국토 외곽선.
    # GEE 는 시도에 따라 Polygon / MultiPolygon / GeometryCollection 을 섞어 준다.
    # 화면에서 분기하지 않도록 여기서 Polygon 하나로 펴서 내보낸다.
    korea = AOI / "korea_adm1.geojson"
    if korea.exists():
        kg = gpd.read_file(korea).explode(index_parts=False)
        kg = kg[kg.geometry.geom_type == "Polygon"].copy()
        kg["geometry"] = kg.geometry.simplify(0.004)
        kg = kg[kg.to_crs(5179).area > 5e6]        # 5 km2 미만 섬은 뺀다
        out_korea = WEB_DATA / "korea_adm1.geojson"
        if out_korea.exists():
            out_korea.unlink()
        kg[["geometry"]].to_file(out_korea, driver="GeoJSON")
        print(f"국토 외곽 {len(kg)}폴리곤 ({out_korea.stat().st_size/1e3:.0f} KB)")
    else:
        print("  주의: korea_adm1.geojson 이 없어 미니 지도가 비어 보인다.")

    print("출력:", WEB_DATA)


if __name__ == "__main__":
    build(sys.argv[1:] or ["deep.jsonl", "pilot.jsonl"])
