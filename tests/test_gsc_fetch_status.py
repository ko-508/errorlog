"""Search Console 取得の認証の組み合わせと、失敗の扱いのテスト（通信なし）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import gsc_client  # noqa: E402
from gsc_client import GscError  # noqa: E402

GSC_VARS = (
    "GSC_SERVICE_ACCOUNT_KEY",
    "GSC_OAUTH_CLIENT_ID",
    "GSC_OAUTH_CLIENT_SECRET",
    "GSC_OAUTH_REFRESH_TOKEN",
    "GA4_SERVICE_ACCOUNT_KEY",
    "GA4_OAUTH_CLIENT_ID",
    "GA4_OAUTH_CLIENT_SECRET",
    "GA4_OAUTH_REFRESH_TOKEN",
)
SITE = "https://errorlog.jp/"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in GSC_VARS:
        monkeypatch.delenv(name, raising=False)


# ── 模擬の Search Console API ──────────────────────────────────────────────


class _Request:
    def __init__(self, result=None, error: Exception | None = None):
        self._result = result
        self._error = error

    def execute(self):
        if self._error is not None:
            raise self._error
        return self._result


class FakeService:
    """sites.list と searchanalytics.query だけを持つ模擬。"""

    def __init__(self, *, rows_by_dims=None, error: Exception | None = None, sites=None):
        self.rows_by_dims = rows_by_dims or {}
        self.error = error
        self.sites_entries = sites if sites is not None else [{"siteUrl": SITE, "permissionLevel": "siteOwner"}]
        self.queries: list[dict] = []

    def sites(self):
        service = self

        class _Sites:
            def list(self_inner):
                if service.error is not None:
                    return _Request(error=service.error)
                return _Request({"siteEntry": service.sites_entries})

        return _Sites()

    def searchanalytics(self):
        service = self

        class _SA:
            def query(self_inner, siteUrl, body):
                service.queries.append({"siteUrl": siteUrl, "body": body})
                if service.error is not None:
                    return _Request(error=service.error)
                dims = tuple(body.get("dimensions", []))
                return _Request({"rows": service.rows_by_dims.get(dims, [])})

        return _SA()


def _refresh_error():
    from google.auth.exceptions import RefreshError

    return RefreshError("unauthorized_client: Unauthorized", {"error": "unauthorized_client"})


# ── 認証の組み合わせ ──────────────────────────────────────────────────────


def test_no_gsc_settings_is_config_error_and_ga4_values_are_not_used(monkeypatch):
    for name in ("GA4_OAUTH_CLIENT_ID", "GA4_OAUTH_CLIENT_SECRET", "GA4_OAUTH_REFRESH_TOKEN", "GA4_SERVICE_ACCOUNT_KEY"):
        monkeypatch.setenv(name, "ga4-value-should-not-be-used")
    with pytest.raises(GscError) as exc:
        gsc_client.auth_mode()
    assert exc.value.kind == "config"


def test_partial_gsc_oauth_settings_stop_with_missing_names(monkeypatch):
    # 週次の旧設定の再現: GSC の更新トークンだけがあり、クライアントは GA4 のもの
    monkeypatch.setenv("GSC_OAUTH_REFRESH_TOKEN", "gsc-refresh-token-value")
    monkeypatch.setenv("GA4_OAUTH_CLIENT_ID", "ga4-client-id-value")
    monkeypatch.setenv("GA4_OAUTH_CLIENT_SECRET", "ga4-client-secret-value")
    with pytest.raises(GscError) as exc:
        gsc_client.auth_mode()
    assert exc.value.kind == "config"
    assert "GSC_OAUTH_CLIENT_ID" in str(exc.value)
    assert "GSC_OAUTH_CLIENT_SECRET" in str(exc.value)
    assert "gsc-refresh-token-value" not in str(exc.value)


def test_complete_gsc_oauth_settings_select_oauth(monkeypatch):
    for name in ("GSC_OAUTH_CLIENT_ID", "GSC_OAUTH_CLIENT_SECRET", "GSC_OAUTH_REFRESH_TOKEN"):
        monkeypatch.setenv(name, f"{name.lower()}-value")
    assert gsc_client.auth_mode() == "oauth"


def test_build_service_uses_only_gsc_oauth_values(monkeypatch):
    for name in ("GSC_OAUTH_CLIENT_ID", "GSC_OAUTH_CLIENT_SECRET", "GSC_OAUTH_REFRESH_TOKEN"):
        monkeypatch.setenv(name, f"gsc-{name.lower()}")
    monkeypatch.setenv("GA4_OAUTH_CLIENT_ID", "ga4-client")
    captured = {}
    import googleapiclient.discovery

    def fake_build(api, version, credentials, cache_discovery):
        captured["api"] = (api, version)
        captured["credentials"] = credentials
        return object()

    monkeypatch.setattr(googleapiclient.discovery, "build", fake_build)
    gsc_client.build_service()
    creds = captured["credentials"]
    assert captured["api"] == ("searchconsole", "v1")
    assert creds.client_id == "gsc-gsc_oauth_client_id"
    assert creds.client_secret == "gsc-gsc_oauth_client_secret"
    assert creds.refresh_token == "gsc-gsc_oauth_refresh_token"


def test_redact_removes_secret_values(monkeypatch):
    monkeypatch.setenv("GSC_OAUTH_REFRESH_TOKEN", "very-secret-refresh-token")
    assert "very-secret-refresh-token" not in gsc_client.redact("error with very-secret-refresh-token inside")


def test_refresh_error_is_classified_as_auth():
    with pytest.raises(GscError) as exc:
        gsc_client.execute(_Request(error=_refresh_error()), what="sites.list")
    assert exc.value.kind == "auth"
    assert "unauthorized_client" in str(exc.value)


def test_property_not_visible_is_access_error():
    service = FakeService(sites=[{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"}])
    with pytest.raises(GscError) as exc:
        gsc_client.verify_property_access(service, SITE)
    assert exc.value.kind == "access"


# ── fetch_search_console.py ─────────────────────────────────────────────


@pytest.fixture
def fsc(monkeypatch, tmp_path):
    import fetch_search_console as module

    (tmp_path / "reports" / "ga4").mkdir(parents=True)
    (tmp_path / "content" / "posts").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(module, "BASE", tmp_path)
    monkeypatch.setattr(module, "POSTS_DIR", tmp_path / "content" / "posts")
    monkeypatch.setattr(module, "REPORTS_DIR", tmp_path / "reports" / "ga4")
    monkeypatch.setattr(module, "GSC_REPORT_FILE", tmp_path / "reports" / "ga4" / "gsc_test.json")
    monkeypatch.setattr(module, "PRIORITY_FILE", tmp_path / "scripts" / "rewrite_priority.json")
    monkeypatch.setattr(module, "PRIORITY_REPORT_FILE", tmp_path / "scripts" / "rewrite_priority_report.json")
    monkeypatch.setattr(module, "SITE_URL", SITE)
    monkeypatch.setattr(module.gsc_client, "auth_mode", lambda: "oauth")
    return module


def test_fetch_success_with_rows_records_ok(fsc, monkeypatch):
    rows = [{"keys": [SITE + "posts/a/"], "impressions": 30, "clicks": 1, "ctr": 0.03, "position": 9.0}]
    qrows = [{"keys": ["query a", SITE + "posts/a/"], "impressions": 30, "clicks": 1, "ctr": 0.03, "position": 9.0}]
    service = FakeService(rows_by_dims={("page",): rows, ("query", "page"): qrows})
    monkeypatch.setattr(fsc, "_build_service", lambda: service)
    fsc.main()
    report = json.loads(fsc.GSC_REPORT_FILE.read_text(encoding="utf-8"))
    assert report["fetch_status"]["status"] == "ok"
    assert report["total_pages"] == 1


def test_fetch_success_with_zero_rows_is_ok_zero(fsc, monkeypatch):
    monkeypatch.setattr(fsc, "_build_service", lambda: FakeService())
    fsc.main()
    report = json.loads(fsc.GSC_REPORT_FILE.read_text(encoding="utf-8"))
    assert report["fetch_status"]["status"] == "ok"
    assert report["fetch_status"]["raw_rows"] == 0
    assert report["total_pages"] == 0


def test_fetch_auth_failure_is_recorded_as_failed_and_exits_1(fsc, monkeypatch):
    post = fsc.POSTS_DIR / "a.md"
    post.write_text("---\ntitle: \"A\"\n---\nbody\n", encoding="utf-8")
    monkeypatch.setattr(fsc, "_build_service", lambda: FakeService(error=_refresh_error()))
    with pytest.raises(SystemExit) as exc:
        fsc.main()
    assert exc.value.code == 1
    report = json.loads(fsc.GSC_REPORT_FILE.read_text(encoding="utf-8"))
    assert report["fetch_status"]["status"] == "failed"
    assert report["fetch_status"]["error_kind"] == "auth"
    # 失敗を 0 件として保存しない
    assert "total_pages" not in report
    assert "bottlenecks" not in report
    # 学習データと記事は書き換えない
    assert not (fsc.BASE / "data" / "search_queries.json").exists()
    assert post.read_text(encoding="utf-8") == "---\ntitle: \"A\"\n---\nbody\n"


def test_fetch_query_failure_after_access_check_is_failed(fsc, monkeypatch):
    class HttpLikeError(Exception):
        class resp:  # noqa: N801 - googleapiclient.errors.HttpError と同じ形
            status = 500

    service = FakeService()
    original_sa = service.searchanalytics

    def failing_sa():
        class _SA:
            def query(self_inner, siteUrl, body):
                return _Request(error=HttpLikeError("backend error"))

        return _SA()

    service.searchanalytics = failing_sa
    monkeypatch.setattr(fsc, "_build_service", lambda: service)
    with pytest.raises(SystemExit):
        fsc.main()
    report = json.loads(fsc.GSC_REPORT_FILE.read_text(encoding="utf-8"))
    assert report["fetch_status"]["status"] == "failed"
    assert report["fetch_status"]["error_kind"] == "api"
    assert original_sa is not None


# ── weekly_report.py / monthly_report.py ─────────────────────────────────


def test_weekly_fetch_gsc_data_failure_returns_none_and_failed(monkeypatch):
    import weekly_report as wr

    monkeypatch.setattr(wr, "_build_gsc_service", lambda: FakeService(error=_refresh_error()))
    bottlenecks, summary, previous, status = wr.fetch_gsc_data()
    assert summary is None and previous is None and bottlenecks == []
    assert status["status"] == "failed"
    assert status["error_kind"] == "auth"


def test_weekly_fetch_gsc_data_zero_rows_is_ok_zero(monkeypatch):
    import weekly_report as wr

    monkeypatch.setattr(wr, "SITE_URL", SITE)
    monkeypatch.setattr(wr, "_build_gsc_service", lambda: FakeService())
    bottlenecks, summary, previous, status = wr.fetch_gsc_data()
    assert status["status"] == "ok"
    assert summary == {"impressions": 0, "clicks": 0, "ctr": 0.0, "position": 0.0}


def test_weekly_failed_section_says_not_zero():
    import weekly_report as wr

    status = gsc_client.fetch_status("failed", error=GscError("auth", "unauthorized_client"))
    section = wr._build_gsc_summary_section({}, wr.build_gsc_comparison({}, {}), status)
    assert "取得に失敗" in section
    assert "0 ではなく未取得" in section


def test_weekly_history_skips_failed_and_invalid_reports():
    import weekly_report as wr

    reports = [
        {"period": "bad", "gsc_summary": {}, "gsc": {"current": {}}, "_gsc_invalid": True},
        {"period": "failed", "gsc": {"fetch_status": {"status": "failed"}, "current": None}, "_gsc_invalid": True},
        {"period": "good", "gsc_summary": {"impressions": 80, "clicks": 4, "ctr": 0.05, "position": 12.0}, "_gsc_invalid": False},
    ]
    history = wr._extract_gsc_history("now", {}, reports)
    assert [row["period"] for row in history] == ["good"]


def test_invalid_records_manifest_lists_known_failed_weeks():
    import weekly_report as wr

    invalid = wr.load_invalid_gsc_records()
    assert "weekly_report_20260809.json" in invalid
    assert "weekly_report_20261005.json" in invalid
    assert "weekly_report_20260802.json" not in invalid
    assert "gsc_20260614.json" not in invalid  # 疑いのみ。確認できていないので除外しない


def test_monthly_history_row_for_failed_month_is_not_zero():
    import monthly_report as mr

    row = mr._history_row_from_report({"month": "2026-10", "gsc": {"fetch_status": {"status": "failed"}, "current": None}})
    assert row["impressions"] is None
    section = mr._build_monthly_history_section([row])
    assert "未取得" in section


# ── query_coverage_analyzer.py / update_rewrite_results.py ──────────────


def test_content_gap_exits_on_gsc_failure(monkeypatch):
    import fetch_search_console
    import query_coverage_analyzer as qca

    monkeypatch.setattr(fetch_search_console, "_build_service", lambda: FakeService(error=_refresh_error()))
    with pytest.raises(SystemExit) as exc:
        qca._load_queries_from_gsc()
    assert exc.value.code == 1


def test_rewrite_results_exits_without_writing_on_gsc_failure(monkeypatch, tmp_path):
    import update_rewrite_results as urr

    report = tmp_path / "rewrite_report.json"
    original = json.dumps([{"slug": "a", "rewrite_date": "2026-01-01"}])
    report.write_text(original, encoding="utf-8")
    monkeypatch.setattr(urr, "REWRITE_REPORT_FILE", report)
    monkeypatch.setattr(urr, "_build_service", lambda: FakeService(error=_refresh_error()))
    monkeypatch.setattr(urr, "_write_experiments", lambda records: pytest.fail("記録を書いてはいけない"))
    with pytest.raises(SystemExit) as exc:
        urr.main()
    assert exc.value.code == 1
    assert report.read_text(encoding="utf-8") == original
