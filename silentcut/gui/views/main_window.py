"""
SilentCut 主窗口视图模块
"""
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, 
    QStatusBar, QLabel, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QAction
import os
import platform

from silentcut.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("gui.views")


class MainWindow(QMainWindow):
    """SilentCut 主窗口"""
    
    def __init__(self):
        """初始化主窗口"""
        super().__init__()
        
        # 设置窗口基本属性
        self.setWindowTitle("SilentCut - 音频静音切割工具")
        self.setMinimumSize(800, 600)
        
        # 尝试设置图标（如果存在）
        icon_path = self._get_icon_path()
        if icon_path and os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 创建状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusLabel = QLabel("就绪")
        self.statusBar.addWidget(self.statusLabel)
        
        # 创建标签页控件
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # 创建主要功能标签页
        self.desilencer_tab = QWidget()
        self.waveform_tab = QWidget()
        
        # 添加标签页
        self.tabs.addTab(self.desilencer_tab, "静音切割")
        self.tabs.addTab(self.waveform_tab, "波形查看器")
        
        # 初始化标签页布局
        self._init_tab_layouts()
        
        # 创建菜单栏
        self._create_menus()
        
        # 控制器引用，将在 initialize_controllers 中设置
        self.desilencer_controller = None
        self.waveform_controller = None
        
        logger.info("主窗口初始化完成")
    
    def _init_tab_layouts(self):
        """初始化标签页布局"""
        # 静音切割标签页
        desilencer_layout = QVBoxLayout()
        self.desilencer_tab.setLayout(desilencer_layout)
        
        # 波形查看器标签页
        waveform_layout = QVBoxLayout()
        self.waveform_tab.setLayout(waveform_layout)
    
    def _create_menus(self):
        """创建菜单栏"""
        # 文件菜单
        file_menu = self.menuBar().addMenu("文件")
        
        # 退出动作
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 工具菜单
        tools_menu = self.menuBar().addMenu("工具")
        
        # 清理临时文件动作
        cleanup_action = QAction("清理临时文件", self)
        cleanup_action.triggered.connect(self._cleanup_temp_files)
        tools_menu.addAction(cleanup_action)
        
        # 帮助菜单
        help_menu = self.menuBar().addMenu("帮助")
        
        # 关于动作
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _get_icon_path(self):
        """获取应用图标路径"""
        # 尝试在不同位置查找图标
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "resources", "icon.png"),
            os.path.join(os.path.dirname(__file__), "..", "..", "resources", "icon.png"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return os.path.abspath(path)
        
        return None
    
    def _cleanup_temp_files(self):
        """清理临时文件"""
        from silentcut.utils.cleanup import cleanup_temp_files
        
        # 在状态栏显示正在清理
        self.statusLabel.setText("正在清理临时文件...")
        QApplication.processEvents()
        
        # 清理临时文件
        count = cleanup_temp_files()
        
        # 更新状态栏
        self.statusLabel.setText(f"已清理 {count} 个临时文件")
    
    def _show_about(self):
        """显示关于对话框"""
        from PyQt6.QtWidgets import QMessageBox
        
        QMessageBox.about(
            self,
            "关于 SilentCut",
            f"<h3>SilentCut - 音频静音切割工具</h3>"
            f"<p>版本: 0.1.0</p>"
            f"<p>一个高效的音频处理工具，专注于自动检测并去除音频中的静音段。</p>"
            f"<p>适用于播客剪辑、语音预处理、数据清洗等场景。</p>"
            f"<p>运行环境: Python {platform.python_version()} - {platform.system()} {platform.release()}</p>"
        )
    
    def initialize_controllers(self, desilencer_controller, waveform_controller):
        """初始化控制器"""
        self.desilencer_controller = desilencer_controller
        self.waveform_controller = waveform_controller
        
        logger.info("控制器初始化完成")
    
    def show_status_message(self, message):
        """在状态栏显示消息"""
        self.statusLabel.setText(message)
