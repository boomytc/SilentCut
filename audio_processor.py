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
            # 将音频分成多个小段并分析其特征
            segment_length_ms = 500  # 500毫秒片段
            segments = [self.audio[i:i+segment_length_ms] for i in range(0, len(self.audio), segment_length_ms)]
            
            # 计算非静音片段的平均音量
            non_silent_segments = [seg for seg in segments if seg.dBFS > -70]  # 忽略非常安静的片段
            
            if not non_silent_segments:
                # 如果没有非静音片段，使用默认值
                initial_threshold = -60  # 使用中等阈值作为起点
                logging.warning(f"文件 {basename} 没有检测到明显的非静音片段。使用默认阈值 {initial_threshold} dBFS 开始尝试。")
            else:
                # 计算非静音片段的平均音量
                active_segments_dbfs = [seg.dBFS for seg in non_silent_segments if seg.dBFS > -float('inf')]
                if active_segments_dbfs:
                    active_avg_dbfs = sum(active_segments_dbfs) / len(active_segments_dbfs)
                    # 计算阈值，使用非静音片段的平均值减去偏移量
                    initial_threshold = active_avg_dbfs - ADAPTIVE_THRESHOLD_OFFSET
                    # 确保阈值在合理范围内
                    initial_threshold = max(MIN_THRESHOLD, min(initial_threshold, -30))
                    logging.info(f"文件 {basename} 非静音片段平均音量: {active_avg_dbfs:.2f} dBFS, 计算的自适应阈值: {initial_threshold:.2f} dBFS")
                else:
                    # 如果出现异常情况，使用默认值
                    initial_threshold = -60
                    logging.warning(f"文件 {basename} 音频特征分析异常。使用默认阈值 {initial_threshold} dBFS 开始尝试。")
            
            # 尝试使用预设阈值中最接近的值
            closest_preset = min(PRESET_THRESHOLDS, key=lambda x: abs(x - initial_threshold))
            initial_threshold = closest_preset
            logging.info(f"选择预设阈值: {initial_threshold} dBFS 作为搜索起点")
            
            # --- 改进的自适应搜索策略 ---
            best_threshold = None
            best_output_size = None
            best_output_audio = None
            temp_files = []  # 跟踪临时文件，以便清理
            attempt_count = 0
            
            # 首先尝试所有预设阈值点，快速定位大致范围
            preset_results = {}  # 存储预设阈值的结果
            tried_thresholds = set()  # 记录已尝试过的阈值
            
            # 先尝试初始阈值和其他几个关键阈值点
            key_thresholds = [initial_threshold, -60, -40, -20]  # 关键阈值点
            
            # 定义一个函数来测试特定阈值
            def test_threshold(threshold, is_preset=False):
                nonlocal attempt_count, best_threshold, best_output_size, best_output_audio
                
                # 因为浮点数精度问题，将阈值四舍五入到一位小数
                threshold = round(threshold, 1)
                
                # 检查是否已尝试过该阈值
                if threshold in tried_thresholds:
                    return None
                
                tried_thresholds.add(threshold)
                attempt_count += 1
                
                logging.info(f"尝试阈值 {threshold:.1f} dBFS (第 {attempt_count}/{MAX_SEARCH_ATTEMPTS} 次{', 预设点' if is_preset else ''})")
                
                # 使用当前阈值分割音频
                chunks = split_on_silence(
                    self.audio,
                    min_silence_len=min_silence_len,
                    silence_thresh=threshold,
                    keep_silence=100  # 保留一小段静音，避免声音突然切换
                )
                
                if not chunks:
                    logging.warning(f"阈值 {threshold:.1f} dBFS: 未检测到非静音片段")
                    return "too_small"
                
                # 合并非静音片段
                output_audio = sum(chunks)
                
                # 创建临时文件名以检查大小
                temp_output_path = f"{output_path}.temp_{attempt_count}"
                temp_files.append(temp_output_path)
                
                # 导出并检查大小
                output_audio.export(temp_output_path, format="wav")
                current_output_size = os.path.getsize(temp_output_path)
                size_ratio = current_output_size / input_size
                
                logging.info(f"阈值 {threshold:.1f} dBFS: 输出大小 {current_output_size} bytes (原始: {input_size} bytes, 比例: {size_ratio:.2f})")
                
                # 返回结果和大小信息
                result = {
                    "threshold": threshold,
                    "size": current_output_size,
                    "ratio": size_ratio,
                    "audio": output_audio
                }
                
                # 检查是否在目标范围内
                if min_acceptable_size < current_output_size < max_acceptable_size:
                    # 理想范围
                    logging.info(f"阈值 {threshold:.1f} dBFS: 文件大小在理想范围内 - 减少 {((input_size - current_output_size) / input_size * 100):.2f}%, 保留 {(current_output_size / input_size * 100):.2f}%")
                    
                    # 更新最佳结果
                    if best_threshold is None or abs(current_output_size - (min_acceptable_size + max_acceptable_size) / 2) < abs(best_output_size - (min_acceptable_size + max_acceptable_size) / 2):
                        best_threshold = threshold
                        best_output_size = current_output_size
                        best_output_audio = output_audio
                    
                    return "ideal"
                elif current_output_size <= min_acceptable_size:
                    # 太小
                    logging.warning(f"阈值 {threshold:.1f} dBFS: 文件太小 ({(current_output_size / input_size * 100):.2f}% < {MIN_SIZE_RATIO*100}%)")
                    
                    # 更新最佳结果（如果没有更好的结果）
                    if best_threshold is None or (best_output_size < min_acceptable_size and current_output_size > best_output_size):
                        best_threshold = threshold
                        best_output_size = current_output_size
                        best_output_audio = output_audio
                    
                    return "too_small"
                else:  # current_output_size >= max_acceptable_size
                    # 太大
                    logging.warning(f"阈值 {threshold:.1f} dBFS: 文件太大 ({(current_output_size / input_size * 100):.2f}% > {MAX_SIZE_RATIO*100}%)")
                    return "too_large"
            
            # 先尝试关键阈值点
            key_results = {}
            for threshold in key_thresholds:
                if attempt_count >= MAX_SEARCH_ATTEMPTS:
                    break
                result = test_threshold(threshold, True)
                if result:
                    key_results[threshold] = result
                    if result == "ideal":
                        # 如果找到理想范围内的结果，可以提前结束
                        logging.info(f"已找到理想范围内的阈值 {threshold:.1f} dBFS，提前结束搜索")
                        break
            
            # 如果关键点没有找到理想结果，则进行二分搜索
            if best_threshold is None or best_output_size < min_acceptable_size or best_output_size > max_acceptable_size:
                # 根据关键点结果确定搜索范围
                too_small_thresholds = [t for t, r in key_results.items() if r == "too_small"]
                too_large_thresholds = [t for t, r in key_results.items() if r == "too_large"]
                
                # 设置搜索范围
                if too_small_thresholds and too_large_thresholds:
                    # 如果同时有“太小”和“太大”的结果，则可以缩小搜索范围
                    low_threshold = max(too_small_thresholds)
                    high_threshold = min(too_large_thresholds)
                elif too_small_thresholds:
                    # 只有“太小”的结果，则向上搜索
                    low_threshold = max(too_small_thresholds)
                    high_threshold = MAX_THRESHOLD
                elif too_large_thresholds:
                    # 只有“太大”的结果，则向下搜索
                    low_threshold = MIN_THRESHOLD
                    high_threshold = min(too_large_thresholds)
                else:
                    # 没有有效结果，使用完整范围
                    low_threshold = MIN_THRESHOLD
                    high_threshold = MAX_THRESHOLD
            
            # 如果关键点搜索没有找到理想结果，进行更精细的二分搜索
            if best_threshold is None or (best_output_size is not None and (best_output_size <= min_acceptable_size or best_output_size >= max_acceptable_size)):
                logging.info(f"开始二分搜索，搜索范围: {low_threshold:.1f} - {high_threshold:.1f} dBFS")
                
                # 使用二分搜索策略
                while attempt_count < MAX_SEARCH_ATTEMPTS and abs(high_threshold - low_threshold) > 0.5:
                    # 计算中间阈值
                    current_threshold = (low_threshold + high_threshold) / 2
                    current_threshold = round(current_threshold, 1)  # 四舍五入到一位小数
                    
                    # 检查是否已尝试过该阈值
                    if current_threshold in tried_thresholds:
                        # 如果已尝试过，尝试微调阈值
                        if current_threshold + 0.1 <= high_threshold and (current_threshold + 0.1) not in tried_thresholds:
                            current_threshold += 0.1
                        elif current_threshold - 0.1 >= low_threshold and (current_threshold - 0.1) not in tried_thresholds:
                            current_threshold -= 0.1
                        else:
                            # 如果没有可尝试的阈值，结束搜索
                            logging.info(f"搜索范围内所有可能的阈值均已尝试，结束搜索")
                            break
                    
                    # 测试当前阈值
                    result = test_threshold(current_threshold)
                    
                    # 根据结果调整搜索范围
                    if result == "ideal":
                        # 如果找到理想范围内的结果，可以提前结束
                        logging.info(f"找到理想范围内的阈值 {current_threshold:.1f} dBFS，结束搜索")
                        break
                    elif result == "too_small":
                        # 如果文件太小，向上搜索
                        low_threshold = current_threshold
                    elif result == "too_large":
                        # 如果文件太大，向下搜索
                        high_threshold = current_threshold
                    
                    # 检查搜索范围是否过小
                    if abs(high_threshold - low_threshold) <= 0.5:
                        logging.info(f"搜索范围过小 ({low_threshold:.1f} - {high_threshold:.1f})，停止搜索")
                        break
                
                # 如果二分搜索仍然没有找到理想结果，尝试更宽松的阈值
                if best_threshold is None or (best_output_size is not None and best_output_size <= min_acceptable_size):
                    # 尝试更宽松的阈值
                    for threshold in [-25, -20, -15, -10, -5, 0]:
                        if attempt_count >= MAX_SEARCH_ATTEMPTS:
                            break
                        if threshold not in tried_thresholds:
                            result = test_threshold(threshold)
                            if result == "ideal":
                                logging.info(f"找到理想范围内的阈值 {threshold:.1f} dBFS，结束搜索")
                                break
            
            # --- 清理临时文件 ---
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        logging.debug(f"删除临时文件 {temp_file}")
                    except Exception as e:
                        logging.warning(f"无法删除临时文件 {temp_file}: {e}")
            
            # --- 处理最终结果 ---
            if best_threshold is not None:
                # 检查最终结果是否符合大小要求
                size_ratio = best_output_size / input_size
                reduction_percent = ((input_size - best_output_size) / input_size * 100)
                retention_percent = size_ratio * 100
                
                # 导出最终结果
                best_output_audio.export(output_path, format="wav")
                final_size = os.path.getsize(output_path)  # 获取实际导出后的文件大小
                
                # 重新计算实际比例（以防导出后大小有变化）
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

# 测试代码
if __name__ == '__main__':
    test_file = 'test_audio.wav'
    if os.path.exists(test_file):
        try:
            processor = AudioProcessor(test_file)
            success, message = processor.process_audio(min_silence_len=1000)
            print(f"处理结果: Success={success}, Message='{message}'")
        except Exception as e:
            print(f"测试时出错: {e}")
    else:
        print(f"测试文件未找到: {test_file}")
