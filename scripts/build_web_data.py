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
    seen: set[tuple[str, int]] = set()
    lines: list[str] = []
    for name in sources:
        path = INTERIM / name
        if not path.exists():
            print(f"  건너뜀 (없음): {path.name}")
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            key = (rec["wid"], rec["year"])
            if key in seen:      # 뒤에 온 파일이 이기지 않는다. 먼저 온 것이 정본.
                continue
            seen.add(key)
            lines.append(line)
    merged.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    print(f"원자료 {len(sources)}개 파일 -> 습지-연도 {len(lines)}건")

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
    gdf[["wid", "name", "area_ha", "geometry"]].to_file(
        WEB_DATA / "wetland_shapes.geojson", driver="GeoJSON"
    )

    print(f"습지 {head['n_wetlands']}개소 / 습지-연도 {head['n_wetland_years']}건 "
          f"/ 관측 {head['n_observations']:,}회")
    print(f"평균 재방문 {head['mean_revisit_days']}일, "
          f"식생피복 관측된 습지 {head['n_wetlands_with_veg_cover']}개소")
    # 3.5) 관측 가능성 이력 — 궤도별 연 관측수.
    #      판독보다 이게 먼저다. 관측이 없어서 생긴 공백을 '변화 없음'으로 읽지 않기 위한 것.
    orbits: list[dict] = []
    for name in sources:
        hp = INTERIM / (Path(name).stem + "_orbits.json")
        if hp.exists():
            for rec in json.loads(hp.read_text(encoding="utf-8")):
                if rec["wid"] not in {o["wid"] for o in orbits}:
                    orbits.append(rec)
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
