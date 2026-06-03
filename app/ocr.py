import os
import json
import base64
import httpx
from openai import OpenAI
from datetime import date
from .models import ExpenseRecord, ItemDetail

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _download_image_as_base64(url: str, access_token: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = httpx.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return base64.b64encode(response.content).decode("utf-8")


RECEIPT_PROMPT = """
あなたはレシートを読み取るOCRアシスタントです。
画像からレシート情報を抽出し、必ず以下のJSONフォーマットで返してください。
情報が読み取れない場合はnullを使用してください。

{
  "used_date": "YYYY-MM-DD",
  "store_name": "店舗名",
  "total_amount": 数値（円、税込）,
  "items": [
    {"name": "商品名", "price": 数値},
    ...
  ]
}

注意事項:
- 日付は必ずYYYY-MM-DD形式
- 金額は税込の最終合計金額
- 商品リストは実際に記載されているもののみ
- 金額はすべて整数（円）
"""


def parse_receipt(image_url: str, line_access_token: str) -> dict:
    b64 = _download_image_as_base64(image_url, line_access_token)
    client = _get_client()

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": RECEIPT_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
        response_format={"type": "json_object"},
        max_tokens=1000,
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    used_date = date.today()
    if data.get("used_date"):
        try:
            from datetime import datetime
            used_date = datetime.strptime(data["used_date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    items = [
        ItemDetail(name=item["name"], price=int(item.get("price", 0)))
        for item in data.get("items", [])
        if item.get("name")
    ]

    return {
        "used_date": used_date,
        "store_name": data.get("store_name") or "不明",
        "total_amount": int(data.get("total_amount") or 0),
        "items": items,
    }
