"""Lightweight torch stub for xgrammar optional imports.

XGrammar imports optional testing helpers and tvm_ffi checks a few torch symbols
at import time.  The checker never calls torch-dependent APIs, so this module
only provides enough shape compatibility to avoid installing torch/CUDA.
"""

from __future__ import annotations

import sys
import types


class _TorchDummy:
    def __init__(self, name: str = "torch.dummy"):
        self.__name__ = name

    def __call__(self, *args, **kwargs):
        return _TorchDummy(self.__name__ + "()")

    def __getattr__(self, name: str):
        return _TorchDummy(f"{self.__name__}.{name}")

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False

    def __repr__(self):
        return f"<{self.__name__}>"


class Tensor:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __getattr__(self, name: str):
        return _TorchDummy(f"torch.Tensor.{name}")


class dtype:
    def __init__(self, name: str = "torch.dtype"):
        self.name = name

    def __repr__(self):
        return self.name


class device:
    def __init__(self, value: str = "cpu"):
        self.type = value

    def __repr__(self):
        return self.type


class Size(tuple):
    pass


float16 = dtype("torch.float16")
float32 = dtype("torch.float32")
float64 = dtype("torch.float64")
bfloat16 = dtype("torch.bfloat16")
int8 = dtype("torch.int8")
int16 = dtype("torch.int16")
int32 = dtype("torch.int32")
int64 = dtype("torch.int64")
uint8 = dtype("torch.uint8")
bool = dtype("torch.bool")


def tensor(*args, **kwargs):
    return Tensor(*args, **kwargs)


def from_numpy(*args, **kwargs):
    return Tensor(*args, **kwargs)


def is_tensor(value):
    return isinstance(value, Tensor)


def __getattr__(name: str):
    return _TorchDummy(f"torch.{name}")


utils = types.ModuleType("torch.utils")
dlpack = types.ModuleType("torch.utils.dlpack")
dlpack.from_dlpack = lambda *args, **kwargs: Tensor(*args, **kwargs)
dlpack.to_dlpack = lambda *args, **kwargs: _TorchDummy("torch.utils.dlpack.to_dlpack")
utils.dlpack = dlpack
sys.modules.setdefault("torch.utils", utils)
sys.modules.setdefault("torch.utils.dlpack", dlpack)
