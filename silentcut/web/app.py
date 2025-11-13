"""
SilentCut Web 界面 - 基于 Streamlit 的 Web 应用
"""
import os
import streamlit as st
import tempfile
import librosa
import librosa.display
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import warnings
import time
import platform

from silentcut.audio.processor import AudioProcessor
from silentcut.utils.logger import get_logger
from silentcut.utils.file_utils import ensure_dir_exists, get_output_filename, is_ffmpeg_available

logger = get_logger("web")

warnings.filterwarnings("ignore", category=UserWarning, message="PySoundFile failed.*")
warnings.filterwarnings("ignore", category=FutureWarning, message="librosa.core.audio.__audioread_load.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*tight_layout.*")

if platform.system() == "Windows":
    plt.rcParams['font.sans-serif'] = [
        'Microsoft YaHei',
        'SimHei',
        'Arial Unicode MS'
    ]
elif platform.system() == "Darwin":
    plt.rcParams['font.sans-serif'] = [
        'PingFang SC',
        'Heiti SC',
        'Hiragino Sans GB',
        'STHeiti',
        'Arial Unicode MS',
        'SimHei'
    ]
else:
    plt.rcParams['font.sans-serif'] = [
        'WenQuanYi Zen Hei',
        'Noto Sans CJK SC',
        'DejaVu Sans',
        'SimHei'
    ]

plt.rcParams['axes.unicode_minus'] = False

st.set_page_config(
    page_title="SilentCut - 音频静音切割工具",
    page_icon="🔊",
    layout="wide",
)

if not is_ffmpeg_available():
    st.error("未检测到 ffmpeg。请安装后重试。macOS 可使用 'brew install ffmpeg'，Linux 使用发行版包管理器，Windows 安装官方构建并加入 PATH。")
    st.stop()

st.title("🔊 SilentCut - 音频静音切割工具")
st.markdown("上传音频文件，自动检测并移除静音片段，并可视化比对处理前后的结果。")

from silentcut.utils.file_utils import create_temp_directory, get_project_tmp_dir
temp_dir = create_temp_directory(prefix="web_")

with st.sidebar:
    st.header("参数设置")
    
    st.subheader("VAD 语音检测参数")
    
    vad_threshold = st.slider(
        "VAD 阈值", 
        min_value=0.0, 
        max_value=1.0, 
        value=0.5, 
        step=0.05,
        help="语音活动检测的阈值，值越高检测越严格"
    )
    
    vad_max_duration_ms = st.slider(
        "VAD 最大段时长 (ms)", 
        min_value=1000, 
        max_value=30000, 
        value=5000, 
        step=500,
        help="单个语音段的最大时长"
    )
    
    vad_min_silence_ms = st.slider(
        "VAD 最小静音 (ms)", 
        min_value=0, 
        max_value=5000, 
        value=1000, 
        step=100,
        help="语音段之间的最小静音时长"
    )
    
    st.markdown("---")
    st.subheader("关于")
    st.markdown("""
    **SilentCut** 是一个基于 VAD 的语音检测工具，专注于自动检测并提取音频中的语音段。
    适用于播客剪辑、语音预处理、数据清洗等场景。
    """)

uploaded_file = st.file_uploader("上传音频文件", type=["wav", "mp3", "flac", "ogg", "m4a"], help="支持常见音频格式")


def process_audio(input_file_path, output_dir, vad_threshold=0.5, vad_min_silence_ms=1000, vad_max_duration_ms=5000):
    """使用 VAD 处理音频文件"""
    try:
        ensure_dir_exists(output_dir)
        output_path = get_output_filename(input_file_path, suffix="-desilenced", output_dir=output_dir)
        
        processor = AudioProcessor(input_file_path)
        success, message = processor.process_audio(
            output_folder=output_dir,
            vad_threshold=vad_threshold,
            vad_min_silence_ms=vad_min_silence_ms,
            vad_max_duration_ms=vad_max_duration_ms
        )
        
        if success:
            return True, message, output_path
        else:
            return False, message, None
                
    except Exception as e:
        logger.error(f"处理文件 {input_file_path} 时发生错误: {e}")
        return False, f"处理错误: {e}", None


def safe_load_audio(file_path):
    """安全加载音频文件，处理可能的异常"""
    try:
        y, sr = librosa.load(file_path, sr=None)
        return y, sr, None
    except Exception as e:
        error_message = f"加载音频文件时出错: {e}"
        logger.error(error_message)
        return None, None, error_message


def visualize_audio(original_path, processed_path):
    """创建原始和处理后音频的波形图和频谱图比较"""
    y_orig, sr_orig, error_orig = safe_load_audio(original_path)
    y_proc, sr_proc, error_proc = safe_load_audio(processed_path)
    
    if error_orig or error_proc:
        st.error(f"可视化时出错: {error_orig or error_proc}")
        return None
    
    fig, axs = plt.subplots(2, 2, figsize=(12, 8))
    fig.tight_layout(pad=3.0)
    
    axs[0, 0].set_title("原始音频波形图")
    librosa.display.waveshow(y=y_orig, sr=sr_orig, ax=axs[0, 0])
    axs[0, 0].set_xlabel("时间 (秒)")
    axs[0, 0].set_ylabel("振幅")
    
    axs[0, 1].set_title("处理后音频波形图")
    librosa.display.waveshow(y=y_proc, sr=sr_proc, ax=axs[0, 1])
    axs[0, 1].set_xlabel("时间 (秒)")
    axs[0, 1].set_ylabel("振幅")
    
    D_orig = librosa.amplitude_to_db(np.abs(librosa.stft(y_orig)), ref=np.max)
    img_orig = librosa.display.specshow(D_orig, y_axis='log', x_axis='time', sr=sr_orig, ax=axs[1, 0])
    axs[1, 0].set_title("原始音频频谱图")
    fig.colorbar(img_orig, ax=axs[1, 0], format="%+2.0f dB")
    
    D_proc = librosa.amplitude_to_db(np.abs(librosa.stft(y_proc)), ref=np.max)
    img_proc = librosa.display.specshow(D_proc, y_axis='log', x_axis='time', sr=sr_proc, ax=axs[1, 1])
    axs[1, 1].set_title("处理后音频频谱图")
    fig.colorbar(img_proc, ax=axs[1, 1], format="%+2.0f dB")
    
    return fig


def show_audio_info(original_path, processed_path):
    """显示原始和处理后音频的比较信息"""
    original_size = os.path.getsize(original_path)
    processed_size = os.path.getsize(processed_path)
    
    y_orig, sr_orig, _ = safe_load_audio(original_path)
    y_proc, sr_proc, _ = safe_load_audio(processed_path)
    
    if y_orig is not None and y_proc is not None:
        original_duration = len(y_orig) / sr_orig
        processed_duration = len(y_proc) / sr_proc
        
        size_reduction = (original_size - processed_size) / original_size * 100
        duration_reduction = (original_duration - processed_duration) / original_duration * 100
        
        comparison_data = {
            "指标": ["文件大小", "音频时长"],
            "原始": [f"{original_size/1024/1024:.2f} MB", f"{original_duration:.2f} 秒"],
            "处理后": [f"{processed_size/1024/1024:.2f} MB", f"{processed_duration:.2f} 秒"],
            "减少比例": [f"{size_reduction:.2f}%", f"{duration_reduction:.2f}%"]
        }
        
        return comparison_data
    
    return None


if uploaded_file is not None:
    input_file_path = os.path.join(temp_dir, uploaded_file.name)
    with open(input_file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    file_size_mb = os.path.getsize(input_file_path) / (1024 * 1024)
    st.info(f"已上传: {uploaded_file.name} ({file_size_mb:.2f} MB)")
    
    if st.button("开始处理"):
        with st.spinner("正在处理音频..."):
            start_time = time.time()
            
            try:
                success, message, processed_file_path = process_audio(
                    input_file_path, 
                    temp_dir, 
                    vad_threshold=vad_threshold,
                    vad_min_silence_ms=vad_min_silence_ms,
                    vad_max_duration_ms=vad_max_duration_ms,
                )
                
                processing_time = time.time() - start_time
                
                if success:
                    st.success(f"处理完成！耗时: {processing_time:.2f}秒")
                    
                    st.subheader("音频信息比对")
                    comparison_data = show_audio_info(input_file_path, processed_file_path)
                    st.table(comparison_data)
                    
                    st.subheader("波形图和频谱图比对")
                    fig = visualize_audio(input_file_path, processed_file_path)
                    st.pyplot(fig)
                    
                    with open(processed_file_path, "rb") as file:
                        now = datetime.now().strftime("%Y%m%d_%H%M%S")
                        download_filename = f"{os.path.splitext(uploaded_file.name)[0]}_processed_{now}.wav"
                        st.download_button(
                            label="下载处理后的音频",
                            data=file,
                            file_name=download_filename,
                            mime="audio/wav"
                        )
                    
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
    st.info("请上传一个音频文件进行处理")

st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>SilentCut &copy; 2025 | 智能音频静音切割工具</p>
</div>
""", unsafe_allow_html=True)
