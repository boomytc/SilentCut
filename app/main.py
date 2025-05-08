"""
SilentCut 应用程序入口
"""
import sys
import os
import multiprocessing
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

# 添加项目根目录到路径中，解决导入问题
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# 现在可以正常导入app模块
from app.views.main_window import MainWindow
from app.controllers.desilencer_controller import DesilencerController
from app.controllers.waveform_controller import WaveformController


def main():
    """程序主入口"""
    # 支持多进程（在Windows系统上需要）
    multiprocessing.freeze_support()
    
    # 创建应用程序
    app = QApplication(sys.argv)
    
    # 设置全局字体（可选）
    # font = QFont("Microsoft YaHei UI", 9)  # 使用微软雅黑UI字体
    # app.setFont(font)
    
    # 创建主窗口
    window = MainWindow()
    
    # 创建控制器
    desilencer_controller = DesilencerController(window.desilencer_tab)
    waveform_controller = WaveformController(window.waveform_tab)
    
    # 初始化控制器
    window.initialize_controllers(desilencer_controller, waveform_controller)
    
    # 显示窗口
    window.show()
    
    # 启动应用程序事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
