"""Remove the line.back()==')' condition from Fix B's implicit_result_stable.

It misfires on (a) partial lines (mod2(n) < 2 == compound in progress),
(b) mid-block valid closed calls (m.add("a", 1)), causing false rejects.
FunctionClose boundary covers last-statement ')' anchoring.
"""
src = open("cpp/native_semantic.cpp").read()
old = """        const bool implicit_result_stable =
            active_statement.boundary == ActiveStatementCache::Boundary::FunctionClose ||
            (atomic && !first_open_source_function) ||
            (!line.empty() && line.back() == ')');"""
new = """        const bool implicit_result_stable =
            active_statement.boundary == ActiveStatementCache::Boundary::FunctionClose ||
            (atomic && !first_open_source_function);"""
assert src.count(old) == 1, f"pattern count={src.count(old)}"
open("cpp/native_semantic.cpp", "w").write(src.replace(old, new))
print("patched")
