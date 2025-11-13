import os
import sys
import subprocess

def main():
    app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    print("正在启动 SilentCut Web 界面...")
    print(f"Web 应用路径: {app_path}")
    print("使用 Ctrl+C 停止服务器")
    try:
        subprocess.run(["streamlit", "run", app_path], check=True)
    except KeyboardInterrupt:
        print("\n已停止 SilentCut Web 服务")
    except Exception as e:
        print(f"启动 Web 界面时出错: {e}")
        print("请确保已安装 streamlit，可以使用 'pip install streamlit' 安装")
        sys.exit(1)

if __name__ == "__main__":
    main()