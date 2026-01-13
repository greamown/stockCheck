import base64
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler


def verify_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    mac = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature)


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        signature = self.headers.get("X-Line-Signature", "")
        channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")

        if channel_secret and signature:
            if not verify_signature(body, signature, channel_secret):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"message":"Invalid signature"}')
                return

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}

        user_ids = []
        for event in payload.get("events", []):
            source = event.get("source", {})
            user_id = source.get("userId")
            if user_id:
                user_ids.append(user_id)

        if user_ids:
            print(f"LINE webhook userIds: {', '.join(user_ids)}")
        else:
            print("LINE webhook received, but no userId found.")

        response_body = json.dumps({"status": "ok", "userIds": user_ids}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(response_body)
