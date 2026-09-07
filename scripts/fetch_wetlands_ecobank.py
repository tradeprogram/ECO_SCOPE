"""에코뱅크 오픈API 로 내륙습지 정본을 받습니다.

    python scripts/fetch_wetlands_ecobank.py

속성 조회(attr)를 페이징으로 돌립니다. 이 경로는 `geom` 에 WKT 도형까지 함께 주므로
한 번에 전량(2,704개소)을 받을 수 있습니다. WFS 격자 수집은 도형이 상세해
응답이 커지면 게이트웨이가 HTTP 500 을 돌려주므로 쓰지 않습니다.

결과: data/raw/wetlands_ecobank.geojson (EPSG:5186)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import geopandas as gpd  # noqa: E402
from shapely import wkt  # noqa: E402

from nie.config import RAW  # noqa: E402
from nie.ecobank import client  # noqa: E402

# 에코뱅크 속성 필드 -> 저장소 표준 이름
FIELDS = {
    "wtlCodeId": "wtl_code",
    "wtlNm": "name",
    "wtlTyNm": "type_name",
    "wtlKoreaTyCode": "korea_type_code",
    "wtlRamsaTyCode": "ramsar_code",
    "wtlPrtcAreaAppnNm": "protected_name",
    "addresNm": "address",
    "la": "lat",
    "lo": "lon",
    "registDe": "regist_date",
    "updtDe": "update_date",
}


def main() -> None:
    if not client.available():
        raise SystemExit("에코뱅크 인증키가 없습니다. .env 의 ECOBANK_API_KEY 를 확인하십시오.")

    print("에코뱅크 습지_내륙_면 전량 수집을 시작합니다.")
    # 이 엔드포인트는 처리 시간 상한이 약 10초라 페이지가 크면 실패합니다.
    # 작게 나누고, 진행분을 체크포인트에 적어 끊겨도 이어받게 합니다.
    ckpt = RAW / "wetlands_ecobank_pages.jsonl"
    items, failed = client.fetch_layer_attrs("습지_내륙_면", rows=5, checkpoint=ckpt)

    rows, bad = [], 0
    for it in items:
        raw_geom = it.get("geom")
        if not raw_geom:
            bad += 1
            continue
        try:
            geom = wkt.loads(raw_geom)
        except Exception:
            bad += 1
            continue
        rec = {std: it.get(src) for src, std in FIELDS.items()}
        rec["geometry"] = geom
        rows.append(rec)

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=5186)
    for col in ("lat", "lon"):
        gdf[col] = gpd.pd.to_numeric(gdf[col], errors="coerce")

    out = RAW / "wetlands_ecobank.geojson"
    if out.exists():
        out.unlink()
    # 좌표는 미터 단위이므로 소수 1자리(10 cm)면 충분합니다. 파일 크기를 줄입니다.
    gdf.to_file(out, driver="GeoJSON", COORDINATE_PRECISION=1)

    named = int(gdf["name"].notna().sum())
    protected = int(gdf["protected_name"].notna().sum())
    print(f"습지 {len(gdf):,}개소 (도형 해석 실패 {bad}건, 서버 미회수 {len(failed)}건)")
    if failed:
        (RAW / "wetlands_ecobank_failed.txt").write_text(
            chr(10).join(str(i) for i in failed), encoding="utf-8")
        print(f"  미회수 레코드 순번을 data/raw/wetlands_ecobank_failed.txt 에 남겼습니다.")
    print(f"  습지명 확인 {named:,}개소 · 보호지역 지정 {protected:,}개소")
    print(f"  유형: {gdf['type_name'].value_counts().head(6).to_dict()}")
    print(f"저장: {out}  ({out.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
