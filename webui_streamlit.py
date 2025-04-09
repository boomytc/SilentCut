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
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
import time

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
uploaded_file = st.file_uploader("上传音频文件", type=["wav"], help="目前仅支持WAV格式")

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
        return {"error": str(e)}

# 多进程阈值测试函数
def test_threshold_task(input_file_path, min_silence_len, threshold, output_dir):
    """测试特定阈值的效果，用于多进程并行测试多个阈值"""
    try:
        from pydub import AudioSegment
        from pydub.silence import split_on_silence
        
        # 读取音频文件
        audio = AudioSegment.from_file(input_file_path)
        input_size = os.path.getsize(input_file_path)
        
        # 使用当前阈值分割音频
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
    # 解析预设阈值
    try:
        preset_thresholds = [float(t.strip()) for t in preset_thresholds_str.split(",")]
    except:
        preset_thresholds = [-90, -80, -70, -60, -50, -40, -30, -20, -10]
    
    min_acceptable_ratio = 0.5  # 最小可接受大小比例（原始大小的50%）
    max_acceptable_ratio = 0.99  # 最大可接受大小比例（原始大小的99%）
    input_size = os.path.getsize(input_file_path)
    
    progress_placeholder = st.empty()
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 如果不使用多进程，使用普通的AudioProcessor处理
    if max_workers == 1 or not use_parallel_search:
        processor = AudioProcessor(input_file_path)
        success, message = processor.process_audio(min_silence_len=min_silence_len, output_folder=output_dir)
        return success, message, None
    
    # 使用多进程并行测试多个阈值
    status_text.text("正在并行测试多个阈值点，寻找最佳阈值...")
    results = []
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 创建任务列表
        futures = []
        for threshold in preset_thresholds:
            future = executor.submit(
                test_threshold_task, 
                input_file_path, 
                min_silence_len, 
                threshold, 
                output_dir
            )
            futures.append(future)
        
        # 收集结果
        total_tasks = len(futures)
        completed_tasks = 0
        
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            
            completed_tasks += 1
            progress = completed_tasks / total_tasks
            progress_bar.progress(progress)
            status_text.text(f"阈值搜索进度: {completed_tasks}/{total_tasks} - 当前测试: {result.get('threshold', 'N/A')} dBFS")
    
    # 找出最佳阈值
    valid_results = [r for r in results if r["status"] == "success" and min_acceptable_ratio <= r["ratio"] <= max_acceptable_ratio]
    
    if valid_results:
        # 找到符合条件的阈值，选择最接近理想大小的结果
        target_ratio = 0.7  # 目标比例为原始大小的70%
        best_result = min(valid_results, key=lambda r: abs(r["ratio"] - target_ratio))
        
        # 获取最佳输出文件
        temp_path = best_result["temp_path"]
        threshold = best_result["threshold"]
        ratio = best_result["ratio"]
        
        # 重命名为最终输出文件
        basename = os.path.basename(input_file_path)
        name, ext = os.path.splitext(basename)
        output_filename = f"{name}-desilenced{ext}"
        output_path = os.path.join(output_dir, output_filename)
        
        # 如果输出文件已存在，先删除
        if os.path.exists(output_path):
            os.remove(output_path)
            
        os.rename(temp_path, output_path)
        
        # 删除所有其他临时文件
        for result in results:
            if result["status"] == "success" and "temp_path" in result:
                temp_file = result["temp_path"]
                if os.path.exists(temp_file) and temp_file != temp_path:
                    try:
                        os.remove(temp_file)
                    except:
                        pass
        
        message = f"多进程处理成功! 使用阈值: {threshold} dBFS, 输出文件大小: 原始的 {ratio*100:.2f}%"
        return True, message, output_path
    else:
        # 如果没有找到符合条件的阈值，尝试使用普通处理方式
        status_text.text("并行搜索未找到理想阈值，回退到标准处理方式...")
        
        # 删除所有临时文件
        for result in results:
            if result["status"] == "success" and "temp_path" in result:
                temp_file = result["temp_path"]
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
        
        # 使用普通的AudioProcessor处理
        processor = AudioProcessor(input_file_path)
        success, message = processor.process_audio(min_silence_len=min_silence_len, output_folder=output_dir)
        
        basename = os.path.basename(input_file_path)
        name, ext = os.path.splitext(basename)
        output_filename = f"{name}-desilenced{ext}"
        output_path = os.path.join(output_dir, output_filename)
        
        if success and os.path.exists(output_path):
            return True, f"回退到标准处理: {message}", output_path
        else:
            return False, f"处理失败: {message}", None

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

# 性能比较统计
def benchmark_multiprocessing(file_size_mb):
    """估算多进程与单进程处理时间比较"""
    # 这些是根据经验拟合的简化模型，实际性能会受很多因素影响
    cpu_cores = multiprocessing.cpu_count()
    
    # 估算单进程处理时间（秒）- 简化模型
    single_process_time = 2.5 * file_size_mb
    
    # 估算多进程加速比 - 考虑到多进程开销，不是线性加速
    # 一个简化的阿姆达尔定律模型
    parallel_portion = 0.8  # 假设80%的任务可以并行化
    speedup = 1 / ((1 - parallel_portion) + (parallel_portion / cpu_cores))
    
    # 计算多进程估计时间
    multi_process_time = single_process_time / speedup
    
    # 时间节省百分比
    time_saved_percent = (1 - (multi_process_time / single_process_time)) * 100
    
    return {
        "single_process_seconds": single_process_time,
        "multi_process_seconds": multi_process_time,
        "time_saved_percent": time_saved_percent,
        "speedup": speedup,
        "cores": cpu_cores
    }

# 主处理逻辑
if uploaded_file is not None:
    # 保存上传的文件到临时位置
    input_file_path = os.path.join(temp_dir, uploaded_file.name)
    with open(input_file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    st.success(f"文件上传成功: {uploaded_file.name}")
    
    # 显示性能估计
    file_size_mb = os.path.getsize(input_file_path) / (1024 * 1024)
    if file_size_mb > 1:  # 只对超过1MB的文件显示性能比较
        st.subheader("性能估计")
        benchmark = benchmark_multiprocessing(file_size_mb)
        
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
    st.info("请上传一个WAV格式的音频文件进行处理")

# 页脚
st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>SilentCut © 2025 | 智能音频静音切割工具</p>
</div>
""", unsafe_allow_html=True)