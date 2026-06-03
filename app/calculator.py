from .models import MonthlySummary


def format_amount(amount: int) -> str:
    return f"{amount:,}円"


def format_diff(diff: int) -> str:
    if diff > 0:
        return f"+{diff:,}円"
    elif diff < 0:
        return f"{diff:,}円"
    return "±0円"


def format_current_totals(totals: dict) -> str:
    shimizu = totals["shimizu"]
    girlfriend = totals["girlfriend"]
    total = totals["total"]
    per_person = total // 2

    diff = abs(shimizu - per_person)
    if shimizu > per_person:
        settlement = f"彼女さん\n→\n志水さんへ\n\n{format_amount(diff)}支払い"
    elif girlfriend > per_person:
        settlement = f"志水さん\n→\n彼女さんへ\n\n{format_amount(diff)}支払い"
    else:
        settlement = "精算不要"

    return (
        f"今月累計\n\n"
        f"志水さん支払い\n{format_amount(shimizu)}\n\n"
        f"彼女さん支払い\n{format_amount(girlfriend)}\n\n"
        f"合計\n{format_amount(total)}\n\n"
        f"━━━━━━━━━\n\n"
        f"現在の精算予測\n\n"
        f"{settlement}"
    )


def format_monthly_report(summary: MonthlySummary) -> str:
    diff_str = format_diff(summary.prev_month_diff)
    per_person = summary.total // 2
    settlement_amount = summary.settlement_amount
    direction = summary.settlement_direction

    lines = [
        f"【{summary.year}年{summary.month}月支出レポート】",
        "",
        f"総支出\n{format_amount(summary.total)}",
        f"\n先月比\n{diff_str}",
        "",
        "━━━━━━━━━",
        "",
        "カテゴリ別",
        "",
    ]

    # カテゴリ別
    category_order = [
        "家賃", "食費", "日用品", "趣味娯楽", "交際費",
        "交通費", "衣服", "健康医療", "水道光熱費", "その他"
    ]
    for cat in category_order:
        amt = summary.category_breakdown.get(cat, 0)
        if amt > 0:
            lines.append(f"{cat}\n{format_amount(amt)}")

    lines += [
        "",
        "━━━━━━━━━",
        "",
        "支払い者別",
        "",
        f"志水さん\n{format_amount(summary.shimizu_paid)}",
        "",
        f"彼女さん\n{format_amount(summary.girlfriend_paid)}",
        "",
        "━━━━━━━━━",
        "",
        "折半結果",
        "",
        f"対象額\n{format_amount(summary.total)}",
        "",
        f"1人あたり\n{format_amount(per_person)}",
        "",
        f"{direction}",
        "",
        f"{format_amount(settlement_amount)}支払いで精算完了",
    ]

    return "\n".join(lines)
