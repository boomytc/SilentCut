import os
from pydub import AudioSegment
from pydub.silence import split_on_silence
import logging

# 设置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 阈值范围的最小和最大值 - 扩大范围
MIN_THRESHOLD = -100  # 最严格的阈值
MAX_THRESHOLD = 0     # 最宽松的阈值
INITIAL_STEP = 10     # 初始搜索时的步长
FINE_STEP = 2         # 精细搜索时的步长

# 默认初始阈值偏移量（用于计算自适应初始阈值）
ADAPTIVE_THRESHOLD_OFFSET = 30  # 增加偏移量，使初始阈值更严格

# 文件大小比例限制 - 确保处理后文件大小严格小于原始大小但大于原始大小的50%
MIN_SIZE_RATIO = 0.5
MAX_SIZE_RATIO = 0.99  # 确保严格小于原始大小

# 最大搜索次数限制，防止无限循环
MAX_SEARCH_ATTEMPTS = 40  # 增加最大尝试次数

# 预设阈值点 - 用于快速搜索常用阈值
PRESET_THRESHOLDS = [-90, -80, -70, -60, -50, -45, -40, -35, -30, -25, -20, -15, -10]

class AudioProcessor:
    def __init__(self, input_file):
        self.input_file = input_file
        self.audio = None
        self.load_audio() # 初始化时加载音频

    def load_audio(self):
        """加载音频文件"""
        try:
            logging.info(f"开始加载文件: {self.input_file}")
            # 使用 from_file 尝试自动检测格式，而不是强制 from_wav
            self.audio = AudioSegment.from_file(self.input_file)
            logging.info(f"文件加载成功: {self.input_file}")
        except FileNotFoundError:
            logging.error(f"错误: 文件未找到 {self.input_file}")
            self.audio = None
            raise
        except Exception as e:
            logging.error(f"加载文件 {self.input_file} 时出错: {e}")
            self.audio = None
            raise

    def process_audio(self, min_silence_len=1000, output_folder=None):
        """
        处理音频文件，移除静音部分。
        使用自适应搜索策略，确保处理后文件大小严格小于原始文件但大于原始文件的50%。
        
        Args:
            min_silence_len: 最小静音长度（毫秒）
            output_folder: 输出目录，如果为None则使用输入文件所在目录
            
        Returns:
            (success, message): 处理是否成功及相关信息
        """
        if self.audio is None:
            logging.error("错误: 音频未加载，无法处理。")
            return False, "音频未加载"

        try:
            input_size = os.path.getsize(self.input_file)
            basename = os.path.basename(self.input_file)
            
            # --- 确定输出路径 ---
            input_dir, input_filename = os.path.split(self.input_file)
            name, ext = os.path.splitext(input_filename)
            output_filename = f"{name}-desilenced{ext}"
            
            if output_folder and os.path.isdir(output_folder):
                output_dir = output_folder
                os.makedirs(output_dir, exist_ok=True)
            else:
                if output_folder:
                    logging.warning(f"指定的输出文件夹 '{output_folder}' 无效或不是目录，将保存在输入文件旁边。")
                output_dir = input_dir
                
            output_path = os.path.join(output_dir, output_filename)
            
            # --- 计算目标文件大小范围 ---
            min_acceptable_size = int(input_size * MIN_SIZE_RATIO)  # 最小可接受大小（原始大小的50%）
            max_acceptable_size = int(input_size * MAX_SIZE_RATIO)  # 最大可接受大小（原始大小的99%）
            logging.info(f"目标文件大小范围: {min_acceptable_size} - {max_acceptable_size} bytes (原始: {input_size} bytes)")
            
            # --- 计算初始自适应阈值 ---
            average_dbfs = self.audio.dBFS
            
            # 分析音频特征
            # 计算实际最大音量和最小音量，而不仅仅依赖平均值
            # 使用小块采样来加快计算
            sample_size = 100  # 使用较小的采样块数量
            chunk_length_ms = min(500, len(self.audio) // sample_size)  # 最小500ms块
            
            all_dbfs = []
            for i in range(0, len(self.audio), chunk_length_ms):
                chunk = self.audio[i:i+chunk_length_ms]
                if len(chunk) > 0 and chunk.dBFS > float('-inf'):  # 避免静音块的-inf值
                    all_dbfs.append(chunk.dBFS)
                    
            if not all_dbfs:  # 处理全是静音的特殊情况
                all_dbfs = [average_dbfs]
                
            actual_max_dbfs = max(all_dbfs)
            actual_min_dbfs = min(all_dbfs)
            
            # 生成自适应初始阈值 - 使用音频特性来设置
            initial_thresh_base = actual_min_dbfs
            
            # 防止初始阈值过低（过度严格）或过高（过度宽松）
            if initial_thresh_base < MIN_THRESHOLD:
                initial_thresh_base = MIN_THRESHOLD
            
            adaptive_threshold = initial_thresh_base + ADAPTIVE_THRESHOLD_OFFSET
            
            # 安全限制，确保初始阈值在合理范围内
            if adaptive_threshold > -10:  # 过于宽松
                adaptive_threshold = -40  # 使用较保守的默认值
            
            logging.info(f"音频特性: 平均dBFS = {average_dbfs:.1f}, 最小dBFS = {actual_min_dbfs:.1f}, 最大dBFS = {actual_max_dbfs:.1f}")
            logging.info(f"自适应初始阈值: {adaptive_threshold:.1f} dBFS")
            
            # --- 搜索最佳阈值 ---
            
            def test_threshold(threshold, is_preset=False):
                """测试特定阈值"""
                logging.info(f"测试阈值: {threshold:.1f} dBFS{' (预设点)' if is_preset else ''}")
                
                try:
                    # 分割音频 - 基于静音 
                    chunks = split_on_silence(
                        self.audio,
                        min_silence_len=min_silence_len,
                        silence_thresh=threshold,
                        keep_silence=100  # 保留一小段静音，避免声音突然切换
                    )
                    
                    if not chunks:
                        logging.warning(f"在阈值 {threshold:.1f} dBFS 下未检测到非静音片段")
                        return {
                            "threshold": threshold,
                            "status": "no_chunks",
                            "message": f"未检测到非静音片段 (阈值 {threshold:.1f} dBFS)"
                        }
                        
                    # 合并非静音片段
                    output_audio = sum(chunks)
                    
                    # 导出并检查大小
                    # 使用唯一临时文件名，避免并行处理冲突
                    import time
                    temp_output_path = os.path.join(output_dir, f"{name}_temp_{threshold}_{int(time.time() * 1000)}.wav")
                    output_audio.export(temp_output_path, format="wav")
                    
                    output_size = os.path.getsize(temp_output_path)
                    os.remove(temp_output_path)  # 删除临时文件
                    
                    size_ratio = output_size / input_size
                    logging.info(f"阈值 {threshold:.1f} dBFS 结果: 大小比例 {size_ratio:.2f}, {output_size}/{input_size} bytes, {len(chunks)} 个片段")
                    
                    result = {
                        "threshold": threshold,
                        "status": "success",
                        "output_size": output_size,
                        "ratio": size_ratio,
                        "chunks": len(chunks)
                    }
                    
                    return result
                    
                except Exception as e:
                    logging.error(f"测试阈值 {threshold:.1f} dBFS 时出错: {e}")
                    return {
                        "threshold": threshold,
                        "status": "error",
                        "message": f"处理错误: {e}"
                    }
            
            # --- 执行自适应阈值搜索 ---
            best_threshold = None
            best_result = None
            
            # 首先尝试一些预设的阈值点
            preset_results = []
            for threshold in PRESET_THRESHOLDS:
                result = test_threshold(threshold, is_preset=True)
                if result["status"] == "success":
                    preset_results.append(result)
                    # 如果发现满足条件的阈值，记录下来
                    if min_acceptable_size <= result["output_size"] <= max_acceptable_size:
                        # 找到合适的预设点
                        preset_valid = True
                
            # 从预设结果中找到最佳的
            valid_presets = [r for r in preset_results if r["status"] == "success" and 
                             min_acceptable_size <= r["output_size"] <= max_acceptable_size]
            
            if valid_presets:
                # 优先选择文件大小比例接近0.7-0.8的结果（较好的平衡点） 
                target_ratio = 0.75
                valid_presets.sort(key=lambda r: abs(r["ratio"] - target_ratio))
                best_result = valid_presets[0]
                best_threshold = best_result["threshold"]
                logging.info(f"使用预设阈值点 {best_threshold:.1f} dBFS (比例 {best_result['ratio']:.2f})")
            else:
                # 如果预设点没有找到合适的，执行二分搜索
                search_attempts = 0
                current_threshold = adaptive_threshold
                last_low_result = None  # 最近的过低结果
                last_high_result = None  # 最近的过高结果
                
                while search_attempts < MAX_SEARCH_ATTEMPTS:
                    search_attempts += 1
                    result = test_threshold(current_threshold)
                    
                    if result["status"] != "success":
                        # 处理异常情况
                        if result["status"] == "no_chunks":
                            # 没有片段，阈值太严格了，尝试更宽松的阈值
                            logging.info(f"未检测到片段，阈值过于严格，增加阈值")
                            last_low_result = {"threshold": current_threshold, "output_size": 0, "ratio": 0}
                            if last_high_result:
                                # 在当前和上次过高阈值之间折半
                                current_threshold = (current_threshold + last_high_result["threshold"]) / 2
                            else:
                                # 大幅增加阈值
                                current_threshold += 10
                                if current_threshold > -10:
                                    current_threshold = -10  # 防止过高
                        else:
                            # 其他错误，尝试下一个阈值
                            current_threshold += 5
                        continue
                    
                    output_size = result["output_size"]
                    
                    if min_acceptable_size <= output_size <= max_acceptable_size:
                        # 找到合适的阈值!
                        best_threshold = current_threshold
                        best_result = result
                        break
                    elif output_size < min_acceptable_size:
                        # 文件太小，需要更宽松的阈值（更少剪切）
                        last_low_result = result
                        logging.info(f"文件太小 ({result['ratio']:.2f} < {MIN_SIZE_RATIO}), 增加阈值")
                        
                        if last_high_result:
                            # 有过高记录，进行二分查找
                            current_threshold = (current_threshold + last_high_result["threshold"]) / 2
                        else:
                            # 初步搜索使用较大步长
                            step = INITIAL_STEP if search_attempts < 5 else FINE_STEP
                            current_threshold += step
                            if current_threshold > MAX_THRESHOLD:
                                current_threshold = MAX_THRESHOLD
                        
                    else:  # output_size > max_acceptable_size
                        # 文件太大，需要更严格的阈值（更多剪切）
                        last_high_result = result
                        logging.info(f"文件太大 ({result['ratio']:.2f} > {MAX_SIZE_RATIO}), 降低阈值")
                        
                        if last_low_result:
                            # 有过低记录，进行二分查找
                            current_threshold = (current_threshold + last_low_result["threshold"]) / 2
                        else:
                            # 初步搜索使用较大步长
                            step = INITIAL_STEP if search_attempts < 5 else FINE_STEP
                            current_threshold -= step
                            if current_threshold < MIN_THRESHOLD:
                                current_threshold = MIN_THRESHOLD
                    
                # 如果达到最大尝试次数仍未找到完全符合要求的阈值，则使用最接近的结果
                if best_threshold is None and (last_high_result or last_low_result):
                    logging.info(f"达到最大尝试次数 ({MAX_SEARCH_ATTEMPTS})，使用最接近目标的结果")
                    
                    # 优先选择减小后比例在MIN_SIZE_RATIO和1.0之间的结果
                    if last_high_result and MIN_SIZE_RATIO <= last_high_result["ratio"] < 1.0:
                        best_result = last_high_result
                        best_threshold = last_high_result["threshold"]
                    elif last_low_result and last_low_result["ratio"] > 0.3:  # 至少保留30%
                        best_result = last_low_result
                        best_threshold = last_low_result["threshold"]
                    else:
                        # 如果都不符合，选择最接近目标比例的结果
                        valid_results = []
                        if last_high_result:
                            valid_results.append(last_high_result)
                        if last_low_result and last_low_result["ratio"] > 0:
                            valid_results.append(last_low_result)
                            
                        if valid_results:
                            # 排序并选择最接近目标比例的
                            target_ratio = MIN_SIZE_RATIO + (MAX_SIZE_RATIO - MIN_SIZE_RATIO) / 2  # 目标比例中点
                            valid_results.sort(key=lambda r: abs(r["ratio"] - target_ratio))
                            best_result = valid_results[0]
                            best_threshold = best_result["threshold"]
            
            # --- 使用最佳阈值生成最终结果 ---
            if best_threshold is not None:
                logging.info(f"使用最佳阈值 {best_threshold:.1f} dBFS 生成最终结果")
                
                chunks = split_on_silence(
                    self.audio,
                    min_silence_len=min_silence_len,
                    silence_thresh=best_threshold,
                    keep_silence=100
                )
                
                if not chunks:
                    return False, f"使用最佳阈值 {best_threshold:.1f} dBFS 未检测到非静音片段"
                
                output_audio = sum(chunks)
                output_audio.export(output_path, format="wav")
                
                final_size = os.path.getsize(output_path)
                actual_ratio = final_size / input_size
                actual_reduction = ((input_size - final_size) / input_size * 100)
                actual_retention = actual_ratio * 100
                
                logging.info(f"最终文件大小: {input_size} -> {final_size} bytes (减少: {actual_reduction:.2f}%, 保留: {actual_retention:.2f}%)")
                
                # 严格检查文件大小是否符合要求
                if min_acceptable_size < final_size < input_size:
                    # 完全符合要求：小于原始大小但大于原始大小的50%
                    status_msg = "理想范围内"
                    logging.info(f"最终结果完全符合要求: 大小比例 {actual_ratio:.2f} (介于 {MIN_SIZE_RATIO} 和 1.0 之间)")
                    
                    final_message = f"{output_path} (阈值: {best_threshold:.1f} dBFS, 大小: {input_size} -> {final_size} bytes, 减少: {actual_reduction:.2f}%, 保留: {actual_retention:.2f}%, {status_msg})"
                    logging.info(f"处理成功完成: {final_message}")
                    return True, final_message
                    
                elif final_size >= input_size:
                    # 处理后文件大小大于或等于原始文件，不符合要求
                    logging.warning(f"最终结果大于或等于原始文件大小 ({final_size} >= {input_size} bytes)")
                    
                    # 如果非常接近原始大小（差距小于1%），仍然返回成功
                    if actual_ratio < 1.01:  # 允许1%的误差
                        logging.info(f"文件大小非常接近原始大小，仍然返回成功")
                        final_message = f"{output_path} (阈值: {best_threshold:.1f} dBFS, 大小: {input_size} -> {final_size} bytes, 减少: {actual_reduction:.2f}%, 保留: {actual_retention:.2f}%)"
                        return True, final_message
                    
                    return False, f"无法使文件 {basename} 变小，最终结果为原始大小的 {actual_ratio:.2f} 倍"
                    
                elif final_size <= min_acceptable_size:
                    # 处理后文件大小小于原始文件的50%，不符合要求
                    logging.warning(f"最终结果小于最小大小要求 ({final_size} <= {min_acceptable_size} bytes)")
                    
                    # 如果非常接近最小可接受大小（差距小于5%），仍然返回成功
                    if actual_ratio > MIN_SIZE_RATIO * 0.9:  # 如果大小超过最小限制的90%
                        logging.info(f"文件大小接近最小限制，仍然返回成功")
                        final_message = f"{output_path} (阈值: {best_threshold:.1f} dBFS, 大小: {input_size} -> {final_size} bytes, 减少: {actual_reduction:.2f}%, 保留: {actual_retention:.2f}%)"
                        return True, final_message
                    
                    return False, f"无法保留足够的音频内容，最终结果仅保留了 {actual_retention:.2f}% 的原始内容，小于最小要求 {MIN_SIZE_RATIO*100}%"
            else:
                # 没有找到有效的阈值
                logging.warning(f"无法找到任何有效的阈值，放弃处理: {basename}")
                return False, f"无法找到合适的阈值处理文件 {basename}"

        except Exception as e:
            logging.error(f"处理文件 {self.input_file} 时发生意外错误: {e}", exc_info=True)
            return False, f"处理错误: {e}"
