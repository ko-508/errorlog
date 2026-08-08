import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ERRORSEARCH_JS = ROOT / "assets" / "js" / "errorsearch.js"


class ErrorSearchRankingTest(unittest.TestCase):
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
                assertEqual(hasCaseSignal(hits[0].item, 'Docker 500'), false, 'service-only query should fall back');
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
