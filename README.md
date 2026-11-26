<div align="center">

# Consumer CAD AI

**用自然语言驱动任意 AI Agent 完成消费电子 3D 结构建模、干涉校验、运动检查与工程出图**

[![Windows x64 Portable](https://img.shields.io/badge/Windows%2010%2F11%20x64-免安装便携版-0078D4?logo=windows)](https://github.com/phyartego/CAD_designer/releases/download/v0.1.0/Consumer-CAD-AI-v0.1.0-Windows-x64-Portable.zip)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](docs/portable.md)
[![FreeCAD 1.1.2](https://img.shields.io/badge/FreeCAD-1.1.2-CB333B)](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.2)
[![MCP Ready](https://img.shields.io/badge/MCP-stdio%20%7C%20Streamable%20HTTP-10A37F)](docs/deployment.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**简体中文** | [English](README_EN.md)

**[下载 Windows x64 免安装便携版 (v0.1.0)](https://github.com/phyartego/CAD_designer/releases/download/v0.1.0/Consumer-CAD-AI-v0.1.0-Windows-x64-Portable.zip)** · [所有发布版本](https://github.com/phyartego/CAD_designer/releases) · [查看支架成品文件](examples/output/desktop-stand.zip)

</div>

---

## 这是什么？

**Consumer CAD AI** 是一套面向消费电子结构设计的**本地可验证 CAD 引擎 + 通用 AI Agent 工具链**（基于 `build123d` / Open CASCADE 与 FreeCAD）。

- **零依赖开箱即用**：Release 便携整合包内置完整 **Python 3.12 + 全部 CAD/MCP 依赖 + FreeCAD 1.1.2（含图形界面）**，小白无需自己折腾 Python 或 FreeCAD 环境。
- **彻底通用，不绑定任何 Agent**：暴露标准 **MCP (`stdio`)**、**`SKILL.md`** 与 **本地命令行 (`cad.cmd`)**，不限制为 Codex 或特定 IDE —— **WorkBuddy**、Cursor、Claude Desktop / Code、Windsurf、Cline、Antigravity 等都能即插即用。
- **先校验、再出图**：每次建模都会计算零件包围盒尺寸、安装间隙、两两实体交叠体积（精度 `1e-5 mm³`）与转动开合干涉，通过校验后一次性导出全套工程交付物。

---

## 成品效果展示：铝合金桌面手机支架

[![铝合金桌面手机支架总装工程图](examples/output/desktop-stand.png)](examples/output/desktop-stand.zip)

示例基于 [desktop_stand.py](examples/desktop_stand.py) 生成：**铝合金主体支架 + 硅胶防滑垫**（整机包络 `62 × 56 × 65 mm`，15° 倾角，含前挡唇与防滑背垫），已内置在便携版 `Run-Demo.cmd` 中，点击上方图片即可下载完整成品归档 [desktop-stand.zip](examples/output/desktop-stand.zip)。

<details>
<summary>每次构建自动产出的 7 类工程文件一览</summary>

| 输出文件 | 说明与用途 |
| --- | --- |
| `assembly.FCStd` | FreeCAD 原生装配工程文件，保留分组、材质与只读设计参数，可用 `Open-FreeCAD.cmd` 直接打开查看 3D |
| `assembly.step` & `parts/*.step` | 闭合总装与每个零件的独立 STEP（保留统一装配基准坐标，可直接导入 SolidWorks / Creo / Fusion） |
| `assembly.dxf` | 第三角投影三视图（正、顶、右视图）与总体标注尺寸（单位 mm） |
| `assembly.pdf` | A4 横版工程总装图，可直接打印或审图 |
| `preview.png` | 与工程图同源渲染的预览图，Agent 可直接调用 `preview_run` 查看图纸效果 |
| `bom.csv` | 结构 BOM 表（零件名、材质、数量、体积 `mm³` 与对应单件 STEP 路径） |
| `verification.json` & `design.json` | 完整几何校验报告、实测尺寸与输入参数快照（校验不通过时仅保留诊断报告，不输出错误零件） |

</details>

---

## Windows 10 / 11 免安装便携版：3 步极速上手

> **环境说明**：压缩包内已包含 Python 3.12、CAD 内核、MCP 服务与 FreeCAD 1.1.2 图形界面，**全程无需联网安装运行环境**；仅在你接入云端大模型 / AI Agent 对话时需要联网。

### 第 1 步：下载并解压
下载 **[Consumer-CAD-AI-v0.1.0-Windows-x64-Portable.zip](https://github.com/phyartego/CAD_designer/releases/download/v0.1.0/Consumer-CAD-AI-v0.1.0-Windows-x64-Portable.zip)**，右键选择 **全部解压缩**，放到可写短路径（例如 `C:\CAD`）。

### 第 2 步：离线体验建模与 3D 看图
1. 双击 **`Run-Demo.cmd`**：自动生成「铝合金桌面手机支架」全套工程文件，并打开结果目录 `outputs\desktop-stand-*`。
2. 双击 **`Open-FreeCAD.cmd`**：启动内置 FreeCAD 图形界面，把结果目录中的 `assembly.FCStd` 拖进去即可 3D 旋转查看。

### 第 3 步：一键生成 Agent 接入配置
双击 **`Setup-Agent.cmd`**：脚本会自动读取当前解压目录的绝对路径，生成标准 `mcp.json` 与 `.mcp.json`，**自动复制到系统剪贴板**，并在终端里按栏位打印出来。

---

## 接入你的 AI Agent（通用方案）

### 方式一：接入 WorkBuddy（推荐，2 步完成）

1. **添加 MCP 连接器**
   - 打开 **WorkBuddy** → 点击左侧 **连接器** → 点击右上角 **自定义连接器**。
   - 传输类型选择 **`stdio`**，直接粘贴 `Setup-Agent.cmd` 自动复制好的 JSON 配置（或对照终端打印的 `Command`、`Args`、`Env` 逐项填入），保存并批准连接。
2. **加载技能规范（推荐）**
   - 在 WorkBuddy 中导入解压目录下的 [`skills/consumer-cad/SKILL.md`](skills/consumer-cad/SKILL.md) 作为自定义 Skill，AI 就会自动遵循单位核对、干涉复查与完整出图规范。

接入后，你可以直接对 WorkBuddy 发送这段中文提示词：

> 使用 consumer-cad 帮我设计一个消费电子结构：先查看当前示例并生成一个宽度 72 mm、倾角 20° 的铝合金桌面手机支架；再帮我评估一个带 25 × 20 × 12 mm 电池的金属翻盖电池仓，找出通过 0–110° 开合检查的最小机身高度，最后导出 FCStd、STEP、PDF、DXF 和 BOM。

### 方式二：接入任意其他 Agent（不限厂商）

| 客户端类型 | 接入方法 |
| --- | --- |
| **Cursor / Claude Desktop / Windsurf / Cline / Cherry Studio** | 打开客户端 MCP 设置，直接粘贴 `Setup-Agent.cmd` 生成的 `mcp.json` 内容即可。 |
| **Claude Code / Antigravity / 其他工作区 Agent** | 直接用 Agent 打开解压后的根目录：目录内已就绪 `.mcp.json`、[`AGENTS.md`](AGENTS.md)、[`CLAUDE.md`](CLAUDE.md) 和 [`.agents/skills/consumer-cad/SKILL.md`](skills/consumer-cad/SKILL.md)，开箱自动发现。 |
| **任何带终端权限的本地 Coding Agent** | 无需配置 MCP 也能用：让 Agent 直接在终端调用 `.\cad.cmd`（例如 `.\cad.cmd recipe examples\desktop_stand.py --out outputs\my-stand --freecad`）。 |

<details>
<summary>标准 MCP 配置示例（由 Setup-Agent.cmd 自动填充当前解压路径）</summary>

```json
{
  "mcpServers": {
    "consumer-cad": {
      "type": "stdio",
      "command": "C:\\CAD\\runtime\\python\\python.exe",
      "args": ["-m", "consumer_cad_ai", "serve"],
      "env": {
        "CAD_WORKSPACE": "C:\\CAD\\workspace",
        "FREECAD_CMD": "C:\\CAD\\runtime\\freecad\\bin\\freecadcmd.exe"
      }
    }
  }
}
```

> 注：即使在部分界面中未填写 `env`，便携包内的 `python.exe` 也会自动探测同目录下的 `runtime\freecad` 与 `workspace\`。

</details>

---

## 三种建模能力（从改参数到自由曲面）

| 我想做什么 | 对应能力与示例 |
| --- | --- |
| **自定义支架 / 扫掠 / 放样 / 复杂 3D 结构** | 编写 `build(parameters)` Python 配方并用 `recipe` 运行 → [铝合金桌面手机支架](examples/desktop_stand.py) |
| **用盒体、圆柱与布尔运算拼装任意结构** | 调用 MCP `solid_schema` / `check_custom` / `build_custom` → [传感器卡座 JSON](examples/sensor-clip.json) |
| **快速设计并优化金属翻盖电池仓** | 调用 MCP `enclosure_defaults` / `optimize_enclosure_height` → [翻盖电池仓 JSON](examples/hinged-enclosure.json)（[成品包](examples/output/hinged-enclosure.zip)） |

---

## 源码安装与进阶文档

如果你希望从源码部署（Windows / Ubuntu 24.04 Server）、接入网页版远程 MCP，或自己二次开发 / 重新打包 Release：

| 文档 | 内容说明 |
| --- | --- |
| [本地部署与 Agent 接入](docs/deployment.md) | Windows 源码安装、Ubuntu Server 无界面部署、CLI 命令速查 |
| [架构、几何校验与出图规则](docs/architecture.md) | `build123d` 校验机制、FreeCAD 分进程桥接、扩展新零件/产品 |
| [网页 ChatGPT 远程 MCP 部署](docs/remote.md) | Streamable HTTP + OAuth 2.0 鉴权端点配置 |
| [从源码构建 Windows 便携包](docs/portable.md) | 打包脚本、自动化端到端验包、组件与开源许可证说明 |
| [MIT 许可证](LICENSE) | 本项目开源许可协议 |
