"""Adapt middle4originalICLblocks for new hourly relations;preserve public output path."""
from native_four_training import *

class MiddleTransitionBodyAdapter(NativeFourBodyAdapter):
    inference_only_checkpoint=True
    body_trainable_prefixes=tuple(f'icl_predictor.tf_icl.blocks.{i}.' for i in range(4,8))+tuple(f'icl_predictor.tf_icl.blocks.{i}.ffn_gate.' for i in range(8,12))
    # The value paths/attention of the last4,and final norm/decoder stay public.
    # Their derivatives still carry the middle-block gradient to the loss.
