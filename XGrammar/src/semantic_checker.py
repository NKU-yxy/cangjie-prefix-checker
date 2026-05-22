"""
Cangjie Semantic Checker -- incremental symbol-table tracking and type checking.

Operates alongside the syntax checker on the same token stream. Maintains
stack-based scopes for O(1) symbol operations.

Checks:
  1. Symbol table + scope (P1-1): declarations, lookups, duplicate detection
  2. Type inference & compatibility (P1-2): expression types, type mismatches
  3. Context constraints (P1-3): break/continue in loops, return in func, etc.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .lexer import Token, TokenType


# ── Symbol info ───────────────────────────────────────────────────────────────

@dataclass
class SymbolInfo:
    name: str
    declared_type: Optional[str] = None
    kind: str = "variable"  # variable, function, class, param, field


# ── Scope stack ───────────────────────────────────────────────────────────────

class ScopeStack:
    """Stack of symbol tables. Each { pushes, each } pops. O(1) all ops."""

    def __init__(self):
        self._stack: List[Dict[str, SymbolInfo]] = [{}]
        self._tags: List[str] = []  # 'func', 'loop', 'class', 'block'

    def push(self, tag: str = "block") -> None:
        self._stack.append({})
        self._tags.append(tag)

    def pop(self) -> Optional[str]:
        if len(self._stack) > 1:
            self._stack.pop()
            return self._tags.pop()
        return None

    @property
    def depth(self) -> int:
        return len(self._stack)

    @property
    def in_loop(self) -> int:
        return sum(1 for t in self._tags if t == 'loop')

    @property
    def in_func(self) -> int:
        return sum(1 for t in self._tags if t == 'func')

    @property
    def in_class_body(self) -> bool:
        """True if the innermost scope is a class/struct body."""
        return len(self._tags) > 0 and self._tags[-1] == 'class'

    def declare(self, name: str, kind: str = "variable",
                declared_type: Optional[str] = None) -> Tuple[bool, str]:
        """Declare in the innermost scope. Returns (ok, error_message)."""
        if name in self._stack[-1]:
            existing = self._stack[-1][name]
            return False, f"Duplicate declaration: '{name}' (already declared as {existing.kind})"
        self._stack[-1][name] = SymbolInfo(
            name=name, kind=kind, declared_type=declared_type
        )
        return True, ""

    def declare_in_scope(self, name: str, kind: str = "variable",
                         declared_type: Optional[str] = None) -> Tuple[bool, str]:
        """Declare in a specific scope. Used for pre-registering func params."""
        if name in self._stack[-1]:
            existing = self._stack[-1][name]
            return False, f"Duplicate declaration: '{name}' (already declared as {existing.kind})"
        self._stack[-1][name] = SymbolInfo(
            name=name, kind=kind, declared_type=declared_type
        )
        return True, ""

    def lookup(self, name: str) -> Optional[SymbolInfo]:
        """Search from innermost to outermost scope."""
        for scope in reversed(self._stack):
            if name in scope:
                return scope[name]
        return None

    def update_type(self, name: str, declared_type: str) -> bool:
        """Update the type of the most recent declaration of name."""
        for scope in reversed(self._stack):
            if name in scope:
                scope[name].declared_type = declared_type
                return True
        return False


# ── Semantic checker ──────────────────────────────────────────────────────────

@dataclass
class SemanticResult:
    """Per-token semantic check result."""
    ok: bool = True
    error: str = ""
    token_text: str = ""


class SemanticChecker:
    """Token-by-token semantic checker for Cangjie.

    Tracks declaration context and scope to register symbols and validate
    identifier references. Designed to consume the same token stream as
    the syntax checker, one token at a time.
    """

    def __init__(self):
        self.scopes = ScopeStack()

        # Declaration tracking
        self._decl_kw: Optional[TokenType] = None   # var / let / func / class / ...
        self._decl_name: Optional[str] = None        # name being declared
        self._decl_type: Optional[str] = None        # type annotation

        # params pending registration (func params registered when body scope pushes)
        self._pending_params: List[Tuple[str, Optional[str]]] = []

        # Paren / bracket tracking
        self._paren_depth: int = 0
        self._in_params: bool = False
        self._expecting_param_name: bool = False

        # Loop entry tracking (flag set by while/for/do, consumed by LBRACE)
        self._entering_loop: bool = False

        # Struct init context (Point { x: 0.0, y: 0.0 })
        self._in_struct_init: bool = False

        # Class body context: deferred field declaration handling
        self._pending_class_ident: Optional[str] = None

        # Package/import path tracking (don't look up identifiers in paths)
        self._in_package_path: bool = False
        self._in_import_path: bool = False

        # Main function check
        self._has_main: bool = False

        # Previous token tracking
        self._prev_type: Optional[TokenType] = None
        self._prev2_type: Optional[TokenType] = None

        # Expression type tracking (P1-2)
        self._current_expr_type: Optional[str] = None
        self._expected_type: Optional[str] = None  # For assignment/return checking
        self._func_return_type: Optional[str] = None  # Return type of current func
        self._pending_decl_type: Optional[str] = None  # Type from `: Type` annotation

        # Main function tracking (P1-3)
        self._has_main: bool = False

    # ── Public API ────────────────────────────────────────────────────────

    def process(self, token: Token) -> SemanticResult:
        """Process one token. Returns SemanticResult."""
        tt = token.type
        text = token.text

        # Clear type tracking when starting a new statement
        if tt in _STATEMENT_START_TOKENS:
            # Check deferred type compatibility before clearing
            if (self._expected_type is not None
                    and self._current_expr_type is not None
                    and self._expected_type != self._current_expr_type
                    and not _are_types_compatible(self._expected_type, self._current_expr_type)):
                err_msg = (f"Type mismatch: expected '{self._expected_type}', "
                           f"got '{self._current_expr_type}'")
                self._expected_type = None
                self._current_expr_type = None
                return SemanticResult(ok=False, error=err_msg, token_text=text)
            # Clear on statement boundary (next statement or block end)
            self._expected_type = None
            self._current_expr_type = None

        # Reset package/import path on tokens that can't be part of a path
        if self._in_package_path or self._in_import_path:
            if tt not in (TokenType.IDENTIFIER, TokenType.OP_DOT, TokenType.OP_STAR):
                self._in_package_path = False
                self._in_import_path = False

        # --- Brace ---
        if tt == TokenType.LBRACE:
            return self._enter_brace(token)
        elif tt == TokenType.RBRACE:
            return self._exit_brace(token)

        # --- Paren ---
        elif tt == TokenType.LPAREN:
            self._paren_depth += 1
            if self._decl_kw == TokenType.KW_FUNC and self._decl_name:
                self._in_params = True
                self._expecting_param_name = True
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        elif tt == TokenType.RPAREN:
            self._paren_depth -= 1
            if self._paren_depth == 0:
                self._in_params = False
                self._expecting_param_name = False
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        # --- Package / Import ---
        elif tt == TokenType.KW_PACKAGE:
            self._in_package_path = True
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        elif tt == TokenType.KW_IMPORT:
            self._in_import_path = True
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        # --- Declaration keywords ---
        elif tt in _DECL_KEYWORDS:
            self._in_package_path = False
            self._in_import_path = False
            self._start_decl(tt)
            return SemanticResult(ok=True, token_text=text)

        # --- Loop keywords ---
        elif tt in (TokenType.KW_WHILE, TokenType.KW_FOR, TokenType.KW_DO):
            self._entering_loop = True
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        # --- Identifier ---
        elif tt == TokenType.IDENTIFIER:
            result = self._handle_identifier(text, token)
            self._advance(tt)
            return result

        # --- Assignment operator ---
        elif tt == TokenType.OP_ASSIGN:
            # If in a var/let decl with a type annotation, expect that type
            if self._decl_kw in (TokenType.KW_VAR, TokenType.KW_LET) and self._decl_type:
                self._expected_type = self._decl_type
            self._current_expr_type = None  # Reset for RHS
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        # --- Colon ---
        elif tt == TokenType.COLON:
            # If we have a pending class ident, register it as a field now
            if self._pending_class_ident is not None:
                name = self._pending_class_ident
                ok, err = self.scopes.declare(name, kind="field")
                if not ok:
                    self._pending_class_ident = None
                    self._advance(tt)
                    return SemanticResult(ok=False, error=err, token_text=text)
                self._decl_name = name
                self._decl_kw = None  # Not a keyword decl, just a field
                self._pending_class_ident = None
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        # --- Comma in params ---
        elif tt == TokenType.COMMA:
            if self._in_params:
                self._expecting_param_name = True
                self._decl_name = None
                self._decl_type = None
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        # --- Semicolon ---
        elif tt == TokenType.SEMICOLON:
            self._in_package_path = False
            self._in_import_path = False
            # Type inference: if var/let without type annotation, infer from RHS
            if (self._decl_kw in (TokenType.KW_VAR, TokenType.KW_LET)
                    and self._decl_name
                    and not self._decl_type
                    and self._current_expr_type):
                self.scopes.update_type(self._decl_name, self._current_expr_type)
            # Check assignment type compatibility
            result = self._check_assignment_type(token)
            if not result.ok:
                return result
            if self._paren_depth == 0:
                self._end_decl()
            self._current_expr_type = None
            self._expected_type = None
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        # --- Break/Continue (P1-3) ---
        elif tt == TokenType.KW_BREAK:
            self._advance(tt)
            if self.scopes.in_loop == 0:
                return SemanticResult(
                    ok=False, error="'break' outside of loop", token_text=text
                )
            return SemanticResult(ok=True, token_text=text)

        elif tt == TokenType.KW_CONTINUE:
            self._advance(tt)
            if self.scopes.in_loop == 0:
                return SemanticResult(
                    ok=False, error="'continue' outside of loop", token_text=text
                )
            return SemanticResult(ok=True, token_text=text)

        # --- Return (P1-3 + P1-2) ---
        elif tt == TokenType.KW_RETURN:
            self._advance(tt)
            if self.scopes.in_func == 0:
                return SemanticResult(
                    ok=False, error="'return' outside of function",
                    token_text=text
                )
            # Set expected type for return expression checking
            self._expected_type = self._func_return_type
            self._current_expr_type = None
            return SemanticResult(ok=True, token_text=text)

        # --- Literals: track expression type ---
        elif tt in _LITERAL_TYPES:
            self._current_expr_type = _LITERAL_TYPES[tt]
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        elif tt in _BOOL_LITERAL_TYPES:
            self._current_expr_type = "Bool"
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

        # --- Default ---
        else:
            self._advance(tt)
            return SemanticResult(ok=True, token_text=text)

    def finalize(self) -> SemanticResult:
        """Check any deferred type compatibility at end of input."""
        if (self._expected_type is not None
                and self._current_expr_type is not None
                and self._expected_type != self._current_expr_type
                and not _are_types_compatible(self._expected_type, self._current_expr_type)):
            return SemanticResult(
                ok=False,
                error=f"Type mismatch: expected '{self._expected_type}', "
                      f"got '{self._current_expr_type}'",
                token_text="<end>",
            )
        return SemanticResult(ok=True)

    # ── Internal: state tracking ──────────────────────────────────────────

    def _advance(self, tt: TokenType) -> None:
        self._prev2_type = self._prev_type
        self._prev_type = tt

    def _start_decl(self, tt: TokenType) -> None:
        self._decl_kw = tt
        self._decl_name = None
        self._decl_type = None
        self._pending_params.clear()

    def _end_decl(self) -> None:
        self._decl_kw = None
        self._decl_name = None
        self._decl_type = None
        self._pending_params.clear()

    # ── Internal: brace handling ──────────────────────────────────────────

    def _enter_brace(self, token: Token) -> SemanticResult:
        # Determine scope tag
        tag = "block"

        if self._entering_loop:
            tag = "loop"
            self._entering_loop = False

        # Func body: only tag the outermost func body, not nested blocks
        if tag == "block" and self._decl_kw == TokenType.KW_FUNC and self._decl_name is not None:
            tag = "func"

        # Class/struct/enum/interface body
        if tag == "block" and self._decl_kw in (TokenType.KW_CLASS, TokenType.KW_STRUCT,
                                                  TokenType.KW_ENUM, TokenType.KW_INTERFACE):
            tag = "class"

        # Detect struct init: IDENT { ... } in expression context
        if (tag == "block"
                and not self._in_params
                and self._decl_kw in (None, TokenType.KW_VAR, TokenType.KW_LET)
                and self._prev_type == TokenType.IDENTIFIER
                and self._paren_depth == 0):
            # Likely struct init: Point { x: 0.0, y: 0.0 }
            self._in_struct_init = True

        # Push scope
        self.scopes.push(tag)

        # Register pending params in the new scope (func body)
        for pname, ptype in self._pending_params:
            if pname:
                ok, err = self.scopes.declare(pname, kind="param", declared_type=ptype)
                if not ok:
                    self._pending_params.clear()
                    if tag in ("func", "class"):
                        self._end_decl()
                    self._advance(TokenType.LBRACE)
                    return SemanticResult(ok=False, error=err, token_text=token.text)
        self._pending_params.clear()

        # Save func return type for return-statement checking
        if tag == "func" and self._decl_type:
            self._func_return_type = self._decl_type

        # Clear declaration context after entering body scope
        if tag in ("func", "class"):
            self._end_decl()

        self._advance(TokenType.LBRACE)
        return SemanticResult(ok=True, token_text=token.text)

    def _exit_brace(self, token: Token) -> SemanticResult:
        tag = self.scopes.pop()
        self._in_struct_init = False
        self._pending_class_ident = None
        if tag in ("func", "class"):
            self._end_decl()
        self._advance(TokenType.RBRACE)
        return SemanticResult(ok=True, token_text=token.text)

    # ── Internal: identifier handling ─────────────────────────────────────

    def _handle_identifier(self, text: str, token: Token) -> SemanticResult:
        # Case -1: Struct init field label — don't look up
        if self._in_struct_init:
            return SemanticResult(ok=True, token_text=text)

        # Case -1b: Package/import path — skip lookup
        if self._in_package_path or self._in_import_path:
            return SemanticResult(ok=True, token_text=text)

        # Case 0: Param name in function declaration
        if self._in_params and self._expecting_param_name:
            # Check duplicate in pending params
            if text in [p[0] for p in self._pending_params]:
                return SemanticResult(
                    ok=False,
                    error=f"Duplicate parameter: '{text}'",
                    token_text=text
                )
            self._pending_params.append((text, None))
            self._decl_name = text
            self._expecting_param_name = False
            return SemanticResult(ok=True, token_text=text)

        # Case 0b: Type annotation in params (after colon)
        if self._in_params and self._prev_type == TokenType.COLON and self._decl_name is not None:
            # This is the type of the current param
            if self._pending_params:
                last_name, _ = self._pending_params[-1]
                self._pending_params[-1] = (last_name, text)
                self._decl_type = text
            return SemanticResult(ok=True, token_text=text)

        # Case 1: Declaration name (just saw var/let/func/class etc.)
        if self._decl_kw is not None and self._decl_name is None:
            return self._register_declaration(text)

        # Case 1b: Func return type (after colon, after params closed)
        if (self._prev_type == TokenType.COLON
                and self._decl_kw == TokenType.KW_FUNC
                and self._decl_name is not None
                and not self._in_params):
            self._decl_type = text
            self.scopes.update_type(self._decl_name, text)
            return SemanticResult(ok=True, token_text=text)

        # Case 2: Type annotation (after colon in var/let decl)
        if (self._prev_type == TokenType.COLON
                and self._decl_name is not None
                and self._decl_kw in (TokenType.KW_VAR, TokenType.KW_LET, None)):
            self._decl_type = text
            self.scopes.update_type(self._decl_name, text)
            self._expected_type = text  # For assignment type checking
            return SemanticResult(ok=True, token_text=text)

        # Case 3: For-loop variable
        if self._prev2_type == TokenType.KW_FOR and self._prev_type == TokenType.LPAREN:
            self.scopes.declare(text, kind="variable")
            return SemanticResult(ok=True, token_text=text)

        # Case 3b: Dot notation member access (prev was DOT)
        if self._prev_type == TokenType.OP_DOT:
            return SemanticResult(ok=True, token_text=text)

        # Case 4: Class body - potential field declaration (IDENT : Type)
        if self.scopes.in_class_body and self._decl_kw is None:
            sym = self.scopes.lookup(text)
            if sym is None and text not in _BUILTIN_NAMES:
                self._pending_class_ident = text
                return SemanticResult(ok=True, token_text=text)
            if sym is not None:
                return SemanticResult(ok=True, token_text=text)

        # Case 5: Expression context - lookup
        return self._lookup_identifier(text)

    def _register_declaration(self, text: str) -> SemanticResult:
        """Register a newly declared name in the current scope."""
        kw = self._decl_kw

        kind = "variable"
        if kw == TokenType.KW_FUNC:
            kind = "function"
            # Check main() duplication (P1-3)
            if text == "main":
                if self._has_main:
                    return SemanticResult(
                        ok=False,
                        error="Duplicate 'main' function",
                        token_text=text,
                    )
                self._has_main = True
        elif kw in (TokenType.KW_CLASS, TokenType.KW_STRUCT,
                    TokenType.KW_ENUM, TokenType.KW_INTERFACE):
            kind = "class"

        ok, err = self.scopes.declare(text, kind=kind)
        if not ok:
            return SemanticResult(ok=False, error=err, token_text=text)

        self._decl_name = text
        return SemanticResult(ok=True, token_text=text)

    def _check_assignment_type(self, token: Token) -> SemanticResult:
        """Check type compatibility for assignments and returns."""
        if (self._expected_type is not None
                and self._current_expr_type is not None
                and self._expected_type != "Void"  # Void from no return type annotation
                and self._current_expr_type != self._expected_type):
            if not _are_types_compatible(self._expected_type, self._current_expr_type):
                return SemanticResult(
                    ok=False,
                    error=f"Type mismatch: expected '{self._expected_type}', "
                          f"got '{self._current_expr_type}'",
                    token_text=token.text,
                )
        return SemanticResult(ok=True, token_text=token.text)

    def _lookup_identifier(self, text: str) -> SemanticResult:
        """Look up identifier in scope stack and track its type."""
        if text in _BUILTIN_NAMES:
            if text in _NUMERIC_TYPES or text in ("String", "Bool", "Rune", "Float64", "Float32", "Float16"):
                self._current_expr_type = text
            return SemanticResult(ok=True, token_text=text)

        sym = self.scopes.lookup(text)
        if sym is None:
            # main() without 'func' keyword — implicit main function declaration
            if text == "main" and not self._in_params and self._paren_depth == 0:
                if self._has_main:
                    return SemanticResult(
                        ok=False,
                        error="Duplicate 'main' function",
                        token_text=text,
                    )
                self._has_main = True
                self.scopes.declare(text, kind="function")
                return SemanticResult(ok=True, token_text=text)
            return SemanticResult(
                ok=False,
                error=f"Undefined variable: '{text}'",
                token_text=text
            )
        # Track the symbol's type for expression type inference
        if sym.declared_type:
            self._current_expr_type = sym.declared_type
        elif sym.kind == "function":
            pass  # Function references don't have a simple type
        return SemanticResult(ok=True, token_text=text)


# ── Type inference (P1-2) ────────────────────────────────────────────────────

# Maps Cangjie literal token types to their default types
_LITERAL_TYPES: dict[TokenType, str] = {
    TokenType.INTEGER_LITERAL: "Int64",
    TokenType.FLOAT_LITERAL: "Float64",
    TokenType.STRING_LITERAL: "String",
    TokenType.MULTILINE_STRING: "String",
    TokenType.RUNE_LITERAL: "Rune",
}

# Maps Cangjie boolean keyword token types
_BOOL_LITERAL_TYPES: dict[TokenType, str] = {
    TokenType.KW_TRUE: "Bool",
    TokenType.KW_FALSE: "Bool",
}

# Numeric type categories
_INT_TYPES = frozenset({
    "Int8", "Int16", "Int32", "Int64", "IntNative",
    "UInt8", "UInt16", "UInt32", "UInt64", "UIntNative",
})
_FLOAT_TYPES = frozenset({"Float16", "Float32", "Float64"})
_NUMERIC_TYPES = _INT_TYPES | _FLOAT_TYPES


def _is_numeric(t: Optional[str]) -> bool:
    return t in _NUMERIC_TYPES if t else False


def _are_types_compatible(expected: str, actual: str) -> bool:
    """Check if actual type can be assigned to expected type."""
    if expected == actual:
        return True
    # Numeric promotion: int -> float OK
    if expected in _FLOAT_TYPES and actual in _INT_TYPES:
        return True
    # Int narrowing: larger -> smaller OK with potential truncation
    if expected in _INT_TYPES and actual in _INT_TYPES:
        return True
    if expected in _FLOAT_TYPES and actual in _FLOAT_TYPES:
        return True
    if expected == "Bool" and actual == "Bool":
        return True
    if expected == "String" and actual == "String":
        return True
    return False


# ── Constants ─────────────────────────────────────────────────────────────────

_DECL_KEYWORDS = frozenset({
    TokenType.KW_VAR, TokenType.KW_LET, TokenType.KW_FUNC,
    TokenType.KW_CLASS, TokenType.KW_STRUCT, TokenType.KW_ENUM,
    TokenType.KW_INTERFACE, TokenType.KW_EXTEND,
})

# Tokens that start a new statement (trigger deferred type check)
_STATEMENT_START_TOKENS = frozenset({
    TokenType.KW_VAR, TokenType.KW_LET, TokenType.KW_FUNC,
    TokenType.KW_CLASS, TokenType.KW_STRUCT, TokenType.KW_ENUM,
    TokenType.KW_INTERFACE, TokenType.KW_EXTEND,
    TokenType.KW_IF, TokenType.KW_WHILE, TokenType.KW_FOR,
    TokenType.KW_DO, TokenType.KW_RETURN, TokenType.KW_BREAK,
    TokenType.KW_CONTINUE, TokenType.KW_THROW, TokenType.KW_TRY,
    TokenType.KW_MATCH, TokenType.KW_PACKAGE, TokenType.KW_IMPORT,
    TokenType.RBRACE,
})

_BUILTIN_NAMES: frozenset[str] = frozenset({
    "Int8", "Int16", "Int32", "Int64", "IntNative",
    "UInt8", "UInt16", "UInt32", "UInt64", "UIntNative",
    "Float16", "Float32", "Float64",
    "Bool", "Rune", "String", "Unit", "Nothing",
    "VArray", "This",
    "print", "println", "io", "math", "std",
    "_",
})
