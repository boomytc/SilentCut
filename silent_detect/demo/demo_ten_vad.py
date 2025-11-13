from pathlib import Path
from ten_vad import TenVad
import numpy as np
import librosa

WAV_PATH = "assets/example_audio/诗朗诵_面朝大海春暖花开.mp3"
TARGET_SR = 16000
HOP_SIZE = 256
THRESHOLD = 0.5
MAX_AUDIO_DURATION_MS = 5000    # 最大音频时长（毫秒），默认5秒


def vad_detect(audio_path, hop_size=HOP_SIZE, threshold=THRESHOLD, max_duration_ms=MAX_AUDIO_DURATION_MS):
    """对音频文件进行VAD检测，返回语音段时间戳"""
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
    
    # 转换为毫秒
    timestamps = [[int(s * 1000), int(e * 1000)] for s, e in segments]
    
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
    
    return {"key": audio_path.stem, "value": timestamps}



result = vad_detect(WAV_PATH)
print(result)

# 输出内容如下：
'''
{'key': '诗朗诵_面朝大海春暖花开', 'value': [[1376, 4800], [4976, 9184], [9456, 11952], [14032, 18080], [19984, 23792], [24864, 26336], [29216, 33136], [34432, 36512], [38592, 41648], [43056, 47040], [48560, 51296], [51984, 56640], [57328, 61440], [62128, 66576], [66768, 69296], [70944, 73824], [75664, 80656], [81312, 82096]]}
'''


