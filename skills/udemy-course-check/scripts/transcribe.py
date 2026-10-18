"""Transcribe rendered lecture MP4s with faster-whisper (small.en).

Usage: python transcribe.py OUT_DIR file1.mp4 [file2.mp4 ...]
Writes OUT_DIR/<stem>.txt: one line per segment, "[start-end] text".

Audio is decoded by ffmpeg into a 16 kHz float32 array instead of letting
faster-whisper open the file, because its PyAV decoder fails on this machine
(TypeError: open() got an unexpected keyword argument 'metadata_errors').
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

out_dir = Path(sys.argv[1])
out_dir.mkdir(parents=True, exist_ok=True)
model = WhisperModel("small.en", device="cpu", compute_type="int8")
for name in sys.argv[2:]:
    path = Path(name)
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, dtype=np.float32)
    segments, _ = model.transcribe(audio, beam_size=5, vad_filter=False)
    lines = [f"[{s.start:7.2f}-{s.end:7.2f}] {s.text.strip()}" for s in segments]
    (out_dir / f"{path.stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{path.stem}: {len(lines)} segments", flush=True)
