"""
波形查看器控制器模块
"""
import os
import librosa
import numpy as np
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, 
    QLabel, QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from silentcut.gui.widgets import WaveformCanvas
from silentcut.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("gui.waveform_controller")


class AudioLoadWorker(QThread):
    """音频加载工作线程"""
    finished_signal = pyqtSignal(bool, object, str)
    progress_signal = pyqtSignal(int)
    
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.running = True
    
    def run(self):
        """执行音频加载"""
        try:
            # 发送进度信号
            self.progress_signal.emit(10)
            
            # 加载音频文件
            y, sr = librosa.load(self.file_path, sr=None)
            
            # 发送进度信号
            self.progress_signal.emit(90)
            
            # 发送完成信号
            self.finished_signal.emit(True, (y, sr), "加载成功")
            
        except Exception as e:
            logger.error(f"加载音频文件时出错: {e}")
            self.finished_signal.emit(False, None, f"加载失败: {e}")
    
    def stop(self):
        """停止线程"""
        self.running = False
        self.wait()


class WaveformController:
    """波形查看器控制器"""
    
    def __init__(self, tab_widget):
        """初始化波形查看器控制器"""
        self.tab = tab_widget
        self.worker = None
        self.audio_data = None
        self.sample_rate = None
        
        # 初始化UI
        self._init_ui()
        
        logger.info("波形查看器控制器初始化完成")
    
    def _init_ui(self):
        """初始化用户界面"""
        # 获取标签页布局
        layout = self.tab.layout()
        
        # 创建控制区域
        control_layout = QHBoxLayout()
        
        # 文件选择按钮
        self.browse_btn = QPushButton("选择音频文件")
        self.browse_btn.clicked.connect(self.browse_file)
        control_layout.addWidget(self.browse_btn)
        
        # 文件路径标签
        self.file_label = QLabel("未选择文件")
        control_layout.addWidget(self.file_label, 1)
        
        # 添加控制区域到主布局
        layout.addLayout(control_layout)
        
        # 创建波形显示区域
        self.waveform_canvas = WaveformCanvas()
        layout.addWidget(self.waveform_canvas, 1)
        
        # 创建进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # 创建信息标签
        self.info_label = QLabel("就绪")
        layout.addWidget(self.info_label)
    
    def browse_file(self):
        """浏览并选择音频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self.tab,
            "选择音频文件",
            "",
            "音频文件 (*.wav *.mp3 *.flac *.ogg *.m4a);;所有文件 (*.*)"
        )
        
        if file_path:
            self.load_audio(file_path)
    
    def load_audio(self, file_path):
        """加载音频文件"""
        # 更新UI状态
        self.file_label.setText(os.path.basename(file_path))
        self.info_label.setText("正在加载音频...")
        self.progress_bar.setValue(0)
        self.waveform_canvas.clear()
        
        # 禁用浏览按钮
        self.browse_btn.setEnabled(False)
        
        # 创建并启动工作线程
        self.worker = AudioLoadWorker(file_path)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.loading_finished)
        self.worker.start()
    
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
    
    def loading_finished(self, success, data, message):
        """音频加载完成回调"""
        # 恢复UI状态
        self.browse_btn.setEnabled(True)
        
        if success:
            # 保存音频数据
            self.audio_data, self.sample_rate = data
            
            # 显示波形
            self.waveform_canvas.plot_waveform(
                self.audio_data, 
                self.sample_rate,
                f"波形图 - {self.file_label.text()}"
            )
            
            # 更新信息
            duration = len(self.audio_data) / self.sample_rate
            self.info_label.setText(
                f"采样率: {self.sample_rate} Hz, 时长: {duration:.2f} 秒, "
                f"采样点数: {len(self.audio_data)}"
            )
            
            logger.info(f"音频加载成功: {self.file_label.text()}")
        else:
            # 显示错误信息
            self.info_label.setText(f"错误: {message}")
            QMessageBox.warning(self.tab, "加载失败", message)
            logger.error(f"音频加载失败: {message}")
        
        # 完成进度条
        self.progress_bar.setValue(100)
