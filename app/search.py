import os
import json
from datetime import datetime
from collections import defaultdict
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
        "金額": e.total_amount,
        "住所": e.address or "",
        "電話": e.phone or "",
        "MapsURL": e.maps_url or "",
    }


def _build_aggregates(expenses: list[ExpenseRecord]) -> dict:
    today = datetime.now()
    this_month = [
        e for e in expenses
        if e.used_date.year == today.year and e.used_date.month == today.month
    ]
    last_month_date = today.replace(day=1)
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1
    last_month = [
        e for e in expenses
        if e.used_date.year == prev_year and e.used_date.month == prev_month
    ]

    def summarize(records: list[ExpenseRecord]) -> dict:
        total = sum(e.total_amount for e in records)
        shimizu = sum(e.total_amount for e in records if e.paid_by == "志水")
        girlfriend = sum(e.total_amount for e in records if e.paid_by == "彼女")
        by_category: dict[str, int] = defaultdict(int)
        for e in records:
            key = e.category_major + ("/" + e.category_minor if e.category_minor else "")
            by_category[key] += e.total_amount
        return {
            "合計": total,
            "志水さん支払い": shimizu,
            "彼女さん支払い": girlfriend,
            "カテゴリ別": dict(by_category),
            "件数": len(records),
        }

    return {
        "今月集計": summarize(this_month),
        "先月集計": summarize(last_month),
    }


SEARCH_PROMPT = """あなたは家計管理アシスタントです。
以下の支出履歴と集計データをもとに、ユーザーの質問に日本語で答えてください。

【集計データ】
{aggregates}

【支出履歴（新しい順・最大200件）】
{records}

回答ルール:
- 店舗を探す質問 → 店舗名・利用日・金額・住所・電話・MapsURL を含めて回答（複数なら新しい順に最大3件）
- 集計・合計を聞く質問 → 集計データの数字を使って回答
- 支払い者ごとの金額を聞く質問 → 集計データから志水さん・彼女さん別に回答
- データが該当しない場合のみ「記録が見つかりませんでした」と答える
- 金額はカンマ区切りで円表示（例: 12,300円）
- 余計な前置きは不要、結果だけを返す
"""


def answer_search_query(query: str, expenses: list[ExpenseRecord]) -> str:
    if not expenses:
        return "まだ支出の記録がありません。\nレシートを送って登録してください。"

    aggregates = _build_aggregates(expenses)
    records = [_expense_to_dict(e) for e in expenses]

    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": SEARCH_PROMPT.format(
                    aggregates=json.dumps(aggregates, ensure_ascii=False),
                    records=json.dumps(records, ensure_ascii=False),
                ),
            },
            {"role": "user", "content": query},
        ],
        max_tokens=600,
    )
    return response.choices[0].message.content.strip()
