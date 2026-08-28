# Vendored headers and license records

This directory retains development-time headers and upstream license records.
The production build uses the source snapshot in `third_party/xgrammar_core/`
and does not link against precompiled libraries from this directory.

- `xgrammar/`: XGrammar 0.2.1 public C++ headers plus its Apache-2.0 license
  and NOTICE records.
- `tvm_ffi/`: Apache TVM FFI license and NOTICE records retained for provenance.

No precompiled `.so`, `.dylib`, or `.dll` is distributed in this directory.
See `../THIRD_PARTY_NOTICES.md` for the complete disclosure.
