"""
SilentCut GUI 主入口模块
"""
import sys
import multiprocessing
import platform
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QFont

# 导入 SilentCut 模块
from silentcut.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("gui")

# 导入视图和控制器
from silentcut.gui.views.main_window import MainWindow
from silentcut.gui.controllers.desilencer_controller import DesilencerController
from silentcut.gui.controllers.waveform_controller import WaveformController
from silentcut.utils.file_utils import is_ffmpeg_available


def main():
    """程序主入口"""
    # 支持多进程
    multiprocessing.freeze_support()
    
    # 在 macOS 上显式设置多进程启动模式为 'spawn'
    # 这避免了在 PyQt 应用中使用默认的 'fork' 模式可能导致的问题
    if platform.system() == 'Darwin':  # Darwin 是 macOS 的系统名
        try:
            multiprocessing.set_start_method('spawn', force=True)
        except RuntimeError:
            # 如果已经设置过启动模式，可能会抛出异常，忽略它
            pass
    
    # 创建应用程序
    app = QApplication(sys.argv)

    if not is_ffmpeg_available():
        QMessageBox.critical(None, "环境错误", "未检测到 ffmpeg。请安装后重试。macOS 可使用 'brew install ffmpeg'，Linux 使用发行版包管理器，Windows 安装官方构建并加入 PATH。")
        sys.exit(1)
    
    # 设置全局字体（可选）
    # 根据平台选择合适的字体
    if platform.system() == 'Windows':
        font = QFont("Microsoft YaHei UI", 9)
    elif platform.system() == 'Darwin':  # macOS
        font = QFont("PingFang SC", 12)
    else:  # Linux
        font = QFont("Noto Sans CJK SC", 10)
    
    app.setFont(font)
    
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
