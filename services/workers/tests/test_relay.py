import threading

from card_maven.shared.outbox import RelayResult
from card_maven_workers.relay import run_relay


class ScriptedRelay:
    def __init__(self, script: list[RelayResult | Exception], stop: threading.Event) -> None:
        self.script = list(script)
        self.stop = stop
        self.calls = 0

    def run_once(self) -> RelayResult:
        self.calls += 1
        if not self.script:
            self.stop.set()
            return RelayResult(0, 0)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def test_drains_without_sleeping_then_stops() -> None:
    stop = threading.Event()
    relay = ScriptedRelay([RelayResult(100, 0), RelayResult(5, 1)], stop)
    published = run_relay(relay, poll_interval_seconds=0.001, stop=stop)  # type: ignore[arg-type]
    assert published == 105
    assert relay.calls == 3


def test_survives_iteration_errors() -> None:
    stop = threading.Event()
    relay = ScriptedRelay([RuntimeError("db down"), RelayResult(2, 0)], stop)
    assert run_relay(relay, poll_interval_seconds=0.001, stop=stop) == 2  # type: ignore[arg-type]


def test_max_iterations_bounds_the_loop() -> None:
    stop = threading.Event()
    relay = ScriptedRelay([RelayResult(0, 0)] * 10, stop)
    run_relay(relay, poll_interval_seconds=0.001, stop=stop, max_iterations=3)  # type: ignore[arg-type]
    assert relay.calls == 3


def test_already_stopped() -> None:
    stop = threading.Event()
    stop.set()
    relay = ScriptedRelay([RelayResult(1, 0)], stop)
    assert run_relay(relay, poll_interval_seconds=1, stop=stop) == 0  # type: ignore[arg-type]
    assert relay.calls == 0
