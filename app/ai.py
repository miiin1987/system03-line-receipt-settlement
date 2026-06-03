import os
import json
from openai import OpenAI

_client: OpenAI | None = None

MAJOR_CATEGORIES = [
    "家賃", "食費", "日用品", "趣味娯楽", "交際費",
    "交通費", "衣服", "健康医療", "水道光熱費", "その他"
]
MINOR_CATEGORIES = {
    "食費": ["自炊", "外食"],
}

CATEGORY_PROMPT = """
以下の支出情報から最適な大カテゴリと小カテゴリを判定してください。
必ずJSONフォーマットで返してください。

大カテゴリの選択肢: {major}

小カテゴリは食費の場合のみ「自炊」または「外食」を設定してください。
それ以外は空文字列にしてください。

支出情報:
店舗名: {store_name}
業種: {business_type}
商品リスト: {items}

出力形式:
{{"category_major": "大カテゴリ", "category_minor": "小カテゴリ"}}
"""


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def classify_category(store_name: str, business_type: str, items: list[str]) -> dict:
    client = _get_client()
    prompt = CATEGORY_PROMPT.format(
        major="、".join(MAJOR_CATEGORIES),
        store_name=store_name,
        business_type=business_type,
        items="、".join(items) if items else "情報なし",
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=100,
        )
        data = json.loads(response.choices[0].message.content)
        major = data.get("category_major", "その他")
        minor = data.get("category_minor", "")
        if major not in MAJOR_CATEGORIES:
            major = "その他"
        return {"category_major": major, "category_minor": minor}
    except Exception:
        return {"category_major": "その他", "category_minor": ""}
