"""
GA4 用 OAuth2 リフレッシュトークン取得スクリプト。
ローカルで1回だけ実行し、得られたトークンを GitHub Secret に登録する。

使い方:
  python scripts/get_ga4_token.py
"""

import json
import os
import webbrowser
from urllib.parse import urlencode, urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler

CLIENT_ID     = os.environ.get("GA4_OAUTH_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GA4_OAUTH_CLIENT_SECRET", "").strip()
REDIRECT_URI  = "http://localhost:8080"
SCOPE         = "https://www.googleapis.com/auth/analytics.readonly"

if not CLIENT_ID:
    CLIENT_ID = input("GA4_OAUTH_CLIENT_ID を入力: ").strip()
if not CLIENT_SECRET:
    CLIENT_SECRET = input("GA4_OAUTH_CLIENT_SECRET を入力: ").strip()

auth_code_holder = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        code = params.get("code", [None])[0]
        if code:
            auth_code_holder.append(code)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK. This window can be closed.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code received.")

    def log_message(self, *args):
        pass


def main():
    import urllib.request

    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPE,
        "access_type":   "offline",
        "prompt":        "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    print("\nブラウザで認証ページを開きます...")
    webbrowser.open(auth_url)
    print("自動で開かない場合はこの URL をコピーしてください:")
    print(auth_url)

    print("\nローカルサーバーで認証コールバックを待機中...")
    server = HTTPServer(("localhost", 8080), Handler)
    server.handle_request()

    if not auth_code_holder:
        print("認証コードが取得できませんでした。")
        return

    code = auth_code_holder[0]
    print("認証コード取得成功。トークンを交換中...")

    token_data = urlencode({
        "code":          code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=token_data,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    refresh_token = result.get("refresh_token")
    if not refresh_token:
        print(f"リフレッシュトークンが返りませんでした: {result}")
        return

    print("\n" + "=" * 60)
    print("GA4_OAUTH_REFRESH_TOKEN（GitHub Secret に登録してください）:")
    print(refresh_token)
    print("=" * 60)
    print("\nGitHub → Settings → Secrets → New repository secret")
    print("  Name:  GA4_OAUTH_REFRESH_TOKEN")
    print(f"  Value: {refresh_token}")


if __name__ == "__main__":
    main()
