"""
自定义 Matplotlib 画布小部件，用于在 PyQt6 中显示波形图
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import numpy as np
import matplotlib
import platform

# ----------------- Matplotlib 中文字体配置 ------------------ #

def _configure_matplotlib_fonts():
    """根据操作系统为 Matplotlib 设置默认的可用中文字体。"""
    os_name = platform.system()

    if os_name == "Windows":
        # Windows 常见中文字体（SimHei/微软雅黑）
        candidates = [
            "SimHei",         # 黑体
            "Microsoft YaHei",  # 微软雅黑
            "Arial Unicode MS",  # 覆盖大部分字符
        ]
    elif os_name == "Darwin":  # macOS
        candidates = [
            "PingFang SC",    # 系统默认中文字体
            "Hiragino Sans GB",  # 10.15 之前系统字体
            "Heiti SC",       # 老系统黑体
            "Arial Unicode MS",
        ]
    else:  # Linux
        candidates = [
            "Noto Sans CJK SC",  # Noto 字体系列
            "WenQuanYi Zen Hei", # 文泉驿
            "SimHei",
        ]

    # 追加 DejaVu Sans 作为兜底，确保西文符号正常
    font_list = candidates + ["DejaVu Sans"]

    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = font_list
    # 解决负号无法显示
    matplotlib.rcParams["axes.unicode_minus"] = False

# 仅在第一次导入时执行一次
_configure_matplotlib_fonts()


class MplCanvas(FigureCanvasQTAgg):
    """Matplotlib 画布，可集成到 PyQt 应用中"""
    
    def __init__(self, width=5, height=4, dpi=100):
        """初始化画布"""
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        # 支持中文显示
        self.fig.set_tight_layout(True)
        super().__init__(self.fig)


class WaveformCanvas(QWidget):
    """波形图显示控件"""
    
    def __init__(self, parent=None):
        """初始化波形图控件"""
        super().__init__(parent)
        self.canvas = MplCanvas(width=8, height=3, dpi=100)
        
        # 设置布局
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        
    def plot_waveform(self, y, sr, title="波形图"):
        """
        绘制音频波形
        
        Args:
            y: 音频数据数组
            sr: 采样率
            title: 图表标题
        """
        # 清除当前图表
        self.canvas.axes.clear()
        
        # 计算时间轴
        time = np.linspace(0, len(y) / sr, num=len(y))
        
        # 绘制波形
        self.canvas.axes.plot(time, y)
        
        # 设置标题和标签
        self.canvas.axes.set_title(title)
        self.canvas.axes.set_xlabel("时间 (秒)")
        self.canvas.axes.set_ylabel("振幅")
        
        # 设置时间轴刻度
        duration = len(y) / sr
        num_ticks = min(10, max(2, int(duration)))
        ticks = np.linspace(0, duration, num=num_ticks)
        self.canvas.axes.set_xticks(ticks)
        self.canvas.axes.set_xticklabels([f"{t:.2f}" for t in ticks])
        
        # 更新画布
        self.canvas.draw()
    
    def clear(self):
        """清除波形图"""
        self.canvas.axes.clear()
        self.canvas.draw()
