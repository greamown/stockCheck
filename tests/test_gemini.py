import io
import os
import sys

from dotenv import load_dotenv

from google import genai


def main() -> None:
    load_dotenv()
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    api_key = os.getenv("GEMINI_API_KEY") or "你的_API_KEY"
    try:
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        prompt = os.getenv("GEMINI_TEST_PROMPT", "Hello, this is a test. Reply with 'OK'.")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        print("--- Gemini 測試結果 ---")
        print(f"AI 回覆: {getattr(response, 'text', '')}")
        print("狀態: ✅ 連線成功")
    except Exception as exc:
        print("--- Gemini 測試失敗 ---")
        print(f"錯誤訊息: {exc}")


if __name__ == "__main__":
    main()
