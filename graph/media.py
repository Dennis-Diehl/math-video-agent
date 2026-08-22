"""Output paths for a pipeline run.

Scene modules, rendered videos and narration audio are keyed by the problem
being explained, so a second run cannot overwrite the first one's files. The
key is a hash rather than a timestamp, so re-running a problem reuses its
directory instead of creating a new one each time.
"""

import hashlib
import math
from pathlib import Path

# git-ignored, so generated files never reach version control.
MEDIA_DIR = Path("media")

# How many characters of the problem hash name a run's directory.
RUN_ID_LENGTH = 8

# The render quality fixes the frame rate, which the scene timing depends on:
# Manim truncates a pause to whole frames, so durations must be rounded up.
RENDER_QUALITY = "l"
FRAMES_PER_SECOND = 15


def whole_frames(seconds: float) -> float:
    """Round a duration up to the next whole frame."""
    return math.ceil(seconds * FRAMES_PER_SECOND) / FRAMES_PER_SECOND


def run_id(problem: str) -> str:
    """Derive a short, stable directory name from the problem being explained."""
    return hashlib.sha256(problem.encode()).hexdigest()[:RUN_ID_LENGTH]


def scene_stem(run: str, scene_number: int) -> str:
    """Name identifying one scene of one run, used for its files."""
    return f"{run}_scene_{scene_number}"


def scene_dir(run: str) -> Path:
    """Directory holding a run's generated Manim modules."""
    return MEDIA_DIR / "scenes" / run


def audio_dir(run: str) -> Path:
    """Directory holding a run's narration audio."""
    return MEDIA_DIR / "audio" / run
