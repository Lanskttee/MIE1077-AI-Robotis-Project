# 新增功能记录（Contributions Log）

本文件记录 **UI / 演示增强** 方向的开发与后续追加内容，便于组内同步贡献与演示说明。

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

3. **四栏侧栏**（`Tab` 循环，`d/a/m/i` 快捷键）
   | 面板 | 键 | 内容 |
   |------|-----|------|
   | Chat | `d` | 对话记录，PgUp/PgDn 滚动 |
   | Act | `a` | 上一轮 Agent 工具调用轨迹（绿 + 成功 / 红 ! 失败） |
   | Mem | `m` | 长期记忆摘要（回合数、情绪统计、近期请求） |
   | IoT | `i` | 11 个设备按房间分组的状态总览 |

4. **回合结束自动跳转 Actions 面板**，便于演示 pipeline。

5. **IoT 可视化进度条**：咖啡机、烤面包机、窗帘、灯、电视/音箱音量、风扇转速。

6. **地图标注**：`ROBOT` / `OWNER` 标签；顶栏显示 robot/owner 所在房间与 Agent 模式。

7. **记忆管理**：`c` 清空 `data/memory/` 长期记忆。

8. **启动引导**：Mock 模式下提示先按 `1`–`6` 注入情绪。

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
   | `tired_coffee` |  tired 主人 → 找主人 → 共情 → 煮咖啡 |
   | `sad_talk` | 纯情感陪伴，无 IoT |
   | `wind_down` | 关灯 + 音乐 + 窗帘（多设备） |
   | `multi_comfort` | 恒温器 + 咖啡 + 调灯（三动作） |

2. **`--auto-run`**：启动约 1.5 秒后自动发送脚本消息，适合录屏零操作。

3. **世界快照 F5 / F9**
   - `F5`：保存 robot / owner / 全部 IoT 状态到 `data/scenarios/last_snapshot.json`
   - `F9`：从默认路径恢复
   - `--load-snapshot PATH`：启动时加载指定快照

4. **IoT 设备总览面板（`i`）**：按房间列出 11 设备实时 state 摘要。

---

## 待办 / 下一批（规划）

- [ ] 启动引导 overlay（首次打开分步提示）
- [ ] 对话历史导出为 JSON/TXT
- [ ] 侧栏设备面板点击高亮地图上的设备
- [ ] `--script` 链式自动播放（多场景连续录视频）

---

## 快速演示命令（推荐）

```powershell
# 一键离线自动演示（录视频用）
python -m homemate.main --script tired_coffee --auto-run

# 查看所有脚本
python -m homemate.main --list-scripts

# 跑测试
python -m pytest tests/ -q
```
