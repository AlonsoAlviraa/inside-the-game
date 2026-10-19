"""OpenTelemetry hooks.

ITG_OTEL=console  -> spans printed to stdout (needs opentelemetry-sdk)
ITG_OTEL=otlp     -> OTLP exporter (OTEL_EXPORTER_OTLP_ENDPOINT, e.g. Aspire dashboard / App Insights collector)
unset             -> no-op tracer (zero overhead)
Agent Framework's own instrumentation (chat, agent, tool and workflow spans) is enabled through
`agent_framework.observability.configure_otel_providers` when ITG_OTEL is set.
"""
from __future__ import annotations
import contextlib
import os
import time

try:
    from opentelemetry import trace as _otel
    _tracer = _otel.get_tracer("insidethegame.room")
except Exception:  # pragma: no cover
    _tracer = None

_configured = False


def setup() -> None:
    global _configured
    mode = os.getenv("ITG_OTEL", "").lower()
    if _configured or not mode:
        return
    _configured = True
    try:
        from agent_framework.observability import configure_otel_providers
        if mode == "console":
            configure_otel_providers(service_name="inside-the-game", enable_console_exporters=True)
        else:
            configure_otel_providers(service_name="inside-the-game")
    except Exception as e:  # never break the match because of telemetry
        print(f"[otel] disabled: {e!r}")


@contextlib.contextmanager
def span(name: str, trace_list: list | None = None, **attrs):
    """OTel span + an entry in the UI trace list (agent, ms, attributes)."""
    t0 = time.perf_counter()
    entry = {"agent": name, **attrs}
    cm = _tracer.start_as_current_span(f"itg.{name}") if _tracer else contextlib.nullcontext()
    with cm as s:
        try:
            yield entry
        finally:
            entry["ms"] = round((time.perf_counter() - t0) * 1000)
            if s is not None and hasattr(s, "set_attribute"):
                for k, v in entry.items():
                    if isinstance(v, (str, int, float, bool)):
                        s.set_attribute(f"itg.{k}", v)
            if trace_list is not None:
                trace_list.append(entry)
