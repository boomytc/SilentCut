"""
静音切割控制器模块
"""
import os
import time
import tempfile
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QFileDialog, QTextEdit, QSpinBox, QProgressBar, QMessageBox,
    QRadioButton, QButtonGroup, QCheckBox, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from silentcut.audio.processor import AudioProcessor, PRESET_THRESHOLDS
from silentcut.utils.logger import get_logger
from silentcut.utils.file_utils import get_audio_files_in_directory, clean_temp_files

# 获取日志记录器
logger = get_logger("gui.desilencer_controller")


# 顶层函数，用于多进程处理
def process_file_task(args):
    """每个工作进程执行的函数"""
    input_file, output_dir, min_silence_len = args
    try:
        # 每个进程需要自己的 AudioProcessor 实例
        processor = AudioProcessor(input_file)
        success, message = processor.process_audio(min_silence_len, output_folder=output_dir)
        return input_file, success, message
    except Exception as e:
        # 如果处理过程中出错，返回错误详情
        return input_file, False, f"进程内错误: {str(e)}"


# 单个文件阈值测试的多进程函数
def test_threshold_task(args):
    """测试单个阈值点对音频文件的效果"""
    input_file, threshold, min_silence_len, output_dir = args
    
    try:
        from pydub import AudioSegment
        from pydub.silence import split_on_silence
        import os
        
        # 读取音频文件
        audio = AudioSegment.from_file(input_file)
        input_size = os.path.getsize(input_file)
        
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
        basename = os.path.basename(input_file)
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


class Worker(QThread):
    """处理音频的工作线程，避免冻结 GUI"""
    progress_signal = pyqtSignal(int) # 进度信号 (0-100 for batch, 0/100 for single)
    log_signal = pyqtSignal(str)      # 日志信号
    finished_signal = pyqtSignal(bool, str) # 完成信号 (success, message)
    processing_detail_signal = pyqtSignal(dict) # 音频处理详细信息信号
    
    def __init__(self, mode, input_path, output_dir, min_silence_len,
                 use_multiprocessing=False, num_cores=1, 
                 use_parallel_search=False, preset_thresholds=None):
        """初始化工作线程"""
        super().__init__()
        self.mode = mode  # 'single' 或 'batch'
        self.input_path = input_path
        self.output_dir = output_dir
        self.min_silence_len = min_silence_len
        self.use_multiprocessing = use_multiprocessing
        self.num_cores = num_cores
        self.use_parallel_search = use_parallel_search
        self.preset_thresholds = preset_thresholds or PRESET_THRESHOLDS
        self.running = True  # 控制线程运行
    
    def process_single_file(self, input_file):
        """处理单个文件的逻辑"""
        # 确保输出目录存在
        self._ensure_output_dir()
        
        # 根据是否使用并行搜索选择处理方法
        if self.use_parallel_search:
            return self.process_single_file_parallel(input_file, self.output_dir)
        else:
            return self.process_single_file_standard(input_file, self.output_dir)
    
    def _ensure_output_dir(self):
        """确保输出目录存在"""
        if self.output_dir and not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
                self.log_signal.emit(f"已创建输出目录: {self.output_dir}")
            except OSError as e:
                error_msg = f"无法创建输出目录 {self.output_dir}: {e}"
                self.log_signal.emit(error_msg)
                raise RuntimeError(error_msg)
    
    def _clean_temp_files(self, temp_files):
        """清理临时文件"""
        for file_path in temp_files:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except Exception as e:
                self.log_signal.emit(f"无法删除临时文件 {file_path}: {e}")
    
    def process_single_file_standard(self, input_file, output_dir):
        """使用标准方式处理单个文件"""
        start_time = time.time()
        
        # 发送进度信号 (0%)
        self.progress_signal.emit(0)
        
        try:
            # 获取输入文件大小
            input_size = os.path.getsize(input_file)
            
            # 发送处理详情信号
            self.processing_detail_signal.emit({
                "file_size": f"{input_size / 1024 / 1024:.2f} MB",
            })
            
            # 创建处理器并处理
            processor = AudioProcessor(input_file)
            success, message = processor.process_audio(
                min_silence_len=self.min_silence_len,
                output_folder=output_dir
            )
            
            # 处理完成，计算时间
            elapsed_time = time.time() - start_time
            
            # 解析处理结果消息以获取更多详情
            threshold = None
            ratio = None
            
            if success and "阈值:" in message:
                try:
                    # 解析"阈值: XX dBFS"格式的字符串
                    threshold_str = message.split("阈值:")[1].split("dBFS")[0].strip()
                    threshold = f"{float(threshold_str):.1f} dBFS"
                    
                    # 解析"减少: XX%, 保留: XX%"格式的字符串
                    if "减少:" in message and "保留:" in message:
                        ratio_str = message.split("保留:")[1].split("%")[0].strip()
                        ratio = f"{float(ratio_str):.1f}%"
                except:
                    pass
            
            # 发送完整的处理详情
            self.processing_detail_signal.emit({
                "process_time": f"{elapsed_time:.2f} 秒",
                "threshold": threshold or "-",
                "ratio": ratio or "-",
            })
            
            # 发送完成信号 (100%)
            self.progress_signal.emit(100)
            
            # 发送处理结果信号
            self.finished_signal.emit(success, message)
            
            return success, message
            
        except Exception as e:
            # 处理异常
            elapsed_time = time.time() - start_time
            error_message = f"处理文件 {input_file} 时发生错误: {e}"
            
            # 更新处理详情
            self.processing_detail_signal.emit({
                "process_time": f"{elapsed_time:.2f} 秒",
                "threshold": "错误",
                "ratio": "-",
            })
            
            # 发送完成信号 (100%)
            self.progress_signal.emit(100)
            
            # 发送错误消息
            self.log_signal.emit(error_message)
            self.finished_signal.emit(False, error_message)
            
            return False, error_message
    
    def process_single_file_parallel(self, input_file, output_dir):
        """使用并行阈值搜索处理单个文件"""
        start_time = time.time()
        # 创建临时目录管理所有临时文件
        temp_dir = tempfile.TemporaryDirectory(prefix="silentcut_")
        self.log_signal.emit(f"创建临时目录: {temp_dir.name}")
        # 在函数结束时会自动清理这个目录
        
        # 发送进度信号 (0%)
        self.progress_signal.emit(0)
        
        try:
            # 获取输入文件大小
            input_size = os.path.getsize(input_file)
            basename = os.path.basename(input_file)
            
            # 发送处理详情信号
            self.processing_detail_signal.emit({
                "file_size": f"{input_size / 1024 / 1024:.2f} MB",
            })
            
            self.log_signal.emit(f"使用并行搜索处理文件: {basename}")
            self.log_signal.emit(f"测试预设阈值点: {', '.join([str(t) for t in self.preset_thresholds[:5]])} ...")
            
            # 准备阈值测试任务
            tasks = []
            for threshold in self.preset_thresholds:
                # 使用临时目录而不是输出目录进行阈值测试
                tasks.append((input_file, threshold, self.min_silence_len, temp_dir.name))
            
            # 并行测试所有阈值点
            valid_results = []
            thresholds_tested = 0
            total_thresholds = len(tasks)
            temp_files = []  # 用于跟踪所有创建的临时文件
            
            # 目标文件大小范围（原始的50%-99%）
            min_acceptable_size = int(input_size * 0.5)
            max_acceptable_size = int(input_size * 0.99)
            
            with ProcessPoolExecutor(max_workers=self.num_cores) as executor:
                future_to_threshold = {executor.submit(test_threshold_task, task): task[1] for task in tasks}
                
                for future in as_completed(future_to_threshold):
                    if not self.running:
                        self.log_signal.emit("处理已取消")
                        # 清理临时文件
                        executor.shutdown(wait=False)
                        # 删除所有已创建的临时文件
                        self._clean_temp_files(temp_files)
                        return False, "处理已取消"
                    
                    threshold = future_to_threshold[future]
                    
                    try:
                        result = future.result()
                        thresholds_tested += 1
                        
                        # 更新进度
                        progress = int(thresholds_tested / total_thresholds * 80) # 占总进度的80%
                        self.progress_signal.emit(progress)
                        
                        # 记录结果
                        if result["status"] == "success":
                            self.log_signal.emit(
                                f"阈值 {threshold} dBFS: 比例={result['ratio']:.2f}, "
                                f"大小={result['output_size']/1024/1024:.2f}MB "
                                f"({result['chunks']} 个片段)"
                            )
                            
                            # 检查是否在目标范围内
                            if min_acceptable_size <= result["output_size"] <= max_acceptable_size:
                                valid_results.append(result)
                            
                            # 记录临时文件路径，稍后需要清理
                            if "temp_path" in result and result["temp_path"]:
                                temp_files.append(result["temp_path"])
                        else:
                            self.log_signal.emit(f"阈值 {threshold} dBFS 测试失败: {result.get('message', '未知错误')}")
                    except Exception as e:
                        self.log_signal.emit(f"测试阈值 {threshold} dBFS 出错: {e}")
            
            # 取消时会执行清理
            
            # 处理并行搜索结果
            if not self.running:
                # 清理临时文件
                self._clean_temp_files(temp_files)
                return False, "处理已取消"
                
            self.log_signal.emit(f"共测试了 {thresholds_tested} 个阈值点, 找到 {len(valid_results)} 个有效结果")
            
            # 如果有有效结果，选择最佳的
            if valid_results:
                # 优先选择文件大小比例接近0.7-0.8的结果（较好的平衡点）
                target_ratio = 0.75
                valid_results.sort(key=lambda r: abs(r["ratio"] - target_ratio))
                best_result = valid_results[0]
                best_threshold = best_result["threshold"]
                
                self.log_signal.emit(f"选定最佳阈值: {best_threshold} dBFS (比例 {best_result['ratio']:.2f})")
                
                # 使用最佳阈值生成最终结果
                self.log_signal.emit("生成最终结果...")
                self.progress_signal.emit(90)  # 更新进度到90%
                
                # 创建处理器并使用最佳阈值处理
                processor = AudioProcessor(input_file)
                audio = processor.audio
                
                from pydub.silence import split_on_silence
                
                chunks = split_on_silence(
                    audio,
                    min_silence_len=self.min_silence_len,
                    silence_thresh=best_threshold,
                    keep_silence=100
                )
                
                if not chunks:
                    error_msg = f"使用最佳阈值 {best_threshold} dBFS 未检测到非静音片段"
                    self.log_signal.emit(error_msg)
                    return False, error_msg
                
                # 生成输出文件名
                input_dir, input_filename = os.path.split(input_file)
                name, ext = os.path.splitext(input_filename)
                output_filename = f"{name}-desilenced{ext}"
                output_path = os.path.join(output_dir, output_filename)
                
                # 合并并导出
                output_audio = sum(chunks)
                output_audio.export(output_path, format="wav")
                
                # 构造结果消息，包含关键信息
                result_message = (
                    f"处理完成，输出文件: {output_path} "
                    f"(阈值: {best_threshold} dBFS, 比例 {best_result['ratio']:.2f})"
                )
                self.log_signal.emit(f"处理成功完成: {result_message}")
                self.finished_signal.emit(True, result_message)
                 
                return True, result_message
            else:
                error_msg = f"未找到合适的阈值处理文件 {basename}"
                self.log_signal.emit(error_msg)
                
                # 发送完成信号 (100%)
                self.progress_signal.emit(100)
                
                # 清理临时文件
                self._clean_temp_files(temp_files)
                
                self.finished_signal.emit(False, error_msg)
                
                return False, error_msg
                
        except Exception as e:
            # 处理异常
            elapsed_time = time.time() - start_time
            error_message = f"处理文件 {input_file} 时发生错误: {e}"
            
            # 更新处理详情
            self.processing_detail_signal.emit({
                "process_time": f"{elapsed_time:.2f} 秒",
                "threshold": "错误",
                "ratio": "-",
            })
            
            # 发送完成信号 (100%)
            self.progress_signal.emit(100)
            
            # 发送错误消息
            self.log_signal.emit(error_message)
            self.finished_signal.emit(False, error_message)
            
            return False, error_message
    
    def run(self):
        """线程执行入口"""
        try:
            self.log_signal.emit(f"开始处理，模式: {'单文件' if self.mode == 'single' else '批处理'}")
            
            # 根据模式选择处理方法
            if self.mode == "single":
                if os.path.isfile(self.input_path):
                    self.process_single_file(self.input_path)
                else:
                    self.log_signal.emit(f"错误: 输入路径不是文件: {self.input_path}")
                    self.finished_signal.emit(False, f"输入路径不是文件: {self.input_path}")
            else:  # 批处理模式
                if os.path.isdir(self.input_path):
                    if self.use_multiprocessing:
                        self.run_batch_multiprocessing()
                    else:
                        self.run_batch_sequential()
                else:
                    self.log_signal.emit(f"错误: 输入路径不是目录: {self.input_path}")
                    self.finished_signal.emit(False, f"输入路径不是目录: {self.input_path}")
        except Exception as e:
            self.log_signal.emit(f"处理时发生意外错误: {e}")
            self.finished_signal.emit(False, f"处理错误: {e}")
    
    def run_batch_sequential(self):
        """顺序批处理（原始逻辑）"""
        # 获取目录中的所有音频文件
        audio_files = get_audio_files_in_directory(self.input_path)
        
        if not audio_files:
            self.log_signal.emit(f"错误: 目录 {self.input_path} 中未找到音频文件")
            self.finished_signal.emit(False, "未找到音频文件")
            return
            
        # 确保输出目录存在
        self._ensure_output_dir()
        
        # 处理每个文件
        total_files = len(audio_files)
        processed_files = 0
        success_count = 0
        fail_count = 0
        
        self.log_signal.emit(f"开始处理 {total_files} 个文件...")
        
        for file_path in audio_files:
            if not self.running:
                self.log_signal.emit("处理已取消")
                break
                
            self.log_signal.emit(f"处理文件 {processed_files+1}/{total_files}: {os.path.basename(file_path)}")
            
            # 处理单个文件
            success, message = self.process_single_file(file_path)
            
            # 更新计数
            processed_files += 1
            if success:
                success_count += 1
            else:
                fail_count += 1
                
            # 更新进度
            progress = int(processed_files / total_files * 100)
            self.progress_signal.emit(progress)
            
        # 处理完成
        if self.running:
            result_message = f"批处理完成: 成功 {success_count}/{total_files}, 失败 {fail_count}/{total_files}"
            self.log_signal.emit(result_message)
            self.finished_signal.emit(success_count > 0, result_message)
        else:
            result_message = f"批处理已取消: 已处理 {processed_files}/{total_files}, 成功 {success_count}, 失败 {fail_count}"
            self.log_signal.emit(result_message)
            self.finished_signal.emit(False, result_message)
    
    def run_batch_multiprocessing(self):
        """使用多进程进行批处理"""
        # 获取目录中的所有音频文件
        audio_files = get_audio_files_in_directory(self.input_path)
        
        if not audio_files:
            self.log_signal.emit(f"错误: 目录 {self.input_path} 中未找到音频文件")
            self.finished_signal.emit(False, "未找到音频文件")
            return
            
        # 确保输出目录存在
        self._ensure_output_dir()
        
        # 准备任务列表
        tasks = [(file, self.output_dir, self.min_silence_len) for file in audio_files]
        total_files = len(tasks)
        
        self.log_signal.emit(f"开始使用多进程处理 {total_files} 个文件 (进程数: {self.num_cores})...")
        
        # 处理结果统计
        processed_files = 0
        success_count = 0
        fail_count = 0
        
        # 使用进程池并行处理
        with ProcessPoolExecutor(max_workers=self.num_cores) as executor:
            # 提交所有任务
            future_to_file = {executor.submit(process_file_task, task): task[0] for task in tasks}
            
            # 处理完成的任务
            for future in as_completed(future_to_file):
                if not self.running:
                    self.log_signal.emit("处理已取消")
                    executor.shutdown(wait=False)
                    break
                    
                file_path = future_to_file[future]
                
                try:
                    # 获取处理结果
                    file, success, message = future.result()
                    
                    # 更新计数
                    processed_files += 1
                    if success:
                        success_count += 1
                        self.log_signal.emit(f"成功处理 {os.path.basename(file)}: {message}")
                    else:
                        fail_count += 1
                        self.log_signal.emit(f"处理失败 {os.path.basename(file)}: {message}")
                    
                    # 更新进度
                    progress = int(processed_files / total_files * 100)
                    self.progress_signal.emit(progress)
                    
                except Exception as e:
                    # 处理异常
                    processed_files += 1
                    fail_count += 1
                    self.log_signal.emit(f"处理 {os.path.basename(file_path)} 时发生错误: {e}")
                    
                    # 更新进度
                    progress = int(processed_files / total_files * 100)
                    self.progress_signal.emit(progress)
        
        # 处理完成
        if self.running:
            result_message = f"批处理完成: 成功 {success_count}/{total_files}, 失败 {fail_count}/{total_files}"
            self.log_signal.emit(result_message)
            self.finished_signal.emit(success_count > 0, result_message)
        else:
            result_message = f"批处理已取消: 已处理 {processed_files}/{total_files}, 成功 {success_count}, 失败 {fail_count}"
            self.log_signal.emit(result_message)
            self.finished_signal.emit(False, result_message)
    
    def stop(self):
        """停止处理"""
        self.running = False


class DesilencerController:
    """静音切割控制器"""
    
    def __init__(self, tab_widget):
        """初始化静音切割控制器"""
        self.tab = tab_widget
        self.worker = None
        self.current_mode = 'single'  # 'single' 或 'batch'
        self.max_cores = multiprocessing.cpu_count()
        
        # 初始化UI
        self._init_ui()
        
        logger.info("静音切割控制器初始化完成")
    
    def _init_ui(self):
        """初始化用户界面"""
        # 获取标签页布局
        layout = self.tab.layout()
        
        # 创建模式选择区域
        mode_group = QGroupBox("处理模式")
        mode_layout = QHBoxLayout()
        
        # 单文件模式
        self.single_radio = QRadioButton("单文件处理")
        self.single_radio.setChecked(True)
        self.single_radio.toggled.connect(self.update_mode)
        mode_layout.addWidget(self.single_radio)
        
        # 批处理模式
        self.batch_radio = QRadioButton("批量处理")
        self.batch_radio.toggled.connect(self.update_mode)
        mode_layout.addWidget(self.batch_radio)
        
        # 设置模式组
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # 创建输入区域
        input_group = QGroupBox("输入")
        input_layout = QVBoxLayout()
        
        # 输入路径
        input_path_layout = QHBoxLayout()
        self.input_path_label = QLabel("输入文件:")
        self.input_path_edit = QLineEdit()
        self.input_path_edit.setReadOnly(True)
        self.browse_input_btn = QPushButton("浏览...")
        self.browse_input_btn.clicked.connect(self.browse_input)
        
        input_path_layout.addWidget(self.input_path_label)
        input_path_layout.addWidget(self.input_path_edit, 1)
        input_path_layout.addWidget(self.browse_input_btn)
        input_layout.addLayout(input_path_layout)
        
        # 输出路径
        output_path_layout = QHBoxLayout()
        self.output_path_label = QLabel("输出目录:")
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(True)
        self.browse_output_btn = QPushButton("浏览...")
        self.browse_output_btn.clicked.connect(self.browse_output_folder)
        
        output_path_layout.addWidget(self.output_path_label)
        output_path_layout.addWidget(self.output_path_edit, 1)
        output_path_layout.addWidget(self.browse_output_btn)
        input_layout.addLayout(output_path_layout)
        
        # 设置输入组
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # 创建参数区域
        params_group = QGroupBox("处理参数")
        params_layout = QVBoxLayout()
        
        # 最小静音长度
        silence_len_layout = QHBoxLayout()
        self.silence_len_label = QLabel("最小静音长度 (毫秒):")
        self.silence_len_spinbox = QSpinBox()
        self.silence_len_spinbox.setRange(100, 5000)
        self.silence_len_spinbox.setValue(500)
        self.silence_len_spinbox.setSingleStep(100)
        
        silence_len_layout.addWidget(self.silence_len_label)
        silence_len_layout.addWidget(self.silence_len_spinbox)
        params_layout.addLayout(silence_len_layout)
        
        # 多进程设置
        mp_layout = QHBoxLayout()
        self.mp_checkbox = QCheckBox("启用多进程处理")
        self.mp_checkbox.setChecked(True)
        self.mp_checkbox.toggled.connect(self.toggle_mp_spinbox)
        
        self.mp_cores_label = QLabel("进程数:")
        self.mp_cores_spinbox = QSpinBox()
        self.mp_cores_spinbox.setRange(1, self.max_cores)
        self.mp_cores_spinbox.setValue(min(4, self.max_cores))
        
        mp_layout.addWidget(self.mp_checkbox)
        mp_layout.addWidget(self.mp_cores_label)
        mp_layout.addWidget(self.mp_cores_spinbox)
        params_layout.addLayout(mp_layout)
        
        # 并行搜索设置 (仅单文件模式)
        self.parallel_search_layout = QHBoxLayout()
        self.parallel_search_checkbox = QCheckBox("启用并行阈值搜索")
        self.parallel_search_checkbox.setChecked(True)
        
        self.thresholds_label = QLabel("阈值预设点:")
        self.thresholds_edit = QLineEdit("-90,-80,-70,-60,-50,-40,-30,-20,-10")
        
        self.parallel_search_layout.addWidget(self.parallel_search_checkbox)
        self.parallel_search_layout.addWidget(self.thresholds_label)
        self.parallel_search_layout.addWidget(self.thresholds_edit, 1)
        params_layout.addLayout(self.parallel_search_layout)
        
        # 设置参数组
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # 创建日志区域
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()
        
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        log_layout.addWidget(self.progress_bar)
        
        # 处理详情
        details_layout = QHBoxLayout()
        
        self.file_size_label = QLabel("文件大小: -")
        self.process_time_label = QLabel("处理时间: -")
        self.threshold_label = QLabel("使用阈值: -")
        self.ratio_label = QLabel("大小比例: -")
        
        details_layout.addWidget(self.file_size_label)
        details_layout.addWidget(self.process_time_label)
        details_layout.addWidget(self.threshold_label)
        details_layout.addWidget(self.ratio_label)
        
        log_layout.addLayout(details_layout)
        
        # 设置日志组
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # 创建操作按钮
        action_layout = QHBoxLayout()
        
        self.process_btn = QPushButton("开始处理")
        self.process_btn.clicked.connect(self.start_processing)
        action_layout.addWidget(self.process_btn)
        
        layout.addLayout(action_layout)
        
        # 初始化模式
        self.update_mode()
    
    def update_mode(self):
        """根据选择的模式更新UI元素"""
        if self.single_radio.isChecked():
            self.current_mode = 'single'
            self.input_path_label.setText("输入文件:")
            # 显示并行搜索选项
            self.parallel_search_layout.setEnabled(True)
            for i in range(self.parallel_search_layout.count()):
                item = self.parallel_search_layout.itemAt(i)
                if item and item.widget():
                    item.widget().setVisible(True)
        else:
            self.current_mode = 'batch'
            self.input_path_label.setText("输入目录:")
            # 隐藏并行搜索选项
            self.parallel_search_layout.setEnabled(False)
            for i in range(self.parallel_search_layout.count()):
                item = self.parallel_search_layout.itemAt(i)
                if item and item.widget():
                    item.widget().setVisible(False)
    
    def toggle_mp_spinbox(self):
        """根据多进程复选框状态启用/禁用核心数微调框"""
        self.mp_cores_label.setEnabled(self.mp_checkbox.isChecked())
        self.mp_cores_spinbox.setEnabled(self.mp_checkbox.isChecked())
    
    def browse_input(self):
        """根据当前模式浏览文件或目录"""
        if self.current_mode == 'single':
            file_path, _ = QFileDialog.getOpenFileName(
                self.tab,
                "选择音频文件",
                "",
                "音频文件 (*.wav *.mp3 *.flac *.ogg *.m4a);;所有文件 (*.*)"
            )
            if file_path:
                self.input_path_edit.setText(file_path)
        else:
            dir_path = QFileDialog.getExistingDirectory(
                self.tab,
                "选择输入目录"
            )
            if dir_path:
                self.input_path_edit.setText(dir_path)
    
    def browse_output_folder(self):
        """浏览并选择输出目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self.tab,
            "选择输出目录"
        )
        if dir_path:
            self.output_path_edit.setText(dir_path)
    
    def log(self, message):
        """添加日志消息"""
        self.log_edit.append(message)
        self.log_edit.ensureCursorVisible()
    
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
    
    def update_processing_details(self, details):
        """更新处理详情显示"""
        if "file_size" in details:
            self.file_size_label.setText(f"文件大小: {details['file_size']}")
        
        if "process_time" in details:
            self.process_time_label.setText(f"处理时间: {details['process_time']}")
        
        if "threshold" in details:
            self.threshold_label.setText(f"使用阈值: {details['threshold']}")
        
        if "ratio" in details:
            self.ratio_label.setText(f"大小比例: {details['ratio']}")
    
    def processing_finished(self, success, message):
        """处理完成回调"""
        # 恢复UI状态
        self.set_inputs_enabled(True)
        self.process_btn.setText("开始处理")
        
        # 显示结果消息
        if success:
            self.log(f"处理成功: {message}")
            QMessageBox.information(self.tab, "处理完成", message)
        else:
            self.log(f"处理失败: {message}")
            QMessageBox.warning(self.tab, "处理失败", message)
    
    def set_inputs_enabled(self, enabled):
        """启用/禁用输入控件"""
        # 模式选择
        self.single_radio.setEnabled(enabled)
        self.batch_radio.setEnabled(enabled)
        
        # 输入/输出路径
        self.input_path_edit.setEnabled(enabled)
        self.browse_input_btn.setEnabled(enabled)
        self.output_path_edit.setEnabled(enabled)
        self.browse_output_btn.setEnabled(enabled)
        
        # 参数设置
        self.silence_len_spinbox.setEnabled(enabled)
        self.mp_checkbox.setEnabled(enabled)
        self.mp_cores_spinbox.setEnabled(enabled and self.mp_checkbox.isChecked())
        self.parallel_search_checkbox.setEnabled(enabled and self.current_mode == 'single')
        self.thresholds_edit.setEnabled(enabled and self.current_mode == 'single')
    
    def start_processing(self):
        """开始处理音频"""
        # 如果已经在处理中，则停止处理
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
            self.set_inputs_enabled(True)
            self.process_btn.setText("开始处理")
            return
        
        # 获取输入路径
        input_path = self.input_path_edit.text()
        if not input_path:
            QMessageBox.warning(self.tab, "输入错误", "请选择输入文件或目录")
            return
        
        # 检查输入路径是否存在
        if not os.path.exists(input_path):
            QMessageBox.warning(self.tab, "输入错误", f"输入路径不存在: {input_path}")
            return
        
        # 检查输入路径类型是否与模式匹配
        if self.current_mode == 'single' and not os.path.isfile(input_path):
            QMessageBox.warning(self.tab, "输入错误", "单文件模式下请选择一个文件")
            return
        elif self.current_mode == 'batch' and not os.path.isdir(input_path):
            QMessageBox.warning(self.tab, "输入错误", "批处理模式下请选择一个目录")
            return
        
        # 获取输出目录
        output_dir = self.output_path_edit.text()
        
        # 获取处理参数
        min_silence_len = self.silence_len_spinbox.value()
        
        # 输出目录检查与创建
        if output_dir and not os.path.exists(output_dir):
            reply = QMessageBox.question(
                self.tab,
                "创建目录?",
                f"输出目录 '{output_dir}' 不存在。是否要创建它？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    os.makedirs(output_dir)
                    self.log(f"已创建输出目录: {output_dir}")
                except OSError as e:
                    self.log(f"错误：无法创建输出目录 {output_dir}: {e}")
                    QMessageBox.warning(self.tab, "输出错误", f"无法创建输出目录: {e}")
                    return
            else:
                # 用户不创建，清空让 Worker 使用源目录
                self.log("操作取消：用户选择不创建输出目录。将使用默认输出位置。")
                self.output_path_edit.setText("")
                output_dir = ""
        elif output_dir and not os.path.isdir(output_dir):
            self.log(f"错误：指定的输出路径 '{output_dir}' 不是一个有效的目录。")
            QMessageBox.warning(self.tab, "输出错误", f"指定的输出路径不是一个有效的目录。")
            return
        
        # 清空日志和进度条
        self.log_edit.clear()
        self.progress_bar.setValue(0)
        
        # 重置处理详情
        self.file_size_label.setText("文件大小: -")
        self.process_time_label.setText("处理时间: -")
        self.threshold_label.setText("使用阈值: -")
        self.ratio_label.setText("大小比例: -")
        
        # 禁用输入控件
        self.set_inputs_enabled(False)
        self.process_btn.setText("停止处理")
        self.process_btn.setEnabled(True)
        
        # 获取多进程设置
        use_mp = self.mp_checkbox.isChecked()
        num_cores = self.mp_cores_spinbox.value() if use_mp else 1
        
        # 获取单文件并行搜索选项
        use_parallel_search = False
        preset_thresholds = []
        if self.current_mode == 'single':
            use_parallel_search = self.parallel_search_checkbox.isChecked() and use_mp
            try:
                # 解析阈值预设点
                threshold_text = self.thresholds_edit.text().strip()
                if threshold_text:
                    preset_thresholds = [float(t.strip()) for t in threshold_text.split(',')]
            except ValueError:
                self.log("警告：阈值预设点格式无效，将使用默认值")
                preset_thresholds = PRESET_THRESHOLDS
        
        # 创建并启动工作线程
        self.worker = Worker(
            mode=self.current_mode,
            input_path=input_path,
            output_dir=output_dir,
            min_silence_len=min_silence_len,
            use_multiprocessing=use_mp,
            num_cores=num_cores,
            use_parallel_search=use_parallel_search,
            preset_thresholds=preset_thresholds
        )
        
        # 连接信号
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.processing_detail_signal.connect(self.update_processing_details)
        
        # 启动线程
        self.worker.start()
