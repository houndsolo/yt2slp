"""Declared source generators for controlled evaluation, never search inputs.

Search/refinement consume video and annotations. These known controllers and
their replay posts are reserved for source preparation/post-selection checks.
"""
from dataclasses import dataclass

from .match import NEUTRAL_PADS, PadInput


@dataclass(frozen=True)
class ReferenceCase:
    neutral_steps: int
    active_steps: int
    stick_x: int

    @property
    def total_steps(self):
        return self.neutral_steps + self.active_steps

    def pads(self, step):
        if type(step) is not int or not 0 <= step < self.total_steps:
            raise ValueError("source step is outside its declared recording interval")
        return NEUTRAL_PADS if step < self.neutral_steps else (PadInput(stick_x=self.stick_x), *NEUTRAL_PADS[1:])

    @property
    def input_policy(self):
        return (f"{self.neutral_steps} neutral steps; {self.active_steps} steps P1 stick_x={self.stick_x}; "
                "other ports neutral/disconnected")


@dataclass(frozen=True)
class PhasedReferenceCase:
    """Independent source fixture; not a candidate grid or solver input."""
    total_steps: int
    phases: tuple[tuple[int, int], ...]

    def pads(self, step):
        if type(step) is not int or not 0 <= step < self.total_steps:
            raise ValueError("source step is outside its declared recording interval")
        axis = next(axis for start, axis in reversed(self.phases) if step >= start)
        return (PadInput(stick_x=axis), *NEUTRAL_PADS[1:])

    @property
    def input_policy(self):
        return (f"{self.total_steps} steps; P1 stick_x changes at zero-based request indices "
                f"{self.phases}; other ports neutral/disconnected")


@dataclass(frozen=True)
class JumpReferenceCase:
    """Known source controller kept outside reconstruction's candidate programs."""
    total_steps: int
    press_step: int
    held_steps: int

    def pads(self, step):
        if type(step) is not int or not 0 <= step < self.total_steps:
            raise ValueError("source step is outside its declared recording interval")
        pressed = self.press_step <= step < self.press_step + self.held_steps
        return (PadInput(button=0x400 if pressed else 0), *NEUTRAL_PADS[1:])

    @property
    def input_policy(self):
        return (f"{self.total_steps} steps; P1 X button held for {self.held_steps} requests "
                f"from zero-based request {self.press_step}; all axes neutral; other ports neutral/disconnected")


REFERENCE_CASES = {
    "fox-falco-battlefield-horizontal-v1": ReferenceCase(240, 180, 80),
    "fox-falco-battlefield-left-delayed-v1": ReferenceCase(246, 74, -80),
    "fox-falco-battlefield-right-release-left-v1": PhasedReferenceCase(
        320, ((0, 0), (240, 80), (256, 0), (264, -80))),
    "fox-falco-battlefield-jump-v1": JumpReferenceCase(320, 244, 2),
}


def validate_reference_report(report, replay_sha256, clip_sha256):
    """Bind source-video preparation to a complete, validated controlled clip."""
    if (report.get("case") not in REFERENCE_CASES or report.get("passed") is not True
            or report.get("native_vs_official_postframes", {}).get("passed") is not True
            or report.get("native_observation_phase_check", {}).get("passed") is not True
            or report.get("frame_alignment", {}).get("passed") is not True
            or report.get("frame_alignment", {}).get("interval") != [240, 300]):
        raise ValueError("source reference lacks complete state/frame validation")
    if report.get("native_replay_sha256") != replay_sha256 or report.get("reference_clip_sha256") != clip_sha256:
        raise ValueError("source replay/clip identity differs from validated reference")
    clip = report.get("reference_clip", {})
    if (clip.get("nb_read_frames") != "61" or clip.get("r_frame_rate") != "60/1"
            or [clip.get("width"), clip.get("height")] != [642, 528] or clip.get("codec_name") != "ffv1"):
        raise ValueError("unsupported source reference geometry/count/rate")
