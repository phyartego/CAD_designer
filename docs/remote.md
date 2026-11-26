# 在网页 ChatGPT 中使用 CAD 工具

本地 AI Agent 客户端使用安装脚本配置的 stdio MCP。网页 ChatGPT 的工具运行在云端，需要可访问的 MCP 端点。本项目提供可选的 `serve-remote` 命令，和本机共用参数化建模、校验、优化及导出工具。服务仅监听 `127.0.0.1`，支持 MCP Streamable HTTP 和 OAuth 资源服务器发现。对外发布需要自己的域名、HTTPS 反向代理和 OAuth 身份提供商。仓库安装不会自动创建这些外部资源。

## 配置一个操作者

每个服务实例对应一个独立的 CAD 工作目录、一个身份提供商用户和一个 OAuth 客户端。要让多个人隔离各自的设计，可为每个人运行独立的实例和域名。远程按钮和工具的可用性还取决于账户及工作区授权。[OpenAI 自定义 MCP 说明](https://developers.openai.com/api/docs/guides/custom-mcp-server/)

以下假设已安装本项目、已有 Keycloak realm 和能指向服务器的域名。把示例域名、用户 ID 和客户端 ID 换成自己的值。

1. 在 Keycloak 创建 OIDC 客户端，例如 `chatgpt-cad`。启用授权码流程、客户端认证和 PKCE S256。ChatGPT 作为这个客户端完成登录；注册的静态 secret 填入 ChatGPT 的 OAuth 配置。服务端只使用公开验签密钥。
2. 创建一个名为 `cad:design` 的 client scope，启用“Include in token scope”。将它加入该客户端的可选或默认 scopes。在该 scope 添加 Audience mapper，指定自定义 audience 为对外 MCP 的完整 URL，例如 `https://cad.example.com/mcp`，启用添加到 access token。Keycloak 的签名算法设为 RS256。
3. 在 realm 的 OIDC discovery 文档复制 `issuer` 和 `jwks_uri`。登记要操作 CAD 的用户在该 issuer 下的 `sub` 和 OAuth 客户端 ID。默认 Keycloak 使用用户 UUID 作为 `sub`；若启用了 pairwise subject mapper，填写实际签发给该客户端的 subject。
4. 在 ChatGPT 自定义 MCP 的 OAuth 配置页复制它显示的**完整回调 URI**，加入客户端的 Valid Redirect URIs。回调模式取决于提供商的 issuer metadata，复制页面上的实际值。授权服务器须公布授权码、PKCE S256 能力，并为 MCP URL 发行对应 access token。[Keycloak OIDC 端点](https://www.keycloak.org/securing-apps/oidc-layers) · [OpenAI OAuth 规范与回调说明](https://developers.openai.com/apps-sdk/build/auth/)

其他发行方可使用带 `typ=at+jwt` 或 `application/at+jwt` 头部的 RS256 JWT access token，也支持载荷中 `typ=Bearer` 的 Keycloak access token。令牌需要包含到期时间、精确 issuer、包含 MCP URL 的 audience、subject、`client_id` 或 `azp` 以及空格分隔的 `scope`。签名公钥在服务中缓存五分钟；先发布新公钥，再切换签发密钥。[MCP 授权规范](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)

## 启动服务与 HTTPS

Ubuntu 示例。Windows PowerShell 中用 `$env:变量名 = '值'` 代替 `export`，并使用 `.\.venv\Scripts\consumer-cad.exe serve-remote`。

```bash
export CAD_WORKSPACE="$PWD/workspace-web"
export CAD_RESOURCE_URL="https://cad.example.com/mcp"
export CAD_OAUTH_ISSUER="https://id.example.com/realms/cad"
export CAD_OAUTH_JWKS_URL="https://id.example.com/realms/cad/protocol/openid-connect/certs"
export CAD_OAUTH_SUBJECT="你的用户-sub"
export CAD_OAUTH_CLIENT_ID="chatgpt-cad"
.venv/bin/consumer-cad serve-remote
```

默认本地端口 `8765`。设置 `CAD_REMOTE_PORT` 可使用另一空闲端口，同时修改反向代理上游。将下段加入同机 Caddy 的配置，用实际域名替换示例域名，配置 DNS 和证书签发所需的入站访问后运行或重载 Caddy。保留原始 Host 头。[Caddy 反向代理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)

```caddyfile
cad.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

通过公网 HTTPS 执行下列检查。第一条应返回资源 metadata，确认 `resource`、`authorization_servers` 和 `scopes_supported` 匹配。第二条应返回 HTTP 401，且 `WWW-Authenticate` 带 metadata URL。

```bash
curl -fsS https://cad.example.com/.well-known/oauth-protected-resource/mcp
curl -i -X POST https://cad.example.com/mcp
```

## 添加到 ChatGPT

在网页版打开 Plugins，选择加号和 Add custom MCP server，填写 Server URL 为上述 HTTPS MCP 地址，选择 OAuth 并填入预注册的客户端凭据。在仍使用开发者模式入口的界面，从自定义应用 / MCP 设置进入；工作区是否允许创建、安装和写入型工具由管理员设置控制。核对并添加登录页显示的回调地址后完成创建和安装。在支持工具的会话里输入 `@` 选择本应用，登录后要求它建立设计、检查间隙并显示图纸预览。尺寸源文件和 FCStd 等产物存储在服务端 `CAD_WORKSPACE` 对应目录。服务提供 MCP 工具，模型版本由 ChatGPT 会话选择。[OpenAI 接入与管理步骤](https://developers.openai.com/api/docs/guides/custom-mcp-server/)

可使用 `python -m unittest discover -s tests -p test_remote.py` 复核运输层。这些测试以真实的 RSA 密钥对签发测试令牌，校验 discovery、401 challenge、真实服务的工具发现、参数化零件 CAD 校验、错误签名/issuer/audience/subject/client、过期令牌、权限不足和 Origin 检查，测试公钥由本地夹具供应。开发环境另实测了 CLI 进程监听、从本地 HTTPS 公钥端点获取 JWKS 和已授权工具调用。域名、反向代理、身份提供商签发、用户登录和 ChatGPT 会话内调用需要使用部署者自己的环境联调。
