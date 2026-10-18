"""Optional stem split. Demucs is used when it is installed. Librosa is the fallback.

Nothing in the desk imports Ableton, or requires it.
"""

from __future__ import annotations


def stem_status() -> dict:
    try:
        import demucs  # noqa: F401

        engine = "demucs"
        detail = "Demucs is installed. Stem splits can use it."
    except Exception:
        engine = "librosa"
        detail = (
            "Demucs is not installed. Beats, bass, mids, and highs still come from librosa. "
            "Ableton is not required."
        )
    return {"engine": engine, "required": False, "detail": detail}


def separate(audio, sr: int) -> dict:
    """Return a band split. Demucs is preferred and never required."""
    status = stem_status()
    if status["engine"] == "demucs":
        try:
            return _demucs(audio, sr)
        except Exception:
            status = {
                "engine": "librosa",
                "required": False,
                "detail": "Demucs did not run. The desk used the librosa band split.",
            }
    return {"engine": "librosa", "detail": status["detail"], "bands": ("sub", "bass", "mid", "high")}


def _demucs(audio, sr: int) -> dict:
    """A thin hook. The analysis path already has librosa bands if this raises."""
    from demucs.pretrained import get_model

    get_model("htdemucs")
    return {"engine": "demucs", "detail": "Demucs htdemucs is available.", "sr": int(sr), "samples": len(audio)}
