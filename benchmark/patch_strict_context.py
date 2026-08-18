"""Restrict strict_generic (never-bind-T) to BUILTIN generic global functions.

Official checker binds T for user-defined generics (bad<T>(a: T, b: T, ...)
with consistent args ACCEPTS) but never for builtin min/max (min(1, 2) even
REJECTS).  Mark context-table functions as from_context and gate strict.
"""
src = open("cpp/native_semantic.cpp").read()

# 1. FunctionSig field
old1 = """    std::string result = "Unit";
    std::size_t required = 0;
    bool is_static = false;
};"""
new1 = """    std::string result = "Unit";
    std::size_t required = 0;
    bool is_static = false;
    bool from_context = false;
};"""
assert src.count(old1) == 1, f"field: {src.count(old1)}"
src = src.replace(old1, new1)

# 2. mark global functions loaded from the context table
old2 = """    for (FunctionSig& sig : reader.Signatures()) {
        model->functions[sig.name].push_back(std::move(sig));
    }"""
new2 = """    for (FunctionSig& sig : reader.Signatures()) {
        sig.from_context = true;
        model->functions[sig.name].push_back(std::move(sig));
    }"""
assert src.count(old2) == 1, f"mark: {src.count(old2)}"
src = src.replace(old2, new2)

# 3. strict_generic gate: every generic candidate must come from the context
old3 = """            strict_generic = strict_generic &&
                std::any_of(function->second.begin(), function->second.end(),
                            [](const FunctionSig& sig) { return !sig.type_params.empty(); });"""
new3 = """            strict_generic = strict_generic &&
                std::any_of(function->second.begin(), function->second.end(),
                            [](const FunctionSig& sig) { return !sig.type_params.empty(); }) &&
                std::all_of(function->second.begin(), function->second.end(),
                            [](const FunctionSig& sig) { return sig.from_context; });"""
assert src.count(old3) == 1, f"gate: {src.count(old3)}"
src = src.replace(old3, new3)

open("cpp/native_semantic.cpp", "w").write(src)
print("patched")
