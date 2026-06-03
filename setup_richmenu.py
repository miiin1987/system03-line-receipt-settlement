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

BUTTONS = [
    (0,          0,          MENU_W // 2, MENU_H // 2, "集計確認",    "集計確認",    "#16213e", "#0f3460"),
    (MENU_W // 2, 0,         MENU_W // 2, MENU_H // 2, "月次レポート", "月次レポート", "#16213e", "#533483"),
    (0,          MENU_H // 2, MENU_W // 2, MENU_H // 2, "精算完了",   "精算完了",    "#16213e", "#e94560"),
    (MENU_W // 2, MENU_H // 2, MENU_W // 2, MENU_H // 2, "使い方",   "使い方",      "#16213e", "#0f3460"),
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
        r"C:\Windows\Fonts\YuGothM.ttc",
        r"C:\Windows\Fonts\yugothic.ttf",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def create_image(path: str = "richmenu.png"):
    img = Image.new("RGB", (MENU_W, MENU_H), "#1a1a2e")
    draw = ImageDraw.Draw(img)
    font = _load_font(160)

    for x, y, w, h, label, _, bg, accent in BUTTONS:
        # セル背景
        draw.rectangle([x + 4, y + 4, x + w - 4, y + h - 4], fill=bg)
        # アクセントバー（上部）
        draw.rectangle([x + 4, y + 4, x + w - 4, y + 18], fill=accent)

        # テキスト中央配置
        cx, cy = x + w // 2, y + h // 2
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((cx - tw // 2, cy - th // 2), label, fill="white", font=font)

    # グリッド線
    draw.line([(MENU_W // 2, 0), (MENU_W // 2, MENU_H)], fill="#2a2a4a", width=6)
    draw.line([(0, MENU_H // 2), (MENU_W, MENU_H // 2)], fill="#2a2a4a", width=6)

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
                "action": {"type": "message", "label": label, "text": text},
            }
            for x, y, w, h, label, text, _, __ in BUTTONS
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
