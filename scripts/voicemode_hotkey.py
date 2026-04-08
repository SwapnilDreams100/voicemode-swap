#!/usr/bin/env python3
"""
voicemode-hotkey: Push-to-talk daemon using VoiceMode's Whisper STT.

Hold cmd for 0.3s to start recording, release to transcribe and inject text.
Uses sounddevice for recording (pure Python, inherits mic TCC permission from
the Python process itself — no subprocess permission issues).
"""

import io
import logging
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import numpy as np
import sounddevice as sd

from Quartz import (
    CGEventTapCreate,
    CGEventTapEnable,
    CGEventGetFlags,
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    kCGEventFlagsChanged,
    kCGEventFlagMaskCommand,
    kCGSessionEventTap,
    kCGHeadInsertEventTap,
    kCGEventTapOptionDefault,
    CGEventMaskBit,
)

# Config
WHISPER_URL = "http://localhost:2022/v1/audio/transcriptions"
LOG_FILE = Path.home() / ".claude/plugins/claude-stt/voicemode_hotkey.log"
HOLD_DELAY = 0.3   # seconds to hold cmd before recording starts
SAMPLE_RATE = 16000
AUDIO_DEVICE_INDEX = 2  # MacBook Pro Microphone (sounddevice index)

# Sound feedback
SOUND_START = "/System/Library/Sounds/Tink.aiff"
SOUND_END = "/System/Library/Sounds/Pop.aiff"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.getLogger("voicemode-hotkey")

# State
_cmd_held = False
_recording = False
_audio_chunks: list = []
_stream: sd.InputStream | None = None
_lock = threading.Lock()
_hold_timer: threading.Timer | None = None


def _play_sound(path: str):
    subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _audio_callback(indata, frames, time_info, status):
    if _recording:
        _audio_chunks.append(indata.copy())


def _start_recording():
    global _recording, _audio_chunks, _stream
    with _lock:
        if _recording or not _cmd_held:
            return
        _recording = True
        _audio_chunks = []

    log.info("🎤 Recording started...")
    _play_sound(SOUND_START)

    try:
        _stream = sd.InputStream(
            device=AUDIO_DEVICE_INDEX,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            callback=_audio_callback,
        )
        _stream.start()
    except Exception as e:
        log.error(f"Failed to open audio stream: {e}")
        with _lock:
            _recording = False


def _stop_recording():
    global _recording, _stream
    with _lock:
        if not _recording:
            return
        _recording = False
        stream = _stream
        _stream = None
        chunks = list(_audio_chunks)

    if stream:
        stream.stop()
        stream.close()

    log.info("⏹️  Recording stopped, transcribing...")
    _play_sound(SOUND_END)

    if not chunks:
        log.warning("No audio captured.")
        return

    threading.Thread(target=_transcribe_and_inject, args=(chunks,), daemon=True).start()


def _chunks_to_wav(chunks: list) -> bytes:
    audio = np.concatenate(chunks, axis=0).flatten()
    buf = io.BytesIO()
    # Write WAV header manually
    data = audio.tobytes()
    num_samples = len(audio)
    num_channels = 1
    bits_per_sample = 16
    byte_rate = SAMPLE_RATE * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(data)))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, num_channels, SAMPLE_RATE, byte_rate, block_align, bits_per_sample))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(data)))
    buf.write(data)
    return buf.getvalue()


def _transcribe_and_inject(chunks: list):
    wav_data = _chunks_to_wav(chunks)

    if len(wav_data) < 4096:
        log.info("Audio too short, skipping.")
        return

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                WHISPER_URL,
                files={"file": ("audio.wav", io.BytesIO(wav_data), "audio/wav")},
                data={"model": "whisper-1"},
            )
            response.raise_for_status()
            text = response.json().get("text", "").strip()
    except Exception as e:
        log.error(f"Transcription failed: {e}")
        return

    if not text:
        log.info("No speech detected.")
        return

    log.info(f"📝 Transcribed: {text}")
    _inject_text(text)


def _inject_text(text: str):
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        time.sleep(0.05)
        script = 'tell application "System Events" to keystroke "v" using command down'
        subprocess.run(["osascript", "-e", script], check=True)
        log.info("✅ Text injected.")
    except Exception as e:
        log.error(f"Text injection failed: {e}")


def _cgevent_callback(_proxy, event_type, event, _refcon):
    """Raw CGEventTap callback — fires exactly once per physical modifier key change."""
    global _cmd_held, _hold_timer

    if event_type != kCGEventFlagsChanged:
        return event

    flags = CGEventGetFlags(event)
    cmd_down = bool(flags & kCGEventFlagMaskCommand)

    if cmd_down and not _cmd_held:
        _cmd_held = True
        _hold_timer = threading.Timer(HOLD_DELAY, _start_recording)
        _hold_timer.start()
    elif not cmd_down and _cmd_held:
        _cmd_held = False
        if _hold_timer:
            _hold_timer.cancel()
            _hold_timer = None
        _stop_recording()

    return event


def main():
    log.info(f"voicemode-hotkey started. Hold cmd for {HOLD_DELAY}s to record, release to transcribe.")
    log.info(f"Whisper endpoint: {WHISPER_URL}")
    log.info(f"Audio device: {sd.query_devices(AUDIO_DEVICE_INDEX)['name']}")

    try:
        httpx.get("http://localhost:2022/health", timeout=2.0)
        log.info("✅ Whisper service is reachable.")
    except Exception:
        log.warning("⚠️  Whisper not reachable at port 2022. Start with: voicemode service start whisper")

    tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionDefault,
        CGEventMaskBit(kCGEventFlagsChanged),
        _cgevent_callback,
        None,
    )

    if tap is None:
        log.error("Failed to create CGEventTap. Grant Accessibility access in System Settings > Privacy & Security > Accessibility.")
        sys.exit(1)

    source = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), source, "kCFRunLoopDefaultMode")
    CGEventTapEnable(tap, True)

    log.info("✅ CGEventTap active. Listening for cmd key...")
    CFRunLoopRun()


if __name__ == "__main__":
    main()
