"""
静音删除控制器 - 处理静音删除视图和模型之间的交互
"""
import os
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

from PyQt6.QtCore import QObject, pyqtSignal, QThread
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from app.models.audio_processor import AudioProcessor


# --- 多进程处理函数 ---
def process_file_task(args):
    """多进程处理单个文件的函数"""
    input_file, output_dir, min_silence_len = args
    try:
        # 每个进程需要自己的AudioProcessor实例
        processor = AudioProcessor(input_file)
        success, message = processor.process_audio(min_silence_len, output_folder=output_dir)
        return input_file, success, message
    except Exception as e:
        # 如果处理失败，返回错误详情
        return input_file, False, f"处理错误: {str(e)}"


# --- 单个阈值测试的多进程函数 ---
def test_threshold_task(args):
    """测试单个阈值对音频文件的效果"""
    input_file, threshold, min_silence_len, output_dir = args
    temp_output_path = None
    
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
        # 使用更独特的文件名并加入进程 ID
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        temp_output_path = os.path.join(output_dir, f"{name}_thresh_{threshold}_{unique_id}.temp.wav")
        
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
        # 如果发生错误但已经创建了临时文件，则删除临时文件
        if temp_output_path and os.path.exists(temp_output_path):
            try:
                os.remove(temp_output_path)
            except:
                pass
                
        return {
            "threshold": threshold,
            "status": "error",
            "message": str(e),
            "output_size": 0,
            "ratio": 0,
        }


class Worker(QThread):
    """处理音频的工作线程，避免冻结GUI"""
    
    # 定义信号
    progress_signal = pyqtSignal(int)         # 进度信号 (0-100)
    log_signal = pyqtSignal(str)              # 日志信号
    finished_signal = pyqtSignal(bool, str)   # 完成信号 (success, message)
    processing_detail_signal = pyqtSignal(dict)  # 处理详情信号

    def __init__(self, mode, input_path, output_dir, min_silence_len=1000,
                 use_multiprocessing=False, num_cores=1, use_parallel_search=False,
                 preset_thresholds=None):
        """初始化工作线程"""
        super().__init__()
        
        # 保存参数
        self.mode = mode                       # 'single' 或 'batch'
        self.input_path = input_path           # 输入文件或目录路径
        self.output_dir = output_dir           # 输出目录
        self.min_silence_len = min_silence_len # 最小静音长度(毫秒)
        
        # 多进程设置
        self.use_multiprocessing = use_multiprocessing
        self.num_cores = max(1, min(num_cores, multiprocessing.cpu_count()))
        
        # 并行搜索设置
        self.use_parallel_search = use_parallel_search
        self.preset_thresholds = preset_thresholds or [-90, -80, -70, -60, -50, -40, -30, -20, -10]
        
        # 运行状态
        self.running = True
    
    def process_single_file(self, input_file):
        """处理单个文件的逻辑"""
        self.log_signal.emit(f"开始处理文件: {input_file}")
        
        # 确保输出目录存在
        self._ensure_output_dir()
        
        # 根据是否启用并行搜索选择处理方法
        if self.use_parallel_search:
            return self.process_single_file_parallel(input_file, self.output_dir)
        else:
            return self.process_single_file_standard(input_file, self.output_dir)
    
    def _ensure_output_dir(self):
        """确保输出目录存在"""
        if self.output_dir:
            try:
                if not os.path.exists(self.output_dir):
                    os.makedirs(self.output_dir)
                    self.log_signal.emit(f"已创建输出目录: {self.output_dir}")
                elif not os.path.isdir(self.output_dir):
                    self.log_signal.emit(f"错误：输出路径 '{self.output_dir}' 不是目录")
                    raise ValueError(f"输出路径不是目录: {self.output_dir}")
            except Exception as e:
                self.log_signal.emit(f"创建输出目录时出错: {e}")
                raise
    
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
                tasks.append((input_file, threshold, self.min_silence_len, output_dir))
            
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
                
                final_size = os.path.getsize(output_path)
                actual_ratio = final_size / input_size
                actual_reduction = ((input_size - final_size) / input_size * 100)
                actual_retention = actual_ratio * 100
                
                # 处理完成，计算时间
                elapsed_time = time.time() - start_time
                
                # 更新处理详情
                self.processing_detail_signal.emit({
                    "process_time": f"{elapsed_time:.2f} 秒",
                    "threshold": f"{best_threshold:.1f} dBFS",
                    "ratio": f"{actual_retention:.1f}%",
                })
                
                # 发送完成信号 (100%)
                self.progress_signal.emit(100)
                
                # 构建结果消息
                result_message = (
                    f"{output_path} (阈值: {best_threshold:.1f} dBFS, "
                    f"大小: {input_size} -> {final_size} bytes, "
                    f"减少: {actual_reduction:.2f}%, "
                    f"保留: {actual_retention:.2f}%)"
                )
                
                # 清理临时文件
                self._clean_temp_files(temp_files)
                
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
        """顺序批处理文件"""
        start_time = time.time()
        
        try:
            # 确保输出目录存在
            self._ensure_output_dir()
            
            # 列出所有音频文件
            audio_files = []
            for root, _, files in os.walk(self.input_path):
                for file in files:
                    if file.lower().endswith(('.wav', '.mp3', '.ogg', '.flac', '.aac', '.m4a')):
                        audio_files.append(os.path.join(root, file))
            
            if not audio_files:
                self.log_signal.emit(f"未在 {self.input_path} 中找到音频文件")
                self.finished_signal.emit(False, "未找到音频文件")
                return
            
            self.log_signal.emit(f"找到 {len(audio_files)} 个音频文件")
            
            # 顺序处理每个文件
            success_count = 0
            fail_count = 0
            
            for i, file in enumerate(audio_files):
                if not self.running:
                    self.log_signal.emit("处理已取消")
                    break
                
                # 更新总进度
                progress = int((i / len(audio_files)) * 100)
                self.progress_signal.emit(progress)
                
                # 处理单个文件
                self.log_signal.emit(f"[{i+1}/{len(audio_files)}] 处理文件: {os.path.basename(file)}")
                try:
                    success, msg = self.process_single_file_standard(file, self.output_dir)
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    self.log_signal.emit(f"处理文件 {file} 时出错: {e}")
                    fail_count += 1
            
            # 处理完成
            elapsed_time = time.time() - start_time
            
            if not self.running:
                self.finished_signal.emit(False, "处理已取消")
            else:
                final_msg = f"处理完成: 成功 {success_count}, 失败 {fail_count}, 总计 {len(audio_files)}, 耗时 {elapsed_time:.2f} 秒"
                self.log_signal.emit(final_msg)
                self.finished_signal.emit(success_count > 0, final_msg)
                self.progress_signal.emit(100)
            
        except Exception as e:
            self.log_signal.emit(f"批处理时发生错误: {e}")
            self.finished_signal.emit(False, f"批处理错误: {e}")
    
    def run_batch_multiprocessing(self):
        """使用多进程批处理文件"""
        start_time = time.time()
        
        try:
            # 确保输出目录存在
            self._ensure_output_dir()
            
            # 列出所有音频文件
            audio_files = []
            for root, _, files in os.walk(self.input_path):
                for file in files:
                    if file.lower().endswith(('.wav', '.mp3', '.ogg', '.flac', '.aac', '.m4a')):
                        audio_files.append(os.path.join(root, file))
            
            if not audio_files:
                self.log_signal.emit(f"未在 {self.input_path} 中找到音频文件")
                self.finished_signal.emit(False, "未找到音频文件")
                return
            
            total_files = len(audio_files)
            self.log_signal.emit(f"找到 {total_files} 个音频文件，使用 {self.num_cores} 核心并行处理")
            
            # 准备任务列表
            tasks = [(file, self.output_dir, self.min_silence_len) for file in audio_files]
            
            # 用于统计结果
            success_count = 0
            fail_count = 0
            processed_count = 0
            
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
                    processed_count += 1
                    file_name = os.path.basename(file_path)
                    
                    try:
                        file, success, message = future.result()
                        
                        if success:
                            success_count += 1
                            self.log_signal.emit(f"[{processed_count}/{total_files}] ✓ {file_name} - 成功")
                        else:
                            fail_count += 1
                            self.log_signal.emit(f"[{processed_count}/{total_files}] ✗ {file_name} - 失败: {message}")
                        
                        # 更新进度
                        progress = int((processed_count / total_files) * 100)
                        self.progress_signal.emit(progress)
                        
                    except Exception as e:
                        fail_count += 1
                        self.log_signal.emit(f"[{processed_count}/{total_files}] ✗ {file_name} - 错误: {e}")
                        
                        # 更新进度
                        progress = int((processed_count / total_files) * 100)
                        self.progress_signal.emit(progress)
            
            # 处理完成
            elapsed_time = time.time() - start_time
            
            if not self.running:
                self.finished_signal.emit(False, "处理已取消")
            else:
                final_msg = f"处理完成: 成功 {success_count}, 失败 {fail_count}, 总计 {total_files}, 耗时 {elapsed_time:.2f} 秒"
                self.log_signal.emit(final_msg)
                self.finished_signal.emit(success_count > 0, final_msg)
                self.progress_signal.emit(100)
                
        except Exception as e:
            self.log_signal.emit(f"多进程批处理时发生错误: {e}")
            self.finished_signal.emit(False, f"批处理错误: {e}")
    
    def _clean_temp_files(self, file_list):
        """清理临时文件"""
        if not file_list:
            return
            
        self.log_signal.emit(f"开始清理 {len(file_list)} 个临时文件...")
        cleaned_count = 0
        
        for temp_file in file_list:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    cleaned_count += 1
            except Exception as e:
                self.log_signal.emit(f"删除临时文件失败: {e}")
        
        self.log_signal.emit(f"已清理 {cleaned_count} 个临时文件")
    
    def stop(self):
        """停止处理"""
        self.running = False
        self.log_signal.emit("正在停止处理...")
        # 线程会自行检查running标志并终止


class DesilencerController(QObject):
    """静音删除控制器 - 连接视图和模型"""
    
    def __init__(self, view):
        """初始化控制器"""
        super().__init__()
        self.view = view
        self.worker = None
        self.current_mode = "single"  # 默认为单文件模式
        
        # 检测 CPU 核心数
        try:
            self.max_cores = multiprocessing.cpu_count()
            if not self.max_cores:
                self.max_cores = 4  # 默认值
        except:
            self.max_cores = 4  # 默认值
        
        # 设置最大核心数
        self.view.mp_cores_spinbox.setRange(1, self.max_cores)
        self.view.mp_cores_spinbox.setValue(min(4, self.max_cores))  # 默认使用 4 核心或最大值
        
        # 连接视图信号
        self.connect_signals()
    
    def connect_signals(self):
        """连接视图信号"""
        # 浏览按钮
        self.view.browse_input_signal.connect(self.browse_input)
        self.view.browse_output_signal.connect(self.browse_output_folder)
        
        # 开始处理按钮
        self.view.start_processing_signal.connect(self.start_processing)
    
    def mode_changed(self, is_single_mode):
        """处理模式改变"""
        self.current_mode = "single" if is_single_mode else "batch"
        
        # 更新并行阈值搜索选项可见性
        self.view.parallel_search_checkbox.setEnabled(is_single_mode)
        self.view.thresholds_edit.setEnabled(is_single_mode)
    
    def browse_input(self):
        """浏览输入文件或目录"""
        if self.current_mode == "single":
            # 单文件模式，选择音频文件
            file_path, _ = QFileDialog.getOpenFileName(
                self.view,
                "选择音频文件",
                "",
                "音频文件 (*.wav *.mp3 *.ogg *.flac *.aac *.m4a)"
            )
            if file_path:
                self.view.input_path_edit.setText(file_path)
        else:
            # 批处理模式，选择目录
            dir_path = QFileDialog.getExistingDirectory(
                self.view,
                "选择包含音频文件的目录",
                ""
            )
            if dir_path:
                self.view.input_path_edit.setText(dir_path)
    
    def browse_output_folder(self):
        """浏览输出目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self.view,
            "选择输出目录",
            ""
        )
        if dir_path:
            self.view.output_path_edit.setText(dir_path)
    
    def start_processing(self):
        """开始或停止处理"""
        # 如果正在处理，停止处理
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            return
        
        # 获取处理参数
        params = self.view.get_processing_params()
        input_path = params["input_path"]
        output_path = params["output_path"]
        min_silence_len = params["min_silence_len"]
        
        # 检查输入路径
        if not input_path:
            self.view.log("错误：请选择输入文件或目录")
            return
        
        # 检查模式和路径类型匹配
        if self.current_mode == "single" and not os.path.isfile(input_path):
            self.view.log("错误：单文件模式下输入路径必须是文件")
            return
        elif self.current_mode == "batch" and not os.path.isdir(input_path):
            self.view.log("错误：批处理模式下输入路径必须是目录")
            return
        
        # 检查输出目录
        if output_path and not os.path.exists(output_path):
            reply = QMessageBox.question(
                self.view,
                '创建目录?',
                f"输出目录 '{output_path}' 不存在。是否要创建它？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    os.makedirs(output_path)
                    self.view.log(f"已创建输出目录: {output_path}")
                except OSError as e:
                    self.view.log(f"错误：无法创建输出目录 {output_path}: {e}")
                    return
            else:
                self.view.log("操作取消：用户选择不创建输出目录。将使用默认输出位置。")
                output_path = ""
        elif output_path and not os.path.isdir(output_path):
            self.view.log(f"错误：指定的输出路径 '{output_path}' 不是一个有效的目录。")
            return
        
        # 准备处理
        self.view.log_edit.clear()
        self.view.progress_bar.setValue(0)
        
        # 重置处理详情
        self.view.file_size_label.setText("文件大小: -")
        self.view.process_time_label.setText("处理时间: -")
        self.view.threshold_label.setText("使用阈值: -")
        self.view.ratio_label.setText("大小比例: -")
        
        # 禁用输入控件
        self.view.set_inputs_enabled(False)
        self.view.process_btn.setText("停止处理")
        self.view.process_btn.setEnabled(True)
        
        # 解析阈值预设点
        preset_thresholds = []
        if self.current_mode == "single":
            try:
                threshold_text = params["thresholds"].strip()
                if threshold_text:
                    preset_thresholds = [float(t.strip()) for t in threshold_text.split(',')]
            except ValueError:
                self.view.log("警告：阈值预设点格式无效，将使用默认值")
                preset_thresholds = [-90, -80, -70, -60, -50, -40, -30, -20, -10]
        
        # 创建并启动工作线程
        self.worker = Worker(
            mode=self.current_mode,
            input_path=input_path,
            output_dir=output_path,
            min_silence_len=min_silence_len,
            use_multiprocessing=params["use_multiprocessing"],
            num_cores=params["num_cores"],
            use_parallel_search=params["use_parallel_search"],
            preset_thresholds=preset_thresholds
        )
        
        # 连接工作线程信号
        self.worker.log_signal.connect(self.view.log)
        self.worker.progress_signal.connect(self.view.update_progress)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.processing_detail_signal.connect(self.view.update_processing_details)
        
        # 启动工作线程
        self.worker.start()
    
    def processing_finished(self, success, message):
        """处理完成后的回调"""
        # 更新视图状态
        self.view.processing_finished(success, message)
        
        # 显示结果消息
        if success:
            QMessageBox.information(self.view, "处理完成", "音频处理成功完成!")
        else:
            QMessageBox.warning(self.view, "处理错误", f"处理时出错: {message}")
        
        # 清理工作线程
        self.worker = None
