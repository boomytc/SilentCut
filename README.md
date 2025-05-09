# SilentCut - 智能音频静音切割工具

**SilentCut** 是一个高效的音频处理工具，专注于自动检测并去除音频中的静音段。它适用于播客剪辑、语音预处理、数据清洗等场景，支持批量处理和自定义静音判定参数，帮助用户快速提取有效音频内容。

## ✨ 功能特性
- 🎯 精准静音检测（基于能量阈值算法）
- ⚡ 高速处理，支持多进程并行计算
- 🛠️ 自定义参数：静音时长、音量阈值等
- 📦 支持批量音频文件处理
- 🖥️ 提供三种使用方式：GUI界面、Web界面和命令行工具
- 📊 波形可视化和处理结果对比
- 🔄 自适应阈值搜索算法（精确到±2dBFS）
- 📝 完善的日志记录与错误处理

## 系统要求
- Python 3.8+
- FFmpeg（用于音频处理）

## 安装方法

### 方法一：直接从源码运行
```bash
# 克隆仓库
git clone https://github.com/boomytc/SilentCut.git
cd SilentCut

# 安装依赖
pip install -r requirements.txt

# 运行GUI界面
python silentcut_gui.py

# 或运行Web界面
python silentcut_web.py

# 或使用命令行工具
python silentcut_cli.py
```

### 方法二：通过pip安装
```bash
# 安装包
pip install silentcut

# 使用命令行工具
silentcut --help

# 启动GUI界面
silentcut-gui

# 启动Web界面
silentcut-web
```

## 使用说明

### GUI界面
1. 选择单文件/批量处理模式
2. 设置静音检测参数（默认500ms）
3. 启用多核加速（推荐4核以上CPU）
4. 实时查看处理日志和进度
5. 输出文件自动保存为*-desilenced.wav

### Web界面
1. 启动Web服务后，在浏览器中访问显示的URL（通常是http://localhost:8501）
2. 上传音频文件
3. 调整处理参数
4. 点击“开始处理”按钮
5. 查看处理结果并下载处理后的文件

### 命令行工具
```bash
# 处理单个文件
silentcut process input.mp3 -o output_dir -l 500

# 批量处理目录
silentcut batch input_dir -o output_dir -l 500 -w 4

# 查看帮助
silentcut --help
```

## 项目结构
```
SilentCut/
├─ silentcut/            # 核心包
│   ├─ audio/            # 音频处理模块
│   │   ├─ processor.py  # 音频处理器
│   │   └─ ...
│   ├─ gui/              # GUI界面
│   │   ├─ controllers/  # 控制器
│   │   ├─ views/        # 视图
│   │   ├─ widgets/      # 自定义控件
│   │   └─ main.py       # GUI入口
│   ├─ web/              # Web界面
│   │   └─ app.py        # Streamlit应用
│   ├─ cli/              # 命令行工具
│   │   └─ __main__.py   # CLI入口
│   └─ utils/            # 工具函数
│       ├─ logger.py     # 日志工具
│       ├─ file_utils.py # 文件处理
│       └─ cleanup.py    # 清理工具
├─ silentcut_gui.py      # GUI启动脚本
├─ silentcut_web.py      # Web启动脚本
├─ silentcut_cli.py      # CLI启动脚本
├─ setup.py              # 安装配置
└─ README.md             # 文档
```

## 高级配置
- 预设阈值列表：`silentcut/audio/processor.py` 中的 `PRESET_THRESHOLDS` 变量
- 多进程配置：`silentcut/gui/controllers/desilencer_controller.py` 中的 `DesilencerController` 类
- 日志级别：`silentcut/utils/logger.py` 中的 `setup_logger` 函数

## 常见问题

### Q: 处理后的文件比原始文件大？
A: 这可能是因为阈值设置过低，导致大量噪音被认为是有效音频。尝试提高阈值（例如从 -50 dBFS 提高到 -30 dBFS）。在 GUI 中，可以启用并行阈值搜索功能，自动找到最佳阈值。

### Q: 多进程处理未生效？
A: 确认以下几点：
1. 在 GUI 中确认已勾选“启用多进程处理”
2. 核心数设置不要超过系统物理核心数
3. 在 macOS 上，可能需要使用 `spawn` 而非 `fork` 启动方式（这在代码中已经处理）

### Q: 如何选择最佳静音阈值？
A: 静音阈值因音频内容而异。对于语音文件，通常 -30 到 -40 dBFS 效果较好。对于音乐文件，可能需要更低的阈值（-50 到 -60 dBFS）。在 GUI 和 Web 界面中，可以启用并行阈值搜索功能，自动找到最佳阈值。

## 贡献与反馈
如果你有任何问题或建议，请在 GitHub 仓库上提交 Issue 或 Pull Request。我们非常欢迎你的贡献！
