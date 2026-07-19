---
title: "Docker の 400 エラー：原因と解決策"
date: 2026-01-01
description: "Docker の 400 Bad Request の最頻の原因は、クライアントとデーモンの API バージョン不一致（client version ... is too new / too old）です。CI の Docker-in-Docker や古いデーモンの環境で頻発します。API 直接呼び出しの不正なリクエストを含め、エラー文言から切り分けて解決します。Dockerfile の構文エラーは400ではありません。"
tags: ["Docker"]
errorCode: "400"
lastmod: 2026-07-15
service: "Docker"
error_type: "400"
components: ["Desktop"]
related_services: ["Docker Remote API", "curl"]
trend_incident: true
---

## 冒頭まとめ

[Docker](/glossary/docker/) の 400 Bad Request は、[デーモン](/glossary/デーモン/)まで届いた[リクエスト](/glossary/リクエスト/)の形式や値が不正で、[デーモン](/glossary/デーモン/)が処理を始められなかったことを示します。実際の環境で最も多いのは、[クライアント](/glossary/クライアント/)と[デーモン](/glossary/デーモン/)の [API](/glossary/api/) [バージョン](/glossary/バージョン/)不一致です。[エラー](/glossary/エラー/)文言が client version <番号> is too new（[クライアント](/glossary/クライアント/)が新しすぎる）または too old（古すぎる）なら、これに該当します。新しい [CLI](/glossary/cli/) やツールと古い[デーモン](/glossary/デーモン/)の組み合わせ、CI の [Docker](/glossary/docker/)-in-[Docker](/glossary/docker/) 構成、DOCKER_[API](/glossary/api/)_VERSION [環境変数](/glossary/環境変数/)の固定ミスが典型です。そのほか、[デーモン](/glossary/デーモン/)の [API](/glossary/api/) を直接呼び出す場合の壊れた [JSON](/glossary/json/) や、[設定値](/glossary/設定値/)の検証で弾かれるケースが400になります。

逆に、400と誤解されやすいが400ではないものも押さえておくと迷いません。Dockerfile の構文[エラー](/glossary/エラー/)はビルド時の解析[エラー](/glossary/エラー/)、compose [ファイル](/glossary/ファイル/)の [YAML](/glossary/yaml/) 不正は[クライアント](/glossary/クライアント/)側の読み込み[エラー](/glossary/エラー/)、[イメージ](/glossary/イメージ/)名の形式違反は invalid reference format として[デーモン](/glossary/デーモン/)に送る前に拒否されます。いずれも[デーモン](/glossary/デーモン/)の400応答ではなく、調査の場所が異なります。

## エラーの概要

docker [コマンド](/glossary/コマンド/)は、裏側で [Docker](/glossary/docker/) [デーモン](/glossary/デーモン/)の [API](/glossary/api/) に [HTTP](/glossary/http/) [リクエスト](/glossary/リクエスト/)を送る[クライアント](/glossary/クライアント/)です。Error response from daemon: で始まる[エラー](/glossary/エラー/)は、[リクエスト](/glossary/リクエスト/)が[デーモン](/glossary/デーモン/)まで届いたことを意味します。[デーモン](/glossary/デーモン/)は、不正な[パラメータ](/glossary/パラメータ/)に分類される[エラー](/glossary/エラー/)を 400 として応答する実装になっており（[Docker](/glossary/docker/) のソースコードで確認できます）、[API](/glossary/api/) [バージョン](/glossary/バージョン/)の範囲外もこの分類に含まれます。実際の報告に共通する文言は次の2種です。

```text
Error response from daemon: client version 1.52 is too new.
Maximum supported API version is 1.43
```

```text
Error response from daemon: client version 1.41 is too old.
Minimum supported API version is 1.44
```

too new は[クライアント](/glossary/クライアント/)の要求する [API](/glossary/api/) [バージョン](/glossary/バージョン/)が[デーモン](/glossary/デーモン/)の上限を超えている状態、too old は逆に、[デーモン](/glossary/デーモン/)が受け付ける下限より古い状態です。後者は、[Docker](/glossary/docker/) Engine の[バージョン](/glossary/バージョン/)29が受け付ける最小 [API](/glossary/api/) [バージョン](/glossary/バージョン/)を引き上げたことに伴い、古い[クライアント](/glossary/クライアント/)やツールを使う環境で報告が増えています。

## まず最初に：文言で3つに分岐する

client version ... is too new / too old なら、[API](/glossary/api/) [バージョン](/glossary/バージョン/)の不一致です（原因1）。invalid という語を含む文言（不正な [JSON](/glossary/json/)、不正な[設定値](/glossary/設定値/)の指摘）なら、[リクエスト](/glossary/リクエスト/)の中身の問題です（原因2・3）。dockerfile parse error、[YAML](/glossary/yaml/) の解析[エラー](/glossary/エラー/)、invalid reference format、Cannot connect to the [Docker](/glossary/docker/) daemon のいずれかなら、それは400の問題ではありません（後述の補足へ）。

## よくある原因と解決手順

### 原因1：クライアントとデーモンの API バージョン不一致

まず両者の[バージョン](/glossary/バージョン/)を確認します。

```bash
docker version
# Client: の API version と Server: の API version を比較する

# 環境変数でバージョンを固定していないかを確認
env | grep -i docker_api
```

不一致が起きる典型は3つです。第一に、古い[デーモン](/glossary/デーモン/)が更新されないまま、[クライアント](/glossary/クライアント/)側（[CLI](/glossary/cli/) や、[Docker](/glossary/docker/) [API](/glossary/api/) を使うツール・ライブラリ）だけが更新されるケースです。NAS などの組み込み環境や、長期稼働の古い[サーバー](/glossary/サーバー/)で起きやすい形です。第二に、CI の [Docker](/glossary/docker/)-in-[Docker](/glossary/docker/) 構成です。dind [イメージ](/glossary/イメージ/)やジョブ内の [CLI](/glossary/cli/) に :latest のような浮動[タグ](/glossary/タグ/)を使っていると、どちらか一方だけが新しくなった時点で組み合わせが壊れます。第三に、DOCKER_[API](/glossary/api/)_VERSION [環境変数](/glossary/環境変数/)に古い値が残っているケースで、この場合[クライアント](/glossary/クライアント/)は常にその古い[バージョン](/glossary/バージョン/)を名乗るため、[デーモン](/glossary/デーモン/)側の下限引き上げで突然 too old になります。

対処の本筋は、[デーモン](/glossary/デーモン/)（[サーバー](/glossary/サーバー/)側）を更新して対応範囲を揃えることです。すぐに更新できない場合の応急策として、DOCKER_[API](/glossary/api/)_VERSION を[サーバー](/glossary/サーバー/)が対応する値（docker version の Server: の [API](/glossary/api/) version）に固定すれば、[クライアント](/glossary/クライアント/)がその[バージョン](/glossary/バージョン/)として振る舞い、[通信](/glossary/通信/)は成立します。ただし[クライアント](/glossary/クライアント/)の新機能はその[バージョン](/glossary/バージョン/)の範囲に制限されます。CI では、dind [イメージ](/glossary/イメージ/)と [CLI](/glossary/cli/) の[バージョン](/glossary/バージョン/)を浮動[タグ](/glossary/タグ/)ではなく明示的に固定し、更新を意図的に行う運用が恒久対処です。

### 原因2：API を直接呼び出すリクエストの形式が不正

[デーモン](/glossary/デーモン/)の [API](/glossary/api/) を curl やプログラムから直接呼ぶ場合、本文が [JSON](/glossary/json/) として読めない、または Content-Type が不正だと、[デーモン](/glossary/デーモン/)の入口の検証で拒否され400になります。

**Before（[JSON](/glossary/json/) が壊れていて400になる）：**

```bash
curl -s -o /dev/null -w "%{http_code}\n" --unix-socket /var/run/docker.sock \
  -X POST -H "Content-Type: application/json" \
  -d '{"Image": "nginx" "Cmd": ["echo"]}' \
  http://localhost/containers/create
# → 400（カンマの欠落）
```

**After（修正後）：**

```bash
curl -s --unix-socket /var/run/docker.sock \
  -X POST -H "Content-Type: application/json" \
  -d '{"Image": "nginx", "Cmd": ["echo"]}' \
  http://localhost/containers/create
```

送信前に本文を [JSON](/glossary/json/) 検証にかける（python3 -m json.tool など）のが確実です。プログラムからの呼び出しなら、直列化をライブラリに任せているかを確認します（この落とし穴の詳細は [GitHub API の 400 の記事](/posts/github_api_400/)で扱った内容と同型です）。

### 原因3：設定値がデーモンの検証で弾かれている

[コンテナ](/glossary/コンテナ/)作成時の設定（再起動[ポリシー](/glossary/ポリシー/)、資源制限などの各項目）は、[デーモン](/glossary/デーモン/)側で値の検証が行われ、不正な値は不正な[パラメータ](/glossary/パラメータ/)として400で拒否されます。この場合の[エラー](/glossary/エラー/)文言には、どの項目のどの値が不正かが具体的に書かれます。対処は文言が名指しする項目の修正で、指定できる値の一覧は該当機能の公式リファレンスで確認します。「400だから形式の問題だろう」と [JSON](/glossary/json/) の体裁ばかり見るのではなく、文言が指す個別の値を読むのが近道です。

## 補足：400ではない類似エラー

400と混同されやすい[エラー](/glossary/エラー/)の正しい行き先です。dockerfile parse error や Dockerfile の命令の誤りは、ビルドの解析段階の[エラー](/glossary/エラー/)であり、[HTTP](/glossary/http/) の400ではありません（調査対象は Dockerfile の該当行です）。compose [ファイル](/glossary/ファイル/)の [YAML](/glossary/yaml/) 不正は、compose が[ファイル](/glossary/ファイル/)を読む段階の[クライアント](/glossary/クライアント/)側[エラー](/glossary/エラー/)で、[デーモン](/glossary/デーモン/)には届いていません。invalid reference format（repository name must be lowercase を含む）は[イメージ](/glossary/イメージ/)名の規則違反で、送信前に拒否されます（名前の規則は [docker_404 の記事](/posts/docker_404/)の補足を参照）。Cannot connect to the [Docker](/glossary/docker/) daemon は[デーモン](/glossary/デーモン/)不達で、400どころか [HTTP](/glossary/http/) のやり取り自体が成立していません（[docker_500 の記事](/posts/docker_500/)の補足を参照）。

## 切り分けの順序

1. [エラー](/glossary/エラー/)文言を読む。too new / too old なら原因1、invalid 系なら原因2・3、それ以外（parse error、[YAML](/glossary/yaml/)、reference format、Cannot connect）は400以外の調査に切り替える。
2. 原因1なら docker version で両者の [API](/glossary/api/) [バージョン](/glossary/バージョン/)を確認し、DOCKER_[API](/glossary/api/)_VERSION の残存を洗い出す。本筋は[デーモン](/glossary/デーモン/)更新、応急は[バージョン](/glossary/バージョン/)固定、CI は[イメージ](/glossary/イメージ/)の明示固定。
3. 原因2なら送信本文を [JSON](/glossary/json/) 検証にかけ、直列化の経路を確認する。
4. 原因3なら文言が名指しする設定項目を公式リファレンスと突き合わせて修正する。

## 確認コマンド集

```bash
# 1. クライアントとデーモンの API バージョンを確認
docker version

# 2. バージョン固定の環境変数が残っていないかを確認
env | grep -i docker

# 3. デーモンが対応する API バージョンを直接確認
curl -s --unix-socket /var/run/docker.sock http://localhost/version

# 4. API に送る本文の JSON 検証
python3 -m json.tool < body.json
```

## Editor's Note

原因1の実例として、GitLab の公式サポート文書があります（[Docker API Version Mismatch Errors in CI/CD Pipelines](https://support.gitlab.com/hc/en-us/articles/23582251372060)）。CI の [Docker](/glossary/docker/)-in-[Docker](/glossary/docker/) 構成で、too new と too old の両方の[エラー](/glossary/エラー/)が発生する事象について、原因と対処がまとめられています。背景は、[Docker](/glossary/docker/) 29 が受け付ける最小 [API](/glossary/api/) [バージョン](/glossary/バージョン/)を引き上げたことです。dind サービスの[イメージ](/glossary/イメージ/)に :latest や :dind のような浮動[タグ](/glossary/タグ/)を使っていると、サービス側だけが自動的に29系へ更新され、ジョブ内の古い[クライアント](/glossary/クライアント/)との組み合わせが壊れます。対処として、ランナーが使う [Docker](/glossary/docker/) Engine の[バージョン](/glossary/バージョン/)を明示的に固定する設定が示されています。「何も変えていないのに昨日から急に400」という症状の裏に、浮動[タグ](/glossary/タグ/)経由の片側だけの自動更新がある、という CI の定番の構図をそのまま示す記録です。同種の報告は、古い[デーモン](/glossary/デーモン/)を更新できない NAS 環境（更新されたツールが too new で接続不能になった例）など、CI 以外でも確認できます。

[Docker](/glossary/docker/) の400は、文言が[バージョン](/glossary/バージョン/)の数字や不正な項目を名指ししてくれる親切な[エラー](/glossary/エラー/)です。[リクエスト](/glossary/リクエスト/)の体裁を疑う前に、まず文言を読み、[クライアント](/glossary/クライアント/)と[デーモン](/glossary/デーモン/)の組み合わせを確認することが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*