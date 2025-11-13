# SilentCut - 智能音频静音切割工具

SilentCut 专注于自动检测并移除音频中的静音段，适用于播客剪辑、语音预处理、数据清洗等场景。提供阈值静音切割与 VAD 语音检测两种模式，并覆盖 GUI、Web、CLI 三种使用方式。

## 功能特性
- 阈值静音切割：基于 dBFS 的静音检测，支持并行阈值搜索与自适应搜索
- VAD 语音检测：基于 TenVAD 的语音段检测，更贴合“保留人声”的目标
- 互斥模式控制：启用 VAD 时自动禁用并行阈值搜索与多进程处理
- 格式与编码保持：导出格式与输入一致，仅做切割不改变容器/编码（如输入 mp3 输出 mp3）
- 批量处理与详细日志：支持目录批量处理与处理比例/大小信息输出
- 波形/频谱可视化：对比处理前后效果（Web）

## 系统要求
- Python 3.8+
- FFmpeg（pydub 依赖音频解码/编码）

## 安装与运行

### 源码运行
```bash
git clone https://github.com/boomytc/SilentCut.git
cd SilentCut

# 开发模式安装（推荐）
pip install -e .

# 或仅安装依赖
pip install -r requirements.txt

# GUI
python silentcut_gui.py
# Web
python silentcut_web.py
# CLI
python silentcut_cli.py
```

### 包方式
```bash
pip install silentcut
silentcut --help
silentcut-gui
silentcut-web
```

## 使用说明

### GUI
- 选择“单文件/批处理”模式
- 阈值模式：可启用并行阈值搜索并设置预设阈值列表
- VAD 模式：勾选“启用VAD语音检测”，可设置 `阈值`、`最大段时长(ms)`、`最小静音(ms)`；启用后并行阈值与多进程将自动禁用
- 输出文件名添加 `-desilenced` 后缀，导出格式与输入一致

### Web
- 侧边栏设置“最小静音长度 (ms)”与“VAD 参数”
- 启用 VAD 时自动关闭并行阈值与多进程
- 展示大小比例与波形/频谱对比，并提供下载

### CLI
```bash
# 阈值模式（单文件）
silentcut process input.mp3 -o out -l 500

# 阈值模式（批处理）
silentcut batch input_dir -o out -l 500 -w 4

# VAD 模式（单文件）
silentcut process input.mp3 -o out --use-vad --vad-threshold 0.5 --vad-min-silence-ms 1000 --vad-max-duration-ms 8000

# VAD 模式（批处理，自动禁用多进程）
silentcut batch input_dir -o out --use-vad --vad-threshold 0.55 --vad-min-silence-ms 800 --vad-max-duration-ms 10000
```

## 项目结构
```
SilentCut/
├─ silentcut/
│  ├─ audio/            # 处理器（阈值/VAD）
│  ├─ gui/              # GUI 控制器/视图/控件
│  ├─ web/              # Streamlit 应用
│  ├─ cli/              # 命令行入口
│  └─ utils/            # 日志、文件工具、VAD封装
├─ silentcut_gui.py     # GUI 启动脚本
├─ silentcut_web.py     # Web 启动脚本
├─ silentcut_cli.py     # CLI 启动脚本
└─ README.md
```

## 高级配置
- 阈值预设列表：`silentcut/audio/processor.py` 中 `PRESET_THRESHOLDS`
- VAD 参数：`silentcut/utils/vad_detect.py` 中 `threshold/min_silence_ms/max_duration_ms`
- 互斥规则：
  - GUI/Web：启用 VAD → 禁用并行阈值与多进程
  - CLI：批处理启用 VAD → 自动禁用多进程
- 导出格式：由 `silentcut/utils/file_utils.py:get_format_codec_from_path` 决定（与输入一致）

## 常见问题
- 处理后体积变大：现已按输入格式导出；如输入是 `wav`（无压缩）仍可能体积较大，可考虑使用压缩格式源文件
- 语音段过碎：调大 VAD 的 `min_silence_ms` 或设置 `max_duration_ms` 合并段
- 阈值模式找不到有效阈值：调整 `min_silence_len` 或扩展预设阈值范围
