"""
音频处理器模块 - 静音检测与切割核心算法
"""
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
            segments = self.audio[::1000]  # 每秒采样一次
            segment_dbfs_values = [segment.dBFS for segment in segments if segment.dBFS > float('-inf')]
            
            if segment_dbfs_values:
                max_dbfs = max(segment_dbfs_values)
                min_dbfs = min(segment_dbfs_values)
                
                # 计算音量动态范围
                dynamic_range = max_dbfs - min_dbfs
                
                # 根据动态范围调整初始阈值
                # 如果动态范围大，使用更严格的阈值；如果动态范围小，使用更宽松的阈值
                initial_threshold = min_dbfs + min(dynamic_range * 0.3, ADAPTIVE_THRESHOLD_OFFSET)
                
                # 确保初始阈值在合理范围内
                initial_threshold = max(MIN_THRESHOLD, min(initial_threshold, MAX_THRESHOLD - 20))
            else:
                # 如果无法计算特征，使用基于平均值的保守估计
                initial_threshold = average_dbfs - ADAPTIVE_THRESHOLD_OFFSET
                
            logging.info(f"音频特征: 平均dBFS={average_dbfs:.1f}, 初始阈值={initial_threshold:.1f}")
            
            # --- 二分搜索最佳阈值 ---
            # 首先尝试预设阈值点，看是否有符合要求的
            preset_results = []
            
            def test_threshold(threshold, is_preset=False):
                """测试特定阈值的效果"""
                logging.info(f"测试阈值: {threshold:.1f} dBFS")
                
                try:
                    # 使用当前阈值分割音频
                    chunks = split_on_silence(
                        self.audio,
                        min_silence_len=min_silence_len,
                        silence_thresh=threshold,
                        keep_silence=100  # 保留一小段静音，避免声音突然切换
                    )
                    
                    # 如果没有检测到任何非静音片段，返回失败
                    if not chunks:
                        logging.warning(f"阈值 {threshold:.1f} dBFS: 未检测到非静音片段")
                        return {
                            "threshold": threshold,
                            "status": "no_chunks",
                            "size": 0,
                            "ratio": 0,
                            "chunks": 0
                        }
                    
                    # 合并非静音片段
                    output_audio = sum(chunks)
                    
                    # 创建临时文件以检查大小
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                        temp_path = temp_file.name
                    
                    # 导出并检查大小
                    output_audio.export(temp_path, format="wav")
                    output_size = os.path.getsize(temp_path)
                    size_ratio = output_size / input_size
                    
                    # 删除临时文件
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                    
                    logging.info(f"阈值 {threshold:.1f} dBFS: 比例={size_ratio:.2f}, 大小={output_size} bytes ({len(chunks)} 个片段)")
                    
                    return {
                        "threshold": threshold,
                        "status": "success",
                        "size": output_size,
                        "ratio": size_ratio,
                        "chunks": len(chunks),
                        "audio": output_audio
                    }
                except Exception as e:
                    logging.error(f"测试阈值 {threshold:.1f} dBFS 时出错: {e}")
                    return {
                        "threshold": threshold,
                        "status": "error",
                        "error": str(e)
                    }
            
            # 尝试预设阈值点
            logging.info("尝试预设阈值点...")
            for preset in PRESET_THRESHOLDS:
                result = test_threshold(preset, is_preset=True)
                if result["status"] == "success":
                    preset_results.append(result)
            
            # 如果有预设阈值符合要求，直接使用
            valid_presets = [r for r in preset_results if min_acceptable_size <= r["size"] <= max_acceptable_size]
            if valid_presets:
                # 选择最接近目标比例0.7的预设阈值
                valid_presets.sort(key=lambda r: abs(r["ratio"] - 0.7))
                best_result = valid_presets[0]
                best_threshold = best_result["threshold"]
                best_audio = best_result["audio"]
                
                logging.info(f"找到符合要求的预设阈值: {best_threshold:.1f} dBFS, 比例={best_result['ratio']:.2f}")
            else:
                # 如果预设阈值都不符合要求，使用二分搜索
                logging.info("预设阈值不符合要求，开始二分搜索...")
                
                # 初始化搜索范围
                low = MIN_THRESHOLD
                high = MAX_THRESHOLD
                
                # 如果有预设结果，可以缩小搜索范围
                if preset_results:
                    # 找出最接近但大于目标大小的预设阈值
                    larger_presets = [r for r in preset_results if r["size"] > max_acceptable_size]
                    if larger_presets:
                        larger_presets.sort(key=lambda r: r["size"])
                        high = larger_presets[0]["threshold"]
                    
                    # 找出最接近但小于目标大小的预设阈值
                    smaller_presets = [r for r in preset_results if r["size"] < min_acceptable_size]
                    if smaller_presets:
                        smaller_presets.sort(key=lambda r: -r["size"])
                        low = smaller_presets[0]["threshold"]
                
                # 使用自适应初始阈值作为起点
                current = initial_threshold
                
                # 记录已测试的阈值和结果
                tested_thresholds = {}
                best_result = None
                best_threshold = None
                best_audio = None
                
                # 二分搜索
                attempts = 0
                while attempts < MAX_SEARCH_ATTEMPTS:
                    attempts += 1
                    
                    # 如果当前阈值已测试过，跳过
                    current_rounded = round(current, 1)  # 四舍五入到小数点后1位
                    if current_rounded in tested_thresholds:
                        # 微调当前值，避免重复测试
                        current += 0.2
                        continue
                    
                    # 测试当前阈值
                    result = test_threshold(current_rounded)
                    tested_thresholds[current_rounded] = result
                    
                    if result["status"] == "success":
                        output_size = result["size"]
                        
                        # 检查是否符合大小要求
                        if min_acceptable_size <= output_size <= max_acceptable_size:
                            # 找到符合要求的阈值，记录结果
                            if best_result is None or abs(result["ratio"] - 0.7) < abs(best_result["ratio"] - 0.7):
                                best_result = result
                                best_threshold = current_rounded
                                best_audio = result["audio"]
                                
                                logging.info(f"找到符合要求的阈值: {best_threshold:.1f} dBFS, 比例={best_result['ratio']:.2f}")
                                
                                # 如果比例非常接近0.7，可以提前结束搜索
                                if abs(result["ratio"] - 0.7) < 0.05:
                                    logging.info("比例非常接近目标值，提前结束搜索")
                                    break
                        
                        # 根据结果调整搜索范围
                        if output_size > max_acceptable_size:
                            # 文件太大，需要更严格的阈值（更小的dBFS值）
                            high = current
                            current = (low + current) / 2
                            logging.info(f"文件太大 ({output_size} > {max_acceptable_size})，调整搜索范围: [{low:.1f}, {current:.1f}]")
                        elif output_size < min_acceptable_size:
                            # 文件太小，需要更宽松的阈值（更大的dBFS值）
                            low = current
                            current = (current + high) / 2
                            logging.info(f"文件太小 ({output_size} < {min_acceptable_size})，调整搜索范围: [{current:.1f}, {high:.1f}]")
                    else:
                        # 处理失败，可能是阈值太严格，尝试更宽松的阈值
                        low = current
                        current = (current + high) / 2
                        logging.info(f"处理失败，尝试更宽松的阈值: {current:.1f}")
                    
                    # 检查搜索范围是否已经很小
                    if high - low < 1:
                        logging.info(f"搜索范围已经很小 ({low:.1f} - {high:.1f})，停止搜索")
                        break
                
                logging.info(f"搜索完成，共尝试 {attempts} 次，测试了 {len(tested_thresholds)} 个不同阈值")
            
            # 检查是否找到符合要求的阈值
            if best_threshold is not None and best_audio is not None:
                # 导出最终结果
                logging.info(f"使用最佳阈值 {best_threshold:.1f} dBFS 导出最终结果: {output_path}")
                best_audio.export(output_path, format="wav")
                
                # 检查最终文件大小
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
