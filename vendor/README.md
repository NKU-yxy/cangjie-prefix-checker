# Vendored build/runtime files

This directory makes the competition build deterministic and independent of
package indexes or network access in the grading container.

- `xgrammar/`: XGrammar 0.2.1 public C++ headers and the Linux AArch64 shared
  library from its official wheel. The shared library was processed only with
  `strip --strip-unneeded`; SHA-256:
  `393c9ae05220a751636c231f4ef66142da242e313bb46c636b92804dabab18f6`.
- `tvm_ffi/`: Apache TVM FFI 0.1.13.post3 Linux AArch64 runtime shared library,
  unmodified; SHA-256:
  `87976356cf892e719d9a0a809160441fc2cd75ae55a249996d69675b07a81584`.

The corresponding Apache-2.0 license and NOTICE files are stored beside each
component. See `../THIRD_PARTY_NOTICES.md` for the complete disclosure.
