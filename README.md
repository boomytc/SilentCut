# SilentCut - 智能音频静音切割工具

SilentCut 专注于自动检测并移除音频中的静音段，适用于播客剪辑、语音预处理、数据清洗等场景。基于 VAD（Voice Activity Detection）语音检测技术，提供 GUI、Web、CLI 三种使用方式。

## 功能特性
- VAD 语音检测：基于 TenVAD 的智能语音段检测，精准识别人声
- 格式与编码保持：导出格式与输入一致，仅做切割不改变容器/编码
- 批量处理与详细日志：支持目录批量处理与处理信息输出
- 波形/频谱可视化：对比处理前后效果（Web）
- 灵活参数配置：阈值（0.0-1.0）、最大段时长、最小静音时长

## 系统要求
- Python 3.10+
- FFmpeg（pydub 依赖音频解码/编码）

## 安装与运行

```bash
git clone https://github.com/boomytc/SilentCut.git
cd SilentCut

# 开发模式安装（推荐）
pip install -e .
silentcut-gui    # GUI
silentcut-web    # Web
silentcut --help # CLI

# 或仅安装依赖后直接运行
pip install -r requirements.txt
python silentcut_gui.py
```

## 使用说明

### 参数说明
- `vad-threshold`：语音检测阈值（0.0-1.0，默认 0.5）
- `vad-max-duration-ms`：最大段时长（默认 5000ms）
- `vad-min-silence-ms`：最小静音时长（默认 1000ms）

### GUI
选择"单文件/批处理"模式，设置参数后处理。输出文件名添加 `-desilenced` 后缀。

### Web
侧边栏设置参数，展示波形/频谱对比与大小比例，可下载结果。

### CLI
```bash
# 单文件
silentcut process input.mp3 -o out --vad-threshold 0.5

# 批处理
silentcut batch input_dir -o out --vad-threshold 0.55 --vad-min-silence-ms 800
```

## 项目结构
```
SilentCut/
├─ silentcut/
│  ├─ audio/            # VAD 音频处理
│  ├─ gui/              # GUI 界面
│  ├─ web/              # Streamlit 应用
│  ├─ cli/              # 命令行
│  └─ utils/            # 工具模块
├─ silentcut_gui.py
├─ silentcut_web.py
└─ silentcut_cli.py
```

## 常见问题
- 处理后体积变大：如输入是 `wav` 等无压缩格式，可考虑使用压缩格式源文件
- 语音段过碎：调大 `min_silence_ms` 或 `max_duration_ms`
- 检测不到语音：降低 `vad_threshold`（如从 0.5 降至 0.3）
