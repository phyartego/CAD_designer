# 本地部署和 Agent 接入

## Windows 10/11 x64

准备好 Git、网络连接和一个可写目录。打开 PowerShell，在准备放源码的位置执行以下命令。

```powershell
git clone https://github.com/phyartego/CAD_designer.git
cd CAD_designer
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

已解压源码时，从项目根目录直接执行第三行。脚本复用本机 64 位 Python 3.11/3.12 和 FreeCADCmd，缺少时优先通过 winget 安装当前用户的 Python 3.12 和 FreeCAD。winget 缺失或安装失败时，脚本会先复查安装结果，并按需下载 Python 3.12.10 和 FreeCAD 1.1.2 的官方 x64 安装程序，核验仓库内固定的 SHA-256 后安装。CAD 内核依赖装入仓库的 `.venv`，FreeCAD 使用自己的 Python 和 Open CASCADE。首次安装需要访问 winget 源、安装包下载站和 PyPI。

希望在 Windows 上直接解压运行时，使用 [GitHub Releases](https://github.com/phyartego/CAD_designer/releases) 中的 `Windows-x64-Portable.zip`。

Windows 安装器会复用可运行的 Codex CLI。全新机器会自动下载 OpenAI 发布的 Codex CLI 0.170.0 原生 x64 ZIP（约 205 MiB），校验固定 SHA-256，将完整包安装到当前仓库的 `.local/codex/`，并检查 Windows 辅助程序和 `--version`。这个入口无需 Node.js，也无需修改系统 PATH。首次运行 `.\scripts\cad-codex.cmd` 时按 Codex 提示登录自己的账号。已有本地登录可复用。[OpenAI CLI 文档](https://developers.openai.com/codex/cli/) · [官方固定版本](https://github.com/openai/codex/releases/tag/rust-v0.170.0)

脚本写入当前仓库的 MCP 配置与 Skill，运行环境诊断和需要真实 FreeCAD 的样例。终端最后显示本次示例目录。重复运行会创建新的结果目录。同一个 checkout 可以通过 `git pull` 加重跑安装脚本完成更新。移动 checkout 后请在新位置重新建虚拟环境，Python venv 内的启动器包含绝对路径。

如使用便携版 FreeCAD，在运行安装脚本前设置 `$env:FREECAD_CMD = 'D:\Apps\FreeCAD\bin\FreeCADCmd.exe'`。脚本会把此路径带入 Agent 配置，使新启动的客户端也能找到它。

| 安装选项 | 适用场景 |
| --- | --- |
| `-SkipFreeCAD` | 只需 build123d、STEP、BOM 和二维导出。安装样例跳过 FCStd。 |
| `-SkipCodex` | 使用其他 MCP 客户端，跳过本机 Codex CLI 的检测与安装。 |
| `-SkipDemo` | 已运行过整套案例，希望加快更新。 |
| `-GlobalCodex` | 希望其他项目的 Codex 也使用此 checkout 的 MCP。使用 PATH 中或仓库内的 Codex CLI。默认配置仅在当前受信任项目内生效。 |

更新后可再次验证。指定一个新的输出目录。

```powershell
.\.venv\Scripts\consumer-cad.exe doctor
.\.venv\Scripts\consumer-cad.exe demo --out .\outputs\demo-01 --freecad
```

### 通过命令行构建

在源码目录使用以下命令。便携包内可将 `$cad` 改为 `".\cad.cmd"`。

```powershell
$cad = ".\.venv\Scripts\consumer-cad.exe"
& $cad check examples\hinged-enclosure.json
& $cad build-spec examples\sensor-clip.json --out outputs\sensor-01
& $cad recipe examples\desktop_stand.py --out outputs\stand-01
& $cad optimize examples\hinged-enclosure.json --min-height 12 --max-height 22 --step 0.5 --save-design revised.json
& $cad build revised.json --out outputs\revised-01 --freecad
```

退出码 0 表示成功，2 表示几何校验发现问题，1 表示输入、依赖或运行错误。

在源码目录运行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` 可以执行测试。FreeCAD 原生测试使用 FreeCADCmd 生成并重新打开工程。 [GitHub Actions](https://github.com/phyartego/CAD_designer/actions)

## 在 Agent 中使用

**推荐入口为本机 Codex CLI。** 安装后运行以下命令。启动器为本次 Codex 进程传入 MCP 服务器的绝对路径、工作目录和超时，并在仓库根目录打开会话；全局配置中的其他服务器仍可使用。第一次打开时按 Codex 提示信任该项目，以发现项目的 Skill。可以用 `/mcp` 查看当前会话的工具。

```powershell
.\scripts\cad-codex.cmd mcp list
.\scripts\cad-codex.cmd
```

Linux 对应命令为 `./scripts/cad-codex mcp list` 和 `./scripts/cad-codex`。从仓库以外的目录也可调用启动器的绝对路径。使用支持受信任项目配置的 IDE 或桌面客户端时，打开仓库、重开会话，读取生成的 `.codex/config.toml` 和 `.agents/skills/consumer-cad/SKILL.md`。不加载项目级 MCP 配置的客户端可导入 `.local/mcp.json` 或显式开启全局注册。

可以直接输入以下需求。

> 使用 consumer-cad 设计一个金属翻盖电池仓，先给出 PCB 和电池的装配尺寸，再检查翻盖整个开合范围。如果有干涉就调整尺寸复查，交付通过检查的 STEP、FCStd、PDF、DXF 和 BOM，并说明验证覆盖的角度。

其他支持本地 stdio MCP 的客户端可合并 `.local/mcp.json` 中的服务器条目。它包含此机的绝对路径、独立的设计工作目录 `workspace/` 以及显式指定的 FreeCAD 路径。调整 MCP 客户端的长任务超时时，可从 600 秒开始。本地代码 Agent 也可用终端执行 `consumer-cad` 或编写新的 Python 组件。

网页 ChatGPT 可选用带 OAuth 的 Streamable HTTP 接入。需要为目标主机配置可访问的 HTTPS 地址及身份提供商；本机 stdio 安装完成后可按需启用。[网页 ChatGPT 接入部署](remote.md)

### 常见问题

- **Codex 找不到工具。** 确认打开的是本仓库根目录且已信任，重新启动会话。检查 `.codex/config.toml` 中的 `command` 是否仍指向有效的 `.venv` 启动器。在该目录再次运行安装脚本可刷新绝对路径。
- **winget 下载失败。** 从 Microsoft Store 更新“应用安装程序”，并检查本机能否访问 GitHub Release 安装包和 PyPI。已有发行版可直接给 `FREECAD_CMD` 赋绝对路径后重试。
- **仅调试启动器。** 在终端运行 `.\.venv\Scripts\consumer-cad-mcp.exe` 后会等待 MCP 客户端的标准输入，按 Ctrl+C 退出。用于人工查看的诊断命令是 `consumer-cad doctor`。
- **已有同名 MCP 配置。** 安装器保留其他 MCP 服务，只更新由本项目标记的块。遇到手工配置的同名条目时，先在 `.codex/config.toml` 核对入口并决定保留或改名。

## Ubuntu Server 无界面安装

脚本以 Ubuntu 24.04 x86-64 和 Python 3.12 为目标。进入当前 checkout，使用有 sudo 权限的普通账号运行以下命令。

```bash
bash scripts/install.sh
.venv/bin/consumer-cad doctor
.venv/bin/consumer-cad demo --out ./outputs/server-demo-01 --freecad
```

脚本安装系统的 Python venv、OpenGL/X 运行库，检测系统上的 `freecadcmd` / `FreeCADCmd` 并优先复用。需要安装 FreeCAD 时先使用 apt 软件源；Ubuntu Noble 的软件源没有该包时会添加 FreeCAD maintainers 的 `freecad-stable` PPA。STEP、DXF 和 PDF 的生成使用 headless Python 路径。FCStd 通过 FreeCAD 命令行进程生成。

已有自定义 FreeCAD 安装或其他 Python 安装时可使用以下形式。Linux 与 Windows 的命令行参数采用各平台的命名习惯。

```bash
FREECAD_CMD=/opt/FreeCAD/bin/FreeCADCmd CAD_PYTHON=/usr/bin/python3.12 bash scripts/install.sh
bash scripts/install.sh --skip-freecad --skip-demo
```

在服务器上打开该仓库运行 Codex 即可使用相同的 Skill 和项目配置。若客户端在另一台机器，且客户端支持 stdio 配置，可以把启动命令设为 `ssh`，参数设为服务器名和服务端启动器的绝对路径，由 SSH 提供连接和认证。将服务端的 `CAD_WORKSPACE` 配置为预期的可写绝对路径；用 SSH 密钥验证非交互式调用，禁用登录脚本向 stdout 写欢迎语。

## 参考

- [FreeCAD 的 winget 清单](https://github.com/microsoft/winget-pkgs/tree/master/manifests/f/FreeCAD/FreeCAD)
- [Python 3.12.10 安装包校验清单](https://github.com/microsoft/winget-pkgs/blob/master/manifests/p/Python/Python/3/12/3.12.10/Python.Python.3.12.installer.yaml)
- [FreeCAD 1.1.2 安装包校验清单](https://github.com/microsoft/winget-pkgs/blob/master/manifests/f/FreeCAD/FreeCAD/1.1.2/FreeCAD.FreeCAD.installer.yaml)
- [Ubuntu FreeCAD 维护者 PPA](https://launchpad.net/~freecad-maintainers/+archive/ubuntu/freecad-stable)
- [OpenAI 官方 MCP 客户端配置](https://developers.openai.com/codex/mcp/)
- [OpenAI 官方 Skill 发现规则](https://developers.openai.com/codex/skills/)
