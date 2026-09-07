"""습지 대상 목록(레지스트리).

출처 우선순위
    1. 에코뱅크 정본   data/raw/wetlands_ecobank.geojson
       (에코뱅크 오픈API `습지_내륙_면`, EPSG:5186. scripts/fetch_wetlands_ecobank.py 로 수집)
    2. 공공데이터포털 SHP  data/raw/nie_inland_wetlands/*.shp
       (`국립생태원_내륙습지 공간데이터 및 속성정보`. 내려받기에 로그인이 필요합니다.)
    3. OSM 부트스트랩  data/raw/wetlands_osm.geojson (정본이 없을 때만 사용)

어느 쪽을 쓰든 아래 스키마로 통일해서 내보낸다. 판독 코드가 출처를 몰라도 되게.

    wid           안정 식별자
    name          습지명 (없으면 None — OSM 은 대부분 없다)
    source        "nie" | "osm"
    wetland_type  원 자료의 유형 태그
    inland        내륙습지 여부. 갯벌·염습지는 False (해수부 소관 연안습지)
    area_ha       EPSG:5179 기준 면적 (ha)
    geometry      EPSG:4326 폴리곤
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from ..config import MIN_WETLAND_AREA_HA, RAW

ECOBANK_GEOJSON = RAW / "wetlands_ecobank.geojson"
NIE_SHP_DIR = RAW / "nie_inland_wetlands"
OSM_GEOJSON = RAW / "wetlands_osm.geojson"

# 에코뱅크 `습지_내륙_면` 은 정의상 전부 내륙습지입니다. 별도 연안 필터가 필요 없습니다.
# (처음에 wtl_korea_ty_code 의 'M' 을 해양으로 오독했으나, M2 는 화엄늪 같은 '산지습지'입니다.)

# 해수부 소관 연안습지. 국립생태원 내륙습지 조사 대상이 아니므로 코어에서 뺀다.
COASTAL_TYPES = {"tidalflat", "saltmarsh", "mangrove", "saltern"}

AREA_CRS = 5179  # Korea 2000 / Unified CS — 전국 면적 계산용


def _finalize(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf["geometry"] = gdf.geometry.buffer(0)
    gdf = gdf.to_crs(4326)
    gdf["area_ha"] = gdf.to_crs(AREA_CRS).area / 10_000
    return gdf.sort_values("area_ha", ascending=False).reset_index(drop=True)


def _load_ecobank() -> gpd.GeoDataFrame | None:
    """에코뱅크 `습지_내륙_면` 정본.

    scripts/fetch_wetlands_ecobank.py 가 속성조회(attr) 응답을 표준 이름으로 정리해
    저장한 파일을 읽습니다. 습지명·습지코드·유형명(한글)·보호지역 지정명·주소가 함께 옵니다.
    """
    if not ECOBANK_GEOJSON.exists():
        return None
    gdf = gpd.read_file(ECOBANK_GEOJSON)
    if gdf.empty:
        return None
    if gdf.crs is None:
        gdf = gdf.set_crs(5186)

    out = gpd.GeoDataFrame(
        {
            "wid": gdf["wtl_code"].astype(str),
            "name": gdf.get("name"),
            "source": "ecobank",
            "wetland_type": gdf.get("type_name"),          # 한글 유형명 (산지습지 등)
            "korea_type_code": gdf.get("korea_type_code"),
            "ramsar": gdf.get("ramsar_code"),
            "protected": gdf.get("protected_name"),
            "address": gdf.get("address"),
        },
        geometry=gdf.geometry,
        crs=gdf.crs,
    )
    out["inland"] = True   # 이 레이어 자체가 내륙습지 목록입니다
    return _finalize(out)


def _load_nie() -> gpd.GeoDataFrame | None:
    if not NIE_SHP_DIR.exists():
        return None
    shps = sorted(NIE_SHP_DIR.glob("*.shp"))
    if not shps:
        return None
    gdf = gpd.read_file(shps[0], encoding="utf-8")
    cols = {c.lower(): c for c in gdf.columns}

    def pick(*names: str) -> str | None:
        for n in names:
            if n in cols:
                return cols[n]
        return None

    name_col = pick("wtlnd_nm", "name", "습지명", "wetland_nm", "nm")
    type_col = pick("wtlnd_ty", "type", "습지유형", "wetland_ty", "ty")
    id_col = pick("wtlnd_cd", "code", "습지코드", "id")

    out = gpd.GeoDataFrame(
        {
            "wid": (
                gdf[id_col].astype(str) if id_col else
                [f"nie-{i:05d}" for i in range(len(gdf))]
            ),
            "name": gdf[name_col] if name_col else None,
            "source": "nie",
            "wetland_type": gdf[type_col] if type_col else None,
        },
        geometry=gdf.geometry,
        crs=gdf.crs,
    )
    out["inland"] = True  # 이 자료 자체가 '내륙습지' 목록이다
    return _finalize(out)


def _load_osm() -> gpd.GeoDataFrame | None:
    if not OSM_GEOJSON.exists():
        return None
    gdf = gpd.read_file(OSM_GEOJSON)
    out = gpd.GeoDataFrame(
        {
            "wid": gdf["id"] if "id" in gdf.columns else gdf.index.map(lambda i: f"osm-{i:05d}"),
            "name": gdf.get("name"),
            "source": "osm",
            "wetland_type": gdf.get("wetland_type"),
        },
        geometry=gdf.geometry,
        crs=gdf.crs,
    )
    types = out["wetland_type"].fillna("")
    out["inland"] = ~types.isin(COASTAL_TYPES)
    return _finalize(out)


def load(source: str = "auto", inland_only: bool = True, min_area_ha: float | None = None) -> gpd.GeoDataFrame:
    """레지스트리를 읽습니다. source: "auto" | "ecobank" | "nie" | "osm"."""
    gdf = None
    if source in ("auto", "ecobank"):
        gdf = _load_ecobank()
        if gdf is None and source == "ecobank":
            raise FileNotFoundError(
                f"에코뱅크 정본 없음: {ECOBANK_GEOJSON}. "
                "`python scripts/fetch_wetlands_ecobank.py` 를 먼저 실행하십시오."
            )
    if gdf is None and source in ("auto", "nie"):
        gdf = _load_nie()
        if gdf is None and source == "nie":
            raise FileNotFoundError(f"국립생태원 정본 SHP 없음: {NIE_SHP_DIR}")
    if gdf is None and source in ("auto", "nie", "osm"):
        gdf = _load_osm()
    if gdf is None:
        raise FileNotFoundError(
            "습지 레지스트리 원본이 하나도 없다. "
            "`python scripts/fetch_wetlands_osm.py` 를 먼저 돌리거나 정본 SHP 를 넣을 것."
        )

    if inland_only:
        gdf = gdf[gdf["inland"]].copy()
    floor = MIN_WETLAND_AREA_HA if min_area_ha is None else min_area_ha
    gdf = gdf[gdf["area_ha"] >= floor].copy()
    return gdf.reset_index(drop=True)


def describe() -> dict:
    """현재 잡히는 레지스트리 상태 요약. 문서·제안서 수치를 여기서만 뽑는다."""
    eco, nie, osm = _load_ecobank(), _load_nie(), _load_osm()
    active = "ecobank" if eco is not None else ("nie" if nie is not None else ("osm" if osm is not None else None))
    info: dict = {"active": active}
    for key, gdf in (("ecobank", eco), ("nie", nie), ("osm", osm)):
        if gdf is None:
            info[key] = None
            continue
        inland = gdf[gdf["inland"]]
        info[key] = {
            "total": int(len(gdf)),
            "inland": int(len(inland)),
            "coastal": int(len(gdf) - len(inland)),
            "named": int(gdf["name"].notna().sum()),
            f"inland_ge_{MIN_WETLAND_AREA_HA:g}ha": int((inland["area_ha"] >= MIN_WETLAND_AREA_HA).sum()),
            "inland_ge_10ha": int((inland["area_ha"] >= 10).sum()),
            "inland_area_total_ha": round(float(inland["area_ha"].sum()), 1),
        }
    return info
