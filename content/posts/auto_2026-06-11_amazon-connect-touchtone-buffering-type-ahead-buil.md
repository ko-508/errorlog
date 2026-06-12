---
title: "Amazon Connectのタッチトーンバッファリング（タイプアヘッド）でIVRの顧客体験を向上させる方法"
date: 2026-06-11
lastmod: 2026-06-11
draft: false
description: "Amazon Connectのタッチトーンバッファリング機能（タイプアヘッド）について、その概要、実際の動作、そしてコンタクトフローでの設定方法を詳しく解説します。顧客がIVRで数字を先行入力できるようになり、待ち時間の短縮と顧客体験の向上が期待できます。"
tags: ["Dev.to - AWS", "Amazon Connect", "IVR", "DTMF", "タッチトーンバッファリング"]
trend_incident: true
---

## エラーの概要

Amazon Connectのタッチトーンバッファリングは、厳密にはエラーではなく、IVR（Interactive Voice Response）システムにおける顧客の入力体験を向上させるための機能です。この機能が有効になっていない場合や、設定が不適切な場合に、顧客がIVRのプロンプト再生中に先行入力したDTMF（プッシュトーン）が失われる、あるいは意図した動作にならないという「顧客体験上の問題」が発生します。これは、システムが顧客の入力を適切に処理できていない状態と捉えることができます。

## 実際のエラーメッセージ例

タッチトーンバッファリングに関連する直接的なエラーメッセージは通常出力されません。これは機能の有無や設定の問題であり、システムがクラッシュするようなエラーではないためです。しかし、顧客が意図した通りにIVRを進められない場合、オペレーターへの転送時などに以下のようなログが記録される可能性があります。

**Amazon Connectのコンタクトトレースレコード（CTRs）の例:**

```json
{
  "ContactId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "Channel": "VOICE",
  "InitiationMethod": "INBOUND",
  "Queue": {
    "Name": "BasicQueue",
    "ARN": "arn:aws:connect:ap-northeast-1:xxxxxxxxxxxx:instance/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/queue/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  },
  "DisconnectReason": "CUSTOMER_DISCONNECT",
  "Agent": null,
  "CustomerInput": [
    {
      "Type": "DTMF",
      "Value": "1",
      "OffsetMillis": 15000
    },
    {
      "Type": "DTMF",
      "Value": "2",
      "OffsetMillis": 15500
    }
    // 顧客が「123」と入力したにも関わらず、
    // ログに「3」が記録されていない、あるいは「1」しか記録されていない場合など
  ],
  "Flow": {
    "ContactFlowId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "ContactFlowName": "TestFlow"
  },
  "Segments": [
    // ...
    {
      "SegmentType": "IVR",
      "Details": {
        "Prompt": "Please say or enter your account number.",
        "Input": "1", // 顧客が複数桁入力したにも関わらず、1桁しか認識されていない
        "RecognitionResult": "SUCCESS"
      },
      "StartTime": "2026-06-11T05:00:10.000Z",
      "EndTime": "2026-06-11T05:00:15.000Z"
    }
    // ...
  ]
}
```

## よくある原因と解決手順

### 原因1：タッチトーンバッファリングが無効になっている

Amazon Connectのコンタクトフローでタッチトーンバッファリング機能が明示的に有効化されていない場合、顧客がプロンプト再生中に先行入力したDTMFは失われます。これは、従来のIVRシステムの一般的な動作であり、顧客はプロンプトが終了してから入力を開始する必要がありました。

**Before（エラーが起きるコード）：**

```
# Amazon Connectコンタクトフローの「Set Touchtone Buffer Behavior」ブロックで
# 「Enable Buffering」がチェックされていない状態
# または、ブロック自体がフローに存在しない状態
```

**After（修正後）：**

```
# Amazon Connectコンタクトフローの「Set Touchtone Buffer Behavior」ブロックで
# 「Enable Buffering」をチェックする
```

**解決手順:**

1.  Amazon Connect管理画面にログインします。
2.  ナビゲーションペインから「ルーティング」->「コンタクトフロー」を選択します。
3.  対象のコンタクトフローを開きます。
4.  「インタラクション」カテゴリから「Set Touchtone Buffer Behavior」ブロックをフローに追加します（既に存在する場合はそれを選択）。
5.  ブロックの設定パネルで「Enable Buffering」オプションにチェックを入れます。
6.  フローを保存し、公開します。

### 原因2：「Play prompt」ブロックでスキップオプションが有効になっていない

タッチトーンバッファリングが有効になっていても、「Play prompt」ブロックで「Skip or interrupt this prompt when touchtone buffering is enabled」オプションが有効になっていない場合、バッファにDTMFが残っていてもプロンプトは最後まで再生されます。これにより、顧客は先行入力したにもかかわらず、プロンプトの終了を待つ必要が生じ、タイプアヘッドのメリットが十分に活かされません。

**Before（エラーが起きるコード）：**

```
# Amazon Connectコンタクトフローの「Play prompt」ブロックで
# 「Skip or interrupt this prompt when touchtone buffering is enabled」がチェックされていない状態
```

**After（修正後）：**

```
# Amazon Connectコンタクトフローの「Play prompt」ブロックで
# 「Skip or interrupt this prompt when touchtone buffering is enabled」をチェックする
```

**解決手順:**

1.  Amazon Connect管理画面にログインし、対象のコンタクトフローを開きます。
2.  先行入力によってスキップさせたい「Play prompt」ブロックを選択します。
3.  ブロックの設定パネルで「Skip or interrupt this prompt when touchtone buffering is enabled」オプションにチェックを入れます。
4.  フローを保存し、公開します。
    *注意点：常に再生する必要があるプロンプト（例：重要な注意事項、メニューの冒頭説明など）では、このオプションを無効のままにしておくべきです。*

### 原因3：DTMF入力がサポートされていないチャネルを使用している

タッチトーンバッファリングは、現時点では「音声（Voice）」チャネルのみでサポートされています。チャットやタスクなどの他のチャネルでDTMF入力を試みても、この機能は動作せず、入力は無視されるか、エラーブランチにルーティングされる可能性があります。

**Before（エラーが起きるコード）：**

```
# チャットやタスクチャネルでDTMF入力を期待するコンタクトフローを設計している
```

**After（修正後）：**

```
# 音声チャネルでDTMF入力を利用する
# または、チャットやタスクチャネルではテキスト入力やボタン選択など、
# そのチャネルに適した入力方法を利用する
```

**解決手順:**

1.  コンタクトフローがどのチャネルで利用されているかを確認します。
2.  DTMF入力によるタイプアヘッド機能を利用したい場合は、必ず音声チャネルでコンタクトフローを呼び出すようにします。
3.  チャットやタスクなどの非音声チャネルでは、DTMF入力に依存しない、そのチャネル固有の入力方法（テキスト入力、クイックリプライ、ボタンなど）を使用するようにコンタクトフローを設計し直します。

## ツール固有の注意点

Amazon Connectのタッチトーンバッファリングは、顧客体験を大幅に向上させる強力な機能ですが、いくつかのツール固有の注意点があります。

*   **バッファの容量制限:** バッファリングされるDTMFの桁数は最大30桁です。これを超える入力は無視されます。通常のIVR操作では十分な容量ですが、非常に長いIDなどを入力させる場合は考慮が必要です。
*   **「Get customer input」ブロックの動作:** このブロックは、バッファにDTMFが存在する場合、プロンプトを再生せずに自動的にバッファから入力を消費し、次のブロックに進みます。これにより、顧客はプロンプトを待つことなく、迅速に操作を進めることができます。
*   **「Play prompt」ブロックのスキップオプション:** 前述の通り、このオプションはデフォルトで無効です。重要な情報を含むプロンプトはスキップされないように、意図的に無効のままにしておく必要があります。
*   **ダイヤル文字列からの先行入力:** ウェブサイトやアプリからの発信（choose-to-call / app-to-call）の場合、ダイヤル文字列にDTMFを追加することで、通話接続時にバッファに先行入力させることが可能です。例えば、`tel:+15555555555,1234567` のようにすることで、`1234567` がバッファに格納されます。これは、顧客のコンテキストを事前に渡す際に非常に有用です。
*   **テストの重要性:** タッチトーンバッファリングを有効にした場合、従来のIVRとは動作が大きく変わる可能性があります。必ず実際の通話で、様々な入力パターン（早押し、複数桁入力、プロンプト途中での入力など）をテストし、意図した通りに動作することを確認してください。

## それでも解決しない場合

タッチトーンバッファリングの設定を確認しても問題が解決しない場合、以下の点を確認してください。

*   **コンタクトトレースレコード（CTRs）の確認:**
    *   Amazon Connectの管理画面で「分析と最適化」->「コンタクト検索」から対象のコンタクトIDを検索し、CTRsを確認します。
    *   `CustomerInput` セクションに、顧客が入力したDTMFが期待通りに記録されているかを確認します。
    *   `Segments` セクションの`IVR`タイプで、`Input`フィールドに何が記録されているかを確認します。
    *   `Flow`セクションで、どのコンタクトフローが実行されたか、エラーブランチにルーティングされていないかを確認します。
*   **CloudWatch Logsの確認:**
    *   Amazon Connectインスタンスに関連付けられたCloudWatch Logsグループを確認します。
    *   特に、コンタクトフロー内でLambda関数を呼び出している場合、Lambdaのログにエラーがないか確認します。
    *   コンタクトフローの「Set logging behavior」ブロックで詳細なログを有効にしている場合、より詳細なフローの実行状況が確認できます。
*   **デバッグコマンド/テストフローの利用:**
    *   問題が発生している箇所を特定するために、シンプルなテスト用コンタクトフローを作成し、段階的に機能を検証します。
    *   例えば、「Play prompt」ブロックと「Get customer input」ブロックのみで構成されたフローで、バッファリングのオン/オフによる動作の違いを再確認します。
*   **公式ドキュメントの参照:**
    *   Amazon Connectの公式ドキュメントは常に最新の情報が提供されています。タッチトーンバッファリングに関する最新の仕様や制限事項を確認してください。
        *   [Amazon Connect のタッチトーンバッファリングについて](https://docs.aws.amazon.com/connect/latest/adminguide/touchtone-buffering.html)
        *   [Set touchtone buffer behavior ブロック](https://docs.aws.amazon.com/connect/latest/adminguide/set-touchtone-buffer-behavior.html)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*