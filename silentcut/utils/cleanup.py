import os
import sys
import tempfile
import shutil
from .logger import get_logger
from .file_utils import get_project_tmp_dir

logger = get_logger("cleanup")

def _is_temp_filename(name):
    temp_suffixes = (".tmp", ".temp", ".partial", ".cache", ".swp")
    if name.endswith(temp_suffixes):
        return True
    audio_exts = (".wav", ".mp3", ".flac", ".ogg", ".m4a")
    for ext in audio_exts:
        if name.endswith(ext + ".tmp") or name.endswith(ext + ".temp"):
            return True
        if name.endswith(".tmp" + ext) or name.endswith(".temp" + ext):
            return True
    return False

def _remove_file(path):
    try:
        os.remove(path)
        return 1
    except Exception as e:
        logger.error(f"删除 {path} 时出错: {e}")
        return 0

def _remove_silentcut_temp_dirs():
    root = tempfile.gettempdir()
    removed = 0
    try:
        for name in os.listdir(root):
            if name.startswith("silentcut_"):
                dir_path = os.path.join(root, name)
                if os.path.isdir(dir_path):
                    # 统计目录内文件数
                    file_count = 0
                    for _r, _d, _f in os.walk(dir_path):
                        file_count += len(_f)
                    shutil.rmtree(dir_path, ignore_errors=True)
                    removed += file_count
                    logger.info(f"已删除临时目录: {dir_path}")
    except Exception as e:
        logger.error(f"删除系统临时目录时出错: {e}")
    return removed

def _remove_workspace_temp_dirs():
    base = get_project_tmp_dir()
    removed = 0
    try:
        for name in os.listdir(base):
            dir_path = os.path.join(base, name)
            if os.path.isdir(dir_path):
                file_count = 0
                for _r, _d, _f in os.walk(dir_path):
                    file_count += len(_f)
                shutil.rmtree(dir_path, ignore_errors=True)
                removed += file_count
                logger.info(f"已删除临时目录: {dir_path}")
            else:
                try:
                    os.remove(dir_path)
                    removed += 1
                    logger.info(f"已删除临时文件: {dir_path}")
                except Exception as e:
                    logger.error(f"删除文件 {dir_path} 时出错: {e}")
    except Exception as e:
        logger.error(f"删除工作区临时目录时出错: {e}")
    return removed

def cleanup_workspace_temp():
    return _remove_workspace_temp_dirs()

def cleanup_temp_files(directory=None):
    if directory is None:
        directory = os.getcwd()
    if not os.path.isdir(directory):
        logger.error(f"错误: {directory} 不是一个有效的目录")
        return 0

    removed = 0
    for root, _, files in os.walk(directory):
        for fname in files:
            if _is_temp_filename(fname):
                fpath = os.path.join(root, fname)
                removed += _remove_file(fpath)
                logger.info(f"已删除: {os.path.relpath(fpath, directory)}")

    removed += _remove_workspace_temp_dirs()
    removed += _remove_silentcut_temp_dirs()
    return removed

def main():
    directory = sys.argv[1] if len(sys.argv) > 1 else None
    if directory:
        print(f"正在清理目录: {directory}")
    else:
        print(f"正在清理当前目录: {os.getcwd()}")
    count = cleanup_temp_files(directory)
    print(f"共清理了 {count} 个临时文件")

if __name__ == "__main__":
    main()
