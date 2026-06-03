"""
リッチメニューを LINE に登録するセットアップスクリプト。
一度だけ実行してください。

実行方法:
    python setup_richmenu.py
"""

import os
import json
import requests
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"].strip()
HEADERS_JSON = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

MENU_W = 2500
MENU_H = 843

W2 = MENU_W // 2  # 1250
H1 = MENU_H // 2  # 421
H2 = MENU_H - H1  # 422

BG_COLOR  = "#0F172A"  # ダークネイビー背景
PAD       = 14         # ボタン外縁の余白
RADIUS    = 28         # 丸角半径

# (x, y, w, h, タイトル, サブテキスト, 送信テキスト, ボタン色)
BUTTONS = [
    (0,  0,  W2, H1, "今月の集計",    "支払い状況を確認", "集計確認",    "#2563EB"),
    (W2, 0,  W2, H1, "今月のレポート", "全カテゴリ表示",  "月次レポート", "#7C3AED"),
    (0,  H1, W2, H2, "先月のレポート", "先月の支出まとめ", "前月集計",    "#0D9488"),
    (W2, H1, W2, H2, "手入力",        "テキストで登録",   "手入力",      "#DC2626"),
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\YuGothB.ttc",
        r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
        r"C:\Windows\Fonts\YuGothM.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _lighten(color: str, factor: float = 0.25) -> str:
    r, g, b = _hex_to_rgb(color)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def create_image(path: str = "richmenu.png"):
    img = Image.new("RGB", (MENU_W, MENU_H), BG_COLOR)
    draw = ImageDraw.Draw(img)
    font_title = _load_font(130)
    font_sub   = _load_font(58)

    for x, y, w, h, title, subtitle, _, color in BUTTONS:
        bx0, by0 = x + PAD, y + PAD
        bx1, by1 = x + w - PAD, y + h - PAD

        # ボタン本体（丸角）
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=RADIUS, fill=color)

        # 上部ハイライト（明るいストライプで立体感）
        hl_h = (by1 - by0) // 3
        draw.rounded_rectangle(
            [bx0, by0, bx1, by0 + hl_h],
            radius=RADIUS,
            fill=_lighten(color, 0.20),
        )

        # テキスト垂直中央揃え（タイトル＋サブ）
        tb = draw.textbbox((0, 0), title, font=font_title)
        sb = draw.textbbox((0, 0), subtitle, font=font_sub)
        th, sh = tb[3] - tb[1], sb[3] - sb[1]
        gap = 20
        total_h = th + gap + sh
        cx = (bx0 + bx1) // 2
        ty = (by0 + by1) // 2 - total_h // 2

        # タイトル
        draw.text(
            (cx - (tb[2] - tb[0]) // 2, ty),
            title, fill="white", font=font_title,
        )
        # サブテキスト
        draw.text(
            (cx - (sb[2] - sb[0]) // 2, ty + th + gap),
            subtitle, fill="#CBD5E1", font=font_sub,
        )

    img.save(path)
    print(f"画像を作成しました: {path}")
    return path


def create_richmenu() -> str:
    menu = {
        "size": {"width": MENU_W, "height": MENU_H},
        "selected": True,
        "name": "家計管理メニュー",
        "chatBarText": "メニュー",
        "areas": [
            {
                "bounds": {"x": x, "y": y, "width": w, "height": h},
                "action": {"type": "message", "label": title, "text": text},
            }
            for x, y, w, h, title, subtitle, text, _ in BUTTONS
        ],
    }
    resp = requests.post(
        "https://api.line.me/v2/bot/richmenu",
        headers=HEADERS_JSON,
        json=menu,
    )
    resp.raise_for_status()
    rich_menu_id = resp.json()["richMenuId"]
    print(f"リッチメニュー作成: {rich_menu_id}")
    return rich_menu_id


def upload_image(rich_menu_id: str, image_path: str):
    with open(image_path, "rb") as f:
        resp = requests.post(
            f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
            headers={
                "Authorization": f"Bearer {ACCESS_TOKEN}",
                "Content-Type": "image/png",
            },
            data=f,
        )
    resp.raise_for_status()
    print("画像をアップロードしました")


def set_default(rich_menu_id: str):
    # 全ユーザーにリッチメニューを紐付ける
    resp = requests.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
    )
    resp.raise_for_status()
    print("デフォルトメニューに設定しました")


def delete_existing_menus():
    resp = requests.get(
        "https://api.line.me/v2/bot/richmenu/list",
        headers=HEADERS_JSON,
    )
    resp.raise_for_status()
    menus = resp.json().get("richmenus", [])
    for m in menus:
        mid = m["richMenuId"]
        requests.delete(
            f"https://api.line.me/v2/bot/richmenu/{mid}",
            headers=HEADERS_JSON,
        )
        print(f"既存メニューを削除: {mid}")


if __name__ == "__main__":
    print("=== リッチメニューセットアップ ===")
    delete_existing_menus()
    image_path = create_image()
    rich_menu_id = create_richmenu()
    upload_image(rich_menu_id, image_path)
    set_default(rich_menu_id)
    print("\n完了！LINEアプリを再起動するとメニューが表示されます。")
