"""여러 습지 × 여러 해를 돌리는 배치 판독기.

GEE 가 제한 모드라 **중간에 끊기는 것을 정상으로 가정한다.** 진행분은 매 건마다
JSONL 로 흘려 쓰고, 다시 돌리면 이미 끝난 (습지, 연도) 조합은 건너뛴다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import ee

from . import gee, s1_water, s2_veg


def _mapping(geom) -> dict:
    from shapely.geometry import mapping
    return mapping(geom)


def orbit_year_table(log: list[dict]) -> dict[str, dict[str, int]]:
    """장면 목록 -> {궤도: {연도: 관측수}}. 관측 가능성 이력의 원자료."""
    import datetime as _dt

    out: dict[str, dict[str, int]] = {}
    for s in log:
        year = (_dt.datetime.utcfromtimestamp(s["millis"] / 1000) + _dt.timedelta(hours=9)).year
        key = str(s["rel_orbit"])
        out.setdefault(key, {})
        out[key][str(year)] = out[key].get(str(year), 0) + 1
    return out


class Checkpoint:
    """(wid, year) 단위 재개. 파일이 곧 상태다."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.done: set[tuple[str, int]] = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                self.done.add((rec["wid"], rec["year"]))

    def has(self, wid: str, year: int) -> bool:
        return (wid, year) in self.done

    def write(self, rec: dict) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.done.add((rec["wid"], rec["year"]))


# 이 넓이를 넘으면 1년 요청이 GEE 동시성 한도에 걸립니다.
# 실측: 한강하구(5,817 ha) 1년 실패 / 3개월 24초 성공.
BIG_AREA_HA = 1000.0


def _year_in_chunks(geom, year: int, rel_orbit: int, n: int,
                    with_optical: bool) -> tuple[list, list]:
    """1년치를 n등분해 나눠 받습니다.

    대면적 습지(한강하구 5,817 ha 등)에서 1년을 한 번에 요청하면 GEE 가
    'Too many concurrent aggregations' 로 거절합니다. 장면마다 Otsu 히스토그램을
    함께 내기 때문에 폴리곤이 크고 장면이 많을수록 한 요청의 부담이 커집니다.
    같은 요청을 기간으로 쪼개면 통과합니다 — 실측에서 1년은 실패, 3개월은 24초에
    7장면을 받았습니다. 결과는 이어 붙이면 되므로 산출물은 동일합니다.
    """
    months = [1 + (12 * i) // n for i in range(n)] + [13]
    scenes, optical = [], []
    for a, b in zip(months, months[1:]):
        lo = f"{year}-{a:02d}-01"
        hi = f"{year + 1}-01-01" if b == 13 else f"{year}-{b:02d}-01"
        start, end = gee.kst_window(lo, hi)
        scenes.extend(s1_water.wetland_timeseries_dual(
            geom, start, end, rel_orbit=rel_orbit))
        if with_optical:
            optical.extend(s2_veg.wetland_timeseries(geom, start, end))
        time.sleep(2)
    return scenes, optical


def run(
    wetlands,
    years: list[int],
    out_path: Path,
    with_optical: bool = False,
    pause_s: float = 0.5,
    max_retry: int = 3,
) -> Path:
    """wetlands: GeoDataFrame(wid, name, area_ha, geometry). 결과를 JSONL 로 남긴다."""
    gee.init()
    ckpt = Checkpoint(out_path)
    orbit_cache: dict[str, dict | None] = {}
    history: dict[str, dict] = {}
    history_path = out_path.with_name(out_path.stem + "_orbits.json")

    total = len(wetlands) * len(years)
    done_n = 0
    for _, row in wetlands.iterrows():
        geom = ee.Geometry(_mapping(row.geometry.simplify(0.00015)))
        for year in years:
            done_n += 1
            if ckpt.has(row.wid, year):
                continue
            start, end = gee.kst_window(f"{year}-01-01", f"{year + 1}-01-01")

            if row.wid not in orbit_cache:
                try:
                    span_start, span_end = gee.kst_window(
                        f"{min(years)}-01-01", f"{max(years) + 1}-01-01"
                    )
                    orbit, log = gee.dominant_orbit_recent(geom, span_start, span_end)
                    orbit_cache[row.wid] = orbit
                    if orbit is not None:
                        history[row.wid] = {
                            "wid": row.wid,
                            "name": row["name"],
                            "chosen_orbit": orbit["rel_orbit"],
                            "chosen_pass": orbit["pass"],
                            "by_orbit_year": orbit_year_table(log),
                        }
                except Exception as exc:
                    orbit_cache[row.wid] = None
                    print(f"  ! orbit 조회 실패 {row.wid}: {str(exc)[:120]}")
            orbit = orbit_cache[row.wid]
            if orbit is None:
                ckpt.write({"wid": row.wid, "year": year, "status": "no_coverage", "scenes": []})
                continue

            rec = {
                "wid": row.wid,
                "name": row["name"],
                "year": year,
                "area_ha": round(float(row.area_ha), 3),
                "rel_orbit": orbit["rel_orbit"],
                "orbit_pass": orbit["pass"],
                "status": "ok",
            }
            # 대면적 습지는 1년을 한 번에 요청하면 거의 확실히 거절당합니다.
            # 실패를 기다렸다 쪼개면 개소당 3분 남짓을 버리므로, 처음부터 쪼갭니다.
            presplit = 4 if float(row.area_ha) >= BIG_AREA_HA else 0

            for attempt in range(1, max_retry + 1):
                try:
                    if presplit:
                        sc, op = _year_in_chunks(
                            geom, year, orbit["rel_orbit"], presplit, with_optical)
                        rec["scenes"] = sc
                        rec["split_requests"] = presplit
                        if with_optical:
                            rec["optical"] = op
                        break
                    rec["scenes"] = s1_water.wetland_timeseries_dual(
                        geom, start, end, rel_orbit=orbit["rel_orbit"]
                    )
                    if with_optical:
                        rec["optical"] = s2_veg.wetland_timeseries(geom, start, end)
                    break
                except Exception as exc:
                    msg = str(exc)[:160]
                    # 동시성·할당량 오류는 기다린다고 풀리지 않았습니다. 요청 자체가
                    # 무거운 것이므로, 재시도할 때마다 기간을 더 잘게 쪼개 부담을 줄입니다.
                    heavy = any(
                        k in msg
                        for k in ("Too many concurrent", "quota", "Quota",
                                  "rate limit", "Rate limit", "Computation timed out")
                    )
                    if attempt == max_retry:
                        rec["status"] = "error"
                        rec["error"] = msg
                        rec["scenes"] = []
                    elif heavy:
                        parts = max(presplit, 4) * (attempt + 1)   # 8분할 -> 12분할 -> ...
                        try:
                            sc, op = _year_in_chunks(
                                geom, year, orbit["rel_orbit"], parts, with_optical)
                            rec["scenes"] = sc
                            if with_optical:
                                rec["optical"] = op
                            rec["split_requests"] = parts
                            break
                        except Exception as exc2:
                            msg = str(exc2)[:160]
                            time.sleep(20 * attempt)
                    else:
                        time.sleep(4 * attempt)
            ckpt.write(rec)
            n = len(rec.get("scenes", []))
            print(f"[{done_n}/{total}] {row.wid} {year} orbit{orbit['rel_orbit']} "
                  f"scenes={n} {rec['status']}", flush=True)
            time.sleep(pause_s)
            if history:
                history_path.write_text(
                    json.dumps(list(history.values()), ensure_ascii=False, indent=1),
                    encoding="utf-8",
                )
    return out_path
