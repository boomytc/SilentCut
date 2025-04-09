import streamlit as st
import os
import sys
import tempfile
import librosa
import librosa.display
import numpy as np
import matplotlib.pyplot as plt
import soundfile as sf
from datetime import datetime
import warnings

# 忽略指定的警告
warnings.filterwarnings("ignore", category=UserWarning, message="PySoundFile failed.*")
warnings.filterwarnings("ignore", category=FutureWarning, message="librosa.core.audio.__audioread_load.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*tight_layout.*")

plt.rcParams['font.sans-serif'] = ['SimHei']  # 支持中文显示
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# 添加当前目录到Python路径
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# 导入音频处理器
try:
    from audio_processor import AudioProcessor
except ImportError as e:
    st.error(f"错误：无法导入AudioProcessor: {e}")
    st.error(f"请确保audio_processor.py在当前目录下。")
    AudioProcessor = None

# 设置页面
st.set_page_config(
    page_title="SilentCut - 音频静音切割工具",
    page_icon="🔊",
    layout="wide",
)

# 页面标题
st.title("🔊 SilentCut - 音频静音切割工具")
st.markdown("上传音频文件，自动检测并移除静音片段，并可视化比对处理前后的结果。")

# 创建临时目录用于存放处理后的文件
temp_dir = tempfile.mkdtemp()

# 侧边栏 - 参数设置
with st.sidebar:
    st.header("参数设置")
    
    min_silence_len = st.slider(
        "最小静音长度 (ms)",
        min_value=100,
        max_value=5000,
        value=500,
        step=100,
        help="小于此长度的静音片段将被保留"
    )
    
    st.markdown("---")
    st.subheader("关于")
    st.markdown("""
    **SilentCut** 是一个高效的音频处理工具，专注于自动检测并去除音频中的静音段。
    """)

# 音频上传区域
uploaded_file = st.file_uploader("上传音频文件", type=["wav"], help="目前仅支持WAV格式")

# 处理函数
def process_audio(input_file_path, output_dir, min_silence_len):
    processor = AudioProcessor(input_file_path)
    success, message = processor.process_audio(min_silence_len=min_silence_len, output_folder=output_dir)
    return success, message

# 安全音频加载函数
def safe_load_audio(file_path):
    try:
        # 优先使用soundfile库直接读取
        data, samplerate = sf.read(file_path)
        # 如果是立体声，转换为单声道
        if len(data.shape) > 1:
            data = np.mean(data, axis=1)
        return data, samplerate
    except Exception:
        # 如果soundfile失败，回退到librosa
        return librosa.load(file_path, sr=None)

# 可视化函数
def visualize_audio(original_path, processed_path):
    # 读取原始音频和处理后的音频，使用安全加载函数
    y_orig, sr_orig = safe_load_audio(original_path)
    y_proc, sr_proc = safe_load_audio(processed_path)
    
    # 创建子图，稍微调整了大小和布局比例
    fig = plt.figure(figsize=(14, 10))
    
    # 使用GridSpec创建更灵活的布局
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1], hspace=0.3, wspace=0.3)
    
    # 绘制原始音频波形图
    ax1 = fig.add_subplot(gs[0, 0])
    librosa.display.waveshow(y=y_orig, sr=sr_orig, ax=ax1)
    ax1.set_title("原始音频波形")
    ax1.set_xlabel("时间 (秒)")
    ax1.set_ylabel("振幅")
    
    # 绘制处理后音频波形图
    ax2 = fig.add_subplot(gs[0, 1])
    librosa.display.waveshow(y=y_proc, sr=sr_proc, ax=ax2)
    ax2.set_title("处理后音频波形")
    ax2.set_xlabel("时间 (秒)")
    ax2.set_ylabel("振幅")
    
    # 计算频谱图 - 原始音频
    ax3 = fig.add_subplot(gs[1, 0])
    D_orig = librosa.amplitude_to_db(np.abs(librosa.stft(y_orig)), ref=np.max)
    librosa.display.specshow(D_orig, sr=sr_orig, x_axis='time', y_axis='log', ax=ax3)
    ax3.set_title('原始音频频谱图')
    ax3.set_xlabel("时间 (秒)")
    ax3.set_ylabel("频率 (Hz)")
    
    # 计算频谱图 - 处理后音频
    ax4 = fig.add_subplot(gs[1, 1])
    D_proc = librosa.amplitude_to_db(np.abs(librosa.stft(y_proc)), ref=np.max)
    img = librosa.display.specshow(D_proc, sr=sr_proc, x_axis='time', y_axis='log', ax=ax4)
    ax4.set_title('处理后音频频谱图')
    ax4.set_xlabel("时间 (秒)")
    ax4.set_ylabel("频率 (Hz)")
    
    # 添加颜色条
    cbar = fig.colorbar(img, ax=[ax3, ax4], format='%+2.0f dB')
    
    # 代替tight_layout，手动调整
    fig.subplots_adjust(top=0.95, bottom=0.1, left=0.1, right=0.9, hspace=0.4, wspace=0.3)
    
    return fig

# 显示音频时长和大小信息
def show_audio_info(original_path, processed_path):
    # 获取原始文件信息
    orig_size = os.path.getsize(original_path)
    y_orig, sr_orig = safe_load_audio(original_path)
    orig_duration = len(y_orig) / sr_orig  # 手动计算时长，避免使用deprecated的函数
    
    # 获取处理后文件信息
    proc_size = os.path.getsize(processed_path)
    y_proc, sr_proc = safe_load_audio(processed_path)
    proc_duration = len(y_proc) / sr_proc  # 手动计算时长
    
    # 计算减少百分比
    size_reduction = ((orig_size - proc_size) / orig_size) * 100
    duration_reduction = ((orig_duration - proc_duration) / orig_duration) * 100
    
    # 创建比较表格
    comparison_data = {
        "特性": ["文件大小", "时长", "采样率"],
        "原始音频": [f"{orig_size/1024:.2f} KB", f"{orig_duration:.2f} 秒", f"{sr_orig} Hz"],
        "处理后音频": [f"{proc_size/1024:.2f} KB", f"{proc_duration:.2f} 秒", f"{sr_proc} Hz"],
        "减少": [f"{size_reduction:.2f}%", f"{duration_reduction:.2f}%", ""]
    }
    
    return comparison_data

# 主处理逻辑
if uploaded_file is not None:
    # 保存上传的文件到临时位置
    input_file_path = os.path.join(temp_dir, uploaded_file.name)
    with open(input_file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    st.success(f"文件上传成功: {uploaded_file.name}")
    
    # 处理按钮
    if st.button("开始处理"):
        with st.spinner("正在处理音频..."):
            # 尝试处理音频
            try:
                success, message = process_audio(input_file_path, temp_dir, min_silence_len)
                
                if success:
                    st.success("处理完成！")
                    
                    # 获取处理后的文件路径
                    file_name_without_ext = os.path.splitext(uploaded_file.name)[0]
                    processed_file_path = os.path.join(temp_dir, f"{file_name_without_ext}-desilenced.wav")
                    
                    # 显示对比信息
                    st.subheader("音频信息比对")
                    comparison_data = show_audio_info(input_file_path, processed_file_path)
                    st.table(comparison_data)
                    
                    # 显示波形图和频谱图
                    st.subheader("波形图和频谱图比对")
                    fig = visualize_audio(input_file_path, processed_file_path)
                    st.pyplot(fig)
                    
                    # 提供下载链接
                    with open(processed_file_path, "rb") as file:
                        now = datetime.now().strftime("%Y%m%d_%H%M%S")
                        download_filename = f"{file_name_without_ext}_processed_{now}.wav"
                        st.download_button(
                            label="下载处理后的音频",
                            data=file,
                            file_name=download_filename,
                            mime="audio/wav"
                        )
                    
                    # 音频播放器
                    st.subheader("音频播放")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("原始音频:")
                        st.audio(input_file_path)
                    
                    with col2:
                        st.write("处理后音频:")
                        st.audio(processed_file_path)
                else:
                    st.error(f"处理失败: {message}")
            except Exception as e:
                st.error(f"处理过程中出错: {str(e)}")
else:
    st.info("请上传一个WAV格式的音频文件进行处理")

# 页脚
st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>SilentCut © 2025 | 智能音频静音切割工具</p>
</div>
""", unsafe_allow_html=True)