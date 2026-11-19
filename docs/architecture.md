# 建模、校验与扩展

## 几何来源与运行时

零件的尺寸定义保存在模型参数和 Python 源码中。build123d 调用 Open CASCADE 生成边界表示实体（B-rep），整套验证和出图读取这一批实体。Agent 经 MCP 发起设计修订，工程师也能用 CLI 或 Python 重放模型。几何代码、参数和预期校验结果可一起纳入 Git。[build123d 项目文档](https://build123d.readthedocs.io/en/stable/)

| 模块 | 输入 | 对下游的承诺 |
| --- | --- | --- |
| `design.py`、`geometry.py` | 电池仓尺寸、空间间隙、转轴行程 | 返回闭合位姿下的零件列表。每个 `Component` 有唯一名称、材料、实体和运动组标记 |
| `solid_spec.py` | 用 JSON 描述零件、位姿和顺序布尔操作 | 网页 Agent 可用方块、圆柱的并集和差集创建新结构。可选一组铰链位姿；完整实例见 `examples/sensor-clip.json` |
| `recipe.py` | 本地 Python 文件的 `build(parameters)` | 接受全新产品。共用装配校验和导出逻辑 |
| `verify_components`、`verify` | 实体、转轴、采样角度 | 输出整体及零件尺寸、碰撞对、发生角度和交叠体积；电池仓另有 10 项安装间隙 |
| `optimize_height` | 电池仓设计、壳高范围与步长 | 沿壳高搜索，记录实际试算、结果及无法解决的问题 |
| `exports.py`、`drawings.py` | 同一批验证过的装配实体 | 输出有名称的 STEP 装配、单件 STEP、带尺寸的工程视图、BOM 和预览 |
| `freecad_bridge.py`、`freecad_worker.py` | STEP 零件、参数、铰链轴 | 启动独立的 FreeCADCmd 进程生成 FCStd，重新打开验证实体及运动表达式 |

MCP 接收请求后，通过相同的 CLI 在独立 Python 进程执行几何计算。CAD 进程的标准输入与协议管道隔离，结果经 JSON 文件传回，避免 Windows 原生数值库在加载时占用 MCP 的输入流。同一服务器一次运行一个几何任务，客户端仍可查询已完成的运行或读取工程图。[MCP Windows stdio 与原生库问题](https://github.com/modelcontextprotocol/python-sdk/issues/2832)

**FreeCAD 分进程运行的原因。** build123d 环境和 FreeCAD 发行版各自带有 Python 和几何内核绑定。跨进程交换 STEP、参数及部件清单，可以分别选择适合本地操作系统的包。使用模型脚本、尺寸校验、STEP 和二维图的任务只依赖项目 venv；FCStd 生成时才需要启动 FreeCAD。[FreeCAD 上游源码](https://github.com/FreeCAD/FreeCAD)

**与已有 FreeCAD MCP 的分工。** 对需要获取当前窗口、选取对象、查询已有文档特征树的工作，可以并行接入已有适配器。neka-nat/freecad-mcp 的交互路径需要在 FreeCAD 内启动 RPC 工作台；Robust MCP Bridge 还支持 Linux 嵌入式和 headless 运行。本项目的主流程从源码重复生成结构，用消费电子间隙和开合检查给 Agent 反馈，部署时无需在某个已打开的文档内启动服务。MCP 的协议协商、工具发现和 stdio 传输由官方 Python SDK 提供。[neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) · [Robust MCP Bridge](https://github.com/spkane/freecad-addon-robust-mcp-server) · [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

**Skill 与工具分别承担什么。** Skill 描述如何核对单位、重建、审阅问题和读出图纸。几何能否通过校验由程序返回。新产品若需要编写 Python，使用本地代码 Agent 或 CLI 的 recipe 入口运行经过核对的源码；本地 recipe 具有当前账号的文件访问权限。[Agent Skills 规范](https://agentskills.io/specification)

## 参考装配

金属后壳分为固定后盖与可绕轴打开的电池盖。电池和 PCB 留在机身。坐标单位为 mm，X 沿产品长度，Y 沿铰链轴，Z 从壳底指向盖板。

| 结构 | 本例实现 | 按实物适配时要换的数据 |
| --- | --- | --- |
| 机身、固定后盖、电池盖 | 挖腔、支撑柱、安装孔、交错轴耳和连接腹板 | 外形、拔模、刀具可达性、表面处理余量 |
| 转轴、挡圈 | 带头销轴、卡槽和开口挡圈，可调开盖角度 | 销孔配合、装配工序、摩擦与锁止要求 |
| PCB、螺钉 | 带孔 FR-4 外形、螺柱、简化 M1.6 头部与杆部 | 实际孔位、器件高度、接口、电缆与工具空间 |
| 电芯、塑料支架与卡扣 | 电芯包络、带卡臂定位座、受力垫 | 供应商规格书、保护板、极耳、膨胀及移除空间 |
| 压簧 | 按安装高度扫掠圆线螺旋，位于弹起垫下方 | 弹簧常数、自由长度、端部、疲劳和电芯允许受力 |

闭合位姿先检查所有零件对。校验器用包围盒剔除相离的组合，对候选对计算实体交集体积。大于 `1e-5 mm³` 时，报告零件名和位姿。对每个指定角度，继续检查转动组与静止组。默认 0° 到 110°、每 15° 取样，并纳入最终 110°。遇到接近擦碰的位置，可调小 `sweep_step_deg`，或在自定义 recipe 中指定密集角度。采样点之间的碰撞、卡扣弯曲、弹簧载荷和公差叠加分别需要连续运动或力学、公差验证。

## 增加一个产品或零件

同一产品的尺寸变化直接修改设计参数。增加开槽、安装孔、按键缺口或配重时，Agent 可以按 `SolidSpec` 定义新的 JSON 装配并调用已有校验。需要螺旋扫掠、任意轮廓或自己的构造算法时，增加本地 Python recipe，复用已有组件函数或返回自己的 build123d 实体。最小的安装块示例如下。

```python
from build123d import Plane, Solid
from consumer_cad_ai.geometry import Component


def build(parameters):
    thickness = float(parameters.get("thickness", 3))
    if thickness <= 0:
        raise ValueError("thickness must be positive")
    plate = Solid.make_box(30, 16, thickness)
    bore = Solid.make_cylinder(1.6, thickness + 2, Plane((15, 8, -1)))
    return [Component("mounting_plate", "Aluminium", plate.cut(bore))]
```

- 所有实体使用统一的闭合装配坐标，每个零件返回一个有效实体。布尔合并一体成型的特征，分别列出独立采购或装配的零件。
- 对于转动装配，返回 `Recipe(parts, hinge=Axis(...), angles_deg=(0, 10, 25, 45))`，在相应 `Component` 上设置 `moving=True`。角度正向遵循右手定则。当前运动接口支持一个刚性转动组。
- 可复用函数包括 `pcb`、`battery`、`battery_cradle`、`screw` 和 `compression_spring`。需要新模板专属间隙时，把测量加在模板校验层，保留 `verify_components` 给其他产品共用。
- 需要新输出格式时，在 `export_design` 中消费同一批 `Component` 并登记相对产物路径；需要新二维视图时，在 `drawings.py` 定义观察方向及投影位置。

## 如何使用交付文件

| 相对路径 | 数据和用途 |
| --- | --- |
| `design.json`、`verification.json`、`manifest.json` | 源参数、实测结果及文件索引。校验失败的运行保留问题报告；通过后再生成工程文件 |
| `assembly.step`、`parts/*.step` | 闭合装配和单个安装实例。单件保留装配坐标，可在同一基准叠加 |
| `assembly.FCStd` | 原生装配分组、实体和材料属性，保存源参数的只读 JSON。参考电池仓可以在 `HingedParts.OpeningAngle` 上修改开启角度；尺寸变更从参数或 recipe 再生 |
| `assembly.dxf` | 第三角投影的正、顶、右视图及总体尺寸，模型空间单位为 mm。电池仓额外附去盖俯视图 |
| `assembly.pdf`、`preview.png` | 从同一份 DXF 几何渲染的 A4 横版总装图和预览。详细加工图还需零件基准、公差、工艺和检验要求 |
| `bom.csv` | 每个安装实例一行，可按名称及材料追溯其 STEP、数量和实体体积。价格、供应商、采购料号由工程 BOM 补充 |

几何和装配改动应保留至少一个通过案例和一个已知失败案例。测试可断言出错的零件对、测量值或位姿，确认结果来自真实几何。FCStd 的额外测试通过原生 FreeCAD 开档并改变开盖角度，便于发现导出成功但原生工程功能丢失的问题。
