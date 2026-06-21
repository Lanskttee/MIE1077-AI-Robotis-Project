# 新增功能记录（Contributions Log）

本文件记录 **UI / 演示增强 / 离线工具链** 方向的开发与后续追加内容，便于组内同步贡献与演示说明。

维护约定：每次新增功能在此追加一条记录（日期 + 模块 + 说明 + 用法）。

---

## 2026-06-09 — 第一批：离线演示 UI 增强

**涉及文件**

| 文件 | 说明 |
|------|------|
| `homemate/ui_options.py` | Pygame 启动 CLI 参数解析 |
| `homemate/ui_trace.py` | Agent 工具轨迹格式化（无 pygame 依赖，可单测） |
| `homemate/main.py` | 侧栏、进度条、离线模式、键盘交互 |
| `tests/test_ui_options.py` | CLI 与轨迹格式化单元测试 |

**功能清单**

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

6. **地图标注**：`ROBOT` / `OWNER`；顶栏显示 robot/owner 房间与 Agent 模式。

7. **记忆管理**：`c` 清空 `data/memory/`。

8. **启动引导**：Mock 模式提示按 `1`–`6` 注入情绪。

---

## 2026-06-09 — 第二批：演示脚本 + 世界快照 + IoT 面板

**涉及文件**

| 文件 | 说明 |
|------|------|
| `homemate/demo_scripts.py` | 内置可复现演示脚本 |
| `homemate/world_snapshot.py` | 世界状态 JSON 快照 save/load |
| `homemate/ui_devices.py` | IoT 侧栏格式化 |
| `homemate/main.py` | 自动运行、F5/F9 快照、Devices 面板 |
| `tests/test_demo_scripts.py` | 演示脚本测试 |
| `tests/test_world_snapshot.py` | 快照 round-trip 测试 |
| `tests/test_ui_devices.py` | IoT 格式化测试 |

**功能清单**

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

2. **`--auto-run`**：启动约 1.5 秒后自动发送脚本消息。

3. **世界快照 F5 / F9**
   - `F5` → `data/scenarios/last_snapshot.json`
   - `F9` 从默认路径恢复
   - `--load-snapshot PATH` 启动时加载

4. **IoT 设备总览面板（`i`）**。

---

## 2026-06-09 — 第三批：会话录制/回放模块 + 批量演示运行器

### 模块 A — `homemate/session/`（完整功能模块）

**目的**：把每次 Pygame 交互完整落盘，支持逐步回放，用于录视频、调试、课程报告附件。

**涉及文件**

| 文件 | 说明 |
|------|------|
| `homemate/session/store.py` | `SessionStore` / `TurnRecord` / `SessionRecord` |
| `homemate/session/replay.py` | `ReplayController` 逐步恢复 world + dialogue + tool trace |
| `homemate/main.py` | 自动录制、回放模式、`[/]` 步进 |
| `tests/test_session.py` | 录制 / 加载 / 回放 / 导出测试 |

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

**目的**：无 GUI、无 API 地批量跑完 4 个内置演示脚本，输出通过/失败表，可直接贴进课程报告。

**涉及文件**

| 文件 | 说明 |
|------|------|
| `homemate/demo_runner/runner.py` | `DemoBatchRunner` + 检查项（find_owner / read_emotion / speak / IoT） |
| `homemate/demo_runner/__main__.py` | CLI 入口 |
| `tests/test_demo_runner.py` | 全脚本通过性测试 |

**用法**

```powershell
python -m homemate.demo_runner
python -m homemate.demo_runner --only tired_coffee,wind_down
python -m homemate.demo_runner --json out/demo_scripts.jsonl --verbose
```

输出示例：每个脚本的 Pass/Fail、工具调用数、spoken 行数。

---

## 待办 / 下一批（规划）

- [ ] 启动引导 overlay（首次打开分步提示）
- [ ] 对话 / 会话导出为 JSON（`SessionStore.export_session` 已有，补 UI 快捷键）
- [ ] `--script` 链式自动播放（多场景连续录视频）
- [ ] Replay 面板点击 session 条目直接加载

---

## 快速演示命令

```powershell
# 一键离线自动演示（录视频）
python -m homemate.main --script tired_coffee --auto-run

# 批量验证 4 个演示脚本（报告用表格）
python -m homemate.demo_runner

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
homemate/demo_runner/runner.py
homemate/demo_runner/__main__.py
tests/test_ui_options.py
tests/test_ui_devices.py
tests/test_demo_scripts.py
tests/test_world_snapshot.py
tests/test_session.py
tests/test_demo_runner.py
homemate/main.py   (大幅增强)
```
