# 新增功能记录（Contributions Log）

---

## 离线演示 UI 增强



1. **离线演示模式 `--offline`**
   - 等价于 `--mock-llm --mock-emotion --freeze-owner`
   - 不调用 Anthropic API，不依赖摄像头
   ```powershell
   python -m homemate.main --offline --owner-room bedroom --emotion tired
   ```

2. **CLI 参数**
   | 参数 | 作用 |
   |------|------|
   | `--seed N` | 固定随机种子 |
   | `--owner-room <room>` | 主人固定在指定房间 |
   | `--emotion <label>` | 启动时预注入 Mock 情绪 |
   | `--mock-llm` | 强制 MockLLM |
   | `--mock-emotion` | 强制 Mock 情绪 |
   | `--freeze-owner` | 禁止主人在房间间随机走动 |
   | `--replan-demo` | 重规划演示：主人可走动，约 1s 自动发咖啡请求；窗口内按 **F2** 手动触发 |

3. **五栏侧栏**（`Tab` 循环，快捷键跳转）
   | 面板 | 键 | 内容 |
   |------|-----|------|
   | Chat | `d` | 对话记录，PgUp/PgDn 滚动 |
   | Act | `a` | 上一轮 Agent 工具调用轨迹（绿 `+` / 红 `!`） |
   | Mem | `m` | 长期记忆摘要 |
   | IoT | `i` | 11 设备按房间分组的状态总览 |
   | Replay | `v` | 会话录制状态 / 回放控制 |

4. **回合结束自动跳转 Actions 面板**。

5. **IoT 可视化进度条**（咖啡机、烤面包机、窗帘、灯、电视/音箱、风扇）。

6. **地图标注**：`ROBOT` / `OWNER`；顶栏两行显示 robot/owner 房间、`(mode, Nt, R)` 与状态灰字。

7. **记忆管理**：`c` 清空 `data/memory/`。

8. **启动引导**：Mock 模式提示按 `1`–`6` 注入情绪；输入框用 `TEXTINPUT`（避免重复字符）；**F2** 发送预设咖啡请求。

---

## 演示脚本 + 世界快照 + IoT 面板



1. **内置演示脚本 `--script`**
   ```powershell
   python -m homemate.main --list-scripts
   python -m homemate.main --script tired_coffee --auto-run
   ```
   | 脚本 ID | 场景 |
   |---------|------|
   | `tired_coffee` | tired 主人 → 找主人 → 共情 → 煮咖啡 |
   | `sad_talk` | 纯情感陪伴，无 IoT |
   | `wind_down` | 关灯 + 音乐 + 窗帘（多设备） |
   | `multi_comfort` | 恒温器 + 咖啡 + 调灯（三动作） |

   > 注意：`--script` 隐含 `--freeze-owner`，**不适合**测动态重规划；重规划请用 `--replan-demo`。

2. **`--auto-run`**：启动约 1.5 秒后自动发送脚本消息（`--replan-demo` 约 1 秒）。

3. **世界快照 F5 / F9**
   - `F5` → `data/scenarios/last_snapshot.json`
   - `F9` 从默认路径恢复
   - `--load-snapshot PATH` 启动时加载

4. **IoT 设备总览面板（`i`）**。

---

## 会话录制/回放模块 + 批量演示运行器

### 模块 A — `homemate/session/`（完整功能模块）

把每次 Pygame 交互完整落盘，支持逐步回放，用于录视频、调试、课程报告附件。


**数据落盘**：`data/sessions/<timestamp>_<script>.json`

每轮 `TurnRecord` 包含：
- `world_before` / `world_after`（robot、owner、全部 IoT）
- `tool_trace` / `spoken` / `final_text` / `emotion_label`

**CLI**

```powershell
python -m homemate.main --list-sessions
python -m homemate.main --replay-session <SESSION_ID>
python -m homemate.main --no-record          # 关闭自动录制
python -m homemate.main --session-title "My demo"
```

**Pygame 快捷键**

| 键 | 作用 |
|----|------|
| `p` | 进入/退出回放模式 |
| `[` / `]` | 上一回合 / 下一回合 |
| `v` | 打开 Replay 侧栏 |

回放时：恢复该回合结束时的 world 状态，同步 dialogue 与 Actions 面板。

---

### 模块 B — `homemate/demo_runner/`（完整功能模块）

无 GUI、无 API 地批量跑完 4 个内置演示脚本，输出通过/失败表，可直接贴进课程报告。



**用法**

```powershell
python -m homemate.demo_runner
python -m homemate.demo_runner --only tired_coffee,wind_down
python -m homemate.demo_runner --json out/demo_scripts.jsonl --verbose
```

输出示例：每个脚本的 Pass/Fail、工具调用数、spoken 行数。

---

## `homemate/robot/` 机器人核心模块（Robotics 主线）

把机器人本身从 UI/LLM 层抽离为独立运动+感知+操作栈（运动规划、覆盖搜索、概率定位、操作可达性）。

**涉及文件**

| 文件 | 说明 |
|------|------|
| `homemate/robot/kinematics.py` | 设备位姿、停靠点 (dock)、Manhattan 操作半径 |
| `homemate/robot/belief.py` | 主人房间概率信念 `OwnerBelief`（观测更新 + 与时段先验融合） |
| `homemate/robot/coverage.py` | Boustrophedon 房间覆盖路径（系统化搜索 waypoints） |
| `homemate/robot/motion.py` | 里程计 `MotionMetrics`（tile 数、导航次数、**replan_count**） |
| `homemate/robot/controller.py` | `RobotController` 统一调度导航/搜索/操作校验 |
| `homemate/robot/__main__.py` | 离线 benchmark CLI（覆盖 + belief + costmap + 多设备 route） |
| `homemate/action/skills.py` | 全面接入 `RobotController` |
| `homemate/cognition/tools.py` | Agent 工具（共 **14** 个，见第五/六批） |
| `tests/test_robot.py` | 8 项机器人层测试 |

### 子系统说明

#### 1. 运动规划与里程计
- 默认 **costmap A***（转向惩罚 + 主人 social cost）；失败时 fallback plain A*
- `RobotController.commit_path` 统一记录 `path_cost` / `turn_count` / `planner`
- `get_robot_state` 返回 `pose / mode / motion / path_tracker / map`
- Pygame 顶栏显示 `(mode, Nt, R)` — **R** 为累计重规划次数

#### 2. 操作可达性（Manipulation）
- 每个 IoT 设备有 grid 位姿 + **dock 停靠点**（最近可通行操作位）
- `navigate_to_device` 导航到 dock，而非仅到房间中心
- `set_device` **强制** Manhattan 距离 ≤ 2，否则返回 `hint: navigate_to_device`
- 体现「先到位、再操作」的机器人任务约束

#### 3. 概率定位（Owner Belief）
- `OwnerBelief` 维护 4 房间离散概率分布
- `look_around` / `find_owner` / `scan_room` 后更新 belief
- `find_owner` 搜索顺序 = **belief 排序 ⊕ 时段先验**（`OwnerSearchPolicy`）

#### 4. 覆盖搜索（Coverage Search）
- `CoveragePlanner` 生成 boustrophedon 蛇形 waypoints（基于 costmap 估代价）
- `find_owner` 在房间中心未见主人时，自动触发 **intra-room scan**
- 新工具 `scan_room(room)` 可单独调用完整房间 sweep

#### 5. Benchmark CLI
```powershell
python -m homemate.robot
```
输出：每房间 sweep 代价、plain vs costmap 对比、多设备 TSP 顺序、belief 演示。

### 验证结果（第四批）
- **eval 20/20**（109/109 criteria）
- **demo_runner 4/4**

---

## 代价地图 A* + 动态重规划

引入带转向惩罚的状态空间 A*、动态障碍代价（主人格阻塞 + 邻格 proximity cost）、Pygame 运行时重规划。

**涉及文件**：`homemate/planning/costmap.py`、`homemate/robot/path_tracker.py`、`tests/test_costmap.py`

- 状态空间 `(x, y, dir)` + 转向惩罚 + 过门 cost + 主人 social navigation
- `PathTracker`：`owner_moved` / `owner_on_next_tile` 触发 `try_replan()`
- `find_owner` 成功后 `enable_owner_tracking()`；导航去设备时**不覆盖**设备目标
- fallback A* 仍避开主人格

**可视化测试**（不要用 `--offline`，会冻结主人）：
```powershell
python -m homemate.main --replan-demo
```
窗口标题含 `[Replan demo]`；约 1s 自动发送或按 **F2**；顶栏两行 **R** 同步递增；灰字显示 `Animating N tiles left | R=N | last: owner_moved`。

---

## 占据栅格 + 多目标路径优化（TSP）

经典移动机器人 **Occupancy Grid + Frontier Exploration**，以及多 IoT 设备 **TSP 路径优化**（nearest-neighbor + 2-opt）。

**涉及文件**：`homemate/robot/occupancy.py`、`homemate/robot/route_optimizer.py`、`tests/test_occupancy.py`、`tests/test_route_optimizer.py`

**新增 3 个 Agent 工具**（合计 14 个）：
- `plan_device_route` — 规划多设备最优访问顺序（不移动）
- `visit_devices` — 沿优化路线依次导航到各 dock
- `explore_frontier` — 主动探索 unknown frontier（辅助找主人）

```powershell
# 终端示例（无 GUI）
python -c "
from homemate.cognition.tools import dispatch_tool
# ... setup Skills ...
dispatch_tool(skills, 'plan_device_route', {'device_ids': ['coffee.kitchen','lamp.bedroom']})
"
```

- 地图 **淡绿色 overlay** = 已探索自由格（`OccupancyGrid.reveal_from_pose`）
- `find_owner` 在 belief sweep + coverage scan 失败后，自动 **frontier_explore**（最多 2 hop）

### 验证结果（第五+六批后）
- **99 tests passed**
- **eval 20/20**（109/109 criteria）
- **demo_runner 4/4**

---

## 快速演示命令

```powershell
# 一键离线自动演示（录视频，主人冻结）
python -m homemate.main --script tired_coffee --auto-run

# 动态重规划演示（主人可走动）
python -m homemate.main --replan-demo

# 批量验证 4 个演示脚本（报告用表格）
python -m homemate.demo_runner

# 机器人 benchmark（报告用表格）
python -m homemate.robot

# 列出已录制的会话
python -m homemate.main --list-sessions

# 回放某次会话
python -m homemate.main --replay-session 20260609_153045_tired_coffee

# 全量测试
python -m pytest tests/ -q
```

---

## 新增文件总览（Contributor 分支）

```
docs/MY_CONTRIBUTIONS.md
homemate/ui_options.py
homemate/ui_trace.py
homemate/ui_devices.py
homemate/demo_scripts.py
homemate/world_snapshot.py
homemate/session/store.py
homemate/session/replay.py
homemate/robot/kinematics.py
homemate/robot/belief.py
homemate/robot/coverage.py
homemate/robot/motion.py
homemate/robot/controller.py
homemate/robot/__main__.py
homemate/planning/costmap.py
homemate/robot/path_tracker.py
homemate/robot/occupancy.py
homemate/robot/route_optimizer.py
tests/test_costmap.py
tests/test_occupancy.py
tests/test_route_optimizer.py
homemate/demo_runner/runner.py
homemate/demo_runner/__main__.py
tests/test_ui_options.py
tests/test_ui_devices.py
tests/test_demo_scripts.py
tests/test_world_snapshot.py
tests/test_session.py
tests/test_demo_runner.py
tests/test_robot.py
homemate/main.py   (大幅增强)
homemate/action/skills.py  (接入 RobotController)
homemate/cognition/tools.py  (14 工具：scan_room, get_robot_state, plan_device_route, visit_devices, explore_frontier, ...)
```
