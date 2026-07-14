import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "layouts" / "index.html"


class HomeSearchRankingTest(unittest.TestCase):
    def _run_search_ranking_js(self, script: str) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node executable is not available")

        source = INDEX_HTML.read_text(encoding="utf-8")
        start = source.index("  /* エラー記事=0")
        end = source.index("  var timer;", start)
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

    def test_code_and_tool_match_beats_close_fuzzy_match(self):
        self._run_search_ranking_js(
            textwrap.dedent(
                r"""
                function assertEqual(actual, expected, label) {
                  if (actual !== expected) {
                    throw new Error(label + ': expected ' + expected + ', got ' + actual);
                  }
                }

                var hits = [
                  { item: { title: 'Docker の 400 エラー：原因と解決策', errorCode: '400', permalink: '/posts/docker-400/' }, score: 0.01 },
                  { item: { title: 'Docker の 500 エラー：原因と解決策', errorCode: '500', permalink: '/posts/docker-500/' }, score: 0.20 },
                  { item: { title: 'GitHub API の 500 エラー：原因と解決策', errorCode: '500', permalink: '/posts/github-500/' }, score: 0.02 },
                  { item: { title: 'Docker の使い方', errorCode: '', permalink: '/posts/docker-guide/' }, score: 0.001 }
                ];

                var code = extractErrorCode('docker 500');
                var terms = extractToolTerms('docker 500', code);
                hits.sort(function (a, b) { return compareSearchHits(a, b, code, terms); });

                assertEqual(hits[0].item.title, 'Docker の 500 エラー：原因と解決策', 'docker 500 first result');
                assertEqual(hits[1].item.title, 'GitHub API の 500 エラー：原因と解決策', 'same code before wrong code');
                assertEqual(hits[2].item.title, 'Docker の 400 エラー：原因と解決策', 'wrong code after matching code');
                """
            )
        )

    def test_common_query_cases(self):
        self._run_search_ranking_js(
            textwrap.dedent(
                r"""
                function titlesFor(query) {
                  var hits = [
                    { item: { title: 'Docker の 400 エラー：原因と解決策', errorCode: '400', permalink: '/posts/docker-400/' }, score: 0.05 },
                    { item: { title: 'Docker の 500 エラー：原因と解決策', errorCode: '500', permalink: '/posts/docker-500/' }, score: 0.15 },
                    { item: { title: 'GitHub API の 401 エラー：原因と解決策', errorCode: '401', permalink: '/posts/github-api-401/' }, score: 0.15 },
                    { item: { title: 'Nginx の 500 エラー：原因と解決策', errorCode: '500', permalink: '/posts/nginx-500/' }, score: 0.01 },
                    { item: { title: 'Docker とは', errorCode: '', permalink: '/glossary/docker/' }, score: 0.001 }
                  ];
                  var code = extractErrorCode(query);
                  var terms = extractToolTerms(query, code);
                  hits.sort(function (a, b) { return compareSearchHits(a, b, code, terms); });
                  return hits.map(function (h) { return h.item.title; });
                }

                function assertEqual(actual, expected, label) {
                  if (actual !== expected) {
                    throw new Error(label + ': expected ' + expected + ', got ' + actual);
                  }
                }

                assertEqual(titlesFor('docker 400')[0], 'Docker の 400 エラー：原因と解決策', 'docker 400');
                assertEqual(titlesFor('github 401')[0], 'GitHub API の 401 エラー：原因と解決策', 'github 401');
                assertEqual(titlesFor('500')[0], 'Nginx の 500 エラー：原因と解決策', '500 keeps 500 before 400');
                assertEqual(titlesFor('docker　　500')[0], 'Docker の 500 エラー：原因と解決策', 'full-width and repeated spaces');
                assertEqual(titlesFor('DOCKER 500')[0], 'Docker の 500 エラー：原因と解決策', 'case-insensitive');
                assertEqual(titlesFor('docker')[0], 'Docker の 400 エラー：原因と解決策', 'query without code keeps article priority and score order');
                """
            )
        )


if __name__ == "__main__":
    unittest.main()
