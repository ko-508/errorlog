"""
スケジュール定期実行ワークフローに失敗通知ステップと
issues: write パーミッションを一括追加する。
実行後に自身を削除してよい（一時スクリプト）。
"""
from pathlib import Path

WORKFLOWS_DIR = Path(".github/workflows")

TARGETS = {
    "daily.yml":             "publish",
    "rss_pipeline.yml":      "pipeline",
    "quarterly_refresh.yml": "refresh",
    "replenish_queue.yml":   "replenish",
    "weekly_quality.yml":    "quality",
    "weekly_ga4.yml":        "analyze",
    "weekly_glossary.yml":   "glossary",
}

NOTIFY_STEP = """\
      - name: Notify on failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.issues.create({
              owner: context.repo.owner,
              repo:  context.repo.repo,
              title: `🚨 ${context.workflow} 失敗 (${new Date().toISOString().slice(0,10)})`,
              body: [
                '## パイプライン停止検知',
                '',
                `- **ワークフロー**: \\`${context.workflow}\\``,
                `- **実行ログ**: ${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`,
                `- **失敗日時**: ${new Date().toISOString()}`,
                '',
                '確認後、このIssueをクローズしてください。',
              ].join('\\n'),
              labels: ['pipeline-failure'],
            });
"""


def patch(path: Path, job_name: str) -> bool:
    text = path.read_text(encoding="utf-8")

    if "issues: write" not in text:
        text = text.replace(
            "permissions:\n  contents: write",
            "permissions:\n  contents: write\n  issues: write",
        )

    if "Notify on failure" in text:
        print(f"  SKIP (already patched): {path.name}")
        return False

    text = text.rstrip() + "\n\n" + NOTIFY_STEP.rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"  PATCHED: {path.name}")
    return True


if __name__ == "__main__":
    for fname, job in TARGETS.items():
        p = WORKFLOWS_DIR / fname
        if not p.exists():
            print(f"  NOT FOUND: {fname}")
            continue
        patch(p, job)
    print("Done.")
