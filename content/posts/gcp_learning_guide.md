---
title: "GCPを体系的に学ぶ：6段階ロードマップ"
date: 2026-08-09
description: "Google Cloudを個別のエラー対処で終わらせず、認証情報とプロジェクト、APIの有効化、IAMの評価順序、サービスアカウント、ネットワークの到達性まで順序立てて学ぶためのロードマップを解説します。"
tags: ["GCP"]
images: ["og/posts/gcp_learning_guide.png"]
errorCode: ""
lastmod: 2026-08-09
service: "GCP"
error_type: "learning guide"
components: ["IAM", "VPC"]
related_services: []
trend_incident: false
---

> この記事にはアフィリエイト広告が含まれています。

## 冒頭まとめ

Google Cloudのエラーを検索して1件ずつ直しているのに、翌日は別のサービスで同じような壁に当たる。この繰り返しから抜けるには、覚える順序を変える必要があります。

Google Cloudのエラーの多くは、4つの境界のどこかで起きています。誰として呼んでいるかという境界、そのAPIがプロジェクトで有効になっているかという境界、何を許されているかという境界、そしてネットワークの到達性の境界です。エラー文はこの境界のどれで止まったかを示していますが、境界の存在を知らないと文言が読めません。

他のクラウドと比べたときの最大の違いは、2つ目です。Google Cloudでは、権限があってもAPIが有効でなければ呼べません。公式ドキュメントは、ほとんどのGoogle APIを使う前にGoogle Cloudプロジェクトで有効化する必要があると明記しています（[Service Usage overview](https://cloud.google.com/service-usage/docs/overview)）。この段階を知らないと、権限の設定を延々と見直すことになります。

学ぶ順序は、認証情報とプロジェクト、APIの有効化、IAMの評価順序、サービスアカウント、ネットワークの到達性、トラブルシューティングの6段階です。各段階には「次へ進む目安」を置きました。飛ばした段階は、後の段階のエラーとして別の顔で現れます。

## 個別に直すだけでは理解しにくい理由

検索で見つかる対処は、多くの場合その環境で有効だった手順です。なぜ有効だったかは書かれていないことがあります。

たとえば、アクセスが拒否されたときに編集者や所有者の役割を付けたら通った、という手順があります。確かにエラーは消えます。しかし何が足りなかったのかは分からないままです。次に同じ構成を作るとき、同じ広い役割を付けることになります。

同じことがAPIの有効化でも起きます。`gcloud services enable` を実行したら動いた、という手順は、それが権限の問題ではなく有効化の問題だったことを教えてくれません。区別できないままだと、次は逆の場面で有効化を試して時間を使います。

エラー文も同じです。Google Cloudの拒否は、認証に失敗したのか、APIが無効なのか、権限が無いのかを示しています。この区別は、次に説明する全体像を知っていれば読み取れます。

## 最初に理解するべきGoogle Cloudの全体像

先に、すべての操作が通る道筋を押さえます。ここを飛ばすと、後のすべての段階で判断がぶれます。

どのサービスへの操作も、同じ関門を順に通ります。第一に、どの認証情報を使うかが決まります。第二に、対象のプロジェクトが決まります。第三に、そのプロジェクトでそのAPIが有効かどうかが確認されます。第四に、その主体にその操作が許されているかが判定されます。

この4つは独立しています。認証情報が正しくてもAPIが無効なら止まります。APIが有効でも権限が無ければ止まります。順番に確認しないと、直したはずのものが直っていない状態が続きます。

もう1つ、資源の階層が重要です。組織、フォルダ、プロジェクト、そして個々の資源という階層があり、上位に設定した内容は下位へ引き継がれます。したがって、プロジェクトの設定だけを見ても答えが出ないことがあります。

まずは手元の環境が誰として、どのプロジェクトに対して動いているかを確認してください。

```bash
gcloud auth list
gcloud config list
```

`gcloud auth list` は有効なアカウントを、`gcloud config list` は対象プロジェクトとリージョンを示します。ここが想定と違えば、この先の調査はすべて無駄になります。

## 学習ステップ1：認証情報とプロジェクト

**何を理解する段階か**：認証情報がどこから読まれるか、そして `gcloud` と自分のコードで使われる認証情報が別であることです。

**なぜエラー解決に必要か**：`gcloud` では通るのにコードでは拒否される、という症状の大半はここです。

**最低限覚える概念**：アプリケーションのデフォルト認証情報（ADC）は、認証ライブラリが実行環境に応じて自動的に認証情報を探す仕組みです。公式ドキュメントによれば、ADCは次の場所を順に探します。`GOOGLE_APPLICATION_CREDENTIALS` 環境変数、`gcloud auth application-default login` コマンドで作られた認証情報ファイル、そしてメタデータサーバーが返す接続済みのサービスアカウントです（[How Application Default Credentials works](https://cloud.google.com/docs/authentication/application-default-credentials)）。

ここに重要な注意があります。公式ドキュメントは、gcloud CLI自体はGoogle Cloudの資源へアクセスするためにADCを使わないと明記しています（[Set up Application Default Credentials](https://cloud.google.com/docs/authentication/provide-credentials-adc)）。つまり `gcloud auth login` で入れた認証情報と、ライブラリが使う認証情報は別管理です。

この2つを混同すると、手元では `gcloud` が動くのにコードだけ認証エラーになる、という状況が生まれます。コードを動かすなら `gcloud auth application-default login` が必要です。

プロジェクトの指定も分かれます。`gcloud` の対象プロジェクトと、ADCが使う請求先プロジェクトは別々に決まります。

**実際に試すコマンド**：

```bash
# gcloud が使っているアカウントを確認する
gcloud auth list

# ADC が使う認証情報ファイルの有無を確認する
gcloud auth application-default print-access-token > /dev/null && echo "ADC あり"

# 対象プロジェクトとリージョンを確認する
gcloud config list

# ADC を設定する（ライブラリ用）
gcloud auth application-default login

# 環境変数に値が残っていないかを確認する
env | grep -i "GOOGLE_"
```

`GOOGLE_APPLICATION_CREDENTIALS` に古いファイルの経路が残っていると、それが最優先で使われます。「設定を直したのに変わらない」という状況の典型です。

**次の段階へ進む目安**：`gcloud` が使う認証情報とコードが使う認証情報の違いを説明できることです。

**関連して発生しやすいエラー**：`Could not automatically determine credentials` は、ADCがどの場所にも認証情報を見つけられなかった状態です。権限の問題ではありません。

## 学習ステップ2：APIの有効化

**何を理解する段階か**：権限とは別に、プロジェクトごとにサービスを有効化する必要があることです。

**なぜエラー解決に必要か**：この段階はGoogle Cloud固有で、他のクラウドから来た人が最初につまずく場所です。権限を疑って時間を使う前に、まずここを見ます。

**最低限覚える概念**：公式ドキュメントによれば、ほとんどのGoogle APIは使う前にGoogle Cloudプロジェクトで有効化する必要があります。一部のAPIとサービスはプロジェクト作成時に既定で有効になり、他のものはコンソールで使用したときに自動で有効になります（[Service Usage overview](https://cloud.google.com/service-usage/docs/overview)）。

有効化そのものにも権限が要ります。公式ドキュメントは、APIを有効化するには対象プロジェクトに対する `serviceusage.services.enable` 権限が必要だと述べています（[Cloud APIs getting started](https://cloud.google.com/apis/docs/getting-started)）。したがって「APIを有効にすればよい」と分かっても、自分にその権限が無ければ進めません。

無効化にも注意が要ります。公式ドキュメントは、サービスのAPIアクセスを無効にしても背後のデータは削除されず、課金は続くと述べています。またGKEのAPIを無効にすると、そのプロジェクトで動いているクラスターが停止状態になり、30日後に削除されるとも明記されています（[Enable and disable services](https://cloud.google.com/service-usage/docs/enable-disable)）。整理のつもりで無効化すると、取り返しがつかなくなります。

**実際に試すコマンド**：

```bash
# 有効になっているサービスを一覧する
gcloud services list --enabled

# 特定のサービスが有効かを確認する
gcloud services list --enabled --filter="config.name:compute.googleapis.com"

# 有効化できるサービスを検索する
gcloud services list --available --filter="NAME:pubsub"

# サービスを有効化する
gcloud services enable pubsub.googleapis.com
```

エラー本文に `SERVICE_DISABLED` や有効化用の画面へのリンクが含まれていれば、この段階で止まっています。権限の設定を見直す必要はありません。

**次の段階へ進む目安**：エラーを見て、APIの有効化の問題か権限の問題かを区別できることです。

**関連して発生しやすいエラー**：`accessNotConfigured` を伴う拒否は有効化の問題です。役割を足しても解消しません。

## 学習ステップ3：IAMの評価順序

**何を理解する段階か**：許可がどう決まるか、階層をどう引き継ぐか、そして拒否がどう優先されるかです。

**なぜエラー解決に必要か**：`PERMISSION_DENIED` は最も頻繁に見るエラーです。評価順序と階層を知らないと、役割を足しても通らない理由が分かりません。

**最低限覚える概念**：公式ドキュメントによれば、IAMはまず該当するプリンシパルアクセス境界ポリシーを確認し、次に該当するすべての拒否ポリシーを確認して、そのプリンシパルが権限を拒否されていないかを見ます。拒否ポリシーが妨げていない場合にのみ、次の段階へ進んで許可ポリシーを確認します（[IAM policy types](https://cloud.google.com/iam/docs/policy-types)）。つまり拒否が先に評価され、そこで止まれば許可は見られません。

階層の引き継ぎも押さえてください。公式ドキュメントは、資源が親の許可ポリシーを継承すること、そしてある資源に対する実効的な許可ポリシーが、その資源に設定された許可ポリシーと親から継承した許可ポリシーの和集合であることを明記しています（[Using resource hierarchy for access control](https://cloud.google.com/iam/docs/resource-hierarchy-access-control)）。

拒否ポリシーも同じく階層を通じて継承されます。公式ドキュメントによれば、組織の拒否ポリシーがある権限を使えないと定めれば、その組織内のどの資源に対してもその権限は使えません。これは配下のフォルダやプロジェクトがより緩やかな拒否ポリシーを持っていても適用されます（[Deny policies](https://cloud.google.com/iam/docs/deny-overview)）。

ここから2つのことが言えます。プロジェクトで役割を付けても、上位に拒否があれば通りません。逆に、プロジェクトで役割を外しても、上位で付与されていれば通ります。

**実際に試すコマンド**：

```bash
# プロジェクトの許可ポリシーを確認する
gcloud projects get-iam-policy <プロジェクトID>

# 特定の主体に絞って確認する
gcloud projects get-iam-policy <プロジェクトID> \
  --flatten="bindings[].members" \
  --filter="bindings.members:<メールアドレス>" \
  --format="table(bindings.role)"

# 上位階層の設定も確認する
gcloud resource-manager folders get-iam-policy <フォルダID>
gcloud organizations get-iam-policy <組織ID>

# 拒否ポリシーを一覧する
gcloud iam policies list --attachment-point=cloudresourcemanager.googleapis.com/projects/<プロジェクトID> --kind=denypolicies
```

なぜ拒否されたかを機械的に調べる手段も用意されています。コンソールのポリシーアナライザは、どの階層のどのポリシーが結果に効いたかを示します。手当たり次第に役割を足す前に、これで確認してください。

**次の段階へ進む目安**：`PERMISSION_DENIED` を見たときに、許可が無いのか拒否があるのか、そしてどの階層を見るべきかを言えることです。

**関連して発生しやすいエラー**：本文には多くの場合、どの主体がどの権限を欠いているかが含まれます。この2点をそのまま読んでください。推測で役割を広げるより速く進みます。

## 学習ステップ4：サービスアカウント

**何を理解する段階か**：自分の権限と、処理が使う権限が別物であることです。

**なぜエラー解決に必要か**：自分は所有者なのに、動かした処理が拒否される。この状況はこの層の理解不足で起きます。

**最低限覚える概念**：Cloud RunやCompute Engineのような環境では、あなたの認証情報ではなく、その資源に紐づいたサービスアカウントの権限で動きます。前の段階で見たADCの探索順序の3番目、メタデータサーバーが返す接続済みのサービスアカウントがこれに当たります。

したがって確認すべき対象は2つあります。あなたがその資源を作ったり動かしたりできるか、そしてその資源に紐づいたサービスアカウントが目的のAPIを呼べるかです。

さらにもう1段あります。あるサービスアカウントを資源に紐づけるには、あなた自身がそのサービスアカウントを使う権限を持っている必要があります。サービスアカウントが持つ権限と、それを使ってよいという権限は別です。

前段階で見た評価順序はここでも同じです。サービスアカウントに役割が無ければ拒否され、上位に拒否があれば役割があっても拒否されます。

**実際に試すコマンド**：

```bash
# プロジェクトのサービスアカウントを一覧する
gcloud iam service-accounts list

# 資源に紐づいているサービスアカウントを確認する（Cloud Run の例）
gcloud run services describe <サービス名> --region=<リージョン> \
  --format='value(spec.template.spec.serviceAccountName)'

# そのサービスアカウントに付いている役割を調べる
gcloud projects get-iam-policy <プロジェクトID> \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:<サービスアカウントのメールアドレス>" \
  --format="table(bindings.role)"

# サービスアカウント自体のポリシー（誰が使ってよいか）を確認する
gcloud iam service-accounts get-iam-policy <サービスアカウントのメールアドレス>
```

自分の権限で試して通っても、それは何の証明にもなりません。実際に動く主体で確認してください。

**次の段階へ進む目安**：拒否されたときに、自分の権限の問題かサービスアカウントの権限の問題かを、エラー本文の主体から判断できることです。

**関連して発生しやすいエラー**：サービスアカウントの鍵ファイルを配布して解決する手順が広く共有されていますが、鍵は漏れると取り消すまで有効です。可能なら鍵を作らず、資源に紐づける方式を選んでください。

## 学習ステップ5：ネットワークの到達性

**何を理解する段階か**：通信の既定がどうなっているかと、規則の優先順位です。

**なぜエラー解決に必要か**：「繋がらない」という症状は、権限のエラーと違って明示的なメッセージが出ないまま時間切れになります。既定を知らないと、どこから見ればよいか決まりません。

**最低限覚える概念**：VPCには削除できない暗黙の規則があります。公式ドキュメントによれば、受信方向の暗黙の動作は拒否で、送信方向の暗黙の動作は許可です（[Evaluation order for firewall policies and rules](https://cloud.google.com/firewall/docs/firewall-policies-rule-eval-order)）。つまり外から入る通信は明示的に許可しない限り届かず、中から出る通信は明示的に拒否しない限り通ります。

そして状態の扱いです。公式ドキュメントは、あるVMが送った通信に対する応答が許可される理由として、ファイアウォール規則が状態を持つためだと説明しています（[VPC firewall rules](https://cloud.google.com/firewall/docs/firewalls)）。したがって、接続を開始する向きにだけ規則を書けば、戻りの通信は自動的に通ります。

優先順位も押さえてください。数値が小さいほど優先度が高く、同じ優先度で動作が異なる規則が両方一致した場合は拒否が適用されます。

**実際に試すコマンド**：

```bash
# ネットワークの規則を優先度順に一覧する
gcloud compute firewall-rules list --sort-by=priority \
  --format="table(name,direction,priority,sourceRanges.list(),allowed[].map().firewall_rule().list())"

# 特定の規則の中身を確認する
gcloud compute firewall-rules describe <規則名>

# 対象 VM に付いているネットワークタグを確認する
gcloud compute instances describe <インスタンス名> --zone=<ゾーン> \
  --format='value(tags.items)'

# 到達性を自動で判定する
gcloud network-management connectivity-tests create <テスト名> \
  --source-instance=<送信元> --destination-instance=<宛先> \
  --destination-port=443 --protocol=TCP
```

規則を1つずつ目で追うのは間違いやすい作業です。到達性の判定機能を使うと、どこで止まっているかを機械的に特定できます。全開放して切り分ける方法は避けてください。開けた状態のまま戻し忘れることがあります。

**次の段階へ進む目安**：応答が返らない場合に、規則の優先順位とタグの一致を確認する手順を言えることです。

**関連して発生しやすいエラー**：接続が拒否される場合は相手まで届いています。応答が返らないまま時間切れになる場合は、経路のどこかで破棄されています。この2つは調べる場所が違います。

## 学習ステップ6：失敗時の確認順序

**何を理解する段階か**：エラーが出たときに、どの順番で何を見るかです。

**なぜエラー解決に必要か**：ここまでの5段階は、この順序を実行するための前提知識です。順序が決まっていれば、初めて見るサービスのエラーでも調べる範囲を絞れます。

**確認の順序**：

第一に、認証情報と対象プロジェクトを確認します。

```bash
gcloud auth list
gcloud config list
```

第二に、エラー全文を読みます。Google Cloudの拒否は構造化されており、理由を示す語や、対処用の画面へのリンクが含まれることがあります。ここに有効化用のリンクがあれば、それだけで判断がつきます。

第三に、APIが有効かを確認します。権限を調べる前にここを通してください。

```bash
gcloud services list --enabled --filter="config.name:<サービス名>"
```

第四に、権限を評価順序に沿って調べます。拒否が先、許可が後です。プロジェクトだけでなく上位階層も見ます。

第五に、動いている主体を確認します。自分の権限ではなく、資源に紐づいたサービスアカウントの権限が使われている場合があります。

第六に、通信が関わる場合は到達性を確認し、そのうえで記録を読みます。

```bash
# 直近の拒否や失敗を検索する
gcloud logging read 'severity>=ERROR' --limit=20 --freshness=1h

# 監査ログから、誰がどの操作を呼んだかを確認する
gcloud logging read 'logName:"cloudaudit.googleapis.com%2Factivity"' --limit=20
```

監査ログには拒否された呼び出しも残ります。どの主体として呼ばれたかを確認できるため、認証情報の取り違えを裏付けるのに使えます。

より詳しい記録が必要な場合は、CLIの出力を増やせます。

```bash
gcloud services list --enabled --log-http 2> gcloud-debug.log
```

この記録には認証に関わる情報が含まれます。そのまま共有しないでください。

**次の段階へ進む目安**：初めて見るエラーに対して、この6段階のどこから調べるかを即座に決められることです。

**避けるべき対処**：所有者や編集者の役割を付けて通す、ファイアウォールを全開放する、サービスアカウントの鍵を作って配布する、不要に見えるAPIを無効化して整理する、といった手順は、症状を消しても原因を残します。特に鍵の配布とAPIの無効化は、戻し忘れや副作用が直接の事故につながります。切り分けのために一時的に緩める場合は、戻す手順を先に決めてから行ってください。

## 独学と動画講座の使い分け

ここまでの6段階は、公式ドキュメントと手元のプロジェクトだけでも進められます。実際、この記事で参照した仕様はすべて公式ドキュメントに書かれています。

独学が向いているのは、目的が明確な場合です。特定のエラーを直す、特定のAPIの引数を確認する、といった作業は、公式ドキュメントを直接読むのが最短です。

一方でGoogle Cloudは、独学の初期に迷いやすい構造をしています。サービスの数が多いうえ、認証、有効化、権限という3つの関門が独立しているため、どれが原因かを切り分ける経験が要ります。加えて、手を動かして確かめると費用が発生します。

動画講座は、学ぶ順序と演習用の構成がまとまっている点が違います。何をどこまで作って確認するかが決まっていれば、消し忘れも減らせます。反面、自分に必要な部分だけを選んで進めるのは難しくなります。

どちらが適しているかは、いま何に時間を取られているかで決まります。仕様が分からなくて止まっているなら公式ドキュメント、何から手を付けるか決められなくて止まっているなら講座、という切り分けが実際的です。

## 学習後に自力で確認できるようにしたいこと

到達点を具体的に置いておきます。以下を自分の環境で確認できるようになっていれば、この記事の範囲は終わりです。

`gcloud` が使う認証情報とコードが使う認証情報の違いを説明できる。ADCがどの順で認証情報を探すかを言える。エラーを見て、APIの有効化の問題か権限の問題かを区別できる。拒否が許可より先に評価されること、そして許可も拒否も階層を通じて継承されることを説明できる。自分の権限と資源に紐づいたサービスアカウントの権限が別物であることを説明できる。受信が既定で拒否、送信が既定で許可であること、そして規則が状態を持つことを説明できる。初めて見るエラーに対して、認証情報とプロジェクト、エラー全文、APIの有効化、権限、主体、到達性と記録の順で調べられる。

これらは暗記ではなく、手を動かして確認する操作です。費用のかからない範囲から1つずつ試してください。

## まとめ

Google Cloudのエラーが繰り返し起きるのは、サービスを知らないからではなく、境界を知らないからです。誰として呼んでいるか、APIが有効か、何を許されているか、そしてネットワークの到達性。この4つの境界を押さえると、エラー文の読み方が変わります。

特に2つ目は他のクラウドに無い関門です。権限を疑う前にAPIの有効化を確認する、という順序を身に付けるだけで、無駄な調査がかなり減ります。

学ぶ順序は、認証情報とプロジェクト、APIの有効化、IAMの評価順序、サービスアカウント、ネットワークの到達性、トラブルシューティングです。それぞれに「次へ進む目安」を置いたのは、飛ばした段階が後から別の顔で現れるからです。

公式ドキュメントは仕様の確認先として最も確実です。一方で、学ぶ順序や演習用の環境を自分で組み立てる負担が大きいと感じる場合は、順序と演習がまとまった教材を使う選択肢もあります。

[Google Cloudを体系的に学べるUdemy講座を確認する（PR）](https://trk.udemy.com/1GVjKg)

内容や価格、対象範囲はリンク先のページで確認してください。自分がいまどの段階で止まっているかを踏まえて、必要な範囲が含まれているかを見るのが選び方の基準になります。

## 参考資料

- [How Application Default Credentials works](https://cloud.google.com/docs/authentication/application-default-credentials)
- [Set up Application Default Credentials](https://cloud.google.com/docs/authentication/provide-credentials-adc)
- [Service Usage overview](https://cloud.google.com/service-usage/docs/overview)
- [Enable and disable services](https://cloud.google.com/service-usage/docs/enable-disable)
- [Cloud APIs getting started](https://cloud.google.com/apis/docs/getting-started)
- [IAM policy types](https://cloud.google.com/iam/docs/policy-types)
- [Using resource hierarchy for access control](https://cloud.google.com/iam/docs/resource-hierarchy-access-control)
- [Deny policies](https://cloud.google.com/iam/docs/deny-overview)
- [VPC firewall rules](https://cloud.google.com/firewall/docs/firewalls)
- [Evaluation order for firewall policies and rules](https://cloud.google.com/firewall/docs/firewall-policies-rule-eval-order)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアや講座の内容、価格、提供条件は予告なく変更されることがあります。最新の情報はGoogle Cloud公式ドキュメントおよびリンク先の講座ページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*