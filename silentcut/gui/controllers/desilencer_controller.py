"""
静音切割控制器模块
"""
import os
import time
from PyQt6.QtWidgets import (
    QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, 
    QFileDialog, QTextEdit, QSpinBox, QDoubleSpinBox, QProgressBar, QMessageBox,
    QRadioButton, QGroupBox
)
from PyQt6.QtCore import QThread, pyqtSignal

from silentcut.audio.processor import AudioProcessor
from silentcut.utils.logger import get_logger
from silentcut.utils.file_utils import get_audio_files_in_directory

logger = get_logger("gui.desilencer_controller")


class Worker(QThread):
    """处理音频的工作线程，避免冻结 GUI"""
    progress_signal = pyqtSignal(int) # 进度信号 (0-100 for batch, 0/100 for single)
    log_signal = pyqtSignal(str)      # 日志信号
    finished_signal = pyqtSignal(bool, str) # 完成信号 (success, message)
    processing_detail_signal = pyqtSignal(dict) # 音频处理详细信息信号
    
    def __init__(self, mode, input_path, output_dir,
                 vad_threshold=0.5, vad_min_silence_ms=1000, vad_max_duration_ms=5000):
        """初始化工作线程"""
        super().__init__()
        self.mode = mode  # 'single' 或 'batch'
        self.input_path = input_path
        self.output_dir = output_dir
        self.running = True  # 控制线程运行
        self.vad_threshold = vad_threshold
        self.vad_min_silence_ms = vad_min_silence_ms
        self.vad_max_duration_ms = vad_max_duration_ms
    
    def process_single_file(self, input_file):
        """处理单个文件的逻辑"""
        # 确保输出目录存在
        self._ensure_output_dir()
        
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
    

    
    def process_single_file_standard(self, input_file, output_dir):
        """使用 VAD 方式处理单个文件"""
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
                output_folder=output_dir,
                vad_threshold=self.vad_threshold,
                vad_min_silence_ms=self.vad_min_silence_ms,
                vad_max_duration_ms=self.vad_max_duration_ms,
            )
            
            # 处理完成，计算时间
            elapsed_time = time.time() - start_time
            
            # 解析处理结果消息以获取更多详情
            ratio = None
            
            if success:
                try:
                    # 解析"减少: XX%, 保留: XX%"格式的字符串
                    if "减少:" in message and "保留:" in message:
                        ratio_str = message.split("保留:")[1].split("%")[0].strip()
                        ratio = f"{float(ratio_str):.1f}%"
                except:
                    pass
            
            # 发送完整的处理详情
            self.processing_detail_signal.emit({
                "process_time": f"{elapsed_time:.2f} 秒",
                "threshold": "VAD",
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
                    self.run_batch_sequential()
                else:
                    self.log_signal.emit(f"错误: 输入路径不是目录: {self.input_path}")
                    self.finished_signal.emit(False, f"输入路径不是目录: {self.input_path}")
        except Exception as e:
            self.log_signal.emit(f"处理时发生意外错误: {e}")
            self.finished_signal.emit(False, f"处理错误: {e}")
    
    def run_batch_sequential(self):
        """顺序批处理"""
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
        
        # 初始化UI
        self._init_ui()
        
        logger.info("静音切割控制器初始化完成")
    
    def _init_ui(self):
        """初始化用户界面"""
        # 获取标签页布局
        layout = self.tab.layout()
        
        # 创建模式选择区域
        mode_group = QGroupBox("处理模式")
        mode_grid = QGridLayout()
        self.single_radio = QRadioButton("单文件处理")
        self.single_radio.setChecked(True)
        self.single_radio.toggled.connect(self.update_mode)
        self.batch_radio = QRadioButton("批量处理")
        self.batch_radio.toggled.connect(self.update_mode)
        mode_grid.addWidget(self.single_radio, 0, 0)
        mode_grid.addWidget(self.batch_radio, 0, 1)
        mode_group.setLayout(mode_grid)
        layout.addWidget(mode_group)
        
        # 创建输入区域
        input_group = QGroupBox("输入")
        input_grid = QGridLayout()
        self.input_path_label = QLabel("输入文件:")
        self.input_path_edit = QLineEdit()
        self.input_path_edit.setReadOnly(True)
        self.browse_input_btn = QPushButton("浏览...")
        self.browse_input_btn.clicked.connect(self.browse_input)
        input_grid.addWidget(self.input_path_label, 0, 0)
        input_grid.addWidget(self.input_path_edit, 0, 1)
        input_grid.addWidget(self.browse_input_btn, 0, 2)
        self.output_path_label = QLabel("输出目录:")
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(True)
        self.browse_output_btn = QPushButton("浏览...")
        self.browse_output_btn.clicked.connect(self.browse_output_folder)
        input_grid.addWidget(self.output_path_label, 1, 0)
        input_grid.addWidget(self.output_path_edit, 1, 1)
        input_grid.addWidget(self.browse_output_btn, 1, 2)
        input_grid.setColumnStretch(1, 1)
        input_group.setLayout(input_grid)
        layout.addWidget(input_group)
        
        # 创建参数区域
        params_group = QGroupBox("VAD 参数")
        params_grid = QGridLayout()
        self.vad_threshold_label = QLabel("VAD 阈值:")
        self.vad_threshold_spinbox = QDoubleSpinBox()
        self.vad_threshold_spinbox.setRange(0.0, 1.0)
        self.vad_threshold_spinbox.setSingleStep(0.05)
        self.vad_threshold_spinbox.setValue(0.5)
        params_grid.addWidget(self.vad_threshold_label, 0, 0)
        params_grid.addWidget(self.vad_threshold_spinbox, 0, 1)
        self.vad_maxdur_label = QLabel("VAD 最大段时长(ms):")
        self.vad_maxdur_spinbox = QSpinBox()
        self.vad_maxdur_spinbox.setRange(1000, 30000)
        self.vad_maxdur_spinbox.setValue(5000)
        params_grid.addWidget(self.vad_maxdur_label, 1, 0)
        params_grid.addWidget(self.vad_maxdur_spinbox, 1, 1)
        self.vad_minsil_label = QLabel("VAD 最小静音(ms):")
        self.vad_minsil_spinbox = QSpinBox()
        self.vad_minsil_spinbox.setRange(0, 5000)
        self.vad_minsil_spinbox.setValue(1000)
        params_grid.addWidget(self.vad_minsil_label, 2, 0)
        params_grid.addWidget(self.vad_minsil_spinbox, 2, 1)
        params_grid.setColumnStretch(2, 1)
        params_group.setLayout(params_grid)
        layout.addWidget(params_group)
        
        # 创建日志区域
        log_group = QGroupBox("处理日志")
        log_grid = QGridLayout()
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        log_grid.addWidget(self.log_edit, 0, 0, 1, 4)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        log_grid.addWidget(self.progress_bar, 1, 0, 1, 4)
        self.file_size_label = QLabel("文件大小: -")
        self.process_time_label = QLabel("处理时间: -")
        self.threshold_label = QLabel("使用阈值: -")
        self.ratio_label = QLabel("大小比例: -")
        log_grid.addWidget(self.file_size_label, 2, 0)
        log_grid.addWidget(self.process_time_label, 2, 1)
        log_grid.addWidget(self.threshold_label, 2, 2)
        log_grid.addWidget(self.ratio_label, 2, 3)
        for i in range(4):
            log_grid.setColumnStretch(i, 1)
        log_group.setLayout(log_grid)
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
        else:
            self.current_mode = 'batch'
            self.input_path_label.setText("输入目录:")
    

    
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
        
        # VAD 参数设置
        self.vad_threshold_spinbox.setEnabled(enabled)
        self.vad_maxdur_spinbox.setEnabled(enabled)
        self.vad_minsil_spinbox.setEnabled(enabled)
    
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
        
        # 获取 VAD 参数
        vad_threshold = self.vad_threshold_spinbox.value()
        vad_max_duration_ms = self.vad_maxdur_spinbox.value()
        vad_min_silence_ms = self.vad_minsil_spinbox.value()
        
        # 创建并启动工作线程
        self.worker = Worker(
            mode=self.current_mode,
            input_path=input_path,
            output_dir=output_dir,
            vad_threshold=vad_threshold,
            vad_min_silence_ms=vad_min_silence_ms,
            vad_max_duration_ms=vad_max_duration_ms
        )
        
        # 连接信号
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.processing_detail_signal.connect(self.update_processing_details)
        
        # 启动线程
        self.worker.start()
