# 打包 Windows 便携版

打包机需要 Windows x64、Git、64 位 Python 3.12、pip、7-Zip 和网络连接。接收便携包的用户只需 Windows 10 或 11 x64。

```powershell
python .\scripts\build_portable.py --ref HEAD --full-tests
```

使用 `--seven-zip "C:\Program Files\7-Zip\7z.exe"` 指定未加到 PATH 的 7-Zip。脚本从指定 Git 提交打包，把官方运行时与 Python wheels 装进 ZIP，再解压到另一个包含空格的路径，验证以下全部环节：
1. `cad.cmd doctor`（不依赖系统环境变量，自动探测内置 Python 与 FreeCAD）。
2. `Run-Demo.cmd --no-open`（离线生成铝合金桌面手机支架全套工程文件，包括 `assembly.FCStd`）。
3. `Setup-Agent.cmd --no-pause --no-copy`（生成标准 `mcp.json` 与 `.mcp.json`）。
4. 标准 MCP `stdio` 协议握手、工具列表检查，以及无额外环境变量时的真实建模调用。
5. 完整单元测试（`--full-tests`）或 MCP 端到端测试（默认）。

便携包里的 `source-commit.txt` 和 `python-packages.txt` 分别记录源码提交与实装版本。

在 GitHub 创建与 `pyproject.toml` 版本一致的标签，并上传 `dist/` 中对应的 `*Windows-x64-Portable.zip`、`*.zip.sha256` 和 `freecad_source_1.1.2.tar.gz`。校验文件用于核对 ZIP，FreeCAD 源码归档用于满足分发要求。

用户可在 PowerShell 运行 `Get-FileHash .\Consumer-CAD-AI-v0.1.0-Windows-x64-Portable.zip -Algorithm SHA256`，将结果与发布页的 `.sha256` 文件比对。

## 随包组件与许可证

- Python 3.12.10 Windows x64 嵌入发行版。许可证在 `runtime/python/LICENSE.txt`。[上游发行页](https://www.python.org/downloads/release/python-31210/)
- FreeCAD 1.1.2 Windows x64 便携发行版。沿用上游二进制包中的授权文件和第三方声明，对应 FreeCAD 源码归档随 GitHub Release 提供。[上游发行页与源码](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.2)
- Python wheels 的许可证与包元数据在 `runtime/python/Lib/site-packages/`。CAD 内核对应的源码参见 [OCP](https://github.com/CadQuery/OCP) 和 [Open CASCADE 7.8.1](https://github.com/Open-Cascade-SAS/OCCT/tree/V7_8_1)。
- 本项目源码采用 [MIT 许可证](../LICENSE)，不捆绑任何厂商专用 AI 客户端。
