"""OSM 습지 폴리곤을 받아 data/raw/wetlands_osm.geojson 으로 저장한다."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nie.config import RAW  # noqa: E402
from nie.wetlands import osm  # noqa: E402

def main() -> None:
    fc = osm.fetch()
    out = RAW / "wetlands_osm.geojson"
    out.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"features : {len(fc['features']):,}")
    print(f"osm base : {fc['fetched_utc']}")
    print(f"saved    : {out}  ({out.stat().st_size/1e6:.1f} MB)")

if __name__ == "__main__":
    main()
