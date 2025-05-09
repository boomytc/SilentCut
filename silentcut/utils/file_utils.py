"""
文件处理工具模块 - 提供文件操作相关的通用函数
"""
import os
import tempfile
import shutil
from datetime import datetime


def ensure_dir_exists(directory):
    """
    确保目录存在，如果不存在则创建
    
    Args:
        directory: 目录路径
        
    Returns:
        创建的目录路径
    """
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    return directory


def get_output_filename(input_file, suffix="-desilenced", output_dir=None):
    """
    根据输入文件生成输出文件名
    
    Args:
        input_file: 输入文件路径
        suffix: 添加到文件名的后缀
        output_dir: 输出目录，如果为None则使用输入文件所在目录
        
    Returns:
        输出文件的完整路径
    """
    input_dir, input_filename = os.path.split(input_file)
    name, ext = os.path.splitext(input_filename)
    output_filename = f"{name}{suffix}{ext}"
    
    if output_dir and os.path.isdir(output_dir):
        output_path = os.path.join(output_dir, output_filename)
    else:
        output_path = os.path.join(input_dir, output_filename)
        
    return output_path


def create_temp_directory(prefix="silentcut_"):
    """
    创建临时目录
    
    Args:
        prefix: 临时目录名称前缀
        
    Returns:
        临时目录路径
    """
    return tempfile.mkdtemp(prefix=prefix)


def clean_temp_files(file_list):
    """
    清理临时文件
    
    Args:
        file_list: 要清理的文件路径列表
    """
    for file_path in file_list:
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"无法删除临时文件 {file_path}: {e}")


def get_audio_files_in_directory(directory, extensions=(".wav", ".mp3", ".flac", ".ogg", ".m4a")):
    """
    获取目录中的所有音频文件
    
    Args:
        directory: 目录路径
        extensions: 音频文件扩展名元组
        
    Returns:
        音频文件路径列表
    """
    audio_files = []
    
    if not os.path.isdir(directory):
        return audio_files
        
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(extensions):
                audio_files.append(os.path.join(root, file))
                
    return audio_files


def get_file_size_info(file_path):
    """
    获取文件大小信息
    
    Args:
        file_path: 文件路径
        
    Returns:
        (size_bytes, size_kb, size_mb): 文件大小（字节、KB、MB）
    """
    if not os.path.exists(file_path):
        return 0, 0, 0
        
    size_bytes = os.path.getsize(file_path)
    size_kb = size_bytes / 1024
    size_mb = size_kb / 1024
    
    return size_bytes, size_kb, size_mb
