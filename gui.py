import sys
import os
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QSpinBox, QProgressBar, QMessageBox,
    QRadioButton, QButtonGroup, QCheckBox, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# 动态添加 audio_desilencer 目录到 Python 路径
# 假设 gui.py 在项目根目录, audio_desilencer 是其子目录
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = script_dir # 如果 gui.py 在根目录
audio_desilencer_path = os.path.join(project_root, 'audio_desilencer')
if audio_desilencer_path not in sys.path:
    sys.path.insert(0, audio_desilencer_path)

# 现在尝试导入
try:
    from audio_processor import AudioProcessor # 导入处理类
except ImportError as e:
    print(f"错误：无法导入 AudioProcessor: {e}")
    print(f"请确保 audio_processor.py 在当前目录下。")
    AudioProcessor = None

# --- Top-level function for multiprocessing --- #
def process_file_task(args):
    """Function executed by each worker process."""
    input_file, output_dir, min_silence_len = args
    try:
        # Each process needs its own AudioProcessor instance
        processor = AudioProcessor(input_file)
        success, message = processor.process_audio(min_silence_len, output_folder=output_dir)
        return input_file, success, message
    except Exception as e:
        # Return error details if processing fails within the process
        return input_file, False, f"Error in subprocess: {str(e)}"

# --- 新增：单个文件阈值测试的多进程函数 --- #
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
    # 新增：音频处理详细信息信号
    processing_detail_signal = pyqtSignal(dict) # 详细处理信息

    def __init__(self, mode, input_path, output_dir, min_silence_len,
                 use_multiprocessing=False, num_cores=1, 
                 use_parallel_search=False, preset_thresholds=None): 
        super().__init__()
        self.mode = mode
        self.input_path = input_path
        self.output_dir = output_dir
        self.min_silence_len = min_silence_len
        self.use_multiprocessing = use_multiprocessing
        self.num_cores = num_cores # Number of cores to use if multiprocessing
        self._is_running = True
        # 新增：用于单文件处理的并行搜索选项
        self.use_parallel_search = use_parallel_search
        # 默认阈值预设点
        self.preset_thresholds = preset_thresholds or [-90, -80, -70, -60, -50, -45, -40, -35, -30, -25, -20, -15, -10]

    def process_single_file(self, input_file):
        """处理单个文件的逻辑"""
        self.progress_signal.emit(0)
        filename = os.path.basename(input_file)
        self.log_signal.emit(f"处理文件: {filename} ...")
        
        # 确保输出目录存在
        if not self._ensure_output_dir():
            return False, "无法创建输出目录"
            
        # 确定输出目录（如果未指定，则与输入文件同目录）
        output_dir_to_use = self.output_dir if self.output_dir else os.path.dirname(input_file)
        
        if self.use_parallel_search:
            return self.process_single_file_parallel(input_file, output_dir_to_use)
        else:
            return self.process_single_file_standard(input_file, output_dir_to_use)

    def _ensure_output_dir(self):
        """确保输出目录存在"""
        if not self.output_dir:
            return True  # 未指定输出目录时使用源目录
            
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
                self.log_signal.emit(f"已创建输出目录: {self.output_dir}")
                return True
            except OSError as e:
                self.log_signal.emit(f"错误：无法创建输出目录 {self.output_dir}: {e}")
                return False
        return True

    def process_single_file_standard(self, input_file, output_dir):
        """使用标准方式处理单个文件"""
        try:
            if not self._is_running: 
                return False, "用户取消"

            start_time = time.time()
            self.log_signal.emit(f"使用标准处理模式...")
                
            audio_processor = AudioProcessor(input_file)
            success, message = audio_processor.process_audio(self.min_silence_len, output_folder=output_dir)
            
            processing_time = time.time() - start_time
            self.log_signal.emit(f"处理耗时: {processing_time:.2f} 秒")

            # 构建预期的输出文件名以供日志记录
            filename = os.path.basename(input_file)
            name, _ = os.path.splitext(filename)
            output_filename = f"{name}-desilenced.wav"
            final_output_path = os.path.join(output_dir, output_filename)
            
            # 检查输出文件
            if os.path.exists(final_output_path):
                input_size = os.path.getsize(input_file)
                output_size = os.path.getsize(final_output_path)
                ratio = output_size / input_size
                
                # 发送详细信息
                details = {
                    "input_size": input_size,
                    "output_size": output_size,
                    "ratio": ratio,
                    "processing_time": processing_time,
                    "output_path": final_output_path
                }
                self.processing_detail_signal.emit(details)
                
                self.log_signal.emit(f"文件 {filename} 处理完成")
                self.log_signal.emit(f"输出文件: {final_output_path}")
                self.log_signal.emit(f"输出大小: {output_size/1024:.1f} KB (原始的 {ratio*100:.1f}%)")
            
            self.progress_signal.emit(100)
            return True, "处理成功完成"
        except Exception as e:
            self.log_signal.emit(f"处理文件 {os.path.basename(input_file)} 时发生错误: {str(e)}")
            return False, f"处理失败: {e}"

    def process_single_file_parallel(self, input_file, output_dir):
        """使用并行阈值搜索处理单个文件"""
        try:
            if not self._is_running:
                return False, "用户取消"
                
            self.log_signal.emit(f"使用并行阈值搜索模式 (使用 {self.num_cores} 个进程)...")
            start_time = time.time()
            
            # 定义文件大小比例限制
            min_acceptable_ratio = 0.5  # 最小可接受比例（原始大小的50%）
            max_acceptable_ratio = 0.99  # 最大可接受比例（原始大小的99%）
            target_ratio = 0.7  # 理想目标比例
            
            input_size = os.path.getsize(input_file)
            self.log_signal.emit(f"原始文件大小: {input_size/1024:.1f} KB")
            
            # 准备并行测试任务
            tasks = [
                (input_file, threshold, self.min_silence_len, output_dir)
                for threshold in self.preset_thresholds
            ]
            
            # 使用进程池并行测试多个阈值点
            results = []
            completed_tasks = 0
            total_tasks = len(tasks)
            
            # 创建临时文件列表，用于后续清理
            temp_files = []
            
            with ProcessPoolExecutor(max_workers=self.num_cores) as executor:
                # 提交所有任务
                futures = [executor.submit(test_threshold_task, task) for task in tasks]
                
                # 收集结果
                for future in as_completed(futures):
                    if not self._is_running:
                        self.log_signal.emit("处理已取消")
                        # 尝试取消剩余任务
                        for f in futures:
                            f.cancel()
                        return False, "用户取消"
                    
                    result = future.result()
                    results.append(result)
                    
                    # 更新进度
                    completed_tasks += 1
                    progress = int((completed_tasks / total_tasks) * 100)
                    self.progress_signal.emit(progress)
                    
                    # 记录临时文件路径
                    if result['status'] == 'success' and 'temp_path' in result:
                        temp_files.append(result['temp_path'])
                    
                    # 输出当前结果
                    threshold = result.get('threshold', 'N/A')
                    status = result.get('status', 'unknown')
                    if status == 'success':
                        ratio = result.get('ratio', 0) * 100
                        chunks = result.get('chunks', 0)
                        self.log_signal.emit(f"阈值 {threshold} dBFS: 大小比例 {ratio:.1f}%, 检测到 {chunks} 个声音片段")
                    else:
                        self.log_signal.emit(f"阈值 {threshold} dBFS: {result.get('message', '处理失败')}")
            
            # 处理完成，选择最佳结果
            processing_time = time.time() - start_time
            self.log_signal.emit(f"阈值搜索完成，耗时: {processing_time:.2f} 秒")
            
            # 找出符合要求的结果
            valid_results = [
                r for r in results 
                if r['status'] == 'success' and 
                min_acceptable_ratio <= r['ratio'] <= max_acceptable_ratio
            ]
            
            if valid_results:
                # 选择最接近目标比例的结果作为最佳结果
                best_result = min(valid_results, key=lambda r: abs(r['ratio'] - target_ratio))
                
                # 获取最佳结果信息
                best_threshold = best_result['threshold']
                best_ratio = best_result['ratio'] * 100
                best_path = best_result['temp_path']
                
                self.log_signal.emit(f"找到最佳阈值: {best_threshold} dBFS (保留原始大小的 {best_ratio:.1f}%)")
                
                # 重命名为最终输出文件
                basename = os.path.basename(input_file)
                name, ext = os.path.splitext(basename)
                output_filename = f"{name}-desilenced{ext}"
                final_output_path = os.path.join(output_dir, output_filename)
                
                # 如果文件已存在，先删除
                if os.path.exists(final_output_path):
                    os.remove(final_output_path)
                
                # 重命名最佳结果文件
                os.rename(best_path, final_output_path)
                
                # 发送详细信息
                details = {
                    "input_size": input_size,
                    "output_size": best_result['output_size'],
                    "ratio": best_result['ratio'],
                    "threshold": best_threshold,
                    "processing_time": processing_time,
                    "chunks": best_result['chunks'],
                    "output_path": final_output_path
                }
                self.processing_detail_signal.emit(details)
                
                # 清理其他临时文件
                for temp_file in temp_files:
                    if os.path.exists(temp_file) and temp_file != best_path:
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                
                return True, f"处理成功完成，使用阈值: {best_threshold} dBFS"
            else:
                # 未找到合适的结果，尝试回退到标准处理
                self.log_signal.emit("未找到理想阈值，回退到标准处理...")
                
                # 清理所有临时文件
                for temp_file in temp_files:
                    if os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                
                # 回退到标准处理
                return self.process_single_file_standard(input_file, output_dir)
                
        except Exception as e:
            self.log_signal.emit(f"并行处理文件 {os.path.basename(input_file)} 时发生错误: {str(e)}")
            return False, f"处理失败: {e}"

    def run(self):
        if AudioProcessor is None:
             self.log_signal.emit("错误: AudioProcessor 类未能加载，无法处理。")
             self.finished_signal.emit(False, "依赖项错误")
             return

        self._is_running = True
        self.log_signal.emit(f"模式: {'单个文件' if self.mode == 'single' else '批量目录'}")
        self.log_signal.emit(f"输入: {self.input_path}")
        self.log_signal.emit(f"输出目录: {self.output_dir}")
        self.log_signal.emit(f"最小静音长度: {self.min_silence_len} ms")

        if self.mode == 'single':
            success, message = self.process_single_file(self.input_path)
            self.finished_signal.emit(success, message)
            return

        # --- Batch Mode Logic --- #
        if self.mode == 'batch':
            if self.use_multiprocessing:
                self.run_batch_multiprocessing()
            else:
                self.run_batch_sequential()

    def run_batch_sequential(self):
        """Sequential batch processing (original logic)."""
        self.log_signal.emit("开始顺序批量处理...")
        try:
            input_dir = self.input_path
            wav_files = []
            for filename in os.listdir(input_dir):
                if filename.lower().endswith('.wav'):
                    full_path = os.path.join(input_dir, filename)
                    if os.path.isfile(full_path):
                        wav_files.append(filename)

            total_files = len(wav_files)
            if total_files == 0:
                self.log_signal.emit("错误：输入目录中未找到 WAV 文件。")
                self.finished_signal.emit(True, "输入目录中未找到 WAV 文件。") # Considered success as no work needed
                return

            # Ensure output directory exists (only if specified, otherwise default handled by processor)
            if self.output_dir and not os.path.exists(self.output_dir):
                 try:
                     os.makedirs(self.output_dir)
                     self.log_signal.emit(f"已创建输出目录: {self.output_dir}")
                 except OSError as e:
                     self.log_signal.emit(f"错误：无法创建输出目录 {self.output_dir}: {e}")
                     self.finished_signal.emit(False, f"无法创建输出目录: {e}")
                     return

            success_count = 0
            processed_count = 0
            for i, filename in enumerate(wav_files):
                if not self._is_running:
                    self.log_signal.emit("处理已取消。")
                    self.finished_signal.emit(False, "用户取消")
                    return

                input_file = os.path.join(input_dir, filename)
                self.log_signal.emit(f"\n处理文件: {filename} ({i+1}/{total_files}) ...")
                try:
                    processor = AudioProcessor(input_file)
                    success, message = processor.process_audio(
                        min_silence_len=self.min_silence_len,
                        output_folder=self.output_dir
                    )
                    processed_count += 1
                    if success:
                        success_count += 1
                        self.log_signal.emit(f"成功: {filename} -> {message}")
                    else:
                         self.log_signal.emit(f"失败: {filename} - {message}")

                except Exception as e:
                     processed_count += 1 # Count as processed even if failed
                     self.log_signal.emit(f"处理文件 {filename} 时发生严重错误: {str(e)}")

                progress = int(((i + 1) / total_files) * 100)
                self.progress_signal.emit(progress)

            summary = f"顺序批量处理完成。成功: {success_count}, 失败: {processed_count - success_count} / 总计: {total_files}."
            self.log_signal.emit(f"\n{summary}")
            self.finished_signal.emit(success_count == total_files, summary)

        except FileNotFoundError:
             self.log_signal.emit(f"错误：输入目录 '{self.input_path}' 未找到或无效。")
             self.finished_signal.emit(False, f"输入目录无效")
        except Exception as e:
            self.log_signal.emit(f"处理过程中发生未预料的错误: {str(e)}")
            self.finished_signal.emit(False, f"处理失败: {e}")

    def run_batch_multiprocessing(self):
        """Batch processing using multiprocessing."""
        self.log_signal.emit(f"开始使用 {self.num_cores} 个核心进行多进程批量处理...")
        try:
            input_dir = self.input_path
            files_to_process_paths = []
            for filename in os.listdir(input_dir):
                if filename.lower().endswith('.wav'):
                    full_path = os.path.join(input_dir, filename)
                    if os.path.isfile(full_path):
                        files_to_process_paths.append(full_path)

            total_files = len(files_to_process_paths)
            if total_files == 0:
                self.log_signal.emit("目录中未找到 .wav 文件。")
                self.finished_signal.emit(True, "目录中没有找到 .wav 文件。")
                return

            self.log_signal.emit(f"找到 {total_files} 个 .wav 文件待处理。")

            # Prepare task arguments for each file
            tasks = [(file_path, self.output_dir, self.min_silence_len)
                     for file_path in files_to_process_paths]

            processed_count = 0
            success_count = 0
            error_count = 0
            pool_error_message = ""
            pool = None

            try:
                # Make sure num_cores is at least 1
                actual_cores = max(1, self.num_cores)
                self.log_signal.emit(f"实际使用 Worker 进程数: {actual_cores}")

                # Create the pool
                # Consider spawn context for better stability on some platforms with GUIs
                # mp_context = multiprocessing.get_context('spawn')
                # pool = mp_context.Pool(processes=actual_cores)
                pool = multiprocessing.Pool(processes=actual_cores)

                # Use imap_unordered for potentially faster progress reporting
                results_iterator = pool.imap_unordered(process_file_task, tasks)

                for input_file, success, message in results_iterator:
                    if not self._is_running: # Check for cancellation during processing
                        self.log_signal.emit("处理已取消 (在多进程结果收集中)。")
                        pool.terminate() # Attempt to stop pool
                        pool.join()
                        self.finished_signal.emit(False, "用户取消")
                        return

                    processed_count += 1
                    base_name = os.path.basename(input_file)
                    if success:
                        success_count += 1
                        self.log_signal.emit(f"成功: {base_name} -> {message}")
                    else:
                        error_count += 1
                        self.log_signal.emit(f"失败: {base_name} - {message}")

                    progress = int((processed_count / total_files) * 100)
                    self.progress_signal.emit(progress)

                # Close the pool and wait for workers to finish AFTER the loop
                pool.close()
                pool.join()

            except Exception as pool_exc:
                error_count = total_files # Assume all failed if pool error occurs
                pool_error_message = f"多进程池错误: {pool_exc}"
                self.log_signal.emit(pool_error_message)
            finally:
                # Ensure pool is terminated if it exists and wasn't closed properly
                if pool and not pool._state == multiprocessing.pool.CLOSE:
                    pool.terminate()
                    pool.join()

            # --- Final Report --- #
            self.progress_signal.emit(100)
            summary = f"多进程批量处理完成。成功: {success_count}, 失败: {error_count} / 总计: {total_files}."
            if pool_error_message:
                 summary += f" ({pool_error_message})"
            self.log_signal.emit(summary)
            self.finished_signal.emit(error_count == 0, summary)

        except FileNotFoundError:
            self.log_signal.emit(f"错误：输入目录 '{self.input_path}' 未找到或无效。")
            self.finished_signal.emit(False, "输入目录无效")
        except Exception as e:
            self.log_signal.emit(f"多进程批量处理启动时发生错误: {str(e)}")
            self.finished_signal.emit(False, f"处理失败: {e}")


    def stop(self):
        self._is_running = False
        self.log_signal.emit("收到停止信号...") # Log stop request

# --- Main Application Window --- #
class DeSilencerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        # Detect CPU cores once at startup
        try:
            self.max_cores = os.cpu_count()
            if self.max_cores is None:
                self.max_cores = 1 # Fallback if detection fails
        except NotImplementedError:
            self.max_cores = 1 # Fallback
        self.initUI()

    def initUI(self):
        self.setWindowTitle('音频去静音工具')
        self.setGeometry(100, 100, 600, 500) # 稍微增大高度以容纳模式选择
        self.current_mode = 'single' # 默认模式
        layout = QVBoxLayout(self)

        # 模式选择
        mode_layout = QHBoxLayout()
        self.mode_label = QLabel("处理模式:", self)
        self.single_mode_radio = QRadioButton("单个文件", self)
        self.batch_mode_radio = QRadioButton("批量目录", self)
        self.single_mode_radio.setChecked(True) # 默认选中单个文件

        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.addButton(self.single_mode_radio, 0)
        self.mode_button_group.addButton(self.batch_mode_radio, 1)
        self.mode_button_group.buttonClicked.connect(self.update_mode) # 连接信号

        mode_layout.addWidget(self.mode_label)
        mode_layout.addWidget(self.single_mode_radio)
        mode_layout.addWidget(self.batch_mode_radio)
        mode_layout.addStretch(1)
        layout.addLayout(mode_layout)

        # 输入路径 (标签和按钮会动态变化)
        input_layout = QHBoxLayout()
        self.input_label = QLabel("选择文件:", self) # 初始标签
        self.input_path_edit = QLineEdit(self)
        self.input_browse_btn = QPushButton("浏览...", self)
        self.input_browse_btn.clicked.connect(self.browse_input) # 连接通用浏览函数
        input_layout.addWidget(self.input_label)
        input_layout.addWidget(self.input_path_edit)
        input_layout.addWidget(self.input_browse_btn)
        layout.addLayout(input_layout)

        # 输出目录
        output_layout = QHBoxLayout()
        self.output_label = QLabel("输出目录 (可选, 默认同文件目录):", self)
        self.output_path_edit = QLineEdit(self)
        self.output_browse_btn = QPushButton("浏览...", self)
        self.output_browse_btn.clicked.connect(self.browse_output_folder)
        output_layout.addWidget(self.output_label)
        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(self.output_browse_btn)
        layout.addLayout(output_layout)

        # 参数设置
        params_layout = QHBoxLayout()
        self.silence_len_label = QLabel("最小静音长度 (ms):", self)
        self.silence_len_spinbox = QSpinBox(self)
        self.silence_len_spinbox.setRange(10, 10000)
        self.silence_len_spinbox.setValue(500)
        self.silence_len_spinbox.setSuffix(" ms")

        params_layout.addWidget(self.silence_len_label)
        params_layout.addWidget(self.silence_len_spinbox)
        params_layout.addStretch(1)
        layout.addLayout(params_layout)

        # --- 添加单文件处理选项组 --- #
        self.single_file_group = QGroupBox("单文件处理选项", self)
        self.single_file_group.setVisible(True)  # 初始可见，默认单文件模式
        
        single_file_layout = QVBoxLayout()
        
        # 并行阈值搜索选项
        self.parallel_search_checkbox = QCheckBox("使用并行阈值搜索 (更快找到最佳阈值)", self)
        self.parallel_search_checkbox.setChecked(True)
        
        # 预设阈值点
        thresholds_layout = QHBoxLayout()
        thresholds_label = QLabel("阈值预设点:", self)
        self.thresholds_edit = QLineEdit(self)
        self.thresholds_edit.setText("-90,-80,-70,-60,-50,-40,-30,-20,-10")
        self.thresholds_edit.setToolTip("使用逗号分隔的预设阈值点 (dBFS)")
        thresholds_layout.addWidget(thresholds_label)
        thresholds_layout.addWidget(self.thresholds_edit)
        
        single_file_layout.addWidget(self.parallel_search_checkbox)
        single_file_layout.addLayout(thresholds_layout)
        
        self.single_file_group.setLayout(single_file_layout)
        layout.addWidget(self.single_file_group)
        
        # --- 多进程控制 --- #
        self.mp_group = QGroupBox("多进程设置", self)
        mp_layout = QVBoxLayout()
        
        self.mp_checkbox = QCheckBox("启用多进程加速", self)
        self.mp_checkbox.setChecked(True)  # 默认启用
        
        cores_layout = QHBoxLayout()
        self.mp_cores_label = QLabel(f"使用核心数 (最多 {self.max_cores}):", self)
        self.mp_cores_spinbox = QSpinBox(self)
        self.mp_cores_spinbox.setRange(1, self.max_cores)
        # 默认使用核心数-1，但至少1个
        default_cores = max(1, self.max_cores - 1 if self.max_cores > 1 else 1)
        self.mp_cores_spinbox.setValue(default_cores)
        
        cores_layout.addWidget(self.mp_cores_label)
        cores_layout.addWidget(self.mp_cores_spinbox)
        
        mp_layout.addWidget(self.mp_checkbox)
        mp_layout.addLayout(cores_layout)
        
        self.mp_group.setLayout(mp_layout)
        layout.addWidget(self.mp_group)
        
        # 连接多进程复选框到启用/禁用核心数选择
        self.mp_checkbox.stateChanged.connect(self.toggle_mp_spinbox)
        self.toggle_mp_spinbox()  # 初始化状态
        
        # 显示/隐藏高级选项组
        self.update_mode()  # 初始化界面状态

        # 处理按钮
        self.process_btn = QPushButton("开始处理", self)
        self.process_btn.clicked.connect(self.start_processing)
        layout.addWidget(self.process_btn)

        # 进度条
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        # 详情区域
        self.info_box = QGroupBox("处理详情", self)
        info_layout = QVBoxLayout()
        
        # 使用水平布局展示处理详情
        info_details_layout = QHBoxLayout()
        
        # 左列 - 文件信息
        info_left_layout = QVBoxLayout()
        self.file_size_label = QLabel("文件大小: -", self)
        self.process_time_label = QLabel("处理时间: -", self)
        info_left_layout.addWidget(self.file_size_label)
        info_left_layout.addWidget(self.process_time_label)
        
        # 右列 - 处理信息
        info_right_layout = QVBoxLayout()
        self.threshold_label = QLabel("使用阈值: -", self)
        self.ratio_label = QLabel("大小比例: -", self)
        info_right_layout.addWidget(self.threshold_label)
        info_right_layout.addWidget(self.ratio_label)
        
        # 添加两列到水平布局
        info_details_layout.addLayout(info_left_layout)
        info_details_layout.addLayout(info_right_layout)
        
        # 将水平布局添加到详情区域
        info_layout.addLayout(info_details_layout)
        
        self.info_box.setLayout(info_layout)
        layout.addWidget(self.info_box)

        # 日志/状态显示
        self.log_edit = QTextEdit(self)
        self.log_edit.setReadOnly(True)
        self.log_edit.setFixedHeight(150)
        layout.addWidget(self.log_edit)

        self.setLayout(layout)

        if AudioProcessor is None:
            self.set_inputs_enabled(False)
            self.process_btn.setEnabled(False)
            self.log("错误：AudioProcessor 未能加载。请检查依赖项和路径设置。")
            QMessageBox.critical(self, "启动错误", "无法加载核心处理模块 (AudioProcessor)。请检查控制台输出。")

    def update_mode(self):
        """Updates UI elements based on selected mode."""
        if self.single_mode_radio.isChecked():
            self.current_mode = 'single'
            self.input_label.setText("选择文件 (WAV):")
            self.output_label.setText("输出目录 (可选, 默认同文件目录):")
            # 显示单文件处理选项
            self.single_file_group.setVisible(True)
            # 多进程设置可见，但修改提示文本
            self.mp_group.setTitle("多进程设置 (用于阈值搜索)")
        else: # batch mode
            self.current_mode = 'batch'
            self.input_label.setText("选择目录 (含WAV):")
            self.output_label.setText("输出目录 (可选, 默认同输入目录):")
            # 隐藏单文件处理选项
            self.single_file_group.setVisible(False)
            # 多进程设置可见，恢复原标题
            self.mp_group.setTitle("多进程设置")
            
        self.input_path_edit.clear()
        # Output dir logic remains the same - default determined in Worker

    def toggle_mp_spinbox(self):
        """Enable/disable cores spinbox based on checkbox state."""
        is_checked = self.mp_checkbox.isChecked()
        self.mp_cores_label.setEnabled(is_checked)
        self.mp_cores_spinbox.setEnabled(is_checked)

    def browse_input(self):
        """根据当前模式浏览文件或目录"""
        if self.current_mode == 'single':
            # 只允许选择 WAV 文件
            file_path, _ = QFileDialog.getOpenFileName(self, "选择 WAV 文件", "", "WAV Files (*.wav)")
            if file_path:
                self.input_path_edit.setText(file_path)
        else: # batch mode
            folder_path = QFileDialog.getExistingDirectory(self, "选择输入目录")
            if folder_path:
                self.input_path_edit.setText(folder_path)

    def browse_output_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder_path:
            self.output_path_edit.setText(folder_path)

    def log(self, message):
        self.log_edit.append(message)
        QApplication.processEvents() # 强制更新UI显示日志

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_processing_details(self, details):
        """更新处理详情显示"""
        if 'input_size' in details:
            self.file_size_label.setText(f"文件大小: {details['input_size']/1024:.1f} KB → {details['output_size']/1024:.1f} KB")
            
        if 'processing_time' in details:
            self.process_time_label.setText(f"处理时间: {details['processing_time']:.2f} 秒")
            
        if 'threshold' in details:
            self.threshold_label.setText(f"使用阈值: {details['threshold']} dBFS")
        
        if 'ratio' in details:
            self.ratio_label.setText(f"大小比例: {details['ratio']*100:.1f}% 的原始大小")

    def processing_finished(self, success, message):
        self.process_btn.setText("开始处理")
        self.process_btn.setEnabled(True)
        self.set_inputs_enabled(True)
        if message != "用户取消":
            msg_box = QMessageBox(self)
            if success:
                msg_box.setIcon(QMessageBox.Icon.Information)
                msg_box.setWindowTitle("完成")
            else:
                msg_box.setIcon(QMessageBox.Icon.Warning)
                msg_box.setWindowTitle("处理中止")
            msg_box.setText(message)
            msg_box.exec()
        self.worker = None

    def set_inputs_enabled(self, enabled):
        # 通用控件启用/禁用
        self.single_mode_radio.setEnabled(enabled)
        self.batch_mode_radio.setEnabled(enabled)
        self.input_path_edit.setEnabled(enabled)
        self.input_browse_btn.setEnabled(enabled)
        self.output_path_edit.setEnabled(enabled)
        self.output_browse_btn.setEnabled(enabled)
        self.silence_len_spinbox.setEnabled(enabled)
        
        # 单文件处理选项
        self.single_file_group.setEnabled(enabled)
        self.parallel_search_checkbox.setEnabled(enabled)
        self.thresholds_edit.setEnabled(enabled)
        
        # 多进程控件
        self.mp_checkbox.setEnabled(enabled)
        self.toggle_mp_spinbox()  # 根据复选框状态更新核心数选择器

    def start_processing(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.process_btn.setText("正在停止...")
            self.process_btn.setEnabled(False)
            return

        input_path = self.input_path_edit.text().strip()
        output_dir = self.output_path_edit.text().strip()
        min_silence_len = self.silence_len_spinbox.value()

        # 输入验证
        if not input_path:
             QMessageBox.warning(self, "输入错误", "请选择输入文件或目录。")
             return

        if self.current_mode == 'single':
             if not os.path.isfile(input_path) or not input_path.lower().endswith('.wav'):
                 QMessageBox.warning(self, "输入错误", "请选择一个有效的 WAV 文件。")
                 return
        else: # batch mode
             if not os.path.isdir(input_path):
                 QMessageBox.warning(self, "输入错误", "请选择一个有效的输入目录。")
                 return

        # 输出目录检查与创建逻辑 (移到 Worker 线程中处理更佳，但也可在此预检)
        if output_dir and not os.path.exists(output_dir):
             reply = QMessageBox.question(self, '创建目录?',
                                         f"输出目录 '{output_dir}' 不存在。是否要创建它？",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
             if reply == QMessageBox.StandardButton.Yes:
                 try:
                     os.makedirs(output_dir)
                     self.log(f"已创建输出目录: {output_dir}")
                 except OSError as e:
                     self.log(f"错误：无法创建输出目录 {output_dir}: {e}")
                     QMessageBox.warning(self, "输出错误", f"无法创建输出目录: {e}")
                     return
             else:
                 # 用户不创建，如果是单文件模式，则清空让 Worker 使用源目录；
                 # 如果是批处理模式，也清空让 Worker 使用源目录
                 self.log("操作取消：用户选择不创建输出目录。将使用默认输出位置。")
                 self.output_path_edit.setText("")
                 output_dir = ""
        elif output_dir and not os.path.isdir(output_dir):
            self.log(f"错误：指定的输出路径 '{output_dir}' 不是一个有效的目录。")
            QMessageBox.warning(self, "输出错误", f"指定的输出路径不是一个有效的目录。")
            return


        self.log_edit.clear()
        self.progress_bar.setValue(0)
        
        # 重置处理详情
        self.file_size_label.setText("文件大小: -")
        self.process_time_label.setText("处理时间: -")
        self.threshold_label.setText("使用阈值: -")
        self.ratio_label.setText("大小比例: -")

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
                preset_thresholds = [-90, -80, -70, -60, -50, -40, -30, -20, -10]

        # Create and start the worker thread
        self.worker = Worker(
            mode=self.current_mode,
            input_path=input_path,
            output_dir=output_dir,
            min_silence_len=min_silence_len,
            use_multiprocessing=use_mp,    # 通用多进程开关
            num_cores=num_cores,           # 核心数量
            use_parallel_search=use_parallel_search,  # 单文件并行搜索
            preset_thresholds=preset_thresholds       # 预设阈值点
        )

        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.processing_detail_signal.connect(self.update_processing_details)
        self.worker.start()

if __name__ == '__main__':
    multiprocessing.freeze_support() # Essential for multiprocessing

    app = QApplication(sys.argv)
    window = DeSilencerApp()
    window.show()
    sys.exit(app.exec())