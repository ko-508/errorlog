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

Docker の 400 Bad Request は、デーモンまで届いたリクエストの形式や値が不正で、デーモンが処理を始められなかったことを示します。実際の環境で最も多いのは、クライアントとデーモンの API バージョン不一致です。エラー文言が client version <番号> is too new（クライアントが新しすぎる）または too old（古すぎる）なら、これに該当します。新しい CLI やツールと古いデーモンの組み合わせ、CI の Docker-in-Docker 構成、DOCKER_API_VERSION 環境変数の固定ミスが典型です。そのほか、デーモンの API を直接呼び出す場合の壊れた JSON や、設定値の検証で弾かれるケースが400になります。

逆に、400と誤解されやすいが400ではないものも押さえておくと迷いません。Dockerfile の構文エラーはビルド時の解析エラー、compose ファイルの YAML 不正はクライアント側の読み込みエラー、イメージ名の形式違反は invalid reference format としてデーモンに送る前に拒否されます。いずれもデーモンの400応答ではなく、調査の場所が異なります。

## エラーの概要

docker コマンドは、裏側で Docker デーモンの API に HTTP リクエストを送るクライアントです。Error response from daemon: で始まるエラーは、リクエストがデーモンまで届いたことを意味します。デーモンは、不正なパラメータに分類されるエラーを 400 として応答する実装になっており（Docker のソースコードで確認できます）、API バージョンの範囲外もこの分類に含まれます。実際の報告に共通する文言は次の2種です。

```text
Error response from daemon: client version 1.52 is too new.
Maximum supported API version is 1.43
```

```text
Error response from daemon: client version 1.41 is too old.
Minimum supported API version is 1.44
```

too new はクライアントの要求する API バージョンがデーモンの上限を超えている状態、too old は逆に、デーモンが受け付ける下限より古い状態です。後者は、Docker Engine のバージョン29が受け付ける最小 API バージョンを引き上げたことに伴い、古いクライアントやツールを使う環境で報告が増えています。

## まず最初に：文言で3つに分岐する

client version ... is too new / too old なら、API バージョンの不一致です（原因1）。invalid という語を含む文言（不正な JSON、不正な設定値の指摘）なら、リクエストの中身の問題です（原因2・3）。dockerfile parse error、YAML の解析エラー、invalid reference format、Cannot connect to the Docker daemon のいずれかなら、それは400の問題ではありません（後述の補足へ）。

## よくある原因と解決手順

### 原因1：クライアントとデーモンの API バージョン不一致

まず両者のバージョンを確認します。

```bash
docker version
# Client: の API version と Server: の API version を比較する

# 環境変数でバージョンを固定していないかを確認
env | grep -i docker_api
```

不一致が起きる典型は3つです。第一に、古いデーモンが更新されないまま、クライアント側（CLI や、Docker API を使うツール・ライブラリ）だけが更新されるケースです。NAS などの組み込み環境や、長期稼働の古いサーバーで起きやすい形です。第二に、CI の Docker-in-Docker 構成です。dind イメージやジョブ内の CLI に :latest のような浮動タグを使っていると、どちらか一方だけが新しくなった時点で組み合わせが壊れます。第三に、DOCKER_API_VERSION 環境変数に古い値が残っているケースで、この場合クライアントは常にその古いバージョンを名乗るため、デーモン側の下限引き上げで突然 too old になります。

対処の本筋は、デーモン（サーバー側）を更新して対応範囲を揃えることです。すぐに更新できない場合の応急策として、DOCKER_API_VERSION をサーバーが対応する値（docker version の Server: の API version）に固定すれば、クライアントがそのバージョンとして振る舞い、通信は成立します。ただしクライアントの新機能はそのバージョンの範囲に制限されます。CI では、dind イメージと CLI のバージョンを浮動タグではなく明示的に固定し、更新を意図的に行う運用が恒久対処です。

### 原因2：API を直接呼び出すリクエストの形式が不正

デーモンの API を curl やプログラムから直接呼ぶ場合、本文が JSON として読めない、または Content-Type が不正だと、デーモンの入口の検証で拒否され400になります。

**Before（JSON が壊れていて400になる）：**

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

送信前に本文を JSON 検証にかける（python3 -m json.tool など）のが確実です。プログラムからの呼び出しなら、直列化をライブラリに任せているかを確認します（この落とし穴の詳細は [GitHub API の 400 の記事](/posts/github_api_400/)で扱った内容と同型です）。

### 原因3：設定値がデーモンの検証で弾かれている

コンテナ作成時の設定（再起動ポリシー、資源制限などの各項目）は、デーモン側で値の検証が行われ、不正な値は不正なパラメータとして400で拒否されます。この場合のエラー文言には、どの項目のどの値が不正かが具体的に書かれます。対処は文言が名指しする項目の修正で、指定できる値の一覧は該当機能の公式リファレンスで確認します。「400だから形式の問題だろう」と JSON の体裁ばかり見るのではなく、文言が指す個別の値を読むのが近道です。

## 補足：400ではない類似エラー

400と混同されやすいエラーの正しい行き先です。dockerfile parse error や Dockerfile の命令の誤りは、ビルドの解析段階のエラーであり、HTTP の400ではありません（調査対象は Dockerfile の該当行です）。compose ファイルの YAML 不正は、compose がファイルを読む段階のクライアント側エラーで、デーモンには届いていません。invalid reference format（repository name must be lowercase を含む）はイメージ名の規則違反で、送信前に拒否されます（名前の規則は [docker_404 の記事](/posts/docker_404/)の補足を参照）。Cannot connect to the Docker daemon はデーモン不達で、400どころか HTTP のやり取り自体が成立していません（[docker_500 の記事](/posts/docker_500/)の補足を参照）。

## 切り分けの順序

1. エラー文言を読む。too new / too old なら原因1、invalid 系なら原因2・3、それ以外（parse error、YAML、reference format、Cannot connect）は400以外の調査に切り替える。
2. 原因1なら docker version で両者の API バージョンを確認し、DOCKER_API_VERSION の残存を洗い出す。本筋はデーモン更新、応急はバージョン固定、CI はイメージの明示固定。
3. 原因2なら送信本文を JSON 検証にかけ、直列化の経路を確認する。
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

原因1の実例として、GitLab の公式サポート文書があります（[Docker API Version Mismatch Errors in CI/CD Pipelines](https://support.gitlab.com/hc/en-us/articles/23582251372060)）。CI の Docker-in-Docker 構成で、too new と too old の両方のエラーが発生する事象について、原因と対処がまとめられています。背景は、Docker 29 が受け付ける最小 API バージョンを引き上げたことです。dind サービスのイメージに :latest や :dind のような浮動タグを使っていると、サービス側だけが自動的に29系へ更新され、ジョブ内の古いクライアントとの組み合わせが壊れます。対処として、ランナーが使う Docker Engine のバージョンを明示的に固定する設定が示されています。「何も変えていないのに昨日から急に400」という症状の裏に、浮動タグ経由の片側だけの自動更新がある、という CI の定番の構図をそのまま示す記録です。同種の報告は、古いデーモンを更新できない NAS 環境（更新されたツールが too new で接続不能になった例）など、CI 以外でも確認できます。

Docker の400は、文言がバージョンの数字や不正な項目を名指ししてくれる親切なエラーです。リクエストの体裁を疑う前に、まず文言を読み、クライアントとデーモンの組み合わせを確認することが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*