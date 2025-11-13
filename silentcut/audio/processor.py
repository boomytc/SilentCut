"""
音频处理器模块 - 基于 VAD 的语音检测与切割
"""
import os
from pydub import AudioSegment
from silentcut.utils.logger import get_logger
from silentcut.utils.file_utils import ensure_dir_exists, get_output_filename, get_format_codec_from_path
from silentcut.utils.vad_detect import vad_detect

logger = get_logger("audio")


class AudioProcessor:
    def __init__(self, input_file):
        self.input_file = input_file
        self.audio = None
        self.load_audio()

    def load_audio(self):
        """加载音频文件"""
        try:
            logger.info(f"开始加载文件: {self.input_file}")
            self.audio = AudioSegment.from_file(self.input_file)
            logger.info(f"文件加载成功: {self.input_file}")
        except FileNotFoundError:
            logger.error(f"错误: 文件未找到 {self.input_file}")
            self.audio = None
            raise
        except Exception as e:
            logger.error(f"加载文件 {self.input_file} 时出错: {e}")
            self.audio = None
            raise

    def process_audio(self, output_folder=None, vad_threshold=0.5, 
                     vad_min_silence_ms=1000, vad_max_duration_ms=5000):
        """
        使用 VAD 语音检测处理音频文件，移除静音部分。
        
        Args:
            output_folder: 输出目录，如果为None则使用输入文件所在目录
            vad_threshold: VAD 检测阈值 (0.0-1.0)
            vad_min_silence_ms: 最小静音长度（毫秒）
            vad_max_duration_ms: 最大段时长（毫秒）
            
        Returns:
            (success, message): 处理是否成功及相关信息
        """
        if self.audio is None:
            logger.error("错误: 音频未加载，无法处理。")
            return False, "音频未加载"

        try:
            input_size = os.path.getsize(self.input_file)
            basename = os.path.basename(self.input_file)
            
            # 确定输出路径
            output_path = get_output_filename(self.input_file, suffix="-desilenced", output_dir=output_folder)
            out_dir = os.path.dirname(output_path)
            ensure_dir_exists(out_dir)
            out_format, out_codec, out_ext = get_format_codec_from_path(self.input_file)
            
            logger.info(f"使用 VAD 模式处理音频: threshold={vad_threshold}, min_silence={vad_min_silence_ms}ms, max_duration={vad_max_duration_ms}ms")
            
            # 使用 VAD 检测语音段
            vad_kwargs = {
                "threshold": vad_threshold,
                "min_silence_ms": vad_min_silence_ms,
                "max_duration_ms": vad_max_duration_ms
            }
            
            segments_info = vad_detect(self.input_file, **vad_kwargs)
            
            # 提取语音段
            segments = []
            for item in segments_info:
                for start_ms, end_ms in item.get("value", []):
                    segment = self.audio[start_ms:end_ms]
                    segments.append(segment)
            
            if not segments:
                logger.warning(f"未检测到语音片段: {basename}")
                return False, f"无法找到语音片段处理文件 {basename}"
            
            # 合并所有语音段
            output_audio = sum(segments)
            
            # 导出处理后的音频
            output_audio.export(output_path, format=out_format, codec=out_codec)
            
            # 计算文件大小和统计信息
            final_size = os.path.getsize(output_path)
            actual_ratio = final_size / input_size
            actual_reduction = ((input_size - final_size) / input_size * 100)
            actual_retention = actual_ratio * 100
            
            logger.info(f"处理完成: {input_size} -> {final_size} bytes (减少: {actual_reduction:.2f}%, 保留: {actual_retention:.2f}%)")
            
            final_message = (
                f"{output_path} "
                f"(模式: VAD, "
                f"大小: {input_size} -> {final_size} bytes, "
                f"减少: {actual_reduction:.2f}%, "
                f"保留: {actual_retention:.2f}%)"
            )
            
            return True, final_message

        except Exception as e:
            logger.error(f"处理文件 {self.input_file} 时发生意外错误: {e}", exc_info=True)
            return False, f"处理错误: {e}"


# 测试代码
if __name__ == '__main__':
    test_file = 'test_audio.wav'
    if os.path.exists(test_file):
        try:
            processor = AudioProcessor(test_file)
            success, message = processor.process_audio()
            print(f"处理结果: Success={success}, Message='{message}'")
        except Exception as e:
            print(f"测试时出错: {e}")
    else:
        print(f"测试文件未找到: {test_file}")
