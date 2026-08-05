# Vendored Cangjie Typechecker

This directory vendors the public `typechecker/typechecker` package from the
competition reference repository:

<https://gitcode.com/bhzhan/cangjie-fragment-checker>

The vendored base is identified in the available project records as the public
snapshot dated 2026-06-07. No independently auditable commit SHA was retained.
It is used as a complete-program parser and semantic oracle for contest
fragments.

Only the typechecker package is vendored. Public answer replay assets and sample
solver scripts are intentionally not included. This directory is development
and test material: it supports differential tests, random-program labelling and
experiment reproduction, but is not compiled, linked or loaded by `solution`.

Relative to the public snapshot, the local copy functionally adapts
`builtin_context.py`, `checker.py`, `context.json`, `type_inference.py` and
`type_services.py`. Excluding the uniform provenance headers, the retained
development record is approximately 98 inserted and 76 deleted lines. These
functional changes expand offline coverage for iteration types, string
operations, default constructors and interface implementations. In addition,
every vendored Python/Lark source that supports comments carries a non-functional
provenance header; therefore a direct filesystem diff reports more changed files
and inserted lines than the functional-change figures above.

Neither the upstream files nor these local adaptations are claimed as original
team work or counted in the team's original-code volume. The upstream snapshot
did not contain a separate LICENSE/NOTICE file, so this repository does not
infer or assert a general open-source licence. See the top-level
`THIRD_PARTY_NOTICES.md` for the complete attribution and submission boundary.
