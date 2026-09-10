"""나라장터에서 국립생태원 습지·자연환경조사 용역 공고를 찾습니다.

    python scripts/find_survey_contracts.py --years 2022 2023 2024 2025

목적
    현장조사 1개소당 투입 인력·일수를 확인하려면 용역 **과업지시서**를 봐야 합니다.
    과업지시서는 나라장터 공고 상세의 첨부파일에 있고, 이 스크립트는 그 공고를
    찾아 상세 URL 을 뽑아줍니다. 첨부 자체는 브라우저로 내려받아야 합니다.

사전 준비 (1회, 자동승인)
    공공데이터포털에서 '조달청_나라장터 입찰공고정보서비스' 활용신청을 해야 합니다.
    https://www.data.go.kr/data/15129394/openapi.do
    신청 전에는 403 '등록되지 않은 서비스키' 가 돌아옵니다 — 엔드포인트 문제가
    아니라 그 서비스에 키가 등록되지 않은 것입니다. 승인 뒤 .env 의
    DATA_GO_KR_KEY 를 그대로 쓰면 됩니다(키는 계정당 하나입니다).

주의
    조회구분(inqryDiv)에 따라 날짜 필드의 의미가 달라집니다. 여기서는 1(공고게시일)
    을 씁니다. 한 번에 받을 수 있는 기간이 제한되므로 연 단위로 끊어 요청합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from nie.config import DATA_GO_KR_KEY  # noqa: E402

BASE = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
OP = "getBidPblancListInfoServcPPSSrch"      # 용역 입찰공고 목록
PAGE = 100
PAUSE = 0.4

# 공고명에 이 말들이 들어가면 조사 용역으로 봅니다.
KEYWORDS = ("습지", "자연환경조사", "생태계", "정밀조사", "일반조사", "모니터링", "인벤토리")
AGENCY = "국립생태원"


def call(op: str, params: dict, retries: int = 4) -> dict:
    q = dict(params)
    q["serviceKey"] = DATA_GO_KR_KEY
    q["type"] = "json"
    url = f"{BASE}/{op}?{urllib.parse.urlencode(q)}"
    last = ""
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                raw = r.read().decode("utf-8", "replace")
            if not raw.lstrip().startswith("{"):
                raise SystemExit(f"JSON 이 아닌 응답: {raw[:250]}")
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            last = f"HTTP {e.code}: {body[:200]}"
            if "등록되지 않은 서비스키" in body:
                raise SystemExit(
                    "403 등록되지 않은 서비스키.\n"
                    "  https://www.data.go.kr/data/15129394/openapi.do 에서\n"
                    "  '조달청_나라장터 입찰공고정보서비스' 활용신청을 하십시오(자동승인).\n"
                    "  엔드포인트는 정상입니다 — 키가 이 서비스에 등록되지 않았을 뿐입니다."
                )
            # 이 API 는 SERVICETIMEOUT_ERROR(503) 를 자주 냅니다. 기다리면 풀립니다.
            if attempt < retries:
                time.sleep(5 * attempt)
                continue
        except Exception as e:                       # 네트워크 단절 등
            last = f"{type(e).__name__}: {str(e)[:150]}"
            if attempt < retries:
                time.sleep(5 * attempt)
                continue
        break
    raise SystemExit(f"요청 실패({retries}회 시도): {last}")


def months(year: int):
    """월 단위로 끊습니다.

    연 단위로 요청하면 오류 없이 조용히 0건이 돌아옵니다. 기간 상한이 있는데
    초과를 알려주지 않습니다 — 실측에서 2025년 전체는 0건, 2025년 6월은 14,645건.
    범위를 넓혔는데 결과가 줄면 상한을 의심해야 합니다.
    """
    for m in range(1, 13):
        end = 31 if m in (1, 3, 5, 7, 8, 10, 12) else (30 if m != 2 else 29)
        yield f"{year}{m:02d}010000", f"{year}{m:02d}{end}2359"


def fetch_year(year: int) -> list[dict]:
    out = []
    for bgn, end in months(year):
        page = 1
        while True:
            d = call(OP, {
                "pageNo": page, "numOfRows": PAGE, "inqryDiv": 1,
                "inqryBgnDt": bgn, "inqryEndDt": end,
                "dminsttNm": AGENCY,
            })
            body = d.get("response", {}).get("body", {})
            items = body.get("items") or []
            if isinstance(items, dict):
                items = items.get("item") or []
            out.extend(items)
            total = int(body.get("totalCount") or 0)
            if page * PAGE >= total or not items:
                break
            page += 1
            time.sleep(PAUSE)
        time.sleep(PAUSE)
    return out


def spec_docs(r: dict) -> list[tuple[str, str]]:
    """공고에 붙은 규격서(과업지시서 포함) 파일명과 내려받기 URL."""
    out = []
    for i in range(1, 11):
        nm = (r.get(f"ntceSpecFileNm{i}") or "").strip()
        url = (r.get(f"ntceSpecDocUrl{i}") or "").strip()
        if nm or url:
            out.append((nm, url))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="+", type=int,
                    default=[2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--all", action="store_true", help="조사 관련 키워드로 거르지 않음")
    args = ap.parse_args()

    if not DATA_GO_KR_KEY:
        raise SystemExit(".env 에 DATA_GO_KR_KEY 가 없습니다.")

    rows = []
    for y in args.years:
        got = fetch_year(y)
        print(f"{y}년: 공고 {len(got)}건")
        rows.extend(got)
        time.sleep(PAUSE)

    if not args.all:
        rows = [r for r in rows
                if any(k in (r.get("bidNtceNm") or "") for k in KEYWORDS)]

    rows.sort(key=lambda r: r.get("bidNtceDt") or "")
    print()
    print(f"조사 관련 공고 {len(rows)}건")
    print()
    for r in rows:
        price = r.get("presmptPrce")
        try:
            price = f"{int(price):,}원"
        except (TypeError, ValueError):
            price = "-"
        print(f"[{(r.get('bidNtceDt') or '')[:10]}] {r.get('bidNtceNm')}")
        print(f"    추정가격 {price} · 계약방법 {r.get('cntrctCnclsMthdNm') or '-'}")
        docs = spec_docs(r)
        if docs:
            print(f"    첨부 {len(docs)}건")
            for nm, url in docs:
                mark = " ←과업지시서" if any(
                    k in nm for k in ("과업", "제안요청", "규격", "사양")) else ""
                print(f"      · {nm}{mark}")
                if url:
                    print(f"        {url}")
        print(f"    공고상세 {r.get('bidNtceDtlUrl') or '-'}")
        print()

    out = Path("data/processed/nara_survey_notices.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("기록:", out)
    print("\n다음: 위 '공고상세' 링크를 브라우저로 열어 첨부의 **과업지시서**를 보십시오.")
    print("      조사 대상지 수 · 수행 기간 · 투입 인력 등급별 인원이 거기 있습니다.")


if __name__ == "__main__":
    main()

# ── 실행 기록 (2026-09-10) ──────────────────────────────────────────────────
#
# 2022~2026년 국립생태원 용역 공고 약 240건을 훑어 확인한 것.
#
#   찾은 것 — 전국자연환경조사 현지조사 여비·수당 (과업설명서 기재)
#     2022  283팀(567명)  44.16억   2023  289팀(584명)  45.42억
#     2024  298팀(596명)  42.50억   2025  555명         33.72억
#     2026  572명         42.95억
#     * 여비·수당만이며 연구 인건비·분석비는 별도.
#
#   못 찾은 것 — 내륙습지조사 1개소당 투입 인력·일수
#     내륙습지조사를 발주한 용역 공고 자체가 없다. 원 자체 수행 + 외부조사원
#     방식으로 보이며, 정산 위탁용역도 전국자연환경조사·멸종위기·관찰종만 대상이다.
#     따라서 습지 개소 단위 단가로 환산할 근거가 아직 없다.
#
# 파라미터 함정 둘.
#   1) inqryBgnDt~inqryEndDt 를 연 단위로 주면 오류 없이 0건이 온다. 월 단위로 끊어야 한다.
#   2) 이 API 는 503 SERVICETIMEOUT_ERROR 를 자주 낸다. 재시도하면 통한다.
