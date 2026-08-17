# XGrammar core provenance

This directory contains the unmodified C++ core files selected from XGrammar
tag `v0.2.1`, commit `5b4e9ce9e72524037ae24ecd831b9b6604d2eb48`:

<https://github.com/mlc-ai/xgrammar/tree/v0.2.1>

Python bindings, TVM FFI bindings, tests, documentation, and unrelated build
assets are intentionally omitted. The core is compiled directly into the
competition executable, so the grading build does not contact package indexes
or require XGrammar/TVM shared libraries or other downloaded packages.

XGrammar is Apache-2.0 licensed; see `LICENSE` and `NOTICE`. The selected
DLPack header is Apache-2.0 licensed; see `third_party/dlpack/LICENSE`.
PicoJSON retains its BSD-2-Clause notice in `third_party/picojson/picojson.h`.
