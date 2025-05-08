"""
主窗口视图 - 负责创建主界面和标签页组织
"""
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt

from app.views.desilencer_tab import DesilencerTabView
from app.views.waveform_tab import WaveformTabView


class MainWindow(QMainWindow):
    """主窗口，包含所有标签页"""
    
    def __init__(self):
        """初始化主窗口"""
        super().__init__()
        
        # 设置窗口属性
        self.setWindowTitle("SilentCut - 音频静音处理工具")
        self.setMinimumSize(800, 800)
        
        # 创建中央部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 创建垂直布局
        self.layout = QVBoxLayout(self.central_widget)
        
        # 创建标签页控件
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        
        # 创建标签页
        self.desilencer_tab = DesilencerTabView()
        self.waveform_tab = WaveformTabView()
        
        # 添加标签页
        self.tabs.addTab(self.desilencer_tab, "静音删除")
        self.tabs.addTab(self.waveform_tab, "波形查看")
        
        # 将标签页添加到布局
        self.layout.addWidget(self.tabs)
    
    def initialize_controllers(self, desilencer_controller, waveform_controller):
        """
        初始化控制器（依赖注入）
        
        Args:
            desilencer_controller: 静音删除控制器
            waveform_controller: 波形查看控制器
        """
        # 设置控制器引用
        self.desilencer_tab.controller = desilencer_controller
        self.waveform_tab.controller = waveform_controller
