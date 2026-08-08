import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ERRORSEARCH_JS = ROOT / "assets" / "js" / "errorsearch.js"


class ErrorSearchRankingTest(unittest.TestCase):
    def test_article_fallback_uses_an_empty_overlay_link(self):
        source = ERRORSEARCH_JS.read_text(encoding="utf-8")

        self.assertIn("a.setAttribute('aria-label', item.title);", source)
        self.assertNotIn("a.textContent = item.title;", source)
        self.assertIn("makeCaseDetail('一致した表示'", source)
        self.assertIn("makeCaseDetail('状況'", source)
        self.assertIn("makeCaseDetail('考えられる原因'", source)
        self.assertIn("body.className = 'search-case-result__body';", source)
        self.assertIn("action.textContent = '確認方法を見る';", source)

    def _run_error_search_js(self, script: str) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node executable is not available")

        source = ERRORSEARCH_JS.read_text(encoding="utf-8")
        start = source.index("  // TEST_EXPORT_START")
        end = source.index("  // TEST_EXPORT_END", start)
        functions = source[start:end]

        result = subprocess.run(
            [node, "-e", functions + "\n" + script],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)

    def test_pasted_docker_pull_error_prefers_matching_cases(self):
        self._run_error_search_js(
            textwrap.dedent(
                r"""
                function assertEqual(actual, expected, label) {
                  if (actual !== expected) {
                    throw new Error(label + ': expected ' + expected + ', got ' + actual);
                  }
                }

                var query = "Error response from daemon: pull access denied for example, repository does not exist or may require 'docker login'";
                var hits = [
                  {
                    item: {
                      service: 'Docker',
                      errorCode: 'pull access denied',
                      errorName: 'pull access denied',
                      causeId: 'repository-not-found',
                      cause: 'リポジトリ名、所有者名、Registryが違う',
                      messages: ['repository does not exist'],
                      aliases: ['pull access denied for']
                    },
                    score: 0.05
                  },
                  {
                    item: {
                      service: 'Docker',
                      errorCode: 'pull access denied',
                      errorName: 'pull access denied',
                      causeId: 'authentication',
                      cause: '非公開リポジトリへ未認証でアクセスしている',
                      messages: ["may require 'docker login'"],
                      aliases: ['requested access to the resource is denied']
                    },
                    score: 0.06
                  },
                  {
                    item: {
                      service: 'Kubernetes',
                      errorCode: 'ErrImagePull',
                      errorName: 'ErrImagePull',
                      causeId: 'image-pull-secret',
                      cause: 'imagePullSecretが不足している',
                      messages: ['pull access denied'],
                      aliases: []
                    },
                    score: 0.01
                  }
                ];

                hits.sort(function (a, b) { return compareCaseHits(a, b, query); });
                assertEqual(hits[0].item.causeId, 'repository-not-found', 'repository cause');
                assertEqual(hits[1].item.causeId, 'authentication', 'authentication cause');
                assertEqual(bestMatchedMessage(hits[0].item, query), 'repository does not exist', 'matched message');
                assertEqual(hasCaseSignal(hits[0].item, query), true, 'case signal');
                """
            )
        )

    def test_message_match_outranks_cause_only_match(self):
        self._run_error_search_js(
            textwrap.dedent(
                r"""
                function assertEqual(actual, expected, label) {
                  if (actual !== expected) {
                    throw new Error(label + ': expected ' + expected + ', got ' + actual);
                  }
                }

                var query = 'repository does not exist';
                var hits = [
                  {
                    item: {
                      causeId: 'message-match',
                      service: 'Docker',
                      errorCode: 'pull access denied',
                      errorName: 'pull access denied',
                      messages: ['repository does not exist'],
                      aliases: [],
                      cause: '参照名が違う'
                    },
                    score: 0.34
                  },
                  {
                    item: {
                      causeId: 'cause-only-match',
                      service: 'Docker',
                      errorCode: 'pull access denied',
                      errorName: 'pull access denied',
                      messages: ['access denied'],
                      aliases: [],
                      cause: 'repository does not exist'
                    },
                    score: 0.01
                  }
                ];

                hits.sort(function (a, b) { return compareCaseHits(a, b, query); });
                assertEqual(hits[0].item.causeId, 'message-match', 'message priority');
                """
            )
        )

    def test_situation_is_searchable_and_optional(self):
        self._run_error_search_js(
            textwrap.dedent(
                r"""
                function assertEqual(actual, expected, label) {
                  if (actual !== expected) {
                    throw new Error(label + ': expected ' + expected + ', got ' + actual);
                  }
                }

                var query = 'ローカルではpullできるがCIでは失敗する';
                var withSituation = {
                  service: 'Docker',
                  errorCode: 'pull access denied',
                  errorName: 'pull access denied',
                  situation: 'ローカルではpullできるがCIでは失敗する',
                  messages: [],
                  aliases: [],
                  cause: 'CIだけ別の認証設定を使っている'
                };
                var withoutSituation = {
                  service: 'Docker',
                  errorCode: 'pull access denied',
                  errorName: 'pull access denied',
                  messages: [],
                  aliases: [],
                  cause: ''
                };

                assertEqual(hasCaseSignal(withSituation, query), true, 'situation signal');
                assertEqual(hasCaseSignal(withoutSituation, query), false, 'missing situation');
                assertEqual(typeof caseRank({ item: withoutSituation, score: 0.1 }, query), 'number', 'optional situation rank');
                """
            )
        )

    def test_service_and_unknown_code_fall_back_to_article_search(self):
        self._run_error_search_js(
            textwrap.dedent(
                r"""
                function assertEqual(actual, expected, label) {
                  if (actual !== expected) {
                    throw new Error(label + ': expected ' + expected + ', got ' + actual);
                  }
                }

                var item = {
                  service: 'Docker',
                  errorCode: 'pull access denied',
                  errorName: 'pull access denied',
                  situation: 'CI環境でのみ発生する',
                  messages: ["may require 'docker login'"],
                  aliases: [],
                  cause: 'CIだけ別の認証設定を使っている'
                };

                assertEqual(hasCaseSignal(item, 'Docker 500'), false, 'service-only query should fall back');
                """
            )
        )

    def test_normalization_masks_variable_values(self):
        self._run_error_search_js(
            textwrap.dedent(
                r"""
                function assertContains(actual, expected, label) {
                  if (actual.indexOf(expected) === -1) {
                    throw new Error(label + ': expected to contain ' + expected + ', got ' + actual);
                  }
                }

                var normalized = normalizeSearchText('GET https://example.com/a/b from 192.168.0.10 id abcdef1234567890');
                assertContains(normalized, 'url', 'url');
                assertContains(normalized, 'ip', 'ip');
                assertContains(normalized, 'id', 'id');
                """
            )
        )


if __name__ == "__main__":
    unittest.main()
