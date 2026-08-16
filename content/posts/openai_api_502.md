---
title: "OpenAI API の 502 エラー：原因と解決策"
date: 2026-08-03
description: "OpenAI API の 502 は公式のエラー一覧に載っていません。応答も JSON ではなく HTML で、末尾に前段の事業者名が入ります。つまり API の層に届く前に遮られています。切り分けの起点は、本文が JSON かどうかを見ることです。502 が本当の原因を隠している場合もあります。"
tags: ["OpenAI API"]
images: ["og/posts/openai_api_502.png"]
errorCode: "502"
lastmod: 2026-08-03
service: "OpenAI API"
error_type: "502"
components: ["Edge", "Reliability"]
related_services: ["Python SDK", "Files API"]
trend_incident: false
top_queries:
- 'openai 502'
---

## 冒頭まとめ

OpenAI [API](/glossary/api/) の 502 には、他の[エラー](/glossary/エラー/)と決定的に違う点があります。**公式の[エラー](/glossary/エラー/)一覧に載っていない**ことです。400、401、403、429、500、503 は項目として説明がありますが、502 はありません。

理由は応答を見れば分かります。502 のときに返るのは [JSON](/glossary/json/) ではなく、次のような HTML です。

```html
<html>
<head><title>502 Bad Gateway</title></head>
<body>
<center><h1>502 Bad Gateway</h1></center>
<hr><center>cloudflare</center>
</body>
</html>
```

末尾に、前段で配信を担う事業者の名前が入っています。**つまりこの応答を作ったのは [API](/glossary/api/) の層ではありません**。要求は [API](/glossary/api/) に届く前に遮られています。

この違いは対処に直結します。`type` も `code` も `param` も存在しないため、応答から原因を読み取る通常の手順が使えません。代わりに確認するのは、**本文が [JSON](/glossary/json/) かどうか**、そして**何が起きたときに出るか**です。

さらに注意すべき点があります。502 は、その裏にある本当の失敗を**覆い隠す**ことがあります。実際に、[認証](/glossary/認証/)の失敗が 502 として現れた事例が報告されています。

## エラーの概要

通常の[エラー](/glossary/エラー/)と並べると、構造の違いが際立ちます。

```text
# 400 や 429 の場合（API の層が返す）
{"error": {"message": "...", "type": "...", "param": null, "code": "..."}}

# 502 の場合（前段が返す）
<html><head><title>502 Bad Gateway</title></head> ... <center>cloudflare</center> ...
```

[プログラム](/glossary/プログラム/)側では、この違いが例外の形にも現れます。本文を [JSON](/glossary/json/) として解釈しようとして失敗する、あるいは中身の無い[エラー](/glossary/エラー/)として扱われる、といった形です。公式の[ソフトウェア](/glossary/ソフトウェア/)開発キットでは 500 番台としてまとめて扱われるため、**500 と 502 が同じ区分に見えてしまう**点にも注意が要ります。

なお、同じ前段の仕組みは 502 以外の[コード](/glossary/コード/)も返します。520 番台のような、通常の [API](/glossary/api/) では使われない[コード](/glossary/コード/)を受け取った場合も、出どころは同じです。

## まず最初に：本文が JSON かを確認する

第一に、応答の本文を見ます。HTML であれば [API](/glossary/api/) の層に到達していません。

第二に、本文の末尾に事業者名が入っているかを確認します。入っていれば、前段が返した応答です。

第三に、同じ要求を別の経路から送って再現するかを確かめます。特定の[回線](/glossary/回線/)や[環境](/glossary/環境/)でのみ起きる場合があります。

第四に、要求の大きさと所要時間を確認します。大きなデータのやり取りで起きやすい傾向があります。

## よくある原因と解決手順

### 原因1：一時的な障害や混雑

最も多い形です。前段と [API](/glossary/api/) の間の[通信](/glossary/通信/)が一時的に成立しなかった状態で、利用者側でできることはありません。

対処は再試行です。ただし、公式の開発キットは 500 番台を**既定で2回再試行**するため、手元に記録が1回でも実際は3回送られています。回数を増やす前に、現状を把握してください。

```python
# 素の応答と回数を確定させてから設計する
client = OpenAI(max_retries=0)
```

広範囲で発生している場合は、稼働状況の確認以上にできることはありません。

### 原因2：大きなデータのやり取り

要求または応答が大きい場合に起こりやすい形です。実際、まとめて実行した結果の大きな[ファイル](/glossary/ファイル/)を取得しようとすると必ず失敗し、小さな[ファイル](/glossary/ファイル/)なら成功する、という報告があります。

この場合、再試行しても同じ結果になります。**大きさそのものが引き金**だからです。

対処は分割です。まとめて実行する処理では、出力を複数に分けるか、取得の単位を小さくします。

```bash
# 応答の大きさと所要時間を測る
curl -sS -o /dev/null -w "size=%{size_download} time=%{time_total}\n" \
  https://api.openai.com/v1/files/<ファイルID>/content \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### 原因3：特定の経路でのみ発生する

一部の利用者や[回線](/glossary/回線/)でのみ継続的に起きる形です。報告の中には、同じ[環境](/glossary/環境/)でも接続の単位によって成否が分かれる、別の[回線](/glossary/回線/)に切り替えると通る、といった観察があります。

この場合、疑うべきは自分と前段の間の経路です。[回線](/glossary/回線/)、中継の仕組み、社内から外部へ出る出口などが該当します。

```bash
# 別の経路から到達するかを確認する
curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

利用者側で解決しきれない場合もありますが、**経路を変えると結果が変わるかどうか**は重要な情報です。問い合わせの際にも役立ちます。

### 原因4：502 が本当の原因を隠している

見落とすと長時間を失う形です。前段が返す 502 は、その先で起きた失敗の内容を含みません。したがって、**別の[エラー](/glossary/エラー/)が 502 として見えている**ことがあります。

対処は、要求を分解して直接確認することです。使っている道具を経由せず、最小の要求を自分で送れば、本来の応答が見えます。

```bash
# 道具を経由せず、認証だけを最小構成で確認する
curl -sS -i https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | head -20
```

ここで 401 や 403 が返るなら、502 は症状であって原因ではありません。

### 原因5：500 や 503 と同じものとして扱っている

対処ではなく、切り分けの問題です。500 は [API](/glossary/api/) の層が返す [JSON](/glossary/json/)、503 も同様に文言を伴う応答です。一方 502 は前段が返す HTML です。

**同じ 5 で始まっていても、誰が返したかが違います**。500 の記事の手順（`type` と `code` を読む、要求の識別子を控える）は、502 には使えません。識別子が付かないためです。

## 補足：似ているが別のもの

[サーバー](/glossary/サーバー/)側の処理で問題が起きた場合は 500 です。公式に項目として定義があり、応答も [JSON](/glossary/json/) です（[OpenAI API の 500 の記事](/posts/openai_api_500/)）。

混雑による一時的な拒否は 503 で、こちらも公式の一覧に項目があります（[OpenAI API の 503 の記事](/posts/openai_api_503/)）。

[認証](/glossary/認証/)の失敗は 401、地域の制限は 403 です。前述のとおり、これらが 502 の裏に隠れている場合があります（[OpenAI API の 401 の記事](/posts/openai_api_401/)、[403 の記事](/posts/openai_api_403/)）。

なお、前段の仕組みが 5xx を返す構造は他の基盤にも共通します。GCP でも 502 は区分の定義に存在せず、応答を作ったのは窓口ではないと整理できます（[GCP の 502 の記事](/posts/gcp_502/)）。**502 を見たら出どころを疑う**、という読み方は基盤を問わず有効です。

## 切り分けの順序

1. 本文が [JSON](/glossary/json/) か HTML かを見る。HTML なら [API](/glossary/api/) の層に届いていない。
2. 末尾の事業者名を確認する。前段が返した証拠になる。
3. 最小の要求を直接送る。本来の[エラー](/glossary/エラー/)が隠れていないか。
4. 要求と応答の大きさを測る。大きい場合は分割を検討する。
5. 別の経路から試す。経路依存かどうかを切り分ける。
6. 開発キットの再試行を止めて、実際の回数を確定させる。
7. 広範囲で発生しているなら、稼働状況を確認して待つ。
8. 500 の手順を流用しない。要求の識別子が付かない。

## 確認コマンド集

```bash
# 1. 状態コードと本文の先頭を同時に見る（JSON か HTML か）
curl -sS -i https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | head -20

# 2. 本文に前段の事業者名が入っているかを確認する
curl -sS https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | grep -i "cloudflare\|bad gateway"

# 3. 応答の大きさと所要時間を測る
curl -sS -o /dev/null -w "code=%{http_code} size=%{size_download} time=%{time_total}\n" \
  https://api.openai.com/v1/files/<ファイルID>/content \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# 4. 発生率を測る（経路依存かどうかの材料になる）
for i in $(seq 10); do
  curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/models \
    -H "Authorization: Bearer $OPENAI_API_KEY"
done | sort | uniq -c

# 5. 開発キットの再試行を止めて素の応答を見る
python3 -c "
from openai import OpenAI
import openai
try:
    OpenAI(max_retries=0).models.list()
except openai.APIStatusError as e:
    print(e.status_code); print(str(e.body)[:200])
"
```

## Editor's Note

502 の危うさは、**別の[エラー](/glossary/エラー/)を覆い隠す**点にあります。それを明快に記録した報告があります（[openai-codex OAuth completes successfully, but runs fail](https://github.com/openclaw/openclaw/issues/36660)）。

2026年3月、ある道具で[認可](/glossary/認可/)の手続きは成功しているのに、実行だけが失敗する、という報告が出されました。返ってきていたのは、あの HTML です。表題も本文も `502 Bad Gateway`、末尾に事業者名。これだけを見れば、提供側の一時的な不調としか読めません。

報告者は、そこで止まりませんでした。[保存](/glossary/保存/)された資格情報を使って、**同じ[エンドポイント](/glossary/エンドポイント/)へ直接要求を送った**のです。返ってきたのは 401 で、必要な[権限](/glossary/権限/)が不足しているという内容でした。

報告の中で、この構造はこう表現されています。**根本にある[認証](/glossary/認証/)の失敗が、前段の 502 として覆い隠されていた**。

ここに、この[エラー](/glossary/エラー/)への向き合い方が要約されています。502 は「何かが失敗した」という事実しか伝えません。何が失敗したかは含まれないのです。したがって、再試行しても直らず、道具の設定を眺めても分からない場合、やるべきことは1つです。**道具を経由せず、最小の要求を自分で送る**。そこで初めて、[API](/glossary/api/) の層が持っている本当の答えが見えます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*