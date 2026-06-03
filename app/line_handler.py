import os
import logging
from datetime import datetime
from linebot.v3.messaging import (
    ApiClient, Configuration, MessagingApi,
    ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, MessageAction,
)
from .models import ExpenseRecord, PendingExpense
from .ocr import parse_receipt
from .maps import search_store
from .ai import classify_category
from .sheets import save_expense, get_current_month_totals, get_monthly_summary, mark_all_settled, get_all_expenses
from .search import answer_search_query
from .calculator import format_current_totals, format_monthly_report

logger = logging.getLogger(__name__)

# in-memory: user_id → PendingExpense
_pending: dict[str, PendingExpense] = {}

HELP_TEXT = (
    "使い方\n\n"
    "【レシート登録】\n"
    "レシートの写真を送ってください\n\n"
    "【コマンド一覧】\n"
    "「月次レポート」→ 今月の集計\n"
    "「精算完了」→ 今月を精算済みにする\n"
    "「集計確認」→ 今月の現在状況"
)


def _get_api_client() -> MessagingApi:
    config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"].strip())
    return MessagingApi(ApiClient(config))


def _format_confirmation(expense: ExpenseRecord) -> str:
    items_text = "\n".join(
        f"{item.name}　{item.price:,}円" for item in expense.items
    ) or "（商品情報なし）"

    address = expense.address or "情報なし"
    phone = expense.phone or "情報なし"
    maps = expense.maps_url or "情報なし"

    return (
        f"登録内容を確認してください。\n\n"
        f"日付：{expense.used_date.strftime('%Y/%m/%d')}\n\n"
        f"店舗：{expense.store_name}\n\n"
        f"住所：\n{address}\n\n"
        f"電話：\n{phone}\n\n"
        f"Maps：\n{maps}\n\n"
        f"カテゴリ：\n{expense.category_major}"
        + (f"（{expense.category_minor}）" if expense.category_minor else "")
        + f"\n\n金額：\n{expense.total_amount:,}円\n\n"
        f"内容：\n{items_text}\n\n"
        f"支払い者を選んで登録してください。"
    )


def _reply(reply_token: str, text: str, quick_reply: QuickReply | None = None):
    api = _get_api_client()
    msg = TextMessage(text=text, quick_reply=quick_reply)
    api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[msg]))


def _save_with_payer(reply_token: str, user_id: str, paid_by: str):
    pending = _pending.pop(user_id, None)
    if pending is None:
        _reply(reply_token, "確認待ちの登録内容がありません。\nまずレシートを送ってください。")
        return
    pending.expense.paid_by = paid_by
    try:
        save_expense(pending.expense)
    except Exception as e:
        logger.error(f"Sheets save error: {e}")
        _reply(reply_token, "保存中にエラーが発生しました。もう一度お試しください。")
        return
    totals = get_current_month_totals()
    _reply(reply_token, "登録しました。\n\n" + format_current_totals(totals))


def handle_image(reply_token: str, user_id: str, image_url: str):
    access_token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"].strip()
    try:
        ocr_result = parse_receipt(image_url, access_token)
    except Exception as e:
        logger.error(f"OCR error: {e}")
        _reply(reply_token, "レシートの読み取りに失敗しました。もう一度送ってみてください。")
        return

    store_name = ocr_result["store_name"]
    store_info = search_store(store_name)

    item_names = [item.name for item in ocr_result["items"]]
    category = classify_category(
        store_name,
        store_info.get("business_type", ""),
        item_names,
    )

    expense = ExpenseRecord(
        used_date=ocr_result["used_date"],
        store_name=store_info.get("store_name") or store_name,
        address=store_info.get("address", ""),
        phone=store_info.get("phone", ""),
        maps_url=store_info.get("maps_url", ""),
        business_type=store_info.get("business_type", ""),
        paid_by="",
        total_amount=ocr_result["total_amount"],
        category_major=category["category_major"],
        category_minor=category["category_minor"],
        items=ocr_result["items"],
    )

    _pending[user_id] = PendingExpense(
        user_id=user_id, expense=expense, created_at=datetime.now()
    )

    qr = QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="志水さん", text="志水さん")),
        QuickReplyItem(action=MessageAction(label="彼女さん", text="彼女さん")),
        QuickReplyItem(action=MessageAction(label="修正", text="修正")),
    ])
    _reply(reply_token, _format_confirmation(expense), quick_reply=qr)


def handle_text(reply_token: str, user_id: str, text: str):
    text = text.strip()

    if text == "志水さん":
        _save_with_payer(reply_token, user_id, "志水")
        return

    if text == "彼女さん":
        _save_with_payer(reply_token, user_id, "彼女")
        return

    if text == "修正":
        _pending.pop(user_id, None)
        _reply(reply_token, "キャンセルしました。\nもう一度レシートを送ってください。")
        return

    if text == "月次レポート":
        today = datetime.now()
        try:
            summary = get_monthly_summary(today.year, today.month)
            report = format_monthly_report(summary)
        except Exception as e:
            logger.error(f"Monthly report error: {e}")
            _reply(reply_token, "レポートの生成に失敗しました。")
            return
        _reply(reply_token, report)
        return

    if text == "精算完了":
        today = datetime.now()
        try:
            mark_all_settled(today.year, today.month)
        except Exception as e:
            logger.error(f"Mark settled error: {e}")
            _reply(reply_token, "精算処理に失敗しました。")
            return
        _reply(reply_token, f"{today.year}年{today.month}月の支出を精算済みにしました。")
        return

    if text == "集計確認":
        try:
            totals = get_current_month_totals()
            msg = "【今月の状況】\n\n" + format_current_totals(totals)
        except Exception as e:
            logger.error(f"Totals error: {e}")
            _reply(reply_token, "集計の取得に失敗しました。")
            return
        _reply(reply_token, msg)
        return

    # コマンド以外はすべて検索クエリとして処理
    try:
        expenses = get_all_expenses()
        answer = answer_search_query(text, expenses)
    except Exception as e:
        logger.error(f"Search error: {e}")
        answer = HELP_TEXT
    _reply(reply_token, answer)
