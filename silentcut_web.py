#!/usr/bin/env python3
"""
SilentCut Web 应用程序启动脚本
"""
import os
import sys
import subprocess

# 确保当前目录在 Python 路径中，以便正确导入 silentcut 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """启动 Streamlit Web 界面"""
    web_app_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "silentcut", "web", "app.py"
    )
    
    print(f"正在启动 SilentCut Web 界面...")
    print(f"Web 应用路径: {web_app_path}")
    print("使用 Ctrl+C 停止服务器")
    
    # 使用 subprocess 启动 streamlit
    try:
        subprocess.run(["streamlit", "run", web_app_path], check=True)
    except KeyboardInterrupt:
        print("\n已停止 SilentCut Web 服务")
    except Exception as e:
        print(f"启动 Web 界面时出错: {e}")
        print("请确保已安装 streamlit，可以使用 'pip install streamlit' 安装")
        sys.exit(1)

if __name__ == "__main__":
    main()
