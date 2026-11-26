# 本地部署和 Agent 接入

## Windows 10/11 x64

准备好 Git、网络连接和一个可写目录。打开 PowerShell，在准备放源码的位置执行以下命令。

```powershell
git clone https://github.com/phyartego/CAD_designer.git
cd CAD_designer
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

已解压源码时，从项目根目录直接执行第三行。脚本复用本机 64 位 Python 3.11/3.12 和 FreeCADCmd，缺少时优先通过 winget 安装当前用户的 Python 3.12 和 FreeCAD。winget 缺失或安装失败时，脚本会先复查安装结果，并按需下载 Python 3.12.10 和 FreeCAD 1.1.2 的官方 x64 安装程序，核验仓库内固定的 SHA-256 后安装。CAD 内核依赖装入仓库的 `.venv`，FreeCAD 使用自己的 Python 和 Open CASCADE。首次安装需要访问 winget 源、安装包下载站和 PyPI。

希望在 Windows 上直接解压运行（无需安装 Python 和 FreeCAD）时，请前往 [GitHub Releases](https://github.com/phyartego/CAD_designer/releases) 下载 `Windows-x64-Portable.zip`。

脚本会自动在项目根目录生成 `.mcp.json` 与 `.local/mcp.json`，并将 Skill 同步到 `.agents/skills/consumer-cad/SKILL.md`，随后运行环境诊断和需要真实 FreeCAD 的样例。终端最后显示本次示例目录。同一个 checkout 可以通过 `git pull` 加重跑安装脚本完成更新。移动 checkout 后请在新位置重新建虚拟环境（Python venv 内的启动器包含绝对路径），再运行一次 `.\.venv\Scripts\python.exe .\scripts\configure_agent.py`。

如使用便携版 FreeCAD，在运行安装脚本前设置 `$env:FREECAD_CMD = 'D:\Apps\FreeCAD\bin\FreeCADCmd.exe'`。脚本会把此路径带入 `.mcp.json` 与 `.local/mcp.json`。

| 安装选项 | 适用场景 |
| --- | --- |
| `-SkipFreeCAD` | 只需 build123d、STEP、BOM 和二维导出。安装样例跳过 FCStd。 |
| `-SkipDemo` | 已运行过整套案例，希望加快更新。 |

更新后可再次验证：

```powershell
.\.venv\Scripts\consumer-cad.exe doctor
.\.venv\Scripts\consumer-cad.exe recipe examples\desktop_stand.py --out .\outputs\stand-01 --freecad
```

### 通过命令行构建

在源码目录使用以下命令。便携包内可将 `$cad` 改为 `".\cad.cmd"`。

```powershell
$cad = ".\.venv\Scripts\consumer-cad.exe"
& $cad recipe examples\desktop_stand.py --out outputs\stand-01 --freecad
& $cad build-spec examples\sensor-clip.json --out outputs\sensor-01
& $cad check examples\hinged-enclosure.json
& $cad optimize examples\hinged-enclosure.json --min-height 12 --max-height 22 --step 0.5 --save-design revised.json
& $cad build revised.json --out outputs\revised-01 --freecad
```

退出码 `0` 表示成功，`2` 表示几何校验发现问题，`1` 表示输入、依赖或运行错误。

在源码目录运行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` 可以执行测试。FreeCAD 原生测试使用 FreeCADCmd 生成并重新打开工程。[GitHub Actions](https://github.com/phyartego/CAD_designer/actions)

## 在 Agent 中使用（WorkBuddy 及任意通用 Agent）

本项目通过标准 **stdio MCP** 与 **Agent Skills** 向外暴露能力，不绑定特定客户端。运行安装脚本或 `configure_agent.py` 后：

- 根目录生成 `.mcp.json`（标准 MCP 配置，包含绝对路径、`CAD_WORKSPACE` 与 `FREECAD_CMD`）
- `.local/mcp.json` 保存同样一份通用配置供手动导入
- `skills/consumer-cad/SKILL.md` 与 `.agents/skills/consumer-cad/SKILL.md` 提供完整的机械设计与验证工作流规范

### WorkBuddy 接入

1. 打开 WorkBuddy → 左侧 **连接器** → **自定义连接器** → 传输类型选 **`stdio`**。
2. 复制 `.mcp.json` 中的 JSON 配置粘贴导入（或在界面分别填入 `command`、`args` 和 `env`）。运行 `python .\scripts\configure_agent.py --print-guide --copy` 可直接把配置复制到剪贴板并打印逐项字段。
3. 在 WorkBuddy 中导入 `skills/consumer-cad/SKILL.md` 作为自定义技能，保存并启用连接器即可。

### 其他 MCP / CLI 客户端（Cursor、Claude Code / Desktop、Windsurf、Cline、Antigravity 等）

- **支持工作区发现的客户端**：直接用客户端打开项目目录，即可读取 `.mcp.json`、`AGENTS.md` 与 `.agents/skills/consumer-cad/SKILL.md`。
- **需要手动添加全局 MCP 的客户端**：将 `.mcp.json`（或 `.local/mcp.json`）中的 `consumer-cad` 块合并到客户端的 MCP 设置即可；长任务超时建议设为 600 秒。
- **终端类 Coding Agent**：除了 MCP，也可直接调用 `consumer-cad` CLI 或编写新的 `build123d` Python 配方并用 `recipe` 命令验证与导出。

可以直接输入以下需求试跑：

> 使用 consumer-cad 帮我查看或调整 examples/desktop_stand.py 的铝合金桌面手机支架，把宽度加宽到 70 mm、倾角改为 20°，验证无干涉后导出 FCStd、STEP、PDF、DXF 和 BOM。

网页 ChatGPT 可选用带 OAuth 的 Streamable HTTP 接入。需要为目标主机配置可访问的 HTTPS 地址及身份提供商；本机 stdio 安装完成后可按需启用。[网页 ChatGPT 接入部署](remote.md)

### 常见问题

- **Agent 找不到工具**：确认客户端已加载最新的 `.mcp.json`，或重跑 `python .\scripts\configure_agent.py` 刷新当前目录的绝对路径。便携包内也可以直接双击 `Setup-Agent.cmd`。
- **winget 下载失败**：从 Microsoft Store 更新“应用安装程序”，并检查本机能否访问 GitHub Release 安装包和 PyPI。已有发行版可直接给 `FREECAD_CMD` 赋绝对路径后重试。
- **仅调试 MCP 启动器**：在终端运行 `.\.venv\Scripts\consumer-cad-mcp.exe`（便携包内运行 `.\cad-mcp.cmd`）后会等待 MCP 客户端的标准输入，按 Ctrl+C 退出。用于人工查看的诊断命令是 `consumer-cad doctor`。

## Ubuntu Server 无界面安装

脚本以 Ubuntu 24.04 x86-64 和 Python 3.12 为目标。进入当前 checkout，使用有 sudo 权限的普通账号运行以下命令。

```bash
bash scripts/install.sh
.venv/bin/consumer-cad doctor
.venv/bin/consumer-cad recipe examples/desktop_stand.py --out ./outputs/server-demo-01 --freecad
```

脚本安装系统的 Python venv、OpenGL/X 运行库，检测系统上的 `freecadcmd` / `FreeCADCmd` 并优先复用。需要安装 FreeCAD 时先使用 apt 软件源；Ubuntu Noble 的软件源没有该包时会添加 FreeCAD maintainers 的 `freecad-stable` PPA。STEP、DXF 和 PDF 的生成使用 headless Python 路径。FCStd 通过 FreeCAD 命令行进程生成。

已有自定义 FreeCAD 安装或其他 Python 安装时可使用以下形式。Linux 与 Windows 的命令行参数采用各平台的命名习惯。

```bash
FREECAD_CMD=/opt/FreeCAD/bin/FreeCADCmd CAD_PYTHON=/usr/bin/python3.12 bash scripts/install.sh
bash scripts/install.sh --skip-freecad --skip-demo
```

在服务器上打开该仓库运行任意支持 stdio MCP 或 CLI 的 Agent 即可使用相同的 Skill 和项目配置。若客户端在另一台机器，且客户端支持 stdio 配置，可以把启动命令设为 `ssh`，参数设为服务器名和服务端启动器 `.venv/bin/consumer-cad-mcp` 的绝对路径，由 SSH 提供连接和认证。将服务端的 `CAD_WORKSPACE` 配置为预期的可写绝对路径；用 SSH 密钥验证非交互式调用，禁用登录脚本向 stdout 写欢迎语。

## 参考

- [FreeCAD 的 winget 清单](https://github.com/microsoft/winget-pkgs/tree/master/manifests/f/FreeCAD/FreeCAD)
- [Python 3.12.10 安装包校验清单](https://github.com/microsoft/winget-pkgs/blob/master/manifests/p/Python/Python/3/12/3.12.10/Python.Python.3.12.installer.yaml)
- [FreeCAD 1.1.2 安装包校验清单](https://github.com/microsoft/winget-pkgs/blob/master/manifests/f/FreeCAD/FreeCAD/1.1.2/FreeCAD.FreeCAD.installer.yaml)
- [Ubuntu FreeCAD 维护者 PPA](https://launchpad.net/~freecad-maintainers/+archive/ubuntu/freecad-stable)
- [Model Context Protocol (MCP) 规范](https://modelcontextprotocol.io/)
- [Agent Skills 规范](https://agentskills.io/specification)
