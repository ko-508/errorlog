---
title: "ELB の 504 エラー：原因と解決策"
date: 2026-08-03
description: "ELB の 504 は、ロードバランサ自身が生成したものと、ターゲットが返したものが混在します。アクセスログの target_status_code を見れば、どちらかは一目で分かります。ロードバランサ生成なら原因は公式に6つ挙げられており、関わるタイマーは接続確立の10秒と idle timeout の2種類です。"
tags: ["AWS"]
errorCode: "504"
lastmod: 2026-08-03
service: "AWS"
error_type: "504"
components: ["Application Load Balancer", "Classic Load Balancer", "CloudWatch"]
related_services: ["EC2", "ECS", "Lambda"]
trend_incident: false
---

## 冒頭まとめ

ELB の 504 Gateway Timeout を調べるとき、最初にやるべきことは原因の推測ではありません。**その 504 を、ロードバランサが作ったのか、ターゲットが返したのかを確定させること**です。

この2つは、調べる場所がまったく違います。前者ならロードバランサとターゲットの間の話、後者ならターゲットの内側の話です。にもかかわらず、[クライアント](/glossary/クライアント/)から見える応答は同じ 504 です。

判定は一瞬で終わります。アクセス[ログ](/glossary/ログ/)の `target_status_code` を見るだけです。公式文書によれば、この欄はターゲットへの接続が確立され、かつターゲットが応答を返した場合にのみ記録され、それ以外は `-` になります。つまり **`elb_status_code` が 504 で `target_status_code` が `-` ならロードバランサ生成**、**両方 504 ならターゲット自身が返した 504** です。多段構成でターゲット側に別の中継役がいる場合、後者になります。

ロードバランサ生成だった場合、原因は公式に6つ挙げられています。関わるタイマーは2種類で、接続を確立するまでの10秒と、応答を待つ idle timeout（既定60秒）です。**前者は変更できません**。

なお、よく混同されますが、ターゲット側の keep-alive がロードバランサの idle timeout より短い場合に返るのは 504 ではなく **502** です。公式の 502 の説明にその条件が明記されています。

## エラーの概要

アクセス[ログ](/glossary/ログ/)の1行から読み取れる情報が、この[エラー](/glossary/エラー/)の診断の中心です。

```text
https 2026-08-03T12:00:00.000000Z app/my-alb/50dc6c495c0c9188 203.0.113.10:54321
  10.0.1.23:8080 0.001 -1 -1 504 - 512 0 "GET https://example.com:443/report HTTP/1.1"
```

読むべき欄は3つです。

`elb_status_code` が 504。`target_status_code` が `-`。この2つが揃えば、ロードバランサが生成した 504 です。

`target_processing_time` が `-1`。公式文書には、この値はロードバランサが要求をターゲットへ送れなかった場合に `-1` になり、その状況としてターゲットが idle timeout より前に接続を閉じた場合や[クライアント](/glossary/クライアント/)が不正な要求を送った場合が挙げられています。加えて、**登録済みのターゲットが idle timeout までに応答しなかった場合も `-1`** になると書かれています。

指標でも同じ切り分けができます。ロードバランサが生成した[エラー](/glossary/エラー/)は `HTTPCode_ELB_5XX_Count`（504 なら `HTTPCode_ELB_504_Count`）に計上され、ターゲットが返した[エラー](/glossary/エラー/)は `HTTPCode_Target_5XX_Count` に計上されます。**`HTTPCode_ELB_504_Count` にデータが無ければ、その 504 はターゲット由来**です。

## まず最初に：誰が返したかを確定する

第一に、アクセス[ログ](/glossary/ログ/)を有効にします。有効になっていなければ、ここから先の切り分けは推測になります。

第二に、`target_status_code` を見ます。`-` ならロードバランサ生成、`504` ならターゲット由来です。

第三に、`target_processing_time` を見ます。`-1` なら応答が返ってきていません。値が入っていて idle timeout に近ければ、待ちきれずに打ち切ったということです。

第四に、`target:port` を見ます。`-` であれば、そもそもターゲットへ振り分けられていません。

## よくある原因と解決手順

### 原因1：ターゲットが idle timeout までに応答しなかった

最も多い形です。公式のトラブルシューティングでは、ロードバランサはターゲットへの接続を確立したが、ターゲットが idle timeout の期間内に応答しなかった、と説明されています。

既定の idle timeout は60秒で、1秒から4000秒の範囲で変更できます。

**Before（時間のかかる処理を同期で待つ）：**

```bash
# 60秒を超える帳票生成などが、必ず 504 になる
```

**After（上限を延ばす。ただし応急処置）：**

```bash
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn <ARN> \
  --attributes Key=idle_timeout.timeout_seconds,Value=120
```

延ばせば通りますが、根本的には非同期化が本筋です。要求を受け付けて識別子を返し、結果は別の口で取りに来てもらう形にすれば、タイマーの制約から外れます。

延ばす場合の注意が1つあります。ターゲット側の keep-alive を、ロードバランサの idle timeout より**長く**設定してください。逆になっていると、今度は 502 が出ます。

### 原因2：接続そのものが確立できなかった

公式に挙げられている原因の1つ目です。ロードバランサがターゲットへの接続を、接続タイムアウトの**10秒**以内に確立できなかった場合です。同じく10秒の SSL handshake のタイムアウトも別項目として挙げられています。

重要なのは、**この10秒は変更できない**ことです。idle timeout をいくら延ばしても、この段階の失敗には効きません。

疑うべきはセキュリティグループと、ターゲットの状態です。

```bash
# ターゲットの健全性を確認する
aws elbv2 describe-target-health --target-group-arn <ARN>

# ロードバランサのセキュリティグループから、ターゲットのポートへ到達できるか
aws ec2 describe-security-groups --group-ids <ターゲット側のSG>
```

ターゲットが高負荷で新規接続を受け付けられない場合も、この形になります。応答が遅いのではなく、接続の受付自体が滞っている状態です。

### 原因3：戻りの経路が塞がれている

見落とされやすい原因です。公式には、サブネットのネットワーク ACL が、ターゲットからロードバランサのノードへの一時ポート（1024から65535）の通信を許可していない場合、と書かれています。

行きは通るのに戻りが通らないため、接続はできても応答が届きません。セキュリティグループは戻りの通信を自動的に許可しますが、ネットワーク ACL は方向ごとに明示的な許可が必要です。**セキュリティグループだけを確認して問題無しと判断すると、ここで詰まります**。

```bash
aws ec2 describe-network-acls --filters "Name=association.subnet-id,Values=<サブネットID>"
```

### 原因4：Content-Length と本体の不一致

公式に挙げられている原因です。ターゲットが返した `Content-Length` [ヘッダー](/glossary/ヘッダー/)の値が実際の本体より大きい場合、ロードバランサは足りない分を待ち続け、時間切れになります。

[アプリケーション](/glossary/アプリケーション/)側で長さを自前で計算している場合や、途中で応答の生成が中断された場合に起こります。ターゲットへ直接問い合わせて、返っている長さと実際の本体を突き合わせてください。

```bash
curl -sI http://<ターゲットのIP>:<ポート>/path | grep -i content-length
curl -s http://<ターゲットのIP>:<ポート>/path | wc -c
```

### 原因5：ターゲットが Lambda の場合

ターゲットが Lambda 関数で、Lambda サービスが接続タイムアウトまでに応答しなかった場合も 504 です。

ただし境界に注意が要ります。**関数が自身の設定したタイムアウトに達して応答しなかった場合は、504 ではなく 502** です。公式の 502 の説明に、そう明記されています。関数の実行時間そのものを疑うなら、見るべきは 502 の側です。

### 原因6：ターゲット自身が 504 を返している

`target_status_code` が 504 だった場合です。ロードバランサは、ターゲットからの正常な HTTP 応答をそのまま[クライアント](/glossary/クライアント/)へ転送します。[エラー](/glossary/エラー/)であっても同じです。

この場合、ロードバランサの設定を変えても何も起きません。ターゲット側の中継役が時間切れを起こしています。多段構成であれば、その中継役の設定を確認してください（[Nginx の 504 の記事](/posts/nginx_504/)）。

## 補足：似ているが別のもの

ターゲット側の keep-alive がロードバランサの idle timeout より短い場合は 502 です。公式の 502 の説明には、ロードバランサが要求を出している最中にターゲットが接続を閉じた場合として挙げられ、keep-alive の長さが idle timeout より短くないかを確認するよう書かれています。**同じ設定の不整合が、タイミング次第で 502 と 504 の両方を生みます**（[AWS の 502 の記事](/posts/aws_502/)）。

ターゲットが1つも登録されていない、あるいはすべて未使用の状態なら 503 です（[AWS の 503 の記事](/posts/aws_503/)）。

打ち切ったのが[クライアント](/glossary/クライアント/)側の場合、ELB 固有の[コード](/glossary/コード/)が使われます。[クライアント](/glossary/クライアント/)が idle timeout より前に接続を閉じた場合は 460、[クライアント](/glossary/クライアント/)がデータを送らないまま idle timeout に達した場合は 408 です。504 と混同しないでください。

API Gateway や他のサービスも含めた AWS 全体の 504 の整理は別記事にあります（[AWS の 504 の記事](/posts/aws_504/)）。本記事はロードバランサに絞っています。

## 切り分けの順序

1. アクセス[ログ](/glossary/ログ/)を有効にする。無ければ切り分けは推測になる。
2. `target_status_code` を見る。`-` ならロードバランサ生成、`504` ならターゲット由来。
3. ターゲット由来なら、ロードバランサの設定は関係ない。ターゲット側の中継役を調べる。
4. `target_processing_time` を見る。`-1` なら応答が返っていない。
5. `target:port` が `-` なら、振り分け自体が行われていない。
6. 接続が確立できていないなら、10秒の壁。idle timeout を延ばしても効かない。
7. 接続はできて応答が来ないなら、idle timeout の側。延ばすか、非同期化する。
8. セキュリティグループが問題無しでも、ネットワーク ACL の戻り方向（一時ポート）を確認する。

## 確認コマンド集

```bash
# 1. アクセスログが有効かを確認する
aws elbv2 describe-load-balancer-attributes --load-balancer-arn <ARN> \
  --query "Attributes[?starts_with(Key, 'access_logs')]"

# 2. 現在の idle timeout を確認する
aws elbv2 describe-load-balancer-attributes --load-balancer-arn <ARN> \
  --query "Attributes[?Key=='idle_timeout.timeout_seconds']"

# 3. ロードバランサ生成の 504 が出ているかを指標で確認する
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB --metric-name HTTPCode_ELB_504_Count \
  --dimensions Name=LoadBalancer,Value=<app/名前/ID> \
  --start-time "$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 --statistics Sum

# 4. ターゲット由来かどうかを指標で確認する
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB --metric-name HTTPCode_Target_5XX_Count \
  --dimensions Name=LoadBalancer,Value=<app/名前/ID> \
  --start-time "$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 --statistics Sum

# 5. 応答時間が idle timeout に張り付いていないかを見る
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value=<app/名前/ID> \
  --start-time "$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 --statistics Maximum

# 6. ターゲットの健全性と理由を確認する
aws elbv2 describe-target-health --target-group-arn <ARN> \
  --query "TargetHealthDescriptions[].{id:Target.Id,state:TargetHealth.State,reason:TargetHealth.Reason}"

# 7. ネットワーク ACL の戻り方向（一時ポート）を確認する
aws ec2 describe-network-acls \
  --filters "Name=association.subnet-id,Values=<サブネットID>" \
  --query "NetworkAcls[].Entries[?Egress==\`false\`]"

# 8. ターゲットへ直接問い合わせて、応答時間を測る
curl -o /dev/null -sS -w "connect=%{time_connect} ttfb=%{time_starttransfer} total=%{time_total}\n" \
  http://<ターゲットのIP>:<ポート>/path
```

## Editor's Note

502 と 504 は、原因が別々に語られがちです。しかし実際には、**1つの設定の不整合が両方を生む**ことがあります。

その構造を明快に記録した報告があります（[Ability to set keepAliveTimeout in server created by "node:http"](https://github.com/oven-sh/bun/issues/12446)）。2024年7月、ある実行環境の HTTP [サーバー](/glossary/サーバー/)で接続の待機時間を設定したい、という要望です。理由の説明が、この記事の主題そのものになっています。

その実行環境は、接続の待機時間が10秒に固定されていました。報告者はまず 502 に悩まされます。ロードバランサ側がまだ有効だと思っている接続を、[サーバー](/glossary/サーバー/)側が10秒で閉じてしまうためです。回避策として、ロードバランサの idle timeout を8〜9秒まで下げれば 502 は減らせる、と報告者自身が書いています。

しかし、そこで別の問題が現れます。報告者の[アプリケーション](/glossary/アプリケーション/)には、正当に10秒以上かかる処理があったのです。idle timeout を10秒未満に下げれば、その処理は今度は **504** で打ち切られます。理想は idle timeout を60秒のままにして、[サーバー](/glossary/サーバー/)側の待機時間をそれより長くすることだが、実行環境がそれを許さない——という板挟みです。

ここから読み取れる原則があります。**[サーバー](/glossary/サーバー/)側の待機時間は、ロードバランサの idle timeout より長くなければならない**。短ければ 502、その回避のために idle timeout を切り詰めれば 504。片方を潰すともう片方が出る関係です。

504 に当たったら、まずアクセス[ログ](/glossary/ログ/)で誰が返したかを確定させる。ロードバランサ生成なら、次に見るのは2つのタイマーの大小関係です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*