"""Job option objects passed to the engine.

engine.process_file() reads argparse-style attributes off its `args`
parameter; JobOptions provides the same attribute names so the GUI can
call the engine without argparse."""

from dataclasses import dataclass


@dataclass
class JobOptions:
    device: str = "cuda"
    language: str = "ru"
    pad: int = 100
    list_only: bool = False
    retranscribe: bool = False
    force_passes: bool = False
    no_vad: bool = False


def build_plan(engines_models) -> list:
    """[(engine, model), ...] one entry per pass. Thin helper so the UI
    has one place that produces the engine's plan format."""
    return list(engines_models)
