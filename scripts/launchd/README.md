# launchd agents

macOS launchd plist templates for auto-starting voicemode services at login.

| File | Service | Port |
|------|---------|------|
| `com.voicemode.whisper.plist` | Whisper STT server | 2022 |
| `com.voicemode.kokoro.plist` | Kokoro TTS server | 8880 |
| `com.voicemode.hotkey.plist` | Push-to-talk hotkey daemon | — |

The Whisper and Kokoro plists are created automatically by `voicemode service enable whisper/kokoro`.
The hotkey plist must be installed manually — see the [Universal Dictation Setup guide](../../docs/guides/universal-dictation-setup.md).

## Installing

```bash
# Replace YOUR_USERNAME in the plist first
sed "s/YOUR_USERNAME/$USER/g" scripts/launchd/com.voicemode.hotkey.plist \
  > ~/Library/LaunchAgents/com.voicemode.hotkey.plist

launchctl load ~/Library/LaunchAgents/com.voicemode.hotkey.plist
```
