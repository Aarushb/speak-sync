"""Unit tests for SpeechService (Prism wrapper)."""

from __future__ import annotations

from speak_dropbox.services.speech import SpeechService


class _FakePrismBackend:
    name = "FakeNVDA"

    def __init__(self) -> None:
        self.spoken: list[tuple[str, bool]] = []
        self.brailled: list[str] = []
        self.outputted: list[tuple[str, bool]] = []
        self.stopped: int = 0

    def speak(self, text: str, interrupt: bool = True) -> None:
        self.spoken.append((text, interrupt))

    def braille(self, text: str) -> None:
        self.brailled.append(text)

    def output(self, text: str, interrupt: bool = True) -> None:
        self.outputted.append((text, interrupt))

    def stop(self) -> None:
        self.stopped += 1


def test_speech_service_output_and_braille() -> None:
    fake = _FakePrismBackend()
    svc = SpeechService(enabled=True, backend=fake)

    assert svc.is_available is True
    assert svc.backend_name == "FakeNVDA"

    assert svc.output("Dropbox: Up to date", interrupt=True) is True
    assert fake.outputted == [("Dropbox: Up to date", True)]
    assert svc.last_spoken_text == "Dropbox: Up to date"

    assert svc.speak("Google Drive: Syncing", interrupt=False) is True
    assert fake.spoken == [("Google Drive: Syncing", False)]

    assert svc.braille("OneDrive: Up to date") is True
    assert fake.brailled == ["OneDrive: Up to date"]

    svc.stop()
    assert fake.stopped == 1


def test_speech_service_disabled_vs_force() -> None:
    fake = _FakePrismBackend()
    svc = SpeechService(enabled=False, backend=fake)

    assert svc.output("Background transition") is False
    assert fake.outputted == []

    # On-demand hotkey query with force=True still speaks even when transition speech is disabled
    assert svc.output("Dropbox: Up to date", force=True) is True
    assert fake.outputted == [("Dropbox: Up to date", True)]
