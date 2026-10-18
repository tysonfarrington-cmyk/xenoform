"""Morphs that blend two shots which already exist.

Nothing here loads a model. v2v-ramp and region-staged restyle on LTX 0.9.5
at a low strength. keyframe-blend and cross-clip mix frames and do not sample.
"""

from xenoform.morph.plan import plan_board, plan_join

__all__ = ["plan_board", "plan_join"]
