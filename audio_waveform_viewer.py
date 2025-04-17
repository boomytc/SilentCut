import streamlit as st
import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np

st.title("音频波形图展示工具")

plt.rcParams['font.sans-serif'] = ['SimHei']  # 支持中文显示
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

uploaded_file = st.file_uploader("上传音频文件", type=["wav", "mp3", "ogg", "flac"])

if uploaded_file is not None:
    # 读取音频数据
    y, sr = librosa.load(uploaded_file, sr=None, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    # 绘制波形图
    fig, ax = plt.subplots(figsize=(10, 4))
    librosa.display.waveshow(y, sr=sr, ax=ax)
    ax.set_title("波形图")
    ax.set_xlabel("时间 (秒)")
    ax.set_ylabel("振幅")
    ax.set_xlim([0, duration])
    # 设置时间轴刻度
    num_ticks = 10
    ticks = np.linspace(0, duration, num=num_ticks)
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t:.2f}" for t in ticks])
    st.pyplot(fig)
    st.success(f"音频时长: {duration:.2f} 秒, 采样率: {sr} Hz")
else:
    st.info("请上传音频文件以查看波形图。")
