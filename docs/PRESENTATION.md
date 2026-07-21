# HomeMate — Lecture 13 演示 PPT 文案 + 讲稿

> 用途：MIE1077 Lecture 13（2026-07-30）课堂汇报  
> 建议时长：讲稿约 **8–10 分钟** + 现场/录屏 Demo **3–5 分钟**  
> 用法：左侧「幻灯片正文」直接贴进 PowerPoint；右侧「讲稿」对着念或做成备注页。

---

## 幻灯片 1 — 封面

**标题**
HomeMate: An Empathetic Home Companion Robot in Simulation

**副标题**
LLM + Vision + Planning + Robot Action  
MIE1077 Artificial Intelligence for Robotics III  
University of Toronto · Lecture 13 · July 30, 2026

**底部**
Simulated 2D apartment · Webcam emotion · Tool-calling agent · Costmap navigation

**讲稿（约 30 秒）**
大家好。今天介绍的是 HomeMate——一个纯仿真的家庭陪伴机器人。我们不碰真机，而是在 2D 公寓里把感知、认知、规划和执行整条链路跑通：摄像头读情绪、LLM 做决策、机器人在代价地图上导航并操作智能家居。接下来我会先讲动机和架构，再重点讲机器人侧的技术难点，最后用定量评估和 Demo 收尾。

---

## 幻灯片 2 — 问题与动机

**标题**
Why a home companion robot?

**要点**
- 居家场景：找人 → 读情绪 → 共情对话 → 操作多设备
- 课程关注点：**AI for Robotics**，不是单纯 ChatBot
- 设计选择：
  - 物理保真度刻意偏低（俯视 2D）→ 投影清晰可读
  - 情感输入用**真实摄像头**，与地图解耦（避免 3D 虚拟脸失败）
  - 仿真交付：可复现、可评估、可录 Demo

**讲稿（约 45 秒）**
动机很直接：主人说「我累了，帮我煮杯咖啡」，机器人要先找到人，读到 tired，说一句共情的话，再去厨房操作咖啡机。这不是单一 NLP 问题，而是感知—规划—执行的闭环。我们故意把地图做成俯视格子图，方便课堂演示；但情绪走真实摄像头 + DeepFace，把「人」和「地图」分开，这也是提案里的明确设计决策。

---

## 幻灯片 3 — 系统总览（四模块）

**标题**
Architecture: four modules + memory

**表格 / 框图（建议画成从左到右的流水线）**

| Module | Tech | Role |
|--------|------|------|
| Perception | OpenCV + DeepFace / MockEmotion | 主人情绪标签 |
| Cognition | Claude / GPT-4o-mini / MockLLM | 工具调用决策 |
| Planning | Costmap A* · ReAct · Belief · Coverage | 路径与子目标分解 |
| Action | Skills + mock IoT（11 设备） | 导航、操作、取送物 |
| Memory | JSONL episodes + profile brief | 注入 system prompt |

**一句话**
Tool dispatch 统一入口：`dispatch_tool` —— Mock 与真 LLM 走同一执行路径。

**讲稿（约 50 秒）**
整体是四模块：感知输出情绪；认知用 LLM 的 tool-calling 选动作；规划负责怎么走、去哪找人、怎么拆多步任务；执行层是一组 JSON 工具，落到 Skills 和 mock IoT。长期记忆把历史 episode 滚成短 brief 塞进 prompt。关键工程点是：所有工具统一 `dispatch_tool`，所以离线 MockLLM 测通的路径，上线 Claude 或 GPT 不用改执行代码。

---

## 幻灯片 4 — 世界与能力面

**标题**
What the robot can do in the apartment

**左栏：世界**
- 4 房间：living / kitchen / bedroom / bathroom
- 11 个 IoT：窗帘、灯、咖啡机、烤面包机、恒温器、TV、音箱、风扇、门锁…
- Pygame UI：对话、工具轨迹、IoT 进度条、会话录制回放

**右栏：工具（约 17 个，摘要）**
- 感知：`look_around` · `sense_emotion` · `scan_room`
- 导航：`find_owner` · `goto_device` · `explore_frontier` · `replan_if_needed`
- 操作：`set_device` · `pickup_item` · `deliver_item` · `clean_room`
- 规划：`make_plan` · `plan_device_route` · `visit_devices`
- 状态：`speak` · `get_robot_state`

**讲稿（约 40 秒）**
公寓四间房、十一台设备。机器人侧暴露大约十七个工具：找人、扫房、读情绪、走到设备停靠点、开关设备、取送物品、清扫房间、多设备路线优化，以及显式的重规划。UI 上能看到对话、每一步 tool trace、设备进度条，还能把整场交互录下来逐步回放——方便录 Demo 和写报告。

---

## 幻灯片 5 — 机器人核心栈（技术主线 ①）

**标题**
Robotics stack: beyond “teleport A*”

**模块图**
```
RobotController
├── kinematics   设备 dock + Manhattan 操作半径
├── belief       主人房间概率分布
├── coverage     Boustrophedon 蛇形覆盖
├── motion       里程计 / replan 计数
├── path_tracker 活动目标 + 动态重规划触发
├── occupancy    占据栅格 + frontier
└── route_opt    多设备 TSP（NN + 2-opt）
```

**要点**
- **先到位再操作**：`set_device` 超出操作半径会自动导航到 dock
- **找人不是瞎逛**：belief ⊕ 时段先验排序房间，房间内再 coverage sweep
- 顶栏实时显示 mode、累计 tiles、重规划次数 R

**讲稿（约 60 秒）**
这是我们相对「会说话的脚本」拉开差距的地方。`RobotController` 把运动、信念、覆盖搜索、占据地图和路线优化收成一层。操作有物理约束：咖啡机不在曼哈顿距离内就不能按，必须先导航到 dock。找人用离散信念更新房间概率，再叠时段先验；进了房间还不够，会走 boustrophedon 覆盖路径扫一遍。这些都是经典移动机器人里的零件，我们把它们接到同一条 skill 管线上。

---

## 幻灯片 6 — 代价地图 A* 与动态重规划（技术主线 ②）

**标题**
Costmap A* + dynamic replanning

**左：状态空间规划**
- 状态 `(x, y, direction)`，不仅是格子
- 代价：转向惩罚 · 过门成本 · **主人占用格阻塞** · 邻格 proximity cost
- 失败时 fallback 到避开主人的普通 A*

**右：运行时重规划**
- `PathTracker` 监视：`owner_moved` / `owner_on_next_tile`
- `try_replan()` 保留设备目标，绕开挡住路径的主人
- Demo：`python -m homemate.main --replan-demo`

**讲稿（约 55 秒）**
导航不是「瞬间瞬移」。我们用带朝向的状态空间 A*，转弯和过门都有代价，主人所在格是动态障碍，旁边还有社交距离式的 proximity cost。主人在动时，`PathTracker` 会触发重规划：如果目标是设备，不会把目标改成主人坐标，而是绕开挡住下一格的人。现场可以用 `--replan-demo` 看到路径蓝点改线、顶栏 R 计数上升。

---

## 幻灯片 7 — 占据栅格与多目标路线（技术主线 ③）

**标题**
Occupancy grid · Frontier · Multi-device TSP

**三点**
1. **OccupancyGrid**：UNKNOWN / FREE / OCCUPIED；位姿附近 reveal
2. **Frontier exploration**：belief + coverage 失败后，向未知边界扩展（辅助找人）
3. **RouteOptimizer**：多设备访问顺序 = nearest-neighbor + 2-opt；工具 `plan_device_route` / `visit_devices`

**一句话价值**
从「单点导航」升级到「部分可观测建图 + 多目标任务规划」。

**讲稿（约 45 秒）**
第三块是占据栅格和多目标优化。地图一开始大量 UNKNOWN，机器人移动时按位姿揭示；探索 frontier 用在找人失败后的兜底。多设备任务——比如恒温器、咖啡、卧室灯——用最近邻再 2-opt，避免按自然语言顺序乱走。这把课程里的规划算法和家居任务绑在一起，而不是只做单次 A*。

---

## 幻灯片 8 — 认知：LLM、规划器与语音

**标题**
Cognition: MockLLM · Claude · GPT · Voice

**要点**
- **ReAct 分解器**（stdlib）：`find_owner → sense_emotion → speak → goto + actuate…`
  - 暴露为 `make_plan`；MockLLM 默认走 planner
- **真模型**：Anthropic Claude tool loop；OpenAI GPT-4o-mini 同构 agent
- **语音**：OpenAI TTS；STT（Whisper）；Windows 可回退系统 SAPI
- 重依赖全部 lazy-load → 无 API / 无摄像头也能跑测试与 Demo

**讲稿（约 45 秒）**
认知层三条路：确定性 MockLLM、Claude、GPT。Mock 背后是同一套 ReAct 分解器，把自然语言拆成有序子目标，保证评估可复现。真模型走 tool-calling，执行仍进同一 `dispatch_tool`。队友还接了 TTS/STT：机器人说话可出声，按键可语音输入。工程上 anthropic、opencv、deepface 都是懒加载，所以 CI 和课堂离线演示不依赖付费 API。

---

## 幻灯片 9 — 演示工程与可复现性

**标题**
Demo engineering: scripts, sessions, snapshots

**要点**
| 能力 | 命令 / 键 |
|------|-----------|
| 一键场景 | `--script tired_coffee --auto-run` |
| 重规划演示 | `--replan-demo` |
| 世界快照 | `F5` 存 / `F9` 读 |
| 会话录制回放 | 自动落盘 · `p` / `[` `]` 逐步回放 |
| 批量脚本验证 | `python -m homemate.demo_runner` |
| 机器人 benchmark | `python -m homemate.robot` |

内置脚本：`tired_coffee` · `sad_talk` · `wind_down` · `multi_comfort`

**讲稿（约 35 秒）**
为了课堂和录视频，我们把演示工程化了：四个脚本覆盖疲惫煮咖啡、纯陪伴、睡前关灯关窗帘、多设备舒适场景；会话自动录 JSON，可逐步回放；还有无 GUI 的 demo_runner 和机器人层 benchmark，方便往报告里贴表。`--offline` 冻结主人保证可复现；测重规划则用专门的 `--replan-demo`。

---

## 幻灯片 10 — 定量评估

**标题**
Evaluation: 20 scenarios · ablations

**主结果（MockLLM + planner）**
- **20 / 20** scenarios
- **109 / 109** criteria
- **demo_runner 4 / 4**
- 单元 / 集成测试：**100+** passed（近期约 101）

**消融（写报告用）**
| Setting | 预期叙事 |
|---------|----------|
| Baseline | 全模块，接近满分 |
| `--no-planner` | 多步任务变脆 |
| `--no-emotion` | 共情场景显著下降（历史约 8/20） |
| `--no-memory` | 依赖历史偏好的任务受损 |
| `--use-llm` | 真 Claude / GPT（需 API key） |

**讲稿（约 50 秒）**
评估套件固定二十个场景、一百零九条判定。基线在 MockLLM 加 planner 下满分，说明技能与规划管线自洽。消融很重要：关掉情绪，共情类场景会塌；关掉 planner，多步 IoT 任务更容易失败。这直接对应提案里「模块是否必要」的问题。真模型路径另有 `--use-llm`，用于补一张真人 API 表，但不替代可复现的 Mock 基线。

---

## 幻灯片 11 — Demo 叙事（建议录屏三段）

**标题**
Live demo storyboard (3–5 min)

**段 1 · tired_coffee（约 90 秒）**
请求：「I'm tired. Brew some coffee.」  
路径：找主人 → 读 tired → 共情说话 → 厨房 brew →（可选）取送咖啡

**段 2 · multi_comfort / wind_down（约 60 秒）**
多设备：恒温器 / 灯 / 窗帘 / 音乐；可点出 `plan_device_route` 或 ReAct 计划

**段 3 · replan-demo（约 60 秒）**
主人走动挡住路径 → 顶栏 R 增加 → 蓝点路径改线绕行

**口令提示（贴备注）**
```text
python -m homemate.main --script tired_coffee --auto-run
python -m homemate.main --script multi_comfort --auto-run
python -m homemate.main --replan-demo
```

**讲稿（约 20 秒 + 切到录屏）**
Demo 分三段：第一段完整闭环；第二段多设备；第三段动态重规划。下面直接看画面。

---

## 幻灯片 12 — 总结与展望

**标题**
Takeaways & next steps

**已完成**
- 端到端仿真伴侣：感知 · LLM · 记忆 · IoT
- 机器人技术栈：costmap A* · 动态重规划 · belief · coverage · occupancy · TSP
- 可复现评估：20 场景 + 消融 + 会话回放

**Phase 4 收尾（Lecture 13 前）**
- 定稿消融表写入报告
- 录制 3–5 分钟 Demo 视频
- 幻灯片定稿 + 课堂演讲

**一句话收尾**
HomeMate shows that companion behaviour is a robotics pipeline — not only a language model.

**讲稿（约 40 秒）**
总结：HomeMate 证明「陪伴」可以做成一条可评估的机器人流水线，而不只是聊天。我们把经典规划组件嵌进家居任务，并用 Mock 路径保证分数可复现。接下来主要是报告表格、Demo 视频和今天这套幻灯片的最终抛光。谢谢，欢迎提问。

---

# 附录 A — 连贯讲稿（可直接通读，约 9 分钟）

各位老师、同学好。我是今天汇报 HomeMate 的同学。HomeMate 是一个**纯仿真**的家庭陪伴机器人，面向 MIE1077 的课程交付：Pygame 实时 Demo、三到五分钟录屏、评估表，以及今天这份讲稿对应的幻灯片。

**动机。** 居家陪伴的典型请求是：「我累了，帮我煮杯咖啡。」机器人必须找到主人、读出情绪、说一句合适的话，再去操作智能家居。这是感知、认知、规划、执行的闭环。我们故意用俯视 2D 公寓保证投影清晰，但情绪输入用真实摄像头，避免在虚拟脸上做情感识别。

**架构。** 四模块加记忆：DeepFace 或 Mock 给情绪；Claude / GPT / MockLLM 做工具调用；规划层负责路径和子目标；Skills 驱动导航与十一台 mock IoT。工具统一 `dispatch_tool`，所以离线测通的路径可以直接换真模型。

**机器人主线——也是我们强调的技术难度。** 第一，`RobotController`：设备 dock、操作半径、主人房间信念、房间内蛇形覆盖、里程计。第二，代价地图 A*：状态带朝向，转向与过门有代价，主人是动态障碍，运行时 `PathTracker` 触发绕行重规划。第三，占据栅格加 frontier，以及多设备 TSP 路线优化。这些把「会说话」升级成「会规划、会避障、会扫房、会排任务顺序」。

**认知与工程。** ReAct 分解器保证 Mock 路径可复现；真模型走同一套工具；TTS/STT 补齐语音交互。演示侧有脚本、`--auto-run`、会话录制回放、世界快照，方便录视频和写报告。

**评估。** 二十场景、一百零九条准则，MockLLM+planner 基线满分；关掉情绪或规划器会明显掉分，支撑模块必要性论述。测试规模已超过一百个用例。

**Demo。** 请看三段：tired 煮咖啡闭环；多设备舒适场景；主人挡路时的动态重规划。

**收尾。** HomeMate 的主张很简单：陪伴机器人首先是一条**机器人流水线**，语言模型只是其中一环。谢谢大家。

---

# 附录 B — Q&A 预备（可选备注页）

| 可能问题 | 简答 |
|----------|------|
| 为什么不用 ROS / 真机？ | 课程交付是仿真；2D 可读性优先；核心算法（A*、belief、occupancy、TSP）与平台解耦。 |
| MockLLM 算不算作弊？ | Mock 是可复现基线；真 Claude/GPT 同构 tool path；报告同时给消融与 `--use-llm`。 |
| 和普通 ChatBot 差在哪？ | 操作半径、dock、动态障碍、重规划、覆盖搜索、多目标路线——执行层有几何与运动约束。 |
| 情绪为什么用真摄像头？ | 提案明确避开 3D avatar 脸；真实 webcam 更稳，也更适合课堂演示。 |
| 还缺什么？ | Phase 4：消融表定稿、Demo 视频、幻灯片抛光；真模型评估可按 API 预算补跑。 |

---

# 附录 C — 建议幻灯片版式（制作提示）

1. 深色或浅灰背景均可；**避免**纯紫渐变 / 奶油衬线 Terracotta 风（课堂投影对比度优先）。
2. 架构页用**横向流水线**，不要堆满文字；细节留给讲稿。
3. 机器人三页（5–7）是技术高潮：每页一张示意图 + 三条 bullet。
4. 评估页放大 **20/20 · 109/109**，消融用小表。
5. Demo 页只放 storyboard + 命令，切录屏时这页可静默停留。
6. 总页数建议 **12 页正文 + 可选 Q&A**；不要超过 15 页。
