"""Search Console API の認証と取得を、失敗を隠さずに行う共通処理。

認証は次のどちらか一方だけを使う（GA4 用の認証情報には切り替えない）:
  1. GSC_SERVICE_ACCOUNT_KEY  サービスアカウント JSON
  2. GSC_OAUTH_CLIENT_ID + GSC_OAUTH_CLIENT_SECRET + GSC_OAUTH_REFRESH_TOKEN
     （3項目は同じ OAuth クライアントで発行した組であること）

OAuth の3項目が一部だけ設定されている場合は、足りない設定名を示して停止する。
クライアント ID と更新トークンを別のクライアントの組み合わせで使うと
Google の認証が unauthorized_client で拒否されるため、項目ごとの切り替えはしない。

取得の失敗は GscError として呼び出し元に伝える。失敗を 0 件の結果として返さない。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
OAUTH_ENV_NAMES = ("GSC_OAUTH_CLIENT_ID", "GSC_OAUTH_CLIENT_SECRET", "GSC_OAUTH_REFRESH_TOKEN")
SERVICE_ACCOUNT_ENV_NAME = "GSC_SERVICE_ACCOUNT_KEY"
SECRET_ENV_NAMES = (
    SERVICE_ACCOUNT_ENV_NAME,
    *OAUTH_ENV_NAMES,
    "GA4_SERVICE_ACCOUNT_KEY",
    "GA4_OAUTH_CLIENT_ID",
    "GA4_OAUTH_CLIENT_SECRET",
    "GA4_OAUTH_REFRESH_TOKEN",
)

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_NOT_FETCHED = "not_fetched"


class GscError(RuntimeError):
    """Search Console の認証設定・認証・API 呼び出しの失敗。

    kind:
      config  認証の設定が足りない、または形式が不正
      auth    認証が拒否された（unauthorized_client、invalid_grant など）
      access  プロパティにアクセスできない
      api     API 呼び出しが失敗した
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(redact(message))
        self.kind = kind


def redact(message: str) -> str:
    """環境変数に入っている秘密情報の値を、メッセージから取り除く。"""
    text = str(message)
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if len(value) >= 8:
            text = text.replace(value, f"<{name}>")
    return text


def auth_mode() -> str:
    """使う認証方式を返す。設定が足りなければ GscError(config)。"""
    if os.environ.get(SERVICE_ACCOUNT_ENV_NAME, "").strip():
        return "service_account"
    present = [name for name in OAUTH_ENV_NAMES if os.environ.get(name, "").strip()]
    if len(present) == len(OAUTH_ENV_NAMES):
        return "oauth"
    missing = [name for name in OAUTH_ENV_NAMES if name not in present]
    if present:
        raise GscError(
            "config",
            "GSC の OAuth 設定が一部だけです。同じ OAuth クライアントで発行した3項目をそろえてください。"
            f" 不足: {', '.join(missing)}",
        )
    raise GscError(
        "config",
        f"GSC の認証設定がありません。{SERVICE_ACCOUNT_ENV_NAME}、"
        f"または {', '.join(OAUTH_ENV_NAMES)} を設定してください。",
    )


def build_service():
    """Search Console API のクライアントを作る。"""
    mode = auth_mode()
    from googleapiclient.discovery import build

    if mode == "service_account":
        from google.oauth2.service_account import Credentials as ServiceAccountCredentials

        try:
            info = json.loads(os.environ[SERVICE_ACCOUNT_ENV_NAME])
        except json.JSONDecodeError as exc:
            raise GscError("config", f"{SERVICE_ACCOUNT_ENV_NAME} が JSON ではありません: {exc.msg}") from exc
        credentials = ServiceAccountCredentials.from_service_account_info(info, scopes=[READONLY_SCOPE])
    else:
        from google.oauth2.credentials import Credentials

        # scopes は指定しない。更新トークンに付与済みの権限をそのまま使う
        # （サイトマップ送信と同じトークンを使うため、権限を狭めて要求しない）。
        credentials = Credentials(
            token=None,
            refresh_token=os.environ["GSC_OAUTH_REFRESH_TOKEN"].strip(),
            client_id=os.environ["GSC_OAUTH_CLIENT_ID"].strip(),
            client_secret=os.environ["GSC_OAUTH_CLIENT_SECRET"].strip(),
            token_uri="https://oauth2.googleapis.com/token",
        )
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


def _classify(exc: Exception) -> str:
    try:
        from google.auth.exceptions import RefreshError
    except ImportError:  # pragma: no cover - google-auth は必須依存
        RefreshError = ()  # type: ignore[assignment]
    if RefreshError and isinstance(exc, RefreshError):
        return "auth"
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status in (401,):
        return "auth"
    if status in (403,):
        return "access"
    return "api"


def execute(request: Any, *, what: str) -> Any:
    """API 要求を実行し、失敗は種類付きの GscError にする。"""
    try:
        return request.execute()
    except GscError:
        raise
    except Exception as exc:  # noqa: BLE001 - 種類を判定して GscError に包む
        raise GscError(_classify(exc), f"{what} が失敗しました: {type(exc).__name__}: {exc}") from exc


def verify_property_access(service, site_url: str) -> str:
    """認証したアカウントが対象プロパティにアクセスできるかを確かめ、権限レベルを返す。"""
    response = execute(service.sites().list(), what="sites.list")
    entries = response.get("siteEntry", []) or []
    for entry in entries:
        if entry.get("siteUrl") == site_url:
            level = entry.get("permissionLevel", "")
            if level in ("", "siteUnverifiedUser"):
                raise GscError("access", f"プロパティの権限が不足しています: property={site_url}, permission={level or '不明'}")
            return level
    raise GscError(
        "access",
        f"認証したアカウントから対象プロパティが見えません: property={site_url}, accessible={len(entries)}件",
    )


def search_analytics(service, site_url: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    """searchanalytics.query を実行して rows を返す。0 件は成功として空のリストを返す。"""
    response = execute(
        service.searchanalytics().query(siteUrl=site_url, body=body),
        what=f"searchanalytics.query(dimensions={body.get('dimensions', [])})",
    )
    rows = response.get("rows", [])
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise GscError("api", f"searchanalytics.query の rows が配列ではありません: type={type(rows).__name__}")
    return rows


def fetch_status(status: str, *, error: GscError | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """保存する取得状態の記録を作る。"""
    if status not in (STATUS_OK, STATUS_FAILED, STATUS_NOT_FETCHED):
        raise ValueError(f"unknown fetch status: {status}")
    record: dict[str, Any] = {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if error is not None:
        record["error_kind"] = error.kind
        record["error"] = str(error)
    if extra:
        record.update(extra)
    return record
