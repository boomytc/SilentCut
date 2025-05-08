"""
静音删除标签页 - 用于删除音频中的静音部分
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QSpinBox, QProgressBar,
    QRadioButton, QButtonGroup, QCheckBox, QGroupBox, QGridLayout,
    QFormLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal


class DesilencerTabView(QWidget):
    """静音删除标签页视图"""
    
    # 定义视图发出的信号
    browse_input_signal = pyqtSignal()
    browse_output_signal = pyqtSignal()
    start_processing_signal = pyqtSignal()
    
    def __init__(self):
        """初始化静音删除标签页视图"""
        super().__init__()
        self.controller = None  # 控制器引用将由MainWindow设置
        self.initUI()
    
    def initUI(self):
        """初始化用户界面"""
        # 主布局
        main_layout = QVBoxLayout()
        
        # === 模式选择区域 ===
        mode_group = QGroupBox("处理模式")
        mode_layout = QHBoxLayout()
        
        # 单文件模式
        self.single_radio = QRadioButton("单文件模式")
        self.single_radio.setChecked(True)  # 默认选中
        self.single_radio.toggled.connect(self._update_mode)
        
        # 批处理模式
        self.batch_radio = QRadioButton("批处理模式")
        self.batch_radio.toggled.connect(self._update_mode)
        
        # 添加到布局
        mode_layout.addWidget(self.single_radio)
        mode_layout.addWidget(self.batch_radio)
        mode_layout.addStretch()
        
        # 设置模式组
        mode_group.setLayout(mode_layout)
        main_layout.addWidget(mode_group)
        
        # === 输入/输出选择区域 ===
        io_group = QGroupBox("输入/输出")
        io_layout = QVBoxLayout()
        
        # 输入路径
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("输入:"))
        self.input_path_edit = QLineEdit()
        self.input_path_edit.setPlaceholderText("选择音频文件或文件夹...")
        input_layout.addWidget(self.input_path_edit)
        self.browse_input_btn = QPushButton("浏览...")
        self.browse_input_btn.clicked.connect(self.browse_input_signal.emit)
        input_layout.addWidget(self.browse_input_btn)
        
        # 输出路径
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("输出:"))
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("选择输出文件夹（可选）...")
        output_layout.addWidget(self.output_path_edit)
        self.browse_output_btn = QPushButton("浏览...")
        self.browse_output_btn.clicked.connect(self.browse_output_signal.emit)
        output_layout.addWidget(self.browse_output_btn)
        
        # 添加到布局
        io_layout.addLayout(input_layout)
        io_layout.addLayout(output_layout)
        io_group.setLayout(io_layout)
        main_layout.addWidget(io_group)
        
        # === 处理参数区域 ===
        params_group = QGroupBox("处理参数")
        # 使用FormLayout让标签和控件更有条理地排列
        params_layout = QFormLayout()
        
        # 最小静音长度
        self.silence_len_spinbox = QSpinBox()
        self.silence_len_spinbox.setRange(100, 10000)
        self.silence_len_spinbox.setValue(1000)
        self.silence_len_spinbox.setSingleStep(100)
        # 添加到FormLayout
        params_layout.addRow("最小静音长度(毫秒):", self.silence_len_spinbox)
        
        # 多进程设置（批处理模式用）
        mp_widget = QWidget()
        mp_layout = QHBoxLayout(mp_widget)
        mp_layout.setContentsMargins(0, 0, 0, 0)
        
        self.mp_checkbox = QCheckBox("启用多进程处理")
        self.mp_checkbox.setChecked(True)
        self.mp_cores_spinbox = QSpinBox()
        # 使用系统默认核心数（控制器会设置最大值）
        self.mp_cores_spinbox.setRange(1, 8)
        self.mp_cores_spinbox.setValue(4)
        self.mp_checkbox.toggled.connect(self._toggle_mp_spinbox)
        
        mp_layout.addWidget(self.mp_checkbox)
        mp_layout.addWidget(QLabel("使用核心数:"))
        mp_layout.addWidget(self.mp_cores_spinbox)
        mp_layout.addStretch()
        params_layout.addRow("", mp_widget)
        
        # 单文件并行搜索选项
        self.parallel_search_checkbox = QCheckBox("启用并行阈值搜索（单文件模式）")
        self.parallel_search_checkbox.setChecked(True)
        params_layout.addRow("", self.parallel_search_checkbox)
        
        # 自定义阈值预设点
        self.thresholds_edit = QLineEdit()
        self.thresholds_edit.setPlaceholderText("用逗号分隔，例如: -90,-80,-70,-60,-50,-40,-30,-20")
        self.thresholds_edit.setText("-90,-80,-70,-60,-50,-40,-30,-20")
        # 设置最小宽度和尺寸策略
        self.thresholds_edit.setMinimumWidth(400)
        # 设置SizePolicy让控件能够根据窗口尺寸自适应扩展
        self.thresholds_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        params_layout.addRow("阈值预设点:", self.thresholds_edit)
        params_group.setLayout(params_layout)
        main_layout.addWidget(params_group)
        
        # === 处理详情区域 ===
        details_group = QGroupBox("处理详情")
        details_layout = QGridLayout()
        
        # 文件大小信息
        self.file_size_label = QLabel("文件大小: -")
        details_layout.addWidget(self.file_size_label, 0, 0)
        
        # 处理时间
        self.process_time_label = QLabel("处理时间: -")
        details_layout.addWidget(self.process_time_label, 0, 1)
        
        # 阈值
        self.threshold_label = QLabel("使用阈值: -")
        details_layout.addWidget(self.threshold_label, 1, 0)
        
        # 大小比例
        self.ratio_label = QLabel("大小比例: -")
        details_layout.addWidget(self.ratio_label, 1, 1)
        
        details_group.setLayout(details_layout)
        main_layout.addWidget(details_group)
        
        # === 日志和进度区域 ===
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()
        
        # 日志文本框
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        log_layout.addWidget(self.progress_bar)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # === 操作按钮 ===
        buttons_layout = QHBoxLayout()
        
        # 处理按钮
        self.process_btn = QPushButton("开始处理")
        self.process_btn.clicked.connect(self.start_processing_signal.emit)
        buttons_layout.addWidget(self.process_btn)
        
        main_layout.addLayout(buttons_layout)
        
        # 设置布局
        self.setLayout(main_layout)
        
        # 初始更新UI状态
        self._update_mode()
        self._toggle_mp_spinbox()
    
    def _update_mode(self):
        """根据所选模式更新UI元素状态"""
        # 发送模式变更信号到控制器
        if self.controller:
            self.controller.mode_changed(self.single_radio.isChecked())
    
    def _toggle_mp_spinbox(self):
        """根据多进程复选框状态启用/禁用核心数选择器"""
        self.mp_cores_spinbox.setEnabled(self.mp_checkbox.isChecked())
    
    def set_inputs_enabled(self, enabled):
        """启用或禁用输入控件"""
        # 模式选择
        self.single_radio.setEnabled(enabled)
        self.batch_radio.setEnabled(enabled)
        
        # 路径选择
        self.input_path_edit.setEnabled(enabled)
        self.output_path_edit.setEnabled(enabled)
        self.browse_input_btn.setEnabled(enabled)
        self.browse_output_btn.setEnabled(enabled)
        
        # 处理参数
        self.silence_len_spinbox.setEnabled(enabled)
        self.mp_checkbox.setEnabled(enabled)
        self.mp_cores_spinbox.setEnabled(enabled and self.mp_checkbox.isChecked())
        self.parallel_search_checkbox.setEnabled(enabled)
        self.thresholds_edit.setEnabled(enabled)
    
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
    
    def log(self, message):
        """添加日志消息"""
        self.log_edit.append(message)
        # 自动滚动到底部
        self.log_edit.verticalScrollBar().setValue(
            self.log_edit.verticalScrollBar().maximum()
        )
    
    def update_processing_details(self, details):
        """更新处理详情区域"""
        if 'file_size' in details:
            self.file_size_label.setText(f"文件大小: {details['file_size']}")
        
        if 'process_time' in details:
            self.process_time_label.setText(f"处理时间: {details['process_time']}")
        
        if 'threshold' in details:
            self.threshold_label.setText(f"使用阈值: {details['threshold']}")
        
        if 'ratio' in details:
            self.ratio_label.setText(f"大小比例: {details['ratio']}")
    
    def get_processing_params(self):
        """获取处理参数"""
        return {
            'input_path': self.input_path_edit.text(),
            'output_path': self.output_path_edit.text(),
            'min_silence_len': self.silence_len_spinbox.value(),
            'use_multiprocessing': self.mp_checkbox.isChecked(),
            'num_cores': self.mp_cores_spinbox.value(),
            'use_parallel_search': self.parallel_search_checkbox.isChecked(),
            'thresholds': self.thresholds_edit.text()
        }
    
    def processing_finished(self, success, message):
        """处理完成后更新UI"""
        # 更新处理按钮文本
        self.process_btn.setText("开始处理")
        # 恢复输入控件
        self.set_inputs_enabled(True)
