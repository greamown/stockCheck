import os

from dotenv import load_dotenv

from linebot.v3.messaging import ApiClient, Configuration, MessagingApi, PushMessageRequest, TextMessage


def test_line() -> None:
    load_dotenv()
    access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "你的_TOKEN"
    user_id = os.getenv("LINE_USER_ID") or "你的_USER_ID"
    message = os.getenv("LINE_TEST_MESSAGE", "LINE API 測試成功！")

    configuration = Configuration(access_token=access_token)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        push_message_request = PushMessageRequest(
            to=user_id,
            messages=[TextMessage(text=message)],
        )
        try:
            line_bot_api.push_message(push_message_request)
            print("--- LINE 測試結果 ---")
            print("✅ 訊息已送出，請檢查手機 LINE")
        except Exception as exc:
            print("--- LINE 測試失敗 ---")
            print(f"錯誤訊息: {exc}")
            if isinstance(exc, UnicodeEncodeError):
                print("提示: 可先設 LINE_TEST_MESSAGE=LINE API test success! 以排除字元編碼問題")


if __name__ == "__main__":
    test_line()
