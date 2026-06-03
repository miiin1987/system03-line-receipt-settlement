import os
import re
import logging
from datetime import datetime, date, timedelta
from linebot.v3.messaging import (
    ApiClient, Configuration, MessagingApi,
    ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, MessageAction,
)
from .models import ExpenseRecord, PendingExpense
from .ocr import parse_receipt
from .maps import search_store
from .ai import classify_category
from .sheets import save_expense, get_current_month_totals, get_monthly_summary, get_all_expenses
from .search import answer_search_query
from .calculator import format_current_totals, format_monthly_report

logger = logging.getLogger(__name__)

# in-memory セッション
_pending: dict[str, PendingExpense] = {}
_manual_session: dict[str, dict] = {}   # 手入力Q&Aの状態管理
_edit_session: dict[str, str] = {}      # 修正中のフィールド名

CATEGORIES = [
    "家賃", "食費", "日用品", "趣味娯楽", "交際費",
    "交通費", "衣服", "健康医療", "水道光熱費", "その他",
]

HELP_TEXT = (
    "【使い方】\n\n"
    "■ 登録方法\n"
    "①レシートの写メを送信\n"
    "②「手入力」ボタンから直接打ち込む\n\n"
    "■ 履歴を検索する\n"
    "テキストで自由に質問を送ってください。\n\n"
    "検索例）\n"
    "・先月行ったカラオケどこだっけ？\n"
    "・今月の食費いくら？\n"
    "・最近行ったラーメン屋一覧\n"
    "・先週使った合計金額教えて\n"
    "・〇〇の電話番号は？\n\n"
    "■ ボタンメニュー\n"
    "「今月の集計」→ 今月の支払い状況\n"
    "「今月のレポート」→ 今月の全集計\n"
    "「先月のレポート」→ 先月の全集計\n"
    "「手入力」→ テキストで支出を登録"
)


# ── ユーティリティ ──────────────────────────────────

def _get_api_client() -> MessagingApi:
    config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"].strip())
    return MessagingApi(ApiClient(config))


def _reply(reply_token: str, text: str, quick_reply: QuickReply | None = None):
    api = _get_api_client()
    msg = TextMessage(text=text, quick_reply=quick_reply)
    api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[msg]))


def _cancel_qr() -> QuickReply:
    return QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="キャンセル", text="キャンセル")),
    ])


def _parse_date(text: str) -> date | None:
    today = date.today()
    if text in ("今日", "本日"):
        return today
    if text == "昨日":
        return today - timedelta(days=1)
    # 6/2 または 6月2日
    m = re.match(r'^(\d{1,2})[/月](\d{1,2})日?$', text)
    if m:
        try:
            return date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    # YYYY/MM/DD
    m = re.match(r'^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})$', text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _parse_amount(text: str) -> int | None:
    cleaned = re.sub(r'[,，円\s]', '', text)
    return int(cleaned) if cleaned.isdigit() else None


# ── 手入力Q&Aフロー ────────────────────────────────

def _start_manual_entry(reply_token: str, user_id: str):
    _manual_session[user_id] = {"step": "store"}
    _reply(
        reply_token,
        "手入力を開始します。\n\nSTEP 1/4　店舗名を入力してください。",
        quick_reply=_cancel_qr(),
    )


def _handle_manual_step(reply_token: str, user_id: str, text: str):
    if text == "キャンセル":
        _manual_session.pop(user_id, None)
        _reply(reply_token, "手入力をキャンセルしました。")
        return

    session = _manual_session[user_id]
    step = session["step"]

    if step == "store":
        session["store_name"] = text
        session["step"] = "date"
        qr = QuickReply(items=[
            QuickReplyItem(action=MessageAction(label="今日", text="今日")),
            QuickReplyItem(action=MessageAction(label="昨日", text="昨日")),
            QuickReplyItem(action=MessageAction(label="キャンセル", text="キャンセル")),
        ])
        _reply(reply_token, "STEP 2/4　日付を教えてください。\n例）今日、昨日、6/2", quick_reply=qr)

    elif step == "date":
        used_date = _parse_date(text)
        if not used_date:
            _reply(reply_token, "日付の形式が正しくありません。\n例）今日、昨日、6/2", quick_reply=_cancel_qr())
            return
        session["used_date"] = used_date
        session["step"] = "amount"
        _reply(reply_token, "STEP 3/4　金額を入力してください。\n例）4800", quick_reply=_cancel_qr())

    elif step == "amount":
        amount = _parse_amount(text)
        if not amount:
            _reply(reply_token, "金額は数字で入力してください。\n例）4800", quick_reply=_cancel_qr())
            return
        session["total_amount"] = amount
        session["step"] = "category"
        qr = QuickReply(items=[
            QuickReplyItem(action=MessageAction(label=cat, text=cat))
            for cat in CATEGORIES
        ] + [QuickReplyItem(action=MessageAction(label="キャンセル", text="キャンセル"))])
        _reply(reply_token, "STEP 4/4　カテゴリを選んでください。", quick_reply=qr)

    elif step == "category":
        if text not in CATEGORIES:
            qr = QuickReply(items=[
                QuickReplyItem(action=MessageAction(label=cat, text=cat))
                for cat in CATEGORIES
            ] + [QuickReplyItem(action=MessageAction(label="キャンセル", text="キャンセル"))])
            _reply(reply_token, "ボタンからカテゴリを選んでください。", quick_reply=qr)
            return
        session["category_major"] = text
        if text == "食費":
            session["step"] = "subcategory"
            qr = QuickReply(items=[
                QuickReplyItem(action=MessageAction(label="外食", text="外食")),
                QuickReplyItem(action=MessageAction(label="自炊", text="自炊")),
                QuickReplyItem(action=MessageAction(label="キャンセル", text="キャンセル")),
            ])
            _reply(reply_token, "食費の内訳を選んでください。", quick_reply=qr)
        else:
            session["category_minor"] = ""
            _finish_manual_entry(reply_token, user_id, session)

    elif step == "subcategory":
        session["category_minor"] = text if text in ("外食", "自炊") else ""
        _finish_manual_entry(reply_token, user_id, session)


def _finish_manual_entry(reply_token: str, user_id: str, session: dict):
    _manual_session.pop(user_id, None)
    store_name = session["store_name"]
    store_info = search_store(store_name)

    expense = ExpenseRecord(
        used_date=session["used_date"],
        store_name=store_info.get("store_name") or store_name,
        address=store_info.get("address", ""),
        phone=store_info.get("phone", ""),
        maps_url=store_info.get("maps_url", ""),
        business_type=store_info.get("business_type", ""),
        paid_by="",
        total_amount=session["total_amount"],
        category_major=session["category_major"],
        category_minor=session.get("category_minor", ""),
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


# ── 確認メッセージ ──────────────────────────────────

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


def _show_edit_menu(reply_token: str, user_id: str):
    """確認画面から「修正」を押したときに修正項目を選ばせる"""
    qr = QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="日付を変更", text="日付を変更")),
        QuickReplyItem(action=MessageAction(label="金額を変更", text="金額を変更")),
        QuickReplyItem(action=MessageAction(label="カテゴリを変更", text="カテゴリを変更")),
        QuickReplyItem(action=MessageAction(label="登録をキャンセル", text="登録をキャンセル")),
    ])
    _reply(reply_token, "どの項目を修正しますか？", quick_reply=qr)


def _handle_edit_step(reply_token: str, user_id: str, text: str):
    """修正フィールドの入力を処理する"""
    field = _edit_session.get(user_id)

    # 修正項目の選択
    if text == "日付を変更":
        _edit_session[user_id] = "date"
        qr = QuickReply(items=[
            QuickReplyItem(action=MessageAction(label="今日", text="今日")),
            QuickReplyItem(action=MessageAction(label="昨日", text="昨日")),
            QuickReplyItem(action=MessageAction(label="キャンセル", text="キャンセル")),
        ])
        _reply(reply_token, "新しい日付を入力してください。\n例）今日、昨日、6/2", quick_reply=qr)
        return

    if text == "金額を変更":
        _edit_session[user_id] = "amount"
        _reply(reply_token, "新しい金額を入力してください。\n例）4800", quick_reply=_cancel_qr())
        return

    if text == "カテゴリを変更":
        _edit_session[user_id] = "category"
        qr = QuickReply(items=[
            QuickReplyItem(action=MessageAction(label=cat, text=cat))
            for cat in CATEGORIES
        ] + [QuickReplyItem(action=MessageAction(label="キャンセル", text="キャンセル"))])
        _reply(reply_token, "新しいカテゴリを選んでください。", quick_reply=qr)
        return

    if text == "登録をキャンセル":
        _pending.pop(user_id, None)
        _edit_session.pop(user_id, None)
        _reply(reply_token, "登録をキャンセルしました。")
        return

    if text == "キャンセル":
        _edit_session.pop(user_id, None)
        # pendingが残っていれば確認画面に戻す
        pending = _pending.get(user_id)
        if pending:
            qr = QuickReply(items=[
                QuickReplyItem(action=MessageAction(label="志水さん", text="志水さん")),
                QuickReplyItem(action=MessageAction(label="彼女さん", text="彼女さん")),
                QuickReplyItem(action=MessageAction(label="修正", text="修正")),
            ])
            _reply(reply_token, _format_confirmation(pending.expense), quick_reply=qr)
        else:
            _reply(reply_token, "修正をキャンセルしました。")
        return

    # 値の入力処理
    pending = _pending.get(user_id)
    if not pending or not field:
        _edit_session.pop(user_id, None)
        return

    if field == "date":
        new_date = _parse_date(text)
        if not new_date:
            _reply(reply_token, "日付の形式が正しくありません。\n例）今日、昨日、6/2", quick_reply=_cancel_qr())
            return
        pending.expense.used_date = new_date
        _edit_session.pop(user_id, None)

    elif field == "amount":
        new_amount = _parse_amount(text)
        if not new_amount:
            _reply(reply_token, "金額は数字で入力してください。\n例）4800", quick_reply=_cancel_qr())
            return
        pending.expense.total_amount = new_amount
        _edit_session.pop(user_id, None)

    elif field == "category":
        if text not in CATEGORIES:
            qr = QuickReply(items=[
                QuickReplyItem(action=MessageAction(label=cat, text=cat))
                for cat in CATEGORIES
            ] + [QuickReplyItem(action=MessageAction(label="キャンセル", text="キャンセル"))])
            _reply(reply_token, "ボタンからカテゴリを選んでください。", quick_reply=qr)
            return
        pending.expense.category_major = text
        if text == "食費":
            _edit_session[user_id] = "subcategory"
            qr = QuickReply(items=[
                QuickReplyItem(action=MessageAction(label="外食", text="外食")),
                QuickReplyItem(action=MessageAction(label="自炊", text="自炊")),
                QuickReplyItem(action=MessageAction(label="キャンセル", text="キャンセル")),
            ])
            _reply(reply_token, "食費の内訳を選んでください。", quick_reply=qr)
            return
        pending.expense.category_minor = ""
        _edit_session.pop(user_id, None)

    elif field == "subcategory":
        pending.expense.category_minor = text if text in ("外食", "自炊") else ""
        _edit_session.pop(user_id, None)

    # 修正完了 → 確認画面に戻す
    qr = QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="志水さん", text="志水さん")),
        QuickReplyItem(action=MessageAction(label="彼女さん", text="彼女さん")),
        QuickReplyItem(action=MessageAction(label="修正", text="修正")),
    ])
    _reply(reply_token, "修正しました。\n\n" + _format_confirmation(pending.expense), quick_reply=qr)


def _save_with_payer(reply_token: str, user_id: str, paid_by: str):
    pending = _pending.pop(user_id, None)
    if pending is None:
        _reply(reply_token, "確認待ちの登録内容がありません。\nレシートを送るか「手入力」を使ってください。")
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


# ── メインハンドラー ────────────────────────────────

def handle_image(reply_token: str, user_id: str, image_url: str):
    _manual_session.pop(user_id, None)  # 手入力中の場合はリセット
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
    category = classify_category(store_name, store_info.get("business_type", ""), item_names)

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

    _pending[user_id] = PendingExpense(user_id=user_id, expense=expense, created_at=datetime.now())
    qr = QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="志水さん", text="志水さん")),
        QuickReplyItem(action=MessageAction(label="彼女さん", text="彼女さん")),
        QuickReplyItem(action=MessageAction(label="修正", text="修正")),
    ])
    _reply(reply_token, _format_confirmation(expense), quick_reply=qr)


def handle_text(reply_token: str, user_id: str, text: str):
    text = text.strip()

    # 手入力Q&Aセッション中はすべてここで処理
    if user_id in _manual_session:
        _handle_manual_step(reply_token, user_id, text)
        return

    # 修正フロー中はすべてここで処理
    if user_id in _edit_session or text in ("日付を変更", "金額を変更", "カテゴリを変更", "登録をキャンセル"):
        _handle_edit_step(reply_token, user_id, text)
        return

    if text == "志水さん":
        _save_with_payer(reply_token, user_id, "志水")
        return

    if text == "彼女さん":
        _save_with_payer(reply_token, user_id, "彼女")
        return

    if text == "修正":
        if user_id in _pending:
            _show_edit_menu(reply_token, user_id)
        else:
            _reply(reply_token, "確認待ちの登録内容がありません。\nレシートを送るか「手入力」を使ってください。")
        return

    if text == "手入力":
        _start_manual_entry(reply_token, user_id)
        return

    if text == "使い方":
        _reply(reply_token, HELP_TEXT)
        return

    if text == "集計確認":
        try:
            totals = get_current_month_totals()
            _reply(reply_token, "【今月の状況】\n\n" + format_current_totals(totals))
        except Exception as e:
            logger.error(f"Totals error: {e}")
            _reply(reply_token, "集計の取得に失敗しました。")
        return

    if text == "月次レポート":
        today = datetime.now()
        try:
            summary = get_monthly_summary(today.year, today.month)
            _reply(reply_token, format_monthly_report(summary))
        except Exception as e:
            logger.error(f"Monthly report error: {e}")
            _reply(reply_token, "レポートの生成に失敗しました。")
        return

    if text == "前月集計":
        today = datetime.now()
        prev_year, prev_month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        try:
            summary = get_monthly_summary(prev_year, prev_month)
            _reply(reply_token, f"【{prev_year}年{prev_month}月の集計】\n\n" + format_monthly_report(summary))
        except Exception as e:
            logger.error(f"Prev month report error: {e}")
            _reply(reply_token, "前月集計の取得に失敗しました。")
        return

    # コマンド以外はすべて検索
    try:
        expenses = get_all_expenses()
        answer = answer_search_query(text, expenses)
    except Exception as e:
        logger.error(f"Search error: {e}")
        answer = HELP_TEXT
    _reply(reply_token, answer)
