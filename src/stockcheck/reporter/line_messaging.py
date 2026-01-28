import os
from typing import Any, Dict, List

try:
    from linebot.v3.messaging import (
        ApiClient,
        Configuration,
        FlexContainer,
        FlexMessage,
        MessagingApi,
        PushMessageRequest,
        TextMessage,
    )
    LINE_SDK_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - optional dependency at runtime
    ApiClient = None
    Configuration = None
    FlexContainer = None
    FlexMessage = None
    MessagingApi = None
    PushMessageRequest = None
    TextMessage = None
    LINE_SDK_IMPORT_ERROR = str(exc)


def build_flex_contents(message: str) -> Dict[str, Any]:
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "Stock Daily Brief",
                    "weight": "bold",
                    "size": "lg",
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": message[:1000],
                    "wrap": True,
                    "size": "sm",
                }
            ],
        },
    }


def send_line_message(message: str) -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    user_id = os.getenv("LINE_USER_ID", "")
    if not token or not user_id:
        print("LINE credentials not set; skipping LINE Messaging API push.")
        return
    if ApiClient is None or Configuration is None or MessagingApi is None:
        detail = f" ({LINE_SDK_IMPORT_ERROR})" if LINE_SDK_IMPORT_ERROR else ""
        print(f"line-bot-sdk not installed; skipping LINE Messaging API push.{detail}")
        return

    configuration = Configuration(access_token=token)
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        try:
            print(f"準備發送報告給用戶 {user_id}...")
            if os.getenv("LINE_USE_FLEX", "").lower() in {"1", "true", "yes"} and FlexMessage:
                contents = build_flex_contents(message)
                container = FlexContainer.from_json(contents)
                flex_message = FlexMessage(alt_text="股票分析報告已送達", contents=container)
                payload: List[Any] = [flex_message]
            else:
                payload = [TextMessage(text=message)]

            messaging_api.push_message(PushMessageRequest(to=user_id, messages=payload))
            print("✅ 訊息發送成功！")
        except Exception as exc:
            print(f"❌ 訊息發送失敗，錯誤原因: {exc}")
            raise RuntimeError(f"LINE Messaging API failed: {exc}") from exc
