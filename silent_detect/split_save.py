import librosa
import soundfile as sf
from pathlib import Path
from utils.vad_detect import vad_detect

def split_audio(audio_path, min_silence_ms=None, max_duration_ms=5000, output_dir="output"):
    """根据 VAD 结果将音频分割成语音片段。"""

    audio_path = Path(audio_path)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    vad_result = vad_detect(
        str(audio_path),
        min_silence_ms=min_silence_ms,
        max_duration_ms=max_duration_ms,
    )

    # 使用原始采样率加载一次，以进行精确切片。
    audio_float, sr = librosa.load(str(audio_path), sr=None, mono=True)

    for item in vad_result:
        segments = item.get("value") or []
        audio_key = item.get("key") or audio_path.stem

        for start_ms, end_ms in segments:
            start_sample = int(round(start_ms * sr / 1000))
            end_sample = int(round(end_ms * sr / 1000))

            if end_sample <= start_sample:
                continue

            segment_audio = audio_float[start_sample:end_sample]
            output_filename = f"{audio_key}_{start_ms}_{end_ms}.wav"
            output_path = target_dir / output_filename

            sf.write(output_path, segment_audio, sr)

    return str(target_dir.resolve())


if __name__ == "__main__":
    audio_path = "assets/example_audio/诗朗诵_面朝大海春暖花开.mp3"
    output_dir = "silent_detect/output"
    min_silence_ms = 300
    max_duration_ms = 5000

    result = split_audio(audio_path, min_silence_ms=min_silence_ms, max_duration_ms=max_duration_ms, output_dir=output_dir)
    print("VAD音频切片保存：" + result)

    # 输出内容示例：
    '''
    VAD音频切片保存：silent_detect/output
    '''
