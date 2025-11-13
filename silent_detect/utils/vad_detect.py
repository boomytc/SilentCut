from pathlib import Path
from ten_vad import TenVad
import numpy as np
import librosa
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

TARGET_SR = 16000
HOP_SIZE = 256
THRESHOLD = 0.5
MIN_SILENCE_MS = 1000           # 最小静音时长（毫秒），默认1秒
MAX_AUDIO_DURATION_MS = 5000    # 最大音频时长（毫秒），默认5秒

WAV_PATH = "assets/example_audio/诗朗诵_面朝大海春暖花开.mp3"

def ten_vad_detect(audio_path, hop_size=HOP_SIZE, threshold=THRESHOLD, min_silence_ms=None, max_duration_ms=None):
    """使用TenVAD进行VAD检测，返回语音段时间戳"""
    audio_path = Path(audio_path)
    
    # 音频预处理
    audio_float, sr = librosa.load(audio_path, sr=TARGET_SR, mono=True)
    audio_data = (np.clip(audio_float, -1.0, 1.0) * np.iinfo(np.int16).max).astype(np.int16)
    
    # VAD检测
    vad = TenVad(hop_size, threshold)
    num_frames = len(audio_data) // hop_size
    frame_dur_s = hop_size / float(sr)
    
    # 检测语音段
    segments = []
    seg_start = None
    for i in range(num_frames):
        frame = audio_data[i * hop_size:(i + 1) * hop_size]
        _, is_speech = vad.process(frame)
        if is_speech:
            if seg_start is None:
                seg_start = i
        else:
            if seg_start is not None:
                segments.append((seg_start * frame_dur_s, (i - 1) * frame_dur_s))
                seg_start = None
    
    if seg_start is not None:
        segments.append((seg_start * frame_dur_s, (num_frames - 1) * frame_dur_s))

    # 段合并
    if min_silence_ms is not None:
        merged = []
        if segments:
            merged = [segments[0]]
            min_gap_s = min_silence_ms / 1000.0
            for start, end in segments[1:]:
                last_start, last_end = merged[-1]
                if (start - last_end) < min_gap_s:
                    merged[-1] = (last_start, end)
                else:
                    merged.append((start, end))
    else:
        merged = segments
    
    # 转换为毫秒
    timestamps = [[int(s * 1000), int(e * 1000)] for s, e in merged]

    # 根据最大时长合并段
    if max_duration_ms is not None:
        # 合并逻辑
        if timestamps:
            final_segments = []
            current_start = None
            current_end = None
            for start_ms, end_ms in timestamps:
                if current_start is None:
                    current_start = start_ms
                    current_end = end_ms
                else:
                    potential_duration = end_ms - current_start
                    if potential_duration <= max_duration_ms:
                        current_end = end_ms
                    else:
                        final_segments.append([current_start, current_end])
                        current_start = start_ms
                        current_end = end_ms
            if current_start is not None:
                final_segments.append([current_start, current_end])
            timestamps = final_segments
    
    return [{"key": audio_path.stem, "value": timestamps}]

def vad_detect(audio_path, hop_size=HOP_SIZE, threshold=THRESHOLD, min_silence_ms=None, max_duration_ms=5000):
    """对音频文件进行VAD检测，返回语音段时间戳"""
    return ten_vad_detect(audio_path, hop_size, threshold, min_silence_ms, max_duration_ms)
    
if __name__ == "__main__":
    res_tenvad = vad_detect(WAV_PATH, min_silence_ms=MIN_SILENCE_MS, max_duration_ms=MAX_AUDIO_DURATION_MS)
    print("="*20 + "TenVAD:" + "="*20)
    print(res_tenvad)
