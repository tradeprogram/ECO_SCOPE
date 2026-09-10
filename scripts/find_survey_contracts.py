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


def call(op: str, params: dict) -> dict:
    q = dict(params)
    q["serviceKey"] = DATA_GO_KR_KEY
    q["type"] = "json"
    url = f"{BASE}/{op}?{urllib.parse.urlencode(q)}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if "등록되지 않은 서비스키" in body:
            raise SystemExit(
                "403 등록되지 않은 서비스키.\n"
                "  https://www.data.go.kr/data/15129394/openapi.do 에서\n"
                "  '조달청_나라장터 입찰공고정보서비스' 활용신청을 하십시오(자동승인).\n"
                "  엔드포인트는 정상입니다 — 키가 이 서비스에 등록되지 않았을 뿐입니다."
            )
        raise SystemExit(f"HTTP {e.code}: {body[:300]}")
    if not raw.lstrip().startswith("{"):
        raise SystemExit(f"JSON 이 아닌 응답: {raw[:250]}")
    return json.loads(raw)


def fetch_year(year: int) -> list[dict]:
    out, page = [], 1
    while True:
        d = call(OP, {
            "pageNo": page, "numOfRows": PAGE, "inqryDiv": 1,
            "inqryBgnDt": f"{year}01010000", "inqryEndDt": f"{year}12312359",
            # 수요기관명으로 좁힙니다. 이 파라미터가 막히면 빼고 전량 받아 거르십시오.
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
    print(f"\n조사 관련 공고 {len(rows)}건\n")
    for r in rows:
        print(f"[{(r.get('bidNtceDt') or '')[:10]}] {r.get('bidNtceNm')}")
        print(f"    추정가격 {r.get('presmptPrce') or '-'} · 수요기관 {r.get('dminsttNm')}")
        print(f"    공고상세 {r.get('bidNtceDtlUrl') or r.get('bidNtceUrl') or '-'}")
        print()

    out = Path("data/processed/nara_survey_notices.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("기록:", out)
    print("\n다음: 위 '공고상세' 링크를 브라우저로 열어 첨부의 **과업지시서**를 보십시오.")
    print("      조사 대상지 수 · 수행 기간 · 투입 인력 등급별 인원이 거기 있습니다.")


if __name__ == "__main__":
    main()
