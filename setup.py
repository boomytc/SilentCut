#!/usr/bin/env python3
"""
SilentCut 安装配置脚本
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="silentcut",
    version="0.1.0",
    author="SilentCut Team",
    author_email="example@example.com",
    description="一个高效的音频静音切割工具",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/silentcut",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=[
        "pydub>=0.25.1",
        "librosa>=0.9.0",
        "numpy>=1.20.0",
        "matplotlib>=3.4.0",
        "PyQt6>=6.2.0",
        "streamlit>=1.10.0",
        "soundfile>=0.10.3",
    ],
    entry_points={
        "console_scripts": [
            "silentcut=silentcut.cli.__main__:main",
            "silentcut-gui=silentcut.gui.main:main",
            "silentcut-web=silentcut.web.app:main",
        ],
    },
    include_package_data=True,
)
