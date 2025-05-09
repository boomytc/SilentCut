#!/usr/bin/env python
"""
SilentCut 命令行工具启动脚本
"""
import os
import sys

# 确保当前目录在 Python 路径中，以便正确导入 silentcut 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入命令行主函数
from silentcut.cli.__main__ import main

if __name__ == "__main__":
    main()
