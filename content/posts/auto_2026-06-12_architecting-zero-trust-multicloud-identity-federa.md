---
title: "マルチクラウド環境におけるSPIFFE/SPIREのフェデレーションで発生するHTTPエラーの原因と解決策"
date: 2026-06-12
lastmod: 2026-06-12
draft: false
description: "マルチクラウド環境でSPIFFE/SPIREをフェデレーションする際に遭遇しがちなHTTPエラーについて、その原因と具体的な解決策を解説します。AWSとAzure間でのゼロトラストなID連携を確立し、安全なマイクロサービス間通信を実現するための実践的なヒントを提供します。"
tags: ["Dev.to - AWS"]
trend_incident: true
---

## エラーの概要

マルチクラウド環境でSPIFFE/SPIREをフェデレーションする際、マイクロサービス間の通信でHTTPエラーが発生することがあります。これは主に、SPIFFE IDの検証失敗、信頼バンドルの不整合、またはSPIREエージェントとの通信問題に起因します。具体的には、mTLSハンドシェイクの失敗や、期待されるSPIFFE IDと異なるIDでの接続試行などが挙げられます。

## 実際のエラーメッセージ例

SPIFFE/SPIREを利用したmTLS通信でエラーが発生した場合、アプリケーションのログやSPIREエージェントのログに以下のようなメッセージが出力されることがあります。

**Pythonアプリケーションのコンソール出力例:**

```
mTLS Connection failed or identity rejected: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain (_ssl.c:1129)
```

**SPIREエージェントのログ出力例 (Kubernetes環境):**

```json
{
  "level": "error",
  "time": "2024-06-12T10:00:00Z",
  "caller": "agent/manager/manager.go:XXX",
  "msg": "Failed to fetch X.509 SVID",
  "error": "rpc error: code = Unavailable desc = connection error: desc = \"transport: Error while dialing dial unix /run/spire/sockets/agent.sock: connect: no such file or directory\""
}
```

## よくある原因と解決手順

### 原因1：SPIREサーバー間の信頼バンドル同期の失敗

SPIFFEフェデレーションでは、異なるトラストドメインのSPIREサーバー間で信頼バンドル（公開鍵セット）を定期的に交換し、相互に検証できるようにする必要があります。この同期が正しく行われないと、リモートのSPIFFE IDを持つワークロードからの接続を検証できず、mTLSハンドシェイクが失敗します。

**なぜ発生するかの説明:**
SPIREサーバーの設定で、リモートのバンドルエンドポイントが誤っている、またはネットワークポリシーによってアクセスがブロックされている場合に発生します。

**Before（エラーが起きるコード）：**

```hcl
resource "kubernetes_config_map" "spire_server_config" {
  metadata {
    name      = "spire-server"
    namespace = "spire"
  }
  data = {
    "server.conf" = <<-EOT
      server {
          # ...
          trust_domain = "aws.enterprise.internal"
          # ...
      }
      federation {
          bundle_endpoint_profile "https_spiffe" {
              endpoint_spiffe_id = "spiffe://azure.enterprise.internal/spire/server"
              # 誤ったURL、または到達不能なURL
              endpoint_url = "https://spire-bundle.azure.enterprise.internal/spiffe/v1/bundle-wrong" 
          }
      }
    EOT
  }
}
```

**After（修正後）：**

```hcl
resource "kubernetes_config_map" "spire_server_config" {
  metadata {
    name      = "spire-server"
    namespace = "spire"
  }
  data = {
    "server.conf" = <<-EOT
      server {
          # ...
          trust_domain = "aws.enterprise.internal"
          # ...
      }
      federation {
          bundle_endpoint_profile "https_spiffe" {
              endpoint_spiffe_id = "spiffe://azure.enterprise.internal/spire/server"
              # 正しいバンドルエンドポイントURL
              endpoint_url = "https://spire-bundle.azure.enterprise.internal/spiffe/v1/bundle" 
          }
      }
    EOT
  }
}
```

### 原因2：ワークロードAPIへのアクセス失敗

アプリケーションがSPIREエージェントからSPIFFE ID（SVID）や信頼バンドルを取得するために、Workload APIを利用します。このAPIへのアクセスができない場合、アプリケーションはmTLSに必要な証明書情報を取得できず、通信を開始できません。

**なぜ発生するかの説明:**
Kubernetes環境では、SPIREエージェントのUnixドメインソケットがアプリケーションコンテナに正しくマウントされていない、または環境変数 `SPIFFE_ENDPOINT_SOCKET` が誤っている場合に発生します。

**Before（エラーが起きるコード）：**

```python
import os
# ...
# 環境変数が設定されていない、または誤っている
# os.environ["SPIFFE_ENDPOINT_SOCKET"] = "unix:///run/spire/sockets/agent.sock" 
# ...
```

**After（修正後）：**

```python
import os
# ...
# 正しいUnixドメインソケットパスを設定
os.environ["SPIFFE_ENDPOINT_SOCKET"] = "unix:///run/spire/sockets/agent.sock"
# ...
```

Kubernetes PodのYAML設定で、`volumeMounts` と `volumes` が正しく設定されていることを確認してください。

```yaml
# Pod定義の一部
spec:
  containers:
  - name: <your-app-container>
    image: <your-app-image>
    volumeMounts:
    - name: spire-agent-socket
      mountPath: /run/spire/sockets
  volumes:
  - name: spire-agent-socket
    hostPath:
      path: /run/spire/sockets # SPIRE Agentがソケットを公開するパス
      type: DirectoryOrCreate
```

### 原因3：アプリケーションによるSPIFFE IDの検証ロジックの不備

mTLS通信が確立された後、アプリケーションはピアのSPIFFE IDを検証し、認可ポリシーに基づいて接続を許可または拒否する必要があります。この検証ロジックが不十分であるか、期待するSPIFFE IDと実際のIDが一致しない場合に、アプリケーションレベルで接続が拒否されます。

**なぜ発生するかの説明:**
アプリケーションがピアの証明書からSPIFFE IDを正しく抽出し、定義された認可ポリシー（例：特定のSPIFFE IDのみを許可）と照合できていない場合に発生します。

**Before（エラーが起きるコード）：**

```python
# ...
def execute_federated_mtls_request(payload: bytes) -> None:
    # ...
    try:
        with urllib.request.urlopen(req, context=context) as response:
            print(f"Federated request successful. Status: {response.status}")
            # ピアのSPIFFE ID検証が不十分、または行われていない
            # peer_cert = response.fp.raw._sock.getpeercert()
            # san_entries = peer_cert.get('subjectAltName', [])
            # peer_spiffe_ids = [val for key, val in san_entries if key == 'URI']
            # if str(EXPECTED_AZURE_SPIFFE_ID) not in peer_spiffe_ids:
            #     raise PermissionError(f"Unauthorized peer identity: {peer_spiffe_ids}")
    except Exception as e:
        print(f"mTLS Connection failed or identity rejected: {str(e)}")
# ...
```

**After（修正後）：**

```python
# ...
def execute_federated_mtls_request(payload: bytes) -> None:
    # ...
    try:
        with urllib.request.urlopen(req, context=context) as response:
            print(f"Federated request successful. Status: {response.status}")
            # ピアの証明書からSPIFFE IDを抽出し、期待するIDと厳密に比較する
            peer_cert = response.fp.raw._sock.getpeercert()
            san_entries = peer_cert.get('subjectAltName', [])
            peer_spiffe_ids = [val for key, val in san_entries if key == 'URI']
            
            # 期待するSPIFFE IDがリストに含まれているか確認
            if str(EXPECTED_AZURE_SPIFFE_ID) not in peer_spiffe_ids:
                raise PermissionError(f"Unauthorized peer identity: {peer_spiffe_ids}. Expected: {EXPECTED_AZURE_SPIFFE_ID}")
            print(f"Peer identity {peer_spiffe_ids} successfully validated.")
    except Exception as e:
        print(f"mTLS Connection failed or identity rejected: {str(e)}")
# ...
```

## ツール固有の注意点

*   **AWS IAM Roles for Service Accounts (IRSA) と Azure Workload Identity:** SPIREサーバーがノードアテステーションを行う際、AWSではIRSA、AzureではWorkload Identityを利用します。これらのクラウド固有の認証メカニズムが正しく設定されていないと、SPIREサーバーがノードのアイデンティティを検証できず、SVIDの発行に失敗します。IAMロールやサービスアカウントのポリシー、OIDCプロバイダの設定を注意深く確認してください。
*   **Kubernetes ConfigMap:** SPIREサーバーの設定はKubernetesのConfigMapとしてデプロイされることが一般的です。ConfigMapの更新はPodの再起動を伴う場合があるため、設定変更後は関連するSPIREサーバーPodを再起動し、新しい設定が適用されていることを確認してください。
*   **ネットワークポリシー:** マルチクラウド環境では、異なるクラウドプロバイダ間の通信がファイアウォールやセキュリティグループによってブロックされることがあります。SPIREサーバー間のバンドル交換エンドポイント（通常HTTPS）や、ワークロード間のmTLS通信に必要なポートが適切に開放されていることを確認してください。

## それでも解決しない場合

1.  **SPIREサーバー/エージェントのログを確認:**
    *   SPIREサーバーのPodログ: `kubectl logs -n spire <spire-server-pod-name>`
    *   SPIREエージェントのPodログ: `kubectl logs -n spire <spire-agent-pod-name>`
    *   特に`ERROR`や`WARN`レベルのログに注目し、SVID発行失敗、バンドル同期エラー、アテステーションエラーなどの手がかりを探します。
2.  **SPIRE CLIツールでのデバッグ:**
    *   `spire-server bundle show`: SPIREサーバーが保持している信頼バンドルを確認し、リモートのトラストドメインのバンドルが含まれているか確認します。
    *   `spire-agent validate`: SPIREエージェントの接続状態やSVID取得状況を確認します。
    *   `spire-server entry show -spiffeID <your-spiffe-id>`: 期待するSPIFFE IDのエントリがSPIREサーバーに登録されているか確認します。
3.  **ネットワーク接続の確認:**
    *   SPIREサーバーからリモートのSPIREサーバーのバンドルエンドポイントへの疎通確認（例: `curl -v https://spire-bundle.azure.enterprise.internal/spiffe/v1/bundle`）。
    *   アプリケーションコンテナからSPIREエージェントのUnixソケットへのアクセス確認（例: コンテナ内で`ls -l /run/spire/sockets/agent.sock`）。
4.  **公式ドキュメントの参照:**
    *   [SPIFFE/SPIRE公式ドキュメント](https://spiffe.io/docs/)
    *   [SPIRE Federationに関するドキュメント](https://spiffe.io/docs/latest/spire/server-lifecycle/federation/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*