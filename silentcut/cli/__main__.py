"""
SilentCut 命令行工具入口
"""
import os
import sys
import argparse
import time

from silentcut.audio.processor import AudioProcessor
from silentcut.utils.logger import get_logger
from silentcut.utils.file_utils import get_audio_files_in_directory, ensure_dir_exists

# 获取日志记录器
logger = get_logger("cli")


def process_single_file(input_file, output_dir=None, vad_threshold=0.5,
                        vad_min_silence_ms=1000, vad_max_duration_ms=5000,
                        verbose=False):
    """处理单个音频文件"""
    try:
        # 设置日志级别
        if verbose:
            logger.setLevel("DEBUG")
        
        logger.info(f"处理文件: {input_file}")
        processor = AudioProcessor(input_file)
        start_time = time.time()
        success, message = processor.process_audio(
            output_folder=output_dir,
            vad_threshold=vad_threshold,
            vad_min_silence_ms=vad_min_silence_ms,
            vad_max_duration_ms=vad_max_duration_ms,
        )
        elapsed_time = time.time() - start_time
        
        if success:
            logger.info(f"处理成功 ({elapsed_time:.2f}秒): {message}")
            return True, message
        else:
            logger.error(f"处理失败 ({elapsed_time:.2f}秒): {message}")
            return False, message
    except Exception as e:
        logger.error(f"处理文件 {input_file} 时发生错误: {e}")
        return False, str(e)


def process_batch(input_dir, output_dir=None, vad_threshold=0.5,
                  vad_min_silence_ms=1000, vad_max_duration_ms=5000, verbose=False):
    """批量处理目录中的音频文件"""
    # 设置日志级别
    if verbose:
        logger.setLevel("DEBUG")
    
    # 获取目录中的所有音频文件
    audio_files = get_audio_files_in_directory(input_dir)
    
    if not audio_files:
        logger.error(f"目录 {input_dir} 中未找到音频文件")
        return False, "未找到音频文件"
    
    logger.info(f"找到 {len(audio_files)} 个音频文件")
    
    # 确保输出目录存在
    if output_dir:
        ensure_dir_exists(output_dir)
    
    # 顺序处理所有文件
    logger.info("使用 VAD 模式顺序处理")
    results = []
    
    for i, file in enumerate(audio_files):
        success, message = process_single_file(
            file,
            output_dir,
            vad_threshold,
            vad_min_silence_ms,
            vad_max_duration_ms,
            verbose,
        )
        results.append((success, message))
        
        # 显示进度
        progress = (i + 1) / len(audio_files) * 100
        logger.info(f"进度: {progress:.1f}% ({i+1}/{len(audio_files)})")
    
    # 统计结果
    success_count = sum(1 for success, _ in results if success)
    fail_count = len(results) - success_count
    
    result_message = f"处理完成: 成功 {success_count}/{len(results)}, 失败 {fail_count}/{len(results)}"
    logger.info(result_message)
    
    return success_count > 0, result_message


def main():
    """命令行工具主函数"""
    parser = argparse.ArgumentParser(description="SilentCut - 音频静音切割工具")
    
    # 添加子命令
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # 单文件处理命令
    single_parser = subparsers.add_parser("process", help="处理单个音频文件")
    single_parser.add_argument("input", help="输入音频文件路径")
    single_parser.add_argument("-o", "--output-dir", help="输出目录路径")
    single_parser.add_argument("--vad-threshold", type=float, default=0.5, help="VAD 阈值 (默认: 0.5)")
    single_parser.add_argument("--vad-min-silence-ms", type=int, default=1000, help="VAD 段合并最小静音(ms) (默认: 1000)")
    single_parser.add_argument("--vad-max-duration-ms", type=int, default=5000, help="VAD 段最大时长(ms) (默认: 5000)")
    single_parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")
    
    # 批处理命令
    batch_parser = subparsers.add_parser("batch", help="批量处理目录中的音频文件")
    batch_parser.add_argument("input_dir", help="输入目录路径")
    batch_parser.add_argument("-o", "--output-dir", help="输出目录路径")
    batch_parser.add_argument("--vad-threshold", type=float, default=0.5, help="VAD 阈值 (默认: 0.5)")
    batch_parser.add_argument("--vad-min-silence-ms", type=int, default=1000, help="VAD 段合并最小静音(ms) (默认: 1000)")
    batch_parser.add_argument("--vad-max-duration-ms", type=int, default=5000, help="VAD 段最大时长(ms) (默认: 5000)")
    batch_parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 如果没有指定命令，显示帮助信息
    if not args.command:
        parser.print_help()
        return
    
    # 处理命令
    if args.command == "process":
        # 检查输入文件是否存在
        if not os.path.isfile(args.input):
            logger.error(f"输入文件不存在: {args.input}")
            return
        
        # 处理单个文件
        success, message = process_single_file(
            args.input,
            args.output_dir,
            args.vad_threshold,
            args.vad_min_silence_ms,
            args.vad_max_duration_ms,
            args.verbose,
        )
        
        # 显示处理结果
        if success:
            print(f"处理成功: {message}")
            sys.exit(0)
        else:
            print(f"处理失败: {message}")
            sys.exit(1)
    
    elif args.command == "batch":
        # 检查输入目录是否存在
        if not os.path.isdir(args.input_dir):
            logger.error(f"输入目录不存在: {args.input_dir}")
            return
        
        # 批量处理目录
        success, message = process_batch(
            args.input_dir, 
            args.output_dir, 
            args.vad_threshold,
            args.vad_min_silence_ms,
            args.vad_max_duration_ms,
            args.verbose
        )
        
        # 显示处理结果
        if success:
            print(f"批处理成功: {message}")
            sys.exit(0)
        else:
            print(f"批处理失败: {message}")
            sys.exit(1)


if __name__ == "__main__":
    main()
