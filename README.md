# SilentCut - 智能音频静音切割工具

SilentCut 专注于自动检测并移除音频中的静音段，适用于播客剪辑、语音预处理、数据清洗等场景。基于 VAD（Voice Activity Detection）语音检测技术，提供 GUI、Web、CLI 三种使用方式。

## 功能特性
- VAD 语音检测：基于 TenVAD 的智能语音段检测，精准识别人声
- 格式与编码保持：导出格式与输入一致，仅做切割不改变容器/编码（如输入 mp3 输出 mp3）
- 批量处理与详细日志：支持目录批量处理与处理比例/大小信息输出
- 波形/频谱可视化：对比处理前后效果（Web）
- 灵活参数配置：可调节 VAD 阈值、最大段时长、最小静音时长等参数

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
silentcut --help
silentcut-gui
silentcut-web

# 或仅安装依赖
pip install -r requirements.txt

# GUI
python silentcut_gui.py
# Web
python silentcut_web.py
# CLI
python silentcut_cli.py
```

## 使用说明

### GUI
- 选择"单文件/批处理"模式
- 设置 VAD 参数：`阈值`（0.0-1.0，默认 0.5）、`最大段时长(ms)`（默认 5000）、`最小静音(ms)`（默认 1000）
- 输出文件名添加 `-desilenced` 后缀，导出格式与输入一致

### Web
- 侧边栏设置 VAD 参数：阈值、最大段时长、最小静音时长
- 展示大小比例与波形/频谱对比，并提供下载

### CLI
```bash
# 单文件处理
silentcut process input.mp3 -o out --vad-threshold 0.5 --vad-min-silence-ms 1000 --vad-max-duration-ms 5000

# 批处理
silentcut batch input_dir -o out --vad-threshold 0.55 --vad-min-silence-ms 800 --vad-max-duration-ms 8000
```

## 项目结构
```
SilentCut/
├─ silentcut/
│  ├─ audio/            # VAD 音频处理器
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
- VAD 参数：`silentcut/utils/vad_detect.py` 中 `threshold/min_silence_ms/max_duration_ms`
- 导出格式：由 `silentcut/utils/file_utils.py:get_format_codec_from_path` 决定（与输入一致）

## 常见问题
- 处理后体积变大：现已按输入格式导出；如输入是 `wav`（无压缩）仍可能体积较大，可考虑使用压缩格式源文件
- 语音段过碎：调大 VAD 的 `min_silence_ms` 或设置 `max_duration_ms` 合并段
- 检测不到语音：尝试降低 `vad_threshold` 值（如从 0.5 降至 0.3）
