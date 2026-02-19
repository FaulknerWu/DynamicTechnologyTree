# Dynamic Technology Tree（Stellaris 科技树生成器）

![Dynamic Technology Tree](thumbnail.jpeg)

**Dynamic Technology Tree** MOD 的配套生成工具。扫描 Stellaris 本体及已启用 MOD 的科技定义与本地化，在游戏内为每个科技自动生成格式化的"科技树"描述。

> **⚠️ 破坏性变更**：生成时现在必须选择一个 Stellaris 存档（`.sav`）。工具将根据存档中的帝国科技状态生成针对性的科技树描述。仅支持非铁人模式的文本存档。

## 功能特性

- 自动扫描本体与已启用 MOD（Steam 创意工坊 + 本地 MOD）的科技数据
- 按 MOD 加载顺序合并科技定义与本地化，后加载覆盖先加载
- 可配置的显示参数（最大深度、每节点子项数、展示节点数）
- 输出 Stellaris 可直接读取的本地化 `.yml` 文件
- 基于存档的科技树生成：读取 `.sav` 文件，按帝国实际科技状态定制输出
- 提供 **PyQt6 图形界面**，选择存档后一键生成

## 快速开始

**环境要求**：Python **3.10+**｜目标 Stellaris 版本：**v4.2.\***

```bash
# 安装
python -m pip install -e .

# 启动 GUI
dtt-gui
```

首次运行时在 GUI 中填写 Stellaris 安装路径与 MOD 目录。点击"生成"后，GUI 会弹出文件选择对话框要求选择一个 Stellaris 存档（`.sav`）。选择后自动开始生成，输出文件位于 `./localisation/`。

> **注意**：每次生成都需要重新选择存档。输出基于所选存档的帝国状态，重复运行会覆盖 `./localisation/` 下的同名文件。如需保留多次生成结果，请在不同工作目录下运行。

## 存档要求

- 仅支持**非铁人模式**的文本格式 `.sav` 存档
- 铁人模式或二进制格式的存档会被拒绝，GUI 将显示错误提示
- 存档通常位于 `Documents/Paradox Interactive/Stellaris/save games/`

## 配置（`config.ini`）

GUI 会引导你完成配置。也可以手动编辑 `config.ini`：

```ini
[paths]
base_game_path = /path/to/Stellaris
mod_folder_path = /path/to/Steam/steamapps/workshop/content/281990
local_mod_folder_path =
launcher_db_path = /path/to/launcher-v2.sqlite

[localization]
language = english

[display]
max_children_per_node = 12
max_tree_depth = 4
max_display_nodes = 128
```

- `base_game_path`（必填）：Stellaris 本体安装目录
- `mod_folder_path`（必填）：Steam 创意工坊 MOD 目录
- `launcher_db_path`（必填）：Paradox Launcher 数据库 `launcher-v2.sqlite`（用于读取已启用 MOD 与加载顺序）
- `local_mod_folder_path`（可选）：本地 MOD 目录

> 提示：`launcher-v2.sqlite` 通常位于 `Documents/Paradox Interactive/Stellaris/launcher-v2.sqlite`。
> 旧版配置项 `dlc_load_path` / `priority_mods` 已移除，升级后请删除这些键。

## Windows 打包

Windows `.exe` 必须在 Windows 上构建：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install pyinstaller
pyinstaller packaging/pyinstaller/techtree_gui.spec
```

## 开发

```bash
# 安装开发依赖
python -m pip install -e ".[dev]"

# 运行测试
python -m pytest
```

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| "required configuration entries missing" | `config.ini` 缺少必填路径，至少需填写 `base_game_path`、`mod_folder_path`、`launcher_db_path` |
| 选择存档后提示格式不支持 | 仅支持非铁人模式的文本 `.sav`；铁人存档或二进制格式无法解析 |
| GUI 启动但无输出文件 | 检查启动目录（或 EXE 所在目录）下是否有 `localisation/` 文件夹 |
| 识别不到已启用 MOD | 检查 `launcher_db_path` 是否指向 `launcher-v2.sqlite`；并确认 Paradox Launcher 中有已激活的 playset |
| "No module named 'PyQt6'" | 运行 `python -m pip install -e .` 安装依赖 |
