---
title: "GitHub API の 422 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub API の 422 Unprocessable Entity は、リクエストは JSON として読めたものの、中身がエンドポイントの検証に通らなかったことを示します。調査の核は応答の errors 配列で、code の値（missing_field・invalid・already_exists・missing・custom）が原因をほぼ確定させます。422 は修正しない限り何度送っても同じ結果で、再試行では解決しません。"
tags: ["GitHub API"]
errorCode: "422"
lastmod: 2026-07-22
service: "GitHub API"
error_type: "422"
components: ["REST API"]
related_services: ["GitHub REST API", "Octokit", "GitHub Actions"]
trend_incident: false
---

## 冒頭まとめ

GitHub API の 422 Unprocessable Entity は、リクエストが JSON として正しく読めたうえで、中身がそのエンドポイントの検証ルールに通らなかったことを示すコードです。GitHub 公式の API 定義（OpenAPI）で数えると、422 を応答として定義するエンドポイントは308あり、全コードの中で最多です。つまり422は特別な異常ではなく、「パラメータを持つ操作の、最もありふれた失敗の形」です。

調査の核は、応答の errors 配列を読むことに尽きます。公式文書のとおり、配列の各要素は resource（どの種類の対象か）、field（どの項目か）、code（何が悪いか）を持ち、code の値は公式に定義されています。missing_field は必須項目の未設定、invalid は項目の形式の不正、already_exists は同じ値を持つ対象が既に存在、missing は指した対象が存在しない、unprocessable は入力を処理できない、そして custom の場合は必ず message が付き、その文言をそのまま読みます。code と field が分かれば、原因はほぼ確定します。

境界も先に引いておきます。本文が JSON として壊れている場合は 400（Problems parsing JSON）で、422の手前の問題です。対象の「今の状態」との矛盾（sha の不一致、空リポジトリ）は 409 です。また、422は形式的な性質として、リクエストを修正しない限り何度送っても同じ結果になります。GitHub 公式の Octokit の retry プラグインも422を再試行の対象外としており、422への正しい反応は再送ではなく修正です。

## エラーの概要

422 の応答本文は、公式の API 定義に Validation Error というスキーマとして定義されています。message と documentation_url が必ず含まれ、多くの場合 errors 配列が付きます。配列の各要素で必須なのは code だけで、resource・field・value（実際に送られた値）は項目に応じて付きます。

```json
{
  "message": "Validation Failed",
  "errors": [
    {
      "resource": "Issue",
      "field": "title",
      "code": "missing_field"
    }
  ],
  "documentation_url": "https://docs.github.com/rest/issues/issues#create-an-issue"
}
```

この例は公式文書に掲載されているもので、「Issue の title が未設定」と一行で読めます。もう1つ、errors が文字列の配列だけの簡易な形（Validation Error Simple）も公式定義に存在し、この場合は文字列の文言をそのまま読みます。

なお、公式リファレンスの各エンドポイントで422の要約は「Validation failed, or the endpoint has been spammed.」と記されています。検証失敗だけでなく、エンドポイントへの過剰な連続作成がスパムと判定された場合も422になりうる、ということがこの一文に含まれています。

## まず最初に：errors 配列を3段階で読む

第一に、応答に errors 配列があるかを確認します。無い、または文字列だけの場合は、message の文言そのものが手がかりです。第二に、各要素の code を読みます。missing_field・invalid・already_exists・missing のどれかであれば、この記事の原因1〜4に対応します。custom であれば message を読みます（原因5）。第三に、field と resource で対象の項目を特定します。value が含まれていれば、実際に届いた値まで分かるため、手元で送ったつもりの値との差がその場で確認できます。

## よくある原因と解決手順

### 原因1：必須項目が未設定（missing_field）

エンドポイントが必須と定めるパラメータが本文に含まれていない状態です。field がその項目名を名指しします。

**Before（title を省略して422になる）：**

```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"body": "説明だけを送っている"}'
```

**After（必須項目を確認して追加する）：**

```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"title": "ログインボタンが反応しない", "body": "説明だけを送っている"}'
```

どの項目が必須かは、公式リファレンスの各エンドポイントのパラメータ表（Required の列）で確認できます。プログラムからの呼び出しでは、変数が空文字や null のまま送られて missing_field になるケースが典型で、送信直前の値の確認をログに残すと再発を防げます。

### 原因2：項目の形式が不正（invalid）

値は入っているものの、形式がエンドポイントの仕様に合っていない状態です。典型は Git 参照の完全名です。参照の作成では refs/ から始まる完全な形が求められ、ブランチ名だけを送ると弾かれます。

**Before（ブランチ名だけを送って422になる）：**

```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/git/refs \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"ref": "feature-x", "sha": "<コミットSHA>"}'
```

**After（refs/heads/ を含む完全名で送る）：**

```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/git/refs \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"ref": "refs/heads/feature-x", "sha": "<コミットSHA>"}'
```

invalid の応答に value が含まれる場合は、実際に届いた値がそこに写ります。手元のコードが組み立てた値と見比べれば、テンプレートの展開漏れや余分な空白がその場で見つかります。

### 原因3：同じ値の対象が既に存在する（already_exists）

一意であるべき値が既存の対象と重複した状態です。ブランチ・タグ・ラベル・リリースのタグ名などで起き、ブランチ作成なら message に Reference already exists が入ります。

対処は「確認してから作る」ではなく、「already_exists を正常系として扱う」設計を推奨します。確認と作成の間に他の処理が割り込めば、確認は無意味になるためです。

**Before（重複を異常として落ちる自動化）：**

```bash
curl -sf -X POST https://api.github.com/repos/<owner>/<repo>/git/refs \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"ref": "refs/heads/release", "sha": "<コミットSHA>"}' || exit 1
# 2回目以降の実行は必ず 422 で停止する
```

**After（already_exists なら既存を使う分岐を持つ）：**

```bash
status=$(curl -s -o /tmp/resp.json -w "%{http_code}" -X POST \
  https://api.github.com/repos/<owner>/<repo>/git/refs \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"ref": "refs/heads/release", "sha": "<コミットSHA>"}')

if [ "$status" = "201" ]; then
  echo "作成した"
elif grep -q "already_exists" /tmp/resp.json; then
  echo "既存のブランチを使う"   # 必要なら PATCH で既存参照を更新する
else
  cat /tmp/resp.json; exit 1
fi
```

### 原因4：指した対象が存在しない（missing）

公式定義のとおり、missing は「リソースが存在しない」ことを示します。リクエスト自体の形式は正しいものの、field が指す項目の参照先（指定したブランチ、ユーザー、対象の ID など）が見つからない状態です。対処は、field が名指しする項目の値を、一覧系のエンドポイントで実在確認することです。なお、リポジトリそのものが存在しない・権限がない場合は 422 ではなく 404 になります。missing は「リポジトリには届いたが、その中の指定先がない」段階の話です。

### 原因5：custom、または message だけの422

code が custom の場合、公式文書のとおり必ず message が付きます。文言をそのまま読むのが対処です。代表例は、差分のないプルリクエスト作成で返る No commits between です。base と head の間にコミット差分がないという事実の通知であり、リクエストの書式をいくら直しても解決しません。差分の有無を compare 系の確認で先に見るか、差分がない状態を正常系として扱います。

一方で、message を読んでも原因が判然としない422も現実には存在します。その場合の進め方は2つです。第一に、エンドポイントのリファレンスに戻り、パラメータ表の制約（型・とりうる値・組み合わせ）と突き合わせます。第二に、リクエストを最小化します。パラメータを必須のみまで削って通ることを確認し、1つずつ戻して、422を引き起こす要素を特定します（この手法は [GitHub API の 500 の記事](/posts/github_api_500/)の原因2と同じです）。

## 補足：422ではない類似エラー

本文が JSON として読めない場合は 400 で、message は Problems parsing JSON や Body should be a JSON object になります。422の調査の手前で、直列化の回数を疑う段階です（[GitHub API の 400 の記事](/posts/github_api_400/)）。リクエストの中身ではなく「対象の今の状態」との矛盾は 409 です。sha を伴う更新の追い越し、空リポジトリへの Git 系 API がこれにあたります（[GitHub API の 409 の記事](/posts/github_api_409/)）。マージできない状態のプルリクエストへのマージ要求は 405 です。リポジトリや対象そのものの不存在・権限不足は、private の秘匿のため 404 です（[GitHub API の 404 の記事](/posts/github_api_404/)）。リクエストの量や頻度が弾かれる場合、通常は 403 または 429 の secondary rate limit として現れます（[403 の記事](/posts/github_api_403/)、[429 の記事](/posts/github_api_429/)）。ただし前述のとおり、公式リファレンスの422の要約にはスパム判定の場合が含まれており、連続作成系の操作では「量の問題が422の形で現れる」ことがある点も覚えておくと迷いません。

## 切り分けの順序

1. コードと message を確認する。Problems parsing JSON なら 400、状態の矛盾なら 409、それぞれの記事の調査に切り替える。
2. errors 配列を読む。code（missing_field・invalid・already_exists・missing・custom）と field で、原因1〜5に振り分ける。
3. missing_field・invalid は、公式リファレンスのパラメータ表と value の実値を突き合わせて修正する。
4. already_exists は、重複を正常系として扱う分岐（既存を取得・更新へフォールバック）に直す。
5. message を読んでも確定しない場合は、リクエストを必須パラメータのみまで最小化し、422を引き起こす要素を特定する。422は修正するまで結果が変わらないため、そのままの再送はしない。

## 確認コマンド集

```bash
# 1. errors 配列を整形して読む（code / field / message を一覧にする）
curl -s -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"body": "test"}' | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('message')); [print(e) for e in d.get('errors',[])]"

# 2. 参照（ブランチ・タグ）の実在を確認する（missing / already_exists の切り分け）
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/git/matching-refs/heads/<branch>

# 3. プルリクエスト作成前に差分の有無を確認する（No commits between の予防）
curl -s -H "Authorization: Bearer <your-github-token>" \
  "https://api.github.com/repos/<owner>/<repo>/compare/<base>...<head>" | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('commits:', d.get('total_commits'))"

# 4. 最小構成のリクエストで通ることを確認してから、パラメータを1つずつ戻す
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"title": "minimal"}'
```

## Editor's Note

原因5の実例として、GitHub 自身の API 定義リポジトリに残る報告があります（["Create a reference" API call fails with HTTP 422 without meaningful message](https://github.com/github/rest-api-description/issues/4887)）。2025年6月、参照作成 API が意味のあるメッセージを伴わない422を返すケースについての報告で、公式トラブルシューティング文書に挙げられた422の類型のどれにも当てはまらないこと、そして公式リファレンスの422の要約「Validation failed, or the endpoint has been spammed」のうちスパム判定側の挙動が詳しく文書化されていないことが指摘されています。この記録が示すのは、errors 配列の読み方は公式の設計であり最初に試すべき手段である一方、万能ではないという現実です。読めない422に当たったときの次の一手が、リファレンスのパラメータ表との突き合わせと、リクエストの最小化です。執筆時点から約1年前の報告で、現行のトラブルシューティング文書と公式リファレンスの記述も本文で述べたとおりのままです。

422は、GitHub が「どこが悪いか」を構造化して返してくれる、最も親切な部類のエラーです。再送する前に errors 配列を読む。code と field を見る。それだけで、308のエンドポイントに共通する調査の入口に立てます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*