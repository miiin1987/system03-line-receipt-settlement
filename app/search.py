import os
import json
from openai import OpenAI
from .models import ExpenseRecord

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _expense_to_dict(e: ExpenseRecord) -> dict:
    return {
        "利用日": e.used_date.strftime("%Y/%m/%d"),
        "店舗名": e.store_name,
        "カテゴリ": f"{e.category_major}{'/' + e.category_minor if e.category_minor else ''}",
        "支払い者": e.paid_by,
        "金額": f"{e.total_amount:,}円",
        "住所": e.address or "情報なし",
        "電話": e.phone or "情報なし",
        "MapsURL": e.maps_url or "",
    }


SEARCH_PROMPT = """あなたは家計管理アシスタントです。
以下の支出履歴データをもとに、ユーザーの質問に日本語で答えてください。

支出履歴（新しい順・最大200件）:
{data}

ルール:
- 関連する店舗・支出が見つかれば、店舗名・利用日・金額・住所・電話・MapsURL を含めて回答する
- 複数ヒットした場合は新しい順に最大3件まで表示する
- MapsURLがある場合は必ず記載する
- 見つからない場合は「記録が見つかりませんでした」と答える
- 余計な前置きは不要、結果だけを返す
"""


def answer_search_query(query: str, expenses: list[ExpenseRecord]) -> str:
    if not expenses:
        return "まだ支出の記録がありません。\nレシートを送って登録してください。"

    data = json.dumps(
        [_expense_to_dict(e) for e in expenses],
        ensure_ascii=False,
        indent=None,
    )

    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SEARCH_PROMPT.format(data=data)},
            {"role": "user", "content": query},
        ],
        max_tokens=500,
    )
    return response.choices[0].message.content.strip()
