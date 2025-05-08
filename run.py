#!/usr/bin/env python
"""
SilentCut 应用程序启动脚本
"""
import sys
import os

# 确保正确导入app模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入主函数
from app.main import main

if __name__ == "__main__":
    main()
