# Consumer CAD AI

用自然语言驱动消费电子结构设计。Agent 将设计要求转换为尺寸或建模代码，build123d 生成实体、测量装配、检查开合运动，FreeCAD 输出可打开并驱动翻盖的原生工程。源码采用 MIT 许可证。

[下载完整电池仓样例](examples/output/hinged-enclosure.zip)，包含实测装配的原生 FreeCAD 文件、STEP、PDF、DXF、BOM、输入和验证报告。

![默认电池仓工程图与开盖维修视图](examples/output/hinged-enclosure.png)

## Windows 快速启动

在有 Git 的 Windows 10/11 x64 上打开 PowerShell。

```powershell
git clone https://github.com/phyartego/consumer-cad-ai.git
cd consumer-cad-ai
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

脚本安装或复用 Python 和 FreeCAD，配置虚拟环境、本地 MCP 和项目 Skill，然后实际构建一次电池仓。安装成功后，终端会打印带 FCStd、STEP 和图纸的结果目录。已安装 Codex CLI 时，在同一终端执行 `.\scripts\cad-codex.cmd` 即可启动带 CAD 工具的会话。用 `.\scripts\cad-codex.cmd mcp list` 可确认 `consumer-cad` 已启用。也可用支持项目配置的 Codex 客户端打开此受信任项目。其他本地 stdio 客户端可使用生成的 `.local/mcp.json`。安装选项、Ubuntu Server 步骤和远程网页接入见 [部署说明](docs/deployment.md) 和 [ChatGPT 网页接入](docs/remote.md)。

可交给 Agent 的第一项设计任务：

> 设计金属分体后壳。PCB 在固定后盖下，25 × 20 × 12 mm 的电池留在机身，只有电池仓盖绕轴翻开。先按 13 mm 机身检查干涉，再在 12–22 mm 范围内按 0.5 mm 步长调整机身高度，保持电池和 PCB 的尺寸。复查 0–110° 开合，输出最终工程、图纸和修改依据。

## 可以建什么

| 入口 | 适合的任务 | 示例 |
| --- | --- | --- |
| 参数化电池仓 | 调整外壳、PCB、电池、轴耳、金属盖和支架之间的尺寸 | [双件后盖装配](examples/hinged-enclosure.json) |
| JSON 实体建模 | 网页 Agent 组合盒体、圆柱、并集、切除、装配位姿和单轴运动 | [传感器卡座、PCB、封装](examples/sensor-clip.json) |
| 本地 Python 配方 | 使用 build123d 的草图、扫掠、放样及其他操作，开发新产品和可复用组件 | [双件桌面支架](examples/desktop_stand.py) |

每次构建都建立新目录，保存实际设计输入、验证报告和文件清单。通过校验后生成装配 STEP、单件 STEP、原生 FCStd（安装 FreeCAD 时）、DXF、A4 PDF、BOM CSV 和 PNG 预览。FCStd 保存独立实体；电池仓的 `HingedParts.OpeningAngle` 可在 FreeCAD 中修改。零件尺寸从 JSON 或 Python 重新生成。

## 默认电池仓的实际几何

| 测量或实验 | 结果 |
| --- | --- |
| 机身主体 | 72 × 40 mm，闭合分缝处高 13 mm |
| 整体外包络，含销轴及轴耳 | 76 × 40 × 15.75 mm |
| 装配 | 16 个零件，包括机身、两块后盖、带挡圈销轴、PCB、电芯、塑料卡扣支架、压簧、托板和 6 枚简化螺钉 |
| 标准电池 | 25 × 20 × 5 mm，上方至仓盖间隙 3.85 mm |
| 开合验证 | 0、15、30、45、60、75、90、105、110°，逐姿态检查运动组与固定组 |
| 加厚试验 | 改用 12 mm 电池，13 mm 机身闭合时测得 600 mm³ 干涉 |
| 高度优化 | 在 12–22 mm、步长 0.5 mm 的网格上，18 mm 机身通过复验 |

零件外形和用料用于结构布局。样例中的压簧通过托板作用于电芯；螺纹以简化实体表示。二维图提供装配总图和维修视图。连续运动、公差叠加、转轴耐久、卡扣应力、电芯膨胀与允许载荷需根据实物规格另行验证。[建模接口与工程边界](docs/architecture.md)

## 命令行复现

在仓库根目录使用安装后的 CLI。下列命令各自写入一个新目录。

```powershell
$cad = ".\.venv\Scripts\consumer-cad.exe"
& $cad doctor
& $cad demo --out outputs\hinged-01 --freecad
& $cad check examples\hinged-enclosure.json
& $cad build-spec examples\sensor-clip.json --out outputs\sensor-01
& $cad recipe examples\desktop_stand.py --out outputs\stand-01
```

对于已修改的电池仓 JSON，可运行 `optimize design.json --min-height 12 --max-height 22 --step 0.5 --save-design revised.json`，再用 `build revised.json --out outputs/revised-01 --freecad` 导出。CLI 的进程退出码 0 表示成功，2 表示几何校验发现问题，1 表示输入、依赖或运行错误。

## 测试

安装后运行以下命令。持续集成在 Ubuntu 和 Windows 上执行安装、默认装配出图和测试，并上传样例产物。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试包括中间角度碰撞、真实几何修复、STEP 标签与位置回读、FCStd 重开与运动、DXF/PDF/PNG、输出目录并发发布、MCP stdio 客户端和带 OAuth 的 HTTP MCP。FreeCAD 原生测试需要可执行的 FreeCADCmd。[GitHub Actions](https://github.com/phyartego/consumer-cad-ai/actions)
