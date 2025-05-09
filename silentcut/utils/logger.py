"""
统一日志模块 - 为整个项目提供一致的日志记录
"""
import logging
import os
import sys
import platform
from datetime import datetime


def setup_logger(name="silentcut", level=logging.INFO, log_file=None):
    """
    配置并返回一个日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别
        log_file: 日志文件路径，如果为None则只输出到控制台
        
    Returns:
        配置好的logger对象
    """
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 如果已经有处理器，不重复添加
    if logger.handlers:
        return logger
    
    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 如果指定了日志文件，创建文件处理器
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_default_log_file():
    """
    根据操作系统获取默认日志文件路径
    
    Returns:
        默认日志文件路径
    """
    os_name = platform.system()
    timestamp = datetime.now().strftime("%Y%m%d")
    
    if os_name == "Windows":
        log_dir = os.path.join(os.environ.get("APPDATA", ""), "SilentCut", "logs")
    elif os_name == "Darwin":  # macOS
        log_dir = os.path.join(os.path.expanduser("~"), "Library", "Logs", "SilentCut")
    else:  # Linux
        log_dir = os.path.join(os.path.expanduser("~"), ".silentcut", "logs")
    
    return os.path.join(log_dir, f"silentcut_{timestamp}.log")


# 创建默认日志记录器
default_logger = setup_logger(name="silentcut")


def get_logger(name=None):
    """
    获取指定名称的日志记录器，如果不存在则创建
    
    Args:
        name: 日志记录器名称，如果为None则使用默认日志记录器
        
    Returns:
        日志记录器对象
    """
    if name is None:
        return default_logger
    
    return logging.getLogger(f"silentcut.{name}")
