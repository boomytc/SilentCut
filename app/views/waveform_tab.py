"""
波形查看标签页 - 用于显示音频波形图
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFileDialog, QGroupBox
)
from PyQt6.QtCore import pyqtSignal

from app.widgets.mpl_canvas import WaveformCanvas


class WaveformTabView(QWidget):
    """波形查看标签页视图"""
    
    # 定义视图发出的信号
    browse_audio_signal = pyqtSignal()
    
    def __init__(self):
        """初始化波形查看标签页视图"""
        super().__init__()
        self.controller = None  # 控制器引用将由MainWindow设置
        self.initUI()
    
    def initUI(self):
        """初始化用户界面"""
        # 主布局
        main_layout = QVBoxLayout()
        
        # === 文件选择区域 ===
        file_group = QGroupBox("音频文件")
        file_layout = QHBoxLayout()
        
        # 文件信息标签
        self.file_info_label = QLabel("未选择文件")
        file_layout.addWidget(self.file_info_label)
        
        # 浏览按钮
        self.browse_btn = QPushButton("浏览音频文件...")
        self.browse_btn.clicked.connect(self.browse_audio_signal.emit)
        file_layout.addWidget(self.browse_btn)
        
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # === 音频信息区域 ===
        info_group = QGroupBox("音频信息")
        info_layout = QHBoxLayout()
        
        # 音频时长
        self.duration_label = QLabel("时长: -")
        info_layout.addWidget(self.duration_label)
        
        # 采样率
        self.sample_rate_label = QLabel("采样率: -")
        info_layout.addWidget(self.sample_rate_label)
        
        # 通道数
        self.channels_label = QLabel("通道: -")
        info_layout.addWidget(self.channels_label)
        
        info_group.setLayout(info_layout)
        main_layout.addWidget(info_group)
        
        # === 波形图区域 ===
        waveform_group = QGroupBox("波形图")
        waveform_layout = QVBoxLayout()
        
        # 创建波形图控件
        self.waveform_canvas = WaveformCanvas()
        waveform_layout.addWidget(self.waveform_canvas)
        
        waveform_group.setLayout(waveform_layout)
        main_layout.addWidget(waveform_group, stretch=1)
        
        # 设置布局
        self.setLayout(main_layout)
    
    def update_audio_info(self, info):
        """更新音频信息显示"""
        if 'filename' in info:
            self.file_info_label.setText(f"文件: {info['filename']}")
        
        if 'duration' in info:
            self.duration_label.setText(f"时长: {info['duration']:.2f} 秒")
        
        if 'sample_rate' in info:
            self.sample_rate_label.setText(f"采样率: {info['sample_rate']} Hz")
        
        if 'channels' in info:
            self.channels_label.setText(f"通道: {info['channels']}")
    
    def plot_waveform(self, y, sr):
        """在画布上绘制波形图"""
        self.waveform_canvas.plot_waveform(y, sr)
    
    def clear_waveform(self):
        """清除波形图"""
        self.waveform_canvas.clear()
        
        # 重置音频信息
        self.file_info_label.setText("未选择文件")
        self.duration_label.setText("时长: -")
        self.sample_rate_label.setText("采样率: -")
        self.channels_label.setText("通道: -")
