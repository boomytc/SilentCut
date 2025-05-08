"""
波形查看控制器 - 处理波形显示视图和模型之间的交互
"""
import os
import numpy as np
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtCore import QObject

# 导入librosa用于音频处理
try:
    import librosa
except ImportError:
    print("错误：librosa包未安装，波形图功能将不可用")
    print("请安装librosa：pip install librosa")


class WaveformController(QObject):
    """波形查看控制器类"""
    
    def __init__(self, view):
        """初始化控制器"""
        super().__init__()
        self.view = view
        self.current_audio = None
        self.current_sample_rate = None
        
        # 连接视图信号
        self.connect_signals()
    
    def connect_signals(self):
        """连接视图信号"""
        self.view.browse_audio_signal.connect(self.browse_audio)
    
    def browse_audio(self):
        """浏览并选择音频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self.view,
            "选择音频文件",
            "",
            "音频文件 (*.wav *.mp3 *.ogg *.flac *.aac *.m4a)"
        )
        
        if file_path:
            self.load_audio(file_path)
    
    def load_audio(self, file_path):
        """加载音频文件并显示波形"""
        try:
            # 清除当前波形
            self.view.clear_waveform()
            
            # 提取文件名
            filename = os.path.basename(file_path)
            
            # 加载音频
            y, sr = librosa.load(file_path, sr=None, mono=True)
            self.current_audio = y
            self.current_sample_rate = sr
            
            # 计算音频时长
            duration = librosa.get_duration(y=y, sr=sr)
            
            # 获取通道数（单声道/立体声）
            channels = 1  # librosa总是返回单声道（mono=True）
            
            # 更新音频信息
            self.view.update_audio_info({
                'filename': filename,
                'duration': duration,
                'sample_rate': sr,
                'channels': channels
            })
            
            # 绘制波形
            self.view.plot_waveform(y, sr)
            
        except Exception as e:
            error_msg = f"加载音频文件时出错: {e}"
            print(error_msg)
            self.view.clear_waveform()
            self.view.update_audio_info({
                'filename': f"错误: {os.path.basename(file_path)}",
                'duration': 0,
                'sample_rate': 0,
                'channels': 0
            })
