#!/usr/bin/env python3
"""
voicemode-hotkey: Push-to-talk daemon using VoiceMode's Whisper STT.

Hold cmd for 1 second to start recording, release to transcribe and inject text.
Uses ffmpeg for recording to avoid PortAudio audio ducking.
"""

import io
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
from pynput import keyboard

# Config
WHISPER_URL = "http://localhost:2022/v1/audio/transcriptions"
LOG_FILE = Path.home() / ".claude/plugins/claude-stt/voicemode_hotkey.log"
HOLD_DELAY = 1.0  # seconds to hold cmd before recording starts

# Sound feedback
SOUND_START = "/System/Library/Sounds/Tink.aiff"
SOUND_END = "/System/Library/Sounds/Pop.aiff"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.getLogger("voicemode-hotkey")

# State
_cmd_held = False
_recording = False
_ffmpeg_proc = None
_tmp_file = None
_lock = threading.Lock()
_hold_timer: threading.Timer | None = None


def _is_cmd(key):
    return key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r)


def _play_sound(path: str):
    subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _start_recording():
    global _recording, _ffmpeg_proc, _tmp_file
    with _lock:
        if _recording or not _cmd_held:
            return
        _recording = True

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    _tmp_file = tmp.name

    log.info("🎤 Recording started...")
    _play_sound(SOUND_START)

    _ffmpeg_proc = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-f", "avfoundation",
            "-i", ":0",          # default mic
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            _tmp_file,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_recording():
    global _recording, _ffmpeg_proc, _tmp_file
    with _lock:
        if not _recording:
            return
        _recording = False
        proc = _ffmpeg_proc
        tmp = _tmp_file
        _ffmpeg_proc = None
        _tmp_file = None

    if proc:
        proc.terminate()
        proc.wait()

    log.info("⏹️  Recording stopped, transcribing...")
    _play_sound(SOUND_END)

    if not tmp or not Path(tmp).exists():
        log.warning("No audio file captured.")
        return

    threading.Thread(target=_transcribe_and_inject, args=(tmp,), daemon=True).start()


def _transcribe_and_inject(wav_path: str):
    try:
        with open(wav_path, "rb") as f:
            audio_data = f.read()
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass

    if len(audio_data) < 4096:
        log.info("Audio too short, skipping.")
        return

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                WHISPER_URL,
                files={"file": ("audio.wav", io.BytesIO(audio_data), "audio/wav")},
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


def on_press(key):
    global _cmd_held, _hold_timer
    if not _is_cmd(key):
        # Cancel hold timer on any other key — it's a cmd+X shortcut
        if _hold_timer:
            _hold_timer.cancel()
            _hold_timer = None
        return

    if _cmd_held:
        return

    _cmd_held = True
    _hold_timer = threading.Timer(HOLD_DELAY, _start_recording)
    _hold_timer.start()


def on_release(key):
    global _cmd_held, _hold_timer
    if not _is_cmd(key):
        return

    _cmd_held = False

    if _hold_timer:
        _hold_timer.cancel()
        _hold_timer = None

    _stop_recording()


def main():
    log.info(f"voicemode-hotkey started. Hold cmd for {HOLD_DELAY}s to record, release to transcribe.")
    log.info(f"Whisper endpoint: {WHISPER_URL}")

    try:
        httpx.get("http://localhost:2022/health", timeout=2.0)
        log.info("✅ Whisper service is reachable.")
    except Exception:
        log.warning("⚠️  Whisper not reachable at port 2022. Start with: voicemode service start whisper")

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


if __name__ == "__main__":
    main()
