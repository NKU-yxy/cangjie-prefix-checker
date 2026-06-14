"""Minimal transformers stub for xgrammar optional tokenizer imports.

The checker builds XGrammar TokenizerInfo directly from a raw token vocabulary
and never uses HuggingFace tokenizers.  XGrammar still imports these two classes
at module import time, so this stub avoids pulling the full transformers stack.
"""

from __future__ import annotations


class PreTrainedTokenizerBase:
    pass


class PreTrainedTokenizerFast(PreTrainedTokenizerBase):
    pass


class LogitsProcessor:
    def __call__(self, input_ids, scores):
        return scores


class _TransformersDummy:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, name):
        return _TransformersDummy()


def __getattr__(name: str):
    return type(name, (_TransformersDummy,), {})
