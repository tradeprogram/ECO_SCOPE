"""OpenStreetMap Overpass 로 국내 습지 폴리곤을 받는다.

**이것은 정본이 아니다.** 정본은 공공데이터포털의
`국립생태원_내륙습지 공간데이터 및 속성정보`(내륙습지 2,704개소, SHP)이며
로그인이 필요해 자동 수집이 안 된다. 그 파일이 data/raw/ 에 놓이면
`registry.load()` 가 자동으로 그쪽을 쓴다.

OSM 은 (a) 정본이 오기 전 파이프라인을 돌리기 위한 부트스트랩,
(b) 정본이 온 뒤에는 경계 불일치를 보는 교차검증 레이어로 쓴다.
출처 표기: © OpenStreetMap contributors, ODbL.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import unary_union

ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
UA = "nie-wetland-research/0.1 (contest prototype; contact via repo)"

QUERY = """
[out:json][timeout:300];
area["ISO3166-1"="KR"][admin_level=2]->.kr;
(
  way["natural"="wetland"](area.kr);
  relation["natural"="wetland"](area.kr);
);
out geom;
"""
# 주의 — `out geom tags;` 로 쓰면 tags 가 geom 을 눌러 relation 멤버 지오메트리가
# 통째로 빠진다. `out geom;` 이 태그도 같이 준다.


def _post(query: str) -> dict:
    last: Exception | None = None
    for url in ENDPOINTS:
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode({"data": query}).encode(),
            headers={"User-Agent": UA},
        )
        try:
            with urllib.request.urlopen(req, timeout=420) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:  # 엔드포인트 혼잡은 흔하다. 다음 미러로.
            last = exc
            time.sleep(3)
    raise RuntimeError(f"Overpass 전체 엔드포인트 실패: {last}")


def _ring(geometry: list[dict]) -> Polygon | None:
    coords = [(p["lon"], p["lat"]) for p in geometry]
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if (not poly.is_empty and poly.area > 0) else None


def _relation_polygon(element: dict) -> Polygon | MultiPolygon | None:
    """멤버 way 를 outer/inner 로 나눠 다중폴리곤을 만든다."""
    outers, inners = [], []
    for member in element.get("members", []):
        if member.get("type") != "way" or "geometry" not in member:
            continue
        poly = _ring(member["geometry"])
        if poly is None:
            continue
        (inners if member.get("role") == "inner" else outers).append(poly)
    if not outers:
        return None
    shape = unary_union(outers)
    if inners:
        shape = shape.difference(unary_union(inners))
    return shape if not shape.is_empty else None


def fetch() -> dict:
    """국내 습지 폴리곤 FeatureCollection (EPSG:4326)."""
    payload = _post(QUERY)
    features = []
    for el in payload.get("elements", []):
        tags = el.get("tags", {}) or {}
        if el["type"] == "way":
            shape = _ring(el.get("geometry", []))
        else:
            shape = _relation_polygon(el)
        if shape is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"osm-{el['type']}-{el['id']}",
                "properties": {
                    "source": "osm",
                    "osm_type": el["type"],
                    "osm_id": el["id"],
                    "name": tags.get("name") or tags.get("name:ko"),
                    "name_en": tags.get("name:en"),
                    "wetland_type": tags.get("wetland"),
                    "protect_class": tags.get("protect_class"),
                    "ramsar": tags.get("ramsar") or tags.get("designation"),
                },
                "geometry": mapping(shape),
            }
        )
    return {
        "type": "FeatureCollection",
        "attribution": "© OpenStreetMap contributors, ODbL",
        "fetched_utc": payload.get("osm3s", {}).get("timestamp_osm_base"),
        "features": features,
    }
