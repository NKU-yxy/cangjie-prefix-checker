# Vendored XGrammar core

This directory contains the minimal C++ core dependency closure from XGrammar
v0.2.1, upstream commit
`5b4e9ce9e72524037ae24ecd831b9b6604d2eb48`.  The source is distributed under
the bundled [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

The DLPack header is from the XGrammar-locked submodule commit
`bbd2f4d32427e548797929af08cfe2a9cbb3cf12`; its Apache-2.0 license is in
[`3rdparty/dlpack/LICENSE`](3rdparty/dlpack/LICENSE).  PicoJSON retains its full
copyright and redistribution notice in the source header and in
[`3rdparty/picojson/LICENSE.txt`](3rdparty/picojson/LICENSE.txt).

All bundled files are byte-identical to those upstream revisions except these
three files, each of which carries a prominent modification notice:

- `cpp/earley_parser.h`
- `cpp/earley_parser.cc`
- `cpp/grammar_matcher.cc`

The modification represents the exact Earley completion relation with complete
parser-state signatures and disjoint ranges of `rule_start_pos`.  Finalized-row
range summaries accelerate relation queries.  There is no activation condition
based on grammar text, identifier spelling or length, input source, tokenization,
machine, or benchmark configuration.

`build.sh` compiles every vendored translation unit into the private C++
namespace `xgrammar_g4`.  Production does not load the upstream Python wheel or
TVM FFI.  An explicit grammar-shadow build additionally loads the unmodified
v0.2.1 wheel in its original `xgrammar` namespace and compares both matchers.

Run `sha256sum -c vendor/xgrammar-v0.2.1/SOURCE_MANIFEST.sha256` from the
repository root to verify the 61-file core closure and its four license files.
