"""습지 개방수면 판독 배치 실행.

    python scripts/run_water_batch.py --top 12 --years 2024 --out pilot.jsonl
    python scripts/run_water_batch.py --top 40 --years 2019-2025 --optical

중간에 끊겨도 같은 --out 으로 다시 돌리면 이어서 한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nie.config import INTERIM  # noqa: E402
from nie.rs import batch  # noqa: E402
from nie.wetlands import registry  # noqa: E402


def parse_years(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20, help="면적 상위 N개소")
    ap.add_argument("--min-area", type=float, default=10.0, help="최소 면적(ha)")
    ap.add_argument("--years", default="2024")
    ap.add_argument("--out", default="water_timeseries.jsonl")
    ap.add_argument("--optical", action="store_true", help="Sentinel-2 교차검증 동시 수집")
    ap.add_argument("--wids", default=None, help="쉼표구분 wid 목록. 주면 --top/--min-area 를 무시한다")
    args = ap.parse_args()

    if args.wids:
        want = [w.strip() for w in args.wids.split(",") if w.strip()]
        allw = registry.load(min_area_ha=0)
        wetlands = allw[allw.wid.isin(want)].copy()
        missing = set(want) - set(wetlands.wid)
        if missing:
            print("레지스트리에 없는 wid:", ", ".join(sorted(missing)))
    else:
        wetlands = registry.load(min_area_ha=args.min_area).head(args.top)
    years = parse_years(args.years)
    out = INTERIM / args.out

    print(f"대상 {len(wetlands)}개소 × {len(years)}개년 = {len(wetlands)*len(years)}건")
    print(f"면적 {wetlands.area_ha.min():.0f}~{wetlands.area_ha.max():.0f} ha, 출력 {out}")
    batch.run(wetlands, years, out, with_optical=args.optical)
    print("완료:", out)


if __name__ == "__main__":
    main()
