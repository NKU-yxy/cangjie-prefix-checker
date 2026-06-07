# Vendored Cangjie Typechecker

This directory vendors the public `typechecker/typechecker` package from the
official `cangjie-fragment-checker` repository. It is used as a real parser and
semantic typechecker for contest fragments.

Only the typechecker package is vendored. Answer replay assets such as
`wrong_error_positions.json` and reference/faulty solver scripts are intentionally
not used by the runtime checker.
