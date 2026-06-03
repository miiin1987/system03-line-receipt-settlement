import os
import json
from datetime import datetime, date
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from .models import ExpenseRecord, ItemDetail, MonthlySummary

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_EXPENSES = "支出記録"
SHEET_ITEMS = "商品明細"
EXPENSE_HEADERS = [
    "ID", "登録日時", "利用日", "店舗名", "住所", "電話番号",
    "Google Maps URL", "業種", "支払い者", "合計金額",
    "大カテゴリ", "小カテゴリ", "メモ", "折半対象", "精算済"
]
ITEM_HEADERS = ["支出ID", "商品名", "金額"]


def _get_service():
    json_str = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(json_str)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def _spreadsheet_id() -> str:
    return os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"]


def initialize_sheets():
    service = _get_service()
    sid = _spreadsheet_id()
    sheets_meta = service.spreadsheets().get(spreadsheetId=sid).execute()
    existing = {s["properties"]["title"] for s in sheets_meta["sheets"]}

    requests = []
    for title in [SHEET_EXPENSES, SHEET_ITEMS]:
        if title not in existing:
            requests.append({"addSheet": {"properties": {"title": title}}})

    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sid, body={"requests": requests}
        ).execute()

    # ヘッダー行を書き込む（既存の場合は上書きしない）
    for title, headers in [(SHEET_EXPENSES, EXPENSE_HEADERS), (SHEET_ITEMS, ITEM_HEADERS)]:
        result = service.spreadsheets().values().get(
            spreadsheetId=sid, range=f"{title}!A1:A1"
        ).execute()
        if not result.get("values"):
            service.spreadsheets().values().update(
                spreadsheetId=sid,
                range=f"{title}!A1",
                valueInputOption="RAW",
                body={"values": [headers]},
            ).execute()


def _next_id(service, sid: str) -> str:
    result = service.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{SHEET_EXPENSES}!A:A"
    ).execute()
    rows = result.get("values", [])
    return str(len(rows))  # ヘッダー行含む行数 = 新ID


def save_expense(expense: ExpenseRecord) -> str:
    service = _get_service()
    sid = _spreadsheet_id()
    new_id = _next_id(service, sid)
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    row = [
        new_id,
        now,
        expense.used_date.strftime("%Y/%m/%d"),
        expense.store_name,
        expense.address,
        expense.phone,
        expense.maps_url,
        expense.business_type,
        expense.paid_by,
        expense.total_amount,
        expense.category_major,
        expense.category_minor,
        expense.memo,
        str(expense.is_split_target),
        str(expense.is_settled),
    ]
    service.spreadsheets().values().append(
        spreadsheetId=sid,
        range=f"{SHEET_EXPENSES}!A:O",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()

    if expense.items:
        item_rows = [[new_id, item.name, item.price] for item in expense.items]
        service.spreadsheets().values().append(
            spreadsheetId=sid,
            range=f"{SHEET_ITEMS}!A:C",
            valueInputOption="RAW",
            body={"values": item_rows},
        ).execute()

    return new_id


def get_monthly_expenses(year: int, month: int) -> list[ExpenseRecord]:
    service = _get_service()
    sid = _spreadsheet_id()
    result = service.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{SHEET_EXPENSES}!A:O"
    ).execute()
    rows = result.get("values", [])[1:]  # ヘッダー除外

    prefix = f"{year}/{month:02d}/"
    expenses = []
    for r in rows:
        if len(r) < 15:
            continue
        if not r[2].startswith(prefix):
            continue
        try:
            expenses.append(ExpenseRecord(
                id=r[0],
                used_date=datetime.strptime(r[2], "%Y/%m/%d").date(),
                store_name=r[3],
                address=r[4],
                phone=r[5],
                maps_url=r[6],
                business_type=r[7],
                paid_by=r[8],
                total_amount=int(r[9]),
                category_major=r[10],
                category_minor=r[11],
                memo=r[12],
                is_split_target=r[13] == "True",
                is_settled=r[14] == "True",
            ))
        except Exception:
            continue
    return expenses


def get_monthly_summary(year: int, month: int) -> MonthlySummary:
    expenses = get_monthly_expenses(year, month)
    split_expenses = [e for e in expenses if e.is_split_target]

    total = sum(e.total_amount for e in split_expenses)
    shimizu_paid = sum(e.total_amount for e in split_expenses if e.paid_by == "志水")
    girlfriend_paid = sum(e.total_amount for e in split_expenses if e.paid_by == "彼女")

    category_breakdown: dict[str, int] = {}
    for e in split_expenses:
        key = e.category_major
        category_breakdown[key] = category_breakdown.get(key, 0) + e.total_amount

    # 先月集計
    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    prev_expenses = get_monthly_expenses(prev_year, prev_month)
    prev_total = sum(e.total_amount for e in prev_expenses if e.is_split_target)

    return MonthlySummary(
        year=year,
        month=month,
        total=total,
        shimizu_paid=shimizu_paid,
        girlfriend_paid=girlfriend_paid,
        category_breakdown=category_breakdown,
        prev_month_total=prev_total,
    )


def mark_all_settled(year: int, month: int):
    service = _get_service()
    sid = _spreadsheet_id()
    result = service.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{SHEET_EXPENSES}!A:O"
    ).execute()
    rows = result.get("values", [])

    prefix = f"{year}/{month:02d}/"
    updates = []
    for i, r in enumerate(rows[1:], start=2):
        if len(r) >= 3 and r[2].startswith(prefix) and (len(r) < 15 or r[14] != "True"):
            updates.append({
                "range": f"{SHEET_EXPENSES}!O{i}",
                "values": [["True"]],
            })

    if updates:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=sid,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()


def get_current_month_totals() -> dict:
    today = datetime.now()
    expenses = get_monthly_expenses(today.year, today.month)
    split_expenses = [e for e in expenses if e.is_split_target]
    shimizu = sum(e.total_amount for e in split_expenses if e.paid_by == "志水")
    girlfriend = sum(e.total_amount for e in split_expenses if e.paid_by == "彼女")
    return {
        "shimizu": shimizu,
        "girlfriend": girlfriend,
        "total": shimizu + girlfriend,
    }


def get_all_expenses(limit: int = 200) -> list[ExpenseRecord]:
    service = _get_service()
    sid = _spreadsheet_id()
    result = service.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{SHEET_EXPENSES}!A:O"
    ).execute()
    rows = result.get("values", [])[1:]

    expenses = []
    for r in reversed(rows):  # 新しい順
        if len(r) < 10:
            continue
        try:
            expenses.append(ExpenseRecord(
                id=r[0],
                used_date=datetime.strptime(r[2], "%Y/%m/%d").date(),
                store_name=r[3],
                address=r[4] if len(r) > 4 else "",
                phone=r[5] if len(r) > 5 else "",
                maps_url=r[6] if len(r) > 6 else "",
                business_type=r[7] if len(r) > 7 else "",
                paid_by=r[8] if len(r) > 8 else "",
                total_amount=int(r[9]),
                category_major=r[10] if len(r) > 10 else "",
                category_minor=r[11] if len(r) > 11 else "",
                memo=r[12] if len(r) > 12 else "",
                is_split_target=r[13] == "True" if len(r) > 13 else True,
                is_settled=r[14] == "True" if len(r) > 14 else False,
            ))
        except Exception:
            continue
        if len(expenses) >= limit:
            break
    return expenses


def test_connection():
    service = _get_service()
    result = service.spreadsheets().get(spreadsheetId=_spreadsheet_id()).execute()
    print(f"接続成功: {result['properties']['title']}")
