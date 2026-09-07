"""에코뱅크 인증키·레이어 동작 확인용 진단 도구.

    python scripts/probe_ecobank.py

발급받은 레이어가 실제로 응답하는지, 응답 시간이 얼마인지 한 번에 봅니다.
이 엔드포인트는 처리 시간 상한이 약 10초이고 부하에 따라 같은 요청이
성공하기도 실패하기도 합니다. 실패가 곧 키 문제는 아니므로, 시간대를 바꿔
다시 확인하십시오.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nie.ecobank import client  # noqa: E402

PNG = b"\x89PNG"
UPO_BBOX = (325986.2, 326361.4, 331610.8, 331564.9)   # 우포늪 일대 (EPSG:5186)


def main() -> None:
    if not client.available():
        raise SystemExit("에코뱅크 인증키가 없습니다. .env 의 ECOBANK_API_KEY 를 확인하십시오.")

    print("== 속성 조회 ==")
    for layer in ("습지_내륙_면", "습지_생물상_조사_점", "생태계정밀조사_조사지역_면"):
        t0 = time.time()
        try:
            body = client.attr_page(layer, 1, 2)
            print(f"  {layer:22s} totalCount={body.get('totalCount'):>8}  {time.time()-t0:5.1f}초")
        except Exception as exc:
            print(f"  {layer:22s} 실패: {str(exc)[-60:]}  {time.time()-t0:5.1f}초")
        time.sleep(1)

    print("== WMS (우포늪 일대) ==")
    for layer in ("자연환경조사_식생_면", "생태계정밀조사_식생_면", "습지_내륙_면"):
        t0 = time.time()
        try:
            data = client.wms_image(layer, UPO_BBOX, 320, 300)
            ok = data[:4] == PNG
            print(f"  {layer:22s} {len(data):>8,} bytes  PNG={ok}  {time.time()-t0:5.1f}초")
        except Exception as exc:
            print(f"  {layer:22s} 실패: {str(exc)[-60:]}  {time.time()-t0:5.1f}초")
        time.sleep(1)


if __name__ == "__main__":
    main()
