可以。
在你这个场景里，**MCP client 负责先去 OAuth token endpoint 拿 access token**，然后在连接 MCP server 的 `/sse` 和调用 `/messages` 时带上：

```http
Authorization: Bearer <access_token>
```

所以 **MCP server 侧要做的事** 不是自己发起 OAuth 登录，而是：

1. 从请求头里取 `Bearer Token`
2. 校验 token 是否有效
3. 可选校验 `scope`
4. 校验通过后，才允许访问 `/sse` 和 `/messages`

也就是说，这里更准确地说是：**给 MCP server 加入 Bearer Token 鉴权与 OAuth token 验证流程**。

下面我直接把你的代码改成一个可用版本，支持两种校验方式：

* **开发模式**：直接接受固定 token
* **OAuth introspection 模式**：调用你前面那个 Python mock OAuth server 的 `/oauth/introspect`

---

# 修改后的 MCP Server 代码

```python
import os
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Mount, Route


class OAuthBearerMiddleware(BaseHTTPMiddleware):
    """
    为 /sse 和 /messages 路径增加 Bearer Token 校验。

    支持两种模式：
    1. 本地固定 token 校验（DEV 模式）
    2. 调用 OAuth introspection endpoint 校验
    """

    def __init__(
        self,
        app,
        *,
        protected_prefixes=None,
        introspection_url: Optional[str] = None,
        required_scope: Optional[str] = None,
        dev_bearer_token: Optional[str] = None,
        introspection_client_id: Optional[str] = None,
        introspection_client_secret: Optional[str] = None,
    ):
        super().__init__(app)
        self.protected_prefixes = protected_prefixes or ["/sse", "/messages"]
        self.introspection_url = introspection_url
        self.required_scope = required_scope
        self.dev_bearer_token = dev_bearer_token
        self.introspection_client_id = introspection_client_id
        self.introspection_client_secret = introspection_client_secret

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 只保护 MCP transport 相关路径
        if not any(path.startswith(prefix) for prefix in self.protected_prefixes):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "error": "missing_bearer_token",
                    "error_description": "Authorization: Bearer <token> is required.",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[len("Bearer ") :].strip()
        if not token:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "invalid_bearer_token",
                    "error_description": "Bearer token is empty.",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 方式 1：开发模式，直接校验固定 token
        if self.dev_bearer_token:
            if token != self.dev_bearer_token:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "invalid_token",
                        "error_description": "Bearer token is invalid.",
                    },
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # 开发模式下 scope 不做强校验，直接放过
            return await call_next(request)

        # 方式 2：OAuth introspection
        if self.introspection_url:
            ok, error_response = await self._validate_by_introspection(token)
            if not ok:
                return error_response

            return await call_next(request)

        # 两种模式都没配置，默认拒绝
        return JSONResponse(
            status_code=500,
            content={
                "error": "server_oauth_not_configured",
                "error_description": "No OAuth validation mode is configured.",
            },
        )

    async def _validate_by_introspection(self, token: str):
        form_data = {"token": token}

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        auth = None
        if self.introspection_client_id and self.introspection_client_secret:
            auth = (self.introspection_client_id, self.introspection_client_secret)

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    self.introspection_url,
                    data=form_data,
                    headers=headers,
                    auth=auth,
                )
        except Exception as e:
            return False, JSONResponse(
                status_code=502,
                content={
                    "error": "introspection_unavailable",
                    "error_description": f"Failed to call introspection endpoint: {str(e)}",
                },
            )

        if response.status_code != 200:
            return False, JSONResponse(
                status_code=401,
                content={
                    "error": "invalid_token",
                    "error_description": f"Introspection endpoint returned HTTP {response.status_code}.",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        payload = response.json()
        if not payload.get("active", False):
            return False, JSONResponse(
                status_code=401,
                content={
                    "error": "invalid_token",
                    "error_description": "Token is inactive or expired.",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        if self.required_scope:
            granted_scope = payload.get("scope", "")
            granted_scopes = set(granted_scope.split()) if granted_scope else set()
            if self.required_scope not in granted_scopes:
                return False, JSONResponse(
                    status_code=403,
                    content={
                        "error": "insufficient_scope",
                        "error_description": f"Required scope '{self.required_scope}' is missing.",
                    },
                    headers={"WWW-Authenticate": f'Bearer scope="{self.required_scope}"'},
                )

        return True, None


# Create a vulnerable MCP server for Challenge 2: Tool Poisoning with SSE support
class Challenge2Server:
    def __init__(self):
        self.name = "Challenge 2 - Tool Poisoning"
        self.port = int(os.getenv("MCP_SERVER_PORT", "9002"))
        self.mcp = FastMCP(self.name)
        self.app = FastAPI()

        # ----------------------------
        # OAuth / Bearer Token 配置
        # ----------------------------
        #
        # 方式 A：固定 token 开发模式
        #   export DEV_BEARER_TOKEN=mock-token-xxx
        #
        # 方式 B：OAuth introspection 模式
        #   export OAUTH_INTROSPECTION_URL=http://127.0.0.1:8000/oauth/introspect
        #   export OAUTH_REQUIRED_SCOPE=mcp:read
        #
        # 可选：如果 introspection endpoint 自己也需要 client 认证
        #   export OAUTH_INTROSPECTION_CLIENT_ID=your-client-id
        #   export OAUTH_INTROSPECTION_CLIENT_SECRET=your-client-secret
        #
        dev_bearer_token = os.getenv("DEV_BEARER_TOKEN")
        introspection_url = os.getenv("OAUTH_INTROSPECTION_URL")
        required_scope = os.getenv("OAUTH_REQUIRED_SCOPE", "mcp:read")
        introspection_client_id = os.getenv("OAUTH_INTROSPECTION_CLIENT_ID")
        introspection_client_secret = os.getenv("OAUTH_INTROSPECTION_CLIENT_SECRET")

        self.app.add_middleware(
            OAuthBearerMiddleware,
            protected_prefixes=["/sse", "/messages"],
            introspection_url=introspection_url,
            required_scope=required_scope,
            dev_bearer_token=dev_bearer_token,
            introspection_client_id=introspection_client_id,
            introspection_client_secret=introspection_client_secret,
        )

        @self.app.get("/health")
        async def health():
            return {
                "status": "ok",
                "server": self.name,
                "oauth": {
                    "dev_bearer_token_enabled": bool(dev_bearer_token),
                    "introspection_enabled": bool(introspection_url),
                    "required_scope": required_scope,
                },
            }

        @self.app.get("/")
        async def root():
            return {
                "name": self.name,
                "message": "MCP server is running.",
                "sse_endpoint": f"http://localhost:{self.port}/sse",
                "messages_endpoint": f"http://localhost:{self.port}/messages",
            }

        # Add a vulnerable tool that doesn't validate input properly
        @self.mcp.tool()
        def execute_command(command: str) -> str:
            """Execute a system command (restricted to safe commands only)

            Args:
                command: The command to execute (only 'ls', 'pwd', 'whoami', 'date' allowed)
            """
            safe_commands = ["ls", "pwd", "whoami", "date"]

            if command.split()[0] in safe_commands:
                import subprocess

                try:
                    result = subprocess.check_output(command, shell=True, text=True)
                    return f"Command output:\n{result}"
                except Exception as e:
                    return f"Error executing command: {str(e)}"
            else:
                return f"Error: Command '{command}' is not allowed. Only {', '.join(safe_commands)} are permitted."

        # Add a tool for file operations
        @self.mcp.tool()
        def read_file(filename: str) -> str:
            """Read a file from the system (restricted to safe files only)

            Args:
                filename: The file to read (only files in /tmp/safe/ allowed)
            """
            if filename.startswith("/tmp/safe/"):
                try:
                    with open(filename, "r") as f:
                        return f.read()
                except Exception as e:
                    return f"Error reading file: {str(e)}"
            else:
                return f"Error: Access to '{filename}' is not allowed. Only files in /tmp/safe/ are accessible."

        self.mount_sse_server()

    def mount_sse_server(self):
        """Mount the SSE server to the FastAPI app"""
        self.app.mount("/", self.create_sse_server())

    def create_sse_server(self):
        """Create a Starlette app that handles SSE connections and message handling"""
        transport = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with transport.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await self.mcp._mcp_server.run(
                    streams[0],
                    streams[1],
                    self.mcp._mcp_server.create_initialization_options(),
                )

        routes = [
            Route("/sse", endpoint=handle_sse),
            Mount("/messages", app=transport.handle_post_message),
        ]

        return Starlette(routes=routes)

    def run(self):
        """Run the server with uvicorn"""
        import uvicorn

        print(f"Starting {self.name} MCP Server")
        print(f"Server running at http://localhost:{self.port}")
        print(f"SSE endpoint available at http://localhost:{self.port}/sse")
        print(f"Messages endpoint available at http://localhost:{self.port}/messages")
        print("OAuth config:")
        print(f"  DEV_BEARER_TOKEN set: {bool(os.getenv('DEV_BEARER_TOKEN'))}")
        print(f"  OAUTH_INTROSPECTION_URL: {os.getenv('OAUTH_INTROSPECTION_URL')}")
        print(f"  OAUTH_REQUIRED_SCOPE: {os.getenv('OAUTH_REQUIRED_SCOPE', 'mcp:read')}")

        uvicorn.run(self.app, host="0.0.0.0", port=self.port)


if __name__ == "__main__":
    server = Challenge2Server()
    server.run()
```

---

# 这段代码做了什么

核心变化只有一件事：

**在 `/sse` 和 `/messages` 之前加了一层 Bearer Token 中间件。**

也就是：

* MCP client 先去 token endpoint 拿 token
* 之后连接 `/sse`
* 再调用 `/messages`
* server 都会检查 `Authorization: Bearer ...`

如果 token 不合法，就直接返回 401/403。

---

# 你的整体调用链会变成这样

## 1. 启动 mock OAuth server

你前面那个 Flask mock server 跑在：

```bash
http://127.0.0.1:8000
```

token endpoint:

```bash
http://127.0.0.1:8000/oauth/token
```

introspection endpoint:

```bash
http://127.0.0.1:8000/oauth/introspect
```

---

## 2. 启动 MCP server，并让它用 introspection 校验 token

Linux / macOS:

```bash
export OAUTH_INTROSPECTION_URL=http://127.0.0.1:8000/oauth/introspect
export OAUTH_REQUIRED_SCOPE=mcp:read
python your_mcp_server.py
```

Windows PowerShell:

```powershell
$env:OAUTH_INTROSPECTION_URL="http://127.0.0.1:8000/oauth/introspect"
$env:OAUTH_REQUIRED_SCOPE="mcp:read"
python .\your_mcp_server.py
```

---

## 3. MCP client 配置 OAuth 参数

类似：

```bash
--oauth-client-id your-client-id \
--oauth-client-secret your-client-secret \
--oauth-token-url http://127.0.0.1:8000/oauth/token \
--oauth-scope "mcp:read"
```

---

## 4. MCP client 拿到 token 后访问 MCP server

请求会带：

```http
Authorization: Bearer mock-token-xxxx
```

服务端中间件会调用：

```bash
POST http://127.0.0.1:8000/oauth/introspect
token=<mock-token-xxxx>
```

如果返回：

```json
{
  "active": true,
  "client_id": "your-client-id",
  "scope": "mcp:read",
  "token_type": "Bearer",
  "exp": 9999999999
}
```

就放行。

---

# 如果你只想先做最简单联调

不想依赖 introspection，也可以用固定 token 模式。

比如先设置：

```bash
export DEV_BEARER_TOKEN=test-token
python your_mcp_server.py
```

然后任何带：

```http
Authorization: Bearer test-token
```

的 `/sse` 和 `/messages` 请求都会通过。

这种适合先验证：

* MCP client 会不会带 Authorization 头
* MCP transport 能不能在有鉴权的情况下正常工作

---

# 你需要额外安装的依赖

因为上面代码里加了 `httpx`，所以还需要：

```bash
pip install httpx
```

如果你还没装这些，一起装：

```bash
pip install fastapi starlette uvicorn httpx
```

---

# 一个很重要的说明

你这里加上的不是完整的“OAuth 登录页流程”，而是 **OAuth 资源服务器校验流程**。

也就是说：

* **OAuth server** 负责发 token
* **MCP client** 负责拿 token
* **MCP server** 负责验 token

这才是这里最合理的职责分工。

---

# 这个方案的局限

这个版本适合本地联调，但还不是完整生产级方案，因为它还没有：

* JWKS / JWT 本地验签
* issuer / audience 严格校验
* 缓存 introspection 结果
* 细粒度 scope 到 tool 的授权控制
* 不同 tool 的 RBAC 权限模型

生产里更常见的是：

* access token 是 JWT
* MCP server 本地验签
* 再检查 `iss`、`aud`、`scope`

但你现在这个 mock OAuth 场景下，用 introspection 已经足够联调。

---

# 你接下来最可能还需要的增强

下一步通常会做两件事：

第一，把 `scope` 和工具权限挂钩，比如：

* `mcp:read` 只能用 `read_file`
* `mcp:exec` 才能调用 `execute_command`

第二，把 token 里的 `client_id / subject / scope` 注入到 MCP tool 上下文里，方便你记录审计日志或做细粒度授权。

如果你愿意，我可以下一条直接继续帮你改成：
**“不同 MCP tool 按 scope 分权限”的版本**。
