"""
临时文件清理工具
用于清理SilentCut生成的临时文件
"""
import os
import glob
import sys

def cleanup_temp_files(directory=None):
    """
    清理指定目录中所有的临时音频文件
    
    Args:
        directory: 要清理的目录路径，默认为None(当前目录)
    
    Returns:
        清理的文件数量
    """
    if directory is None:
        directory = os.getcwd()
    
    if not os.path.isdir(directory):
        print(f"错误: {directory} 不是一个有效的目录")
        return 0
        
    count = 0
    # 查找所有包含'_thresh_'和'.temp.wav'的临时文件
    patterns = [
        '*_thresh_*.temp.wav',  # 新的UUID格式临时文件
        '*_thresh_*.temp.*',    # 其他可能的临时文件格式
    ]
    
    for pattern in patterns:
        for temp_file in glob.glob(os.path.join(directory, pattern)):
            try:
                os.remove(temp_file)
                count += 1
                print(f"已删除: {os.path.basename(temp_file)}")
            except Exception as e:
                print(f"删除 {temp_file} 时出错: {e}")
    
    return count

if __name__ == "__main__":
    # 可以从命令行运行
    directory = sys.argv[1] if len(sys.argv) > 1 else None
    
    if directory:
        print(f"正在清理目录: {directory}")
    else:
        print(f"正在清理当前目录: {os.getcwd()}")
        
    count = cleanup_temp_files(directory)
    print(f"共清理了 {count} 个临时文件")
