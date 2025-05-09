"""
SilentCut Web 界面 - 基于 Streamlit 的 Web 应用
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import streamlit as st
import tempfile
import librosa
import librosa.display
import numpy as np
import matplotlib.pyplot as plt
import soundfile as sf
from datetime import datetime
import warnings
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
import time
from pydub import AudioSegment
import platform  # 新增，用于根据系统设置中文字体

# 导入 SilentCut 核心模块
from silentcut.audio.processor import AudioProcessor
from silentcut.utils.logger import get_logger
from silentcut.utils.file_utils import ensure_dir_exists, clean_temp_files

# 获取日志记录器
logger = get_logger("web")

# 忽略指定的警告
warnings.filterwarnings("ignore", category=UserWarning, message="PySoundFile failed.*")
warnings.filterwarnings("ignore", category=FutureWarning, message="librosa.core.audio.__audioread_load.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*tight_layout.*")

# 设置 matplotlib 字体（根据操作系统自动选择可用中文字体）
if platform.system() == "Windows":
    plt.rcParams['font.sans-serif'] = [
        'Microsoft YaHei',  # 常见 Windows 中文字体
        'SimHei',
        'Arial Unicode MS'
    ]
elif platform.system() == "Darwin":  # macOS
    plt.rcParams['font.sans-serif'] = [
        'PingFang SC',
        'Heiti SC',
        'Hiragino Sans GB',
        'STHeiti',
        'Arial Unicode MS',
        'SimHei'
    ]
else:  # Linux 通用
    plt.rcParams['font.sans-serif'] = [
        'WenQuanYi Zen Hei',
        'Noto Sans CJK SC',
        'DejaVu Sans',
        'SimHei'
    ]

# 解决负号显示问题
plt.rcParams['axes.unicode_minus'] = False

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
        value=1000,
        step=100,
        help="小于此长度的静音片段将被保留"
    )
    
    # 添加多进程设置
    enable_multiprocessing = st.checkbox(
        "启用多进程处理", 
        value=True,
        help="使用多进程加速音频分析和处理"
    )
    
    if enable_multiprocessing:
        max_workers = st.slider(
            "最大进程数",
            min_value=2,
            max_value=multiprocessing.cpu_count(),
            value=min(4, multiprocessing.cpu_count()),
            step=1,
            help="设置并行处理的最大进程数。一般设置为CPU核心数或更少"
        )
    else:
        max_workers = 1
        
    st.markdown("---")
    st.subheader("高级参数")
    
    # 添加阈值搜索参数
    show_advanced = st.checkbox("显示高级参数", value=False)
    
    if show_advanced:
        # 阈值预设点，用于并行搜索
        preset_thresholds = st.text_input(
            "阈值预设点 (dBFS)",
            value="-90,-80,-70,-60,-50,-40,-30,-20,-10",
            help="用逗号分隔的预设阈值点，用于并行搜索静音阈值"
        )
        
        parallel_search = st.checkbox(
            "并行阈值搜索", 
            value=True,
            help="并行搜索多个阈值点，加速找到最佳阈值"
        )
    else:
        preset_thresholds = "-90,-80,-70,-60,-50,-40,-30,-20,-10"
        parallel_search = True
    
    st.markdown("---")
    st.subheader("关于")
    st.markdown("""
    **SilentCut** 是一个高效的音频处理工具，专注于自动检测并去除音频中的静音段。
    适用于播客剪辑、语音预处理、数据清洗等场景。
    """)

# 音频上传区域
uploaded_file = st.file_uploader("上传音频文件", type=["wav", "mp3", "flac", "ogg", "m4a"], help="支持常见音频格式")


# 多进程音频分析函数
def analyze_audio_segment(segment_data):
    """分析单个音频片段的特征，用于多进程处理"""
    try:
        if len(segment_data) == 0:
            return {"dBFS": -float('inf')}
        
        segment = AudioSegment(
            segment_data.tobytes(),
            frame_rate=44100,
            sample_width=2,
            channels=1
        )
        
        return {"dBFS": segment.dBFS}
    except Exception as e:
        logger.error(f"分析音频片段时出错: {e}")
        return {"dBFS": -float('inf'), "error": str(e)}


# 多进程阈值测试函数
def test_threshold_task(input_file_path, min_silence_len, threshold, output_dir):
    """测试特定阈值的效果，用于多进程并行测试多个阈值"""
    try:
        from pydub import AudioSegment
        from pydub.silence import split_on_silence
        import os
        
        # 读取音频文件
        audio = AudioSegment.from_file(input_file_path)
        input_size = os.path.getsize(input_file_path)
        
        # 使用指定阈值分割音频
        chunks = split_on_silence(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=threshold,
            keep_silence=100  # 保留一小段静音，避免声音突然切换
        )
        
        if not chunks:
            return {
                "threshold": threshold,
                "status": "failed",
                "message": "未检测到非静音片段",
                "output_size": 0,
                "ratio": 0,
            }
            
        # 合并非静音片段
        output_audio = sum(chunks)
        
        # 创建临时文件以检查大小
        basename = os.path.basename(input_file_path)
        name, ext = os.path.splitext(basename)
        temp_output_path = os.path.join(output_dir, f"{name}_thresh_{threshold}_{time.time()}.temp.wav")
        
        # 导出并检查大小
        output_audio.export(temp_output_path, format="wav")
        output_size = os.path.getsize(temp_output_path)
        size_ratio = output_size / input_size
        
        result = {
            "threshold": threshold,
            "status": "success",
            "temp_path": temp_output_path,
            "output_size": output_size,
            "ratio": size_ratio,
            "chunks": len(chunks),
        }
        
        return result
    except Exception as e:
        return {
            "threshold": threshold,
            "status": "error",
            "message": str(e),
            "output_size": 0,
            "ratio": 0,
        }


# 多进程处理函数
def process_audio_mp(input_file_path, output_dir, min_silence_len, preset_thresholds_str, max_workers=4, use_parallel_search=True):
    """使用多进程处理音频文件"""
    start_time = time.time()
    
    try:
        # 解析阈值预设点
        preset_thresholds = [float(t.strip()) for t in preset_thresholds_str.split(',')]
        
        # 获取输入文件大小
        input_size = os.path.getsize(input_file_path)
        basename = os.path.basename(input_file_path)
        
        # 生成输出文件名
        input_dir, input_filename = os.path.split(input_file_path)
        name, ext = os.path.splitext(input_filename)
        output_filename = f"{name}-desilenced.wav"
        output_path = os.path.join(output_dir, output_filename)
        
        # 确保输出目录存在
        ensure_dir_exists(output_dir)
        
        # 目标文件大小范围（原始的50%-99%）
        min_acceptable_size = int(input_size * 0.5)
        max_acceptable_size = int(input_size * 0.99)
        
        logger.info(f"处理文件: {basename}")
        logger.info(f"使用预设阈值点: {preset_thresholds}")
        
        # 如果启用并行搜索，使用多进程测试所有阈值点
        if use_parallel_search:
            # 准备阈值测试任务
            tasks = []
            for threshold in preset_thresholds:
                tasks.append((input_file_path, min_silence_len, threshold, output_dir))
            
            # 并行测试所有阈值点
            valid_results = []
            temp_files = []  # 用于跟踪所有创建的临时文件
            
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                future_to_threshold = {executor.submit(test_threshold_task, *task): task[2] for task in tasks}
                
                for future in as_completed(future_to_threshold):
                    threshold = future_to_threshold[future]
                    
                    try:
                        result = future.result()
                        
                        if result["status"] == "success":
                            # 记录临时文件路径，稍后需要清理
                            if "temp_path" in result and result["temp_path"]:
                                temp_files.append(result["temp_path"])
                                
                            # 检查是否在目标范围内
                            if min_acceptable_size <= result["output_size"] <= max_acceptable_size:
                                valid_results.append(result)
                        
                    except Exception as e:
                        logger.error(f"测试阈值 {threshold} dBFS 出错: {e}")
            
            # 如果有有效结果，选择最佳的
            if valid_results:
                # 优先选择文件大小比例接近0.7-0.8的结果（较好的平衡点）
                target_ratio = 0.75
                valid_results.sort(key=lambda r: abs(r["ratio"] - target_ratio))
                best_result = valid_results[0]
                best_threshold = best_result["threshold"]
                
                logger.info(f"选定最佳阈值: {best_threshold} dBFS (比例 {best_result['ratio']:.2f})")
                
                # 使用最佳阈值生成最终结果
                logger.info("生成最终结果...")
                
                # 创建处理器并使用最佳阈值处理
                processor = AudioProcessor(input_file_path)
                audio = processor.audio
                
                from pydub.silence import split_on_silence
                
                chunks = split_on_silence(
                    audio,
                    min_silence_len=min_silence_len,
                    silence_thresh=best_threshold,
                    keep_silence=100
                )
                
                if not chunks:
                    # 清理临时文件
                    clean_temp_files(temp_files)
                    return False, f"使用最佳阈值 {best_threshold} dBFS 未检测到非静音片段", None
                
                # 合并并导出
                output_audio = sum(chunks)
                output_audio.export(output_path, format="wav")
                
                # 清理临时文件
                clean_temp_files(temp_files)
                
                # 检查最终文件大小
                final_size = os.path.getsize(output_path)
                actual_ratio = final_size / input_size
                actual_reduction = ((input_size - final_size) / input_size * 100)
                
                result_message = (
                    f"处理完成，输出文件: {output_path} "
                    f"(阈值: {best_threshold} dBFS, 比例 {actual_ratio:.2f}, "
                    f"减少: {actual_reduction:.2f}%)"
                )
                
                return True, result_message, output_path
            else:
                # 清理临时文件
                clean_temp_files(temp_files)
                return False, f"未找到合适的阈值处理文件 {basename}", None
        else:
            # 使用单进程方式处理
            processor = AudioProcessor(input_file_path)
            success, message = processor.process_audio(min_silence_len=min_silence_len, output_folder=output_dir)
            
            # 获取处理后的文件路径
            if success:
                return True, message, output_path
            else:
                return False, message, None
                
    except Exception as e:
        logger.error(f"处理文件 {input_file_path} 时发生错误: {e}")
        return False, f"处理错误: {e}", None


# 安全音频加载函数
def safe_load_audio(file_path):
    """安全加载音频文件，处理可能的异常"""
    try:
        y, sr = librosa.load(file_path, sr=None)
        return y, sr, None
    except Exception as e:
        error_message = f"加载音频文件时出错: {e}"
        logger.error(error_message)
        return None, None, error_message


# 可视化函数
def visualize_audio(original_path, processed_path):
    """创建原始和处理后音频的波形图和频谱图比较"""
    # 加载音频文件
    y_orig, sr_orig, error_orig = safe_load_audio(original_path)
    y_proc, sr_proc, error_proc = safe_load_audio(processed_path)
    
    if error_orig or error_proc:
        st.error(f"可视化时出错: {error_orig or error_proc}")
        return None
    
    # 创建图表
    fig, axs = plt.subplots(2, 2, figsize=(12, 8))
    fig.tight_layout(pad=3.0)
    
    # 波形图 - 原始
    axs[0, 0].set_title("原始音频波形图")
    librosa.display.waveshow(y=y_orig, sr=sr_orig, ax=axs[0, 0])
    axs[0, 0].set_xlabel("时间 (秒)")
    axs[0, 0].set_ylabel("振幅")
    
    # 波形图 - 处理后
    axs[0, 1].set_title("处理后音频波形图")
    librosa.display.waveshow(y=y_proc, sr=sr_proc, ax=axs[0, 1])
    axs[0, 1].set_xlabel("时间 (秒)")
    axs[0, 1].set_ylabel("振幅")
    
    # 频谱图 - 原始
    D_orig = librosa.amplitude_to_db(np.abs(librosa.stft(y_orig)), ref=np.max)
    img_orig = librosa.display.specshow(D_orig, y_axis='log', x_axis='time', sr=sr_orig, ax=axs[1, 0])
    axs[1, 0].set_title("原始音频频谱图")
    fig.colorbar(img_orig, ax=axs[1, 0], format="%+2.0f dB")
    
    # 频谱图 - 处理后
    D_proc = librosa.amplitude_to_db(np.abs(librosa.stft(y_proc)), ref=np.max)
    img_proc = librosa.display.specshow(D_proc, y_axis='log', x_axis='time', sr=sr_proc, ax=axs[1, 1])
    axs[1, 1].set_title("处理后音频频谱图")
    fig.colorbar(img_proc, ax=axs[1, 1], format="%+2.0f dB")
    
    return fig


# 显示音频时长和大小信息
def show_audio_info(original_path, processed_path):
    """显示原始和处理后音频的比较信息"""
    # 获取文件大小
    original_size = os.path.getsize(original_path)
    processed_size = os.path.getsize(processed_path)
    
    # 获取音频时长
    y_orig, sr_orig, _ = safe_load_audio(original_path)
    y_proc, sr_proc, _ = safe_load_audio(processed_path)
    
    if y_orig is not None and y_proc is not None:
        original_duration = len(y_orig) / sr_orig
        processed_duration = len(y_proc) / sr_proc
        
        # 计算减少比例
        size_reduction = (original_size - processed_size) / original_size * 100
        duration_reduction = (original_duration - processed_duration) / original_duration * 100
        
        # 创建比较数据
        comparison_data = {
            "指标": ["文件大小", "音频时长"],
            "原始": [f"{original_size/1024/1024:.2f} MB", f"{original_duration:.2f} 秒"],
            "处理后": [f"{processed_size/1024/1024:.2f} MB", f"{processed_duration:.2f} 秒"],
            "减少比例": [f"{size_reduction:.2f}%", f"{duration_reduction:.2f}%"]
        }
        
        return comparison_data
    
    return None


# 性能比较统计
def benchmark_multiprocessing(file_size_mb):
    """估算多进程与单进程处理时间比较"""
    # 基于文件大小的简单性能估算模型
    cores = multiprocessing.cpu_count()
    
    # 假设处理时间与文件大小成正比
    # 这是一个简化的模型，实际性能会受到很多因素影响
    base_processing_time = file_size_mb * 0.5  # 假设每MB需要0.5秒处理时间
    
    # 单进程处理时间估计
    single_process_seconds = base_processing_time
    
    # 多进程处理时间估计（考虑并行开销）
    # 使用Amdahl定律的简化版本，假设80%的工作可以并行化
    parallel_portion = 0.8
    serial_portion = 1 - parallel_portion
    
    # 计算加速比
    speedup = 1 / (serial_portion + parallel_portion/min(4, cores))
    
    # 多进程处理时间
    multi_process_seconds = single_process_seconds / speedup
    
    # 节省的时间百分比
    time_saved_percent = (single_process_seconds - multi_process_seconds) / single_process_seconds * 100
    
    return {
        "single_process_seconds": single_process_seconds,
        "multi_process_seconds": multi_process_seconds,
        "speedup": speedup,
        "time_saved_percent": time_saved_percent,
        "cores": cores
    }


# 主处理逻辑
if uploaded_file is not None:
    # 保存上传的文件到临时位置
    input_file_path = os.path.join(temp_dir, uploaded_file.name)
    with open(input_file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 显示文件信息
    file_size_mb = os.path.getsize(input_file_path) / (1024 * 1024)
    st.info(f"已上传: {uploaded_file.name} ({file_size_mb:.2f} MB)")
    
    # 显示性能估算
    benchmark = benchmark_multiprocessing(file_size_mb)
    
    with st.expander("处理性能估算", expanded=False):
        st.write("基于文件大小的处理时间估算:")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric(
                label="单进程处理时间估计", 
                value=f"{benchmark['single_process_seconds']:.1f}秒"
            )
            
        with col2:
            st.metric(
                label="多进程处理时间估计", 
                value=f"{benchmark['multi_process_seconds']:.1f}秒", 
                delta=f"-{benchmark['time_saved_percent']:.1f}%"
            )
        
        if enable_multiprocessing:
            st.info(f"多进程处理已启用，预计加速比: {benchmark['speedup']:.1f}倍 (使用{max_workers}个进程，系统共有{benchmark['cores']}个CPU核心)")
        else:
            st.warning(f"多进程处理已禁用。启用后预计可加快{benchmark['time_saved_percent']:.1f}%的处理速度")
    
    # 处理按钮
    if st.button("开始处理"):
        with st.spinner("正在处理音频..."):
            # 记录开始时间用于性能比较
            start_time = time.time()
            
            # 尝试处理音频
            try:
                if enable_multiprocessing:
                    success, message, processed_file_path = process_audio_mp(
                        input_file_path, 
                        temp_dir, 
                        min_silence_len, 
                        preset_thresholds,
                        max_workers=max_workers,
                        use_parallel_search=parallel_search
                    )
                else:
                    # 使用单进程方式处理
                    processor = AudioProcessor(input_file_path)
                    success, message = processor.process_audio(min_silence_len=min_silence_len, output_folder=temp_dir)
                    
                    # 获取处理后的文件路径
                    file_name_without_ext = os.path.splitext(uploaded_file.name)[0]
                    processed_file_path = os.path.join(temp_dir, f"{file_name_without_ext}-desilenced.wav")
                
                # 计算处理时间
                processing_time = time.time() - start_time
                
                if success:
                    st.success(f"处理完成！耗时: {processing_time:.2f}秒")
                    
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
                        download_filename = f"{os.path.splitext(uploaded_file.name)[0]}_processed_{now}.wav"
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
    st.info("请上传一个音频文件进行处理")

# 页脚
st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>SilentCut &copy; 2025 | 智能音频静音切割工具</p>
</div>
""", unsafe_allow_html=True)
