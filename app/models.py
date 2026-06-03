from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class ItemDetail(BaseModel):
    name: str
    price: int


class ExpenseRecord(BaseModel):
    id: Optional[str] = None
    registered_at: Optional[datetime] = None
    used_date: date
    store_name: str
    address: str = ""
    phone: str = ""
    maps_url: str = ""
    business_type: str = ""
    paid_by: str  # "志水" or "彼女"
    total_amount: int
    category_major: str = ""
    category_minor: str = ""
    memo: str = ""
    is_split_target: bool = True
    is_settled: bool = False
    items: list[ItemDetail] = []


class PendingExpense(BaseModel):
    user_id: str
    expense: ExpenseRecord
    created_at: datetime


class MonthlySummary(BaseModel):
    year: int
    month: int
    total: int
    shimizu_paid: int
    girlfriend_paid: int
    category_breakdown: dict[str, int]
    prev_month_total: int

    @property
    def per_person(self) -> int:
        return self.total // 2

    @property
    def settlement_amount(self) -> int:
        return abs(self.shimizu_paid - self.per_person)

    @property
    def settlement_direction(self) -> str:
        if self.shimizu_paid > self.per_person:
            return "彼女→志水さんへ"
        elif self.girlfriend_paid > self.per_person:
            return "志水さん→彼女さんへ"
        return "精算不要"

    @property
    def prev_month_diff(self) -> int:
        return self.total - self.prev_month_total
