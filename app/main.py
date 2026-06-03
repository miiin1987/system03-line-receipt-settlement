import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    MessageEvent, ImageMessageContent, TextMessageContent,
)
from dotenv import load_dotenv
from .sheets import initialize_sheets
from .line_handler import handle_image, handle_text
from datetime import datetime

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        initialize_sheets()
        logger.info("Google Sheets initialized")
    except Exception as e:
        logger.warning(f"Sheets init failed (proceeding anyway): {e}")
    yield


app = FastAPI(title="LINE家計管理Bot", lifespan=lifespan)


def _get_parser() -> WebhookParser:
    return WebhookParser(os.environ["LINE_CHANNEL_SECRET"].strip())


@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(None),
):
    body = await request.body()
    body_text = body.decode("utf-8")

    parser = _get_parser()
    try:
        events = parser.parse(body_text, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue

        reply_token = event.reply_token
        user_id = event.source.user_id

        if isinstance(event.message, ImageMessageContent):
            image_url = f"https://api-data.line.me/v2/bot/message/{event.message.id}/content"
            handle_image(reply_token, user_id, image_url)

        elif isinstance(event.message, TextMessageContent):
            handle_text(reply_token, user_id, event.message.text)

    return {"status": "ok"}


@app.post("/cron/monthly-report")
async def cron_monthly_report(
    request: Request,
    x_cron_secret: str = Header(None),
):
    expected = os.environ.get("CRON_SECRET", "")
    if expected and x_cron_secret != expected:
        raise HTTPException(status_code=403, detail="Forbidden")

    today = datetime.now()
    # 月末日のみ実行（28〜31日のcronで起動するため最終日チェック）
    import calendar
    last_day = calendar.monthrange(today.year, today.month)[1]
    if today.day != last_day:
        return {"status": "skipped", "reason": "not last day of month"}

    from .sheets import get_monthly_summary, mark_all_settled
    from .calculator import format_monthly_report
    from linebot.v3.messaging import (
        ApiClient, Configuration, MessagingApi,
        BroadcastRequest, TextMessage,
    )

    summary = get_monthly_summary(today.year, today.month)
    report = format_monthly_report(summary)

    # 月次レポートを送信してから精算済みにマーク
    config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"].strip())
    api = MessagingApi(ApiClient(config))
    api.broadcast(BroadcastRequest(messages=[TextMessage(text=report)]))
    mark_all_settled(today.year, today.month)

    return {"status": "sent"}


@app.get("/health")
async def health():
    return {"status": "ok"}
