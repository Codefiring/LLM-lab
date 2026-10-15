## 用一个普通 OAuth 服务器,反而比自签那套简单

设定:服务 id `oauth-http`,控制面外部地址 `https://host:8443`,IdP 用一个常规的托管 OAuth 服务器(Auth0 / Okta / Keycloak / Entra ID 都是这个形状)。

**先说省掉的一步**:之前那套要 `export NODE_EXTRA_CA_CERTS=$I/ca.pem`,那**纯粹是因为 Dex 用自签证书**。换成一个有正经公共证书的 IdP,这一步不需要 —— 控制面去取 metadata / JWKS 时 TLS 就直接通。(这也是那一步最值得记住的地方:只有自签 IdP 才需要它,漏了的症状是每个请求都像 token 不对,其实是取 JWKS 失败。)

### 第 1 步:在 IdP 里把这个服务登记成一个 API / resource

名字各家不同,实质一样 —— 你要登记一个 **identifier**,它必须是这个服务自己的 URL:

```
https://host:8443/mcp/oauth-http
```

| IdP | 叫法 |
| --- | --- |
| Auth0 | API 的 **Identifier**(就是 `audience`) |
| Keycloak | client 的 **Audience mapper** / client scope |
| Okta | **Authorization Server** 的 audience |
| Entra ID | **Application ID URI** |

然后在这个 API 下定义你要求的 scope,比如 `mcp:invoke`。

**要紧的是:token 的 `aud` 是这个服务的 URL,不是 IdP 的地址,也不是控制面根地址。** token 是按资源发的 —— 一个服务的 token 拿去打另一个服务**必须被拒**。验证集里专门造了一个 audience 指向 `.../mcp/oauth-http-elsewhere` 的 client 来钉死这条:签名对、没过期、但 audience 指向别处的 token,如果能过,那"验过了"就只等于"这个 IdP 发的",所有服务就互相穿透了。

### 第 2 步:注册一个 client,拿 token

**机器对机器(client credentials)** —— 这是正经做法,不是捷径:

```bash
TOKEN=$(curl -s https://tenant.us.auth0.com/oauth/token \
  -H 'content-type: application/json' \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "audience": "https://host:8443/mcp/oauth-http"
  }' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
```

Keycloak 的形状是表单而不是 JSON:

```bash
TOKEN=$(curl -s https://idp.example.com/realms/main/protocol/openid-connect/token \
  -d grant_type=client_credentials \
  -d client_id=mcp-oauth-http -d client_secret=... \
  -d 'scope=mcp:invoke' \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
```

**有真实用户时**:authorization code + PKCE,拿到的 `access_token` 形状一样,后面的用法完全不变。(前面例子里的 password grant 只是为了一条命令跑完、不开浏览器 —— 复现捷径,别用在真客户端上。)

拿到后值得先解一下 payload 核三件事,比瞎试快得多:

```bash
echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | python3 -m json.tool
```

看 `iss`、`aud`、`scope` 对不对。**`iss` 有个经典坑**:Auth0 的 issuer 带结尾斜杠(`https://tenant.us.auth0.com/`),配置里写成不带的话,比对就不相等。

### 第 3 步:客户端怎么传这个头 —— 就是一个普通 HTTP 头

streamable-http 传输本身就是 HTTP POST,OAuth 头没有任何特殊之处:

```bash
curl -s -X POST https://host:8443/mcp/oauth-http \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize",
       "params":{"protocolVersion":"2025-06-18","capabilities":{},
                 "clientInfo":{"name":"curl","version":"0"}}}'
```

两个和 OAuth 无关但常一起踩的头:**`accept` 必须同时列 `application/json` 和 `text/event-stream`**(服务端可以选择用 SSE 回),`content-type: application/json` 不能省。

SDK 里头是在 transport 构造时给的:

```ts
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const transport = new StreamableHTTPClientTransport(
  new URL('https://host:8443/mcp/oauth-http'),
  { requestInit: { headers: { authorization: `Bearer ${token}` } } },
);
const client = new Client({ name: 'demo', version: '0' });
await client.connect(transport);   // initialize 就带着这个头发出去
```

**每个后续请求都要带,不只是 `initialize`。** OAuth 这层没有"登录一次建立会话"的概念 —— MCP 的会话 id 是另一回事,鉴权是每请求的。所以 token 过期(client credentials 常见 1 小时)时,**会话中途就开始 401**,客户端得自己重新取 token;上面那种"构造时塞一个固定字符串"的写法在长连接里会到点就断,生产里该换成每次请求取一个缓存的、会自动刷新的 token。

### 第 4 步:到达服务那边时

网关按配置里的 `issuer` / `resource` / `requiredScopes` 校验,过了才转发给内部那个只听内部端口的服务。

- **被托管的服务完全不懂 OAuth** —— 它收到的是一个已被放行的内部请求
- scope 不够 → 网关拒,服务根本不被打扰("token 有效"和"token 够用"是两件事)
- `aud` 指向别处 → 拒
- **stdio 那一档也能配 `gateway-oauth`** —— 校验在网关,那个 stdio 进程压根不知道有这回事

### 对照:要让后端自己验的话

那是 `backend-passthrough` —— 网关**不验**,把客户端凭据原样转给下游。它是文档里写明的唯一会转发凭据的模式,所以必须显式选,不是默认。那条路上客户端按后端自己的要求给头,网关只是管道。

## 一个真实缺口,先别假定能用

如果你要的是**服务里知道是哪个用户在调**:stdio 那一档理论上有签名身份上下文(ed25519,密钥文件权限必须 0600 否则拒绝启动)。但 `auth.stdioAuthContext` 虽然在域类型里存在、也有测试,`src/api/server-configuration.ts` 从注册体里只搬 `mode` / `issuer` / `resource` / `requiredScopes` 出来 —— **目前没法通过 HTTP 注册让一个 stdio 服务开启它**。断言表原先声称 `gateway-oauth` 下签名上下文会到达服务,对 stdio 情况不成立,这条是文档工作里纠正过的。

## 侧问里核不了的

- `auth` 段的**确切字段名和层级**,以及一份能直接 POST 的注册体
- 网关**有没有做 OAuth discovery**:401 时 `WWW-Authenticate` 返回什么、有没有 `/.well-known/oauth-protected-resource`。这决定了符合规范的 MCP 客户端(比如 Claude Desktop 这类)能不能**自动**走完发现 → 注册 → PKCE → 取 token,而不用你手工塞头 —— 对"用普通 OAuth 服务器"这个场景,这恰恰是最值得确认的一条
- `resource` 是按 RFC 8707 的 resource indicator 比,还是直接比 `aud`

这几条要读 `src/auth/policy.ts` 和 `src/api/server-configuration.ts`,侧问里没法查。到主对话里问,那边能给你确定的字段名和一份跑得通的注册体 —— 上面第 1–3 步的形状不会变,变的只是配置怎么写。