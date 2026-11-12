"""Transcribe rendered lecture MP4s with faster-whisper.

Usage: python transcribe.py [--model M] [--language L] OUT_DIR file1.mp4 [file2.mp4 ...]
Writes OUT_DIR/<stem>.txt: one line per segment, "[start-end] text".

Defaults to English with small.en. For another language pass --language
(e.g. de); the model then defaults to the multilingual "small", and an
English-only ".en" model is refused. Use --model medium to cross-check
suspects: small produces false positives outside English.

Audio is decoded by ffmpeg into a 16 kHz float32 array instead of letting
faster-whisper open the file, because its PyAV decoder fails on this machine
(TypeError: open() got an unexpected keyword argument 'metadata_errors').
"""
import argparse
import subprocess
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

parser = argparse.ArgumentParser(description="Transcribe lecture MP4s with faster-whisper.")
parser.add_argument("out_dir", type=Path)
parser.add_argument("files", nargs="+", type=Path)
parser.add_argument("--language", default="en",
                    help="spoken language code, e.g. en, de (default: en)")
parser.add_argument("--model",
                    help="Whisper model (default: small.en for English, small otherwise)")
args = parser.parse_args()

language = args.language.lower()
model_name = args.model or ("small.en" if language == "en" else "small")
if language != "en" and model_name.endswith(".en"):
    parser.error(f"{model_name} is English-only; use a multilingual model "
                 f"(small, medium, ...) for --language {language}")

args.out_dir.mkdir(parents=True, exist_ok=True)
model = WhisperModel(model_name, device="cpu", compute_type="int8")
# .en models are English-only and take no language argument; multilingual
# ones would otherwise auto-detect from the first 30 s.
options = {} if model_name.endswith(".en") else {"language": language}
for path in args.files:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, dtype=np.float32)
    segments, _ = model.transcribe(audio, beam_size=5, vad_filter=False, **options)
    lines = [f"[{s.start:7.2f}-{s.end:7.2f}] {s.text.strip()}" for s in segments]
    (args.out_dir / f"{path.stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{path.stem}: {len(lines)} segments ({model_name}, {language})", flush=True)
