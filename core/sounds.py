import os
import sys
import threading
from pathlib import Path


SOUNDS_DIR = Path(__file__).parent.parent / "assets" / "sounds"


class SoundManager:
    """Звуки событий."""

    def __init__(self):
        self.enabled = True
        self.volume = 0.7
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    def play(self, sound_name):
        """Проигрывает звук."""
        if not self.enabled:
            return

        # пробуем из файла
        sound_path = SOUNDS_DIR / f"{sound_name}.wav"
        if sound_path.exists():
            self._play_file(sound_path)
            return

        # fallback — синтез
        self._play_fallback(sound_name)

    def _play_file(self, path):
        """Проигрывает WAV-файл."""
        threading.Thread(
            target=self._play_file_thread,
            args=(path,),
            daemon=True,
        ).start()

    def _play_file_thread(self, path):
        try:
            if os.name == "nt":
                import winsound
                winsound.PlaySound(
                    str(path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC,
                )
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(
                    ["afplay", str(path)],
                    timeout=5,
                )
            else:
                import subprocess
                subprocess.run(
                    ["aplay", str(path)],
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass

    def _play_fallback(self, sound_name):
        """Синтезированный звук через winsound (Windows) или beep."""
        try:
            if os.name == "nt":
                import winsound

                # разные звуки для разных событий
                beeps = {
                    "message": [(800, 80)],
                    "connect": [(600, 60), (900, 80)],
                    "disconnect": [(500, 100), (400, 100)],
                    "error": [(300, 200)],
                    "file": [(700, 60), (900, 60), (1100, 60)],
                    "notification": [(1000, 100)],
                }

                seq = beeps.get(sound_name, [(700, 100)])
                for freq, dur in seq:
                    winsound.Beep(freq, dur)
            else:
                # простой beep
                sys.stdout.write("\a")
                sys.stdout.flush()
        except Exception:
            pass

    def play_message(self):
        self.play("message")

    def play_connect(self):
        self.play("connect")

    def play_disconnect(self):
        self.play("disconnect")

    def play_error(self):
        self.play("error")

    def play_file(self):
        self.play("file")

    def toggle(self, enabled):
        self.enabled = enabled
        return self.enabled

    def set_volume(self, volume):
        self.volume = max(0.0, min(1.0, volume))
        return self.volume