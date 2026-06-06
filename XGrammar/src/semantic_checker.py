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
from typing import Any, Dict, List, Optional, Tuple

from .lexer import Token, TokenType


# ── Symbol info ───────────────────────────────────────────────────────────────

@dataclass
class SymbolInfo:
    name: str
    declared_type: Optional[str] = None
    kind: str = "variable"  # variable, function, class, param, field, constructor
    param_types: List[str] = field(default_factory=list)   # P1-2: func param types
    param_names: List[str] = field(default_factory=list)   # P1-2: func param names
    type_params: List[str] = field(default_factory=list)   # P1-4: func generic params
    constructors: List[List[str]] = field(default_factory=list)  # P1-5: init signatures
    fields: Dict[str, str] = field(default_factory=dict)   # P1-5: class fields


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
    def in_constructor(self) -> int:
        return sum(1 for t in self._tags if t == 'constructor')

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

    def __init__(self, preload_context: Optional[dict[str, Any]] = None):
        self.scopes = ScopeStack()

        # Declaration tracking
        self._decl_kw: Optional[TokenType] = None   # var / let / func / class / ...
        self._decl_name: Optional[str] = None        # name being declared
        self._decl_type: Optional[str] = None        # type annotation
        self._func_decl_name: Optional[str] = None   # P1-2: function name (not overwritten by params)

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

        # Lambda tracking: params collected before => is seen
        self._lambda_pending_params: List[Tuple[str, Optional[str]]] = []
        self._in_lambda_prefix: bool = False
        self._entering_lambda_body: bool = False

        # Type parameter tracking for generics: <T, U>
        self._in_type_params: bool = False
        self._pending_type_params: List[str] = []

        # Inheritance clause tracking: after <:, identifiers are types
        self._in_inheritance: bool = False

        # Class body context: deferred field declaration handling
        self._pending_class_ident: Optional[str] = None
        self._class_stack: List[str] = []

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

        # P1-1: Operator result type tracking
        self._expr_has_comparison: bool = False  # True if any comparison/logical op in current expr
        self._prev_text: str = ""  # Previous token text (for function call detection)

        # P1-2: Function call argument checking
        self._in_call_args: bool = False
        self._call_func_name: Optional[str] = None
        self._call_arg_types: List[str] = []
        self._call_paren_depth: int = 0
        self._last_call_return_type: Optional[str] = None
        self._call_kind: str = "function"
        self._call_type_args: List[str] = []
        self._call_stack: List[Tuple[Optional[str], List[str], int, str, List[str]]] = []

        # P1-5: Constructor-specific tracking
        self._constructor_return_pending: bool = False

        # P1-6: Expression-position generic construction
        self._generic_construct_name: Optional[str] = None
        self._generic_type_args: List[str] = []
        self._in_generic_construct_type_args: bool = False
        self._generic_construct_waiting_lparen: bool = False

        # Main function tracking (P1-3)
        self._has_main: bool = False

        if preload_context:
            self._preload_context(preload_context)

    # ── Public API ────────────────────────────────────────────────────────

    def _preload_context(self, context: dict[str, Any]) -> None:
        """Register competition-provided global declarations."""
        global_scope = self.scopes._stack[0]

        for variable in context.get("variables", []):
            name = variable.get("name") if isinstance(variable, dict) else None
            if not name:
                continue
            global_scope[str(name)] = SymbolInfo(
                name=str(name),
                kind="variable",
                declared_type=variable.get("type"),
            )

        for function in context.get("functions", []):
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not name:
                continue
            global_scope[str(name)] = SymbolInfo(
                name=str(name),
                kind="function",
                declared_type=function.get("return_type"),
                param_types=[p or "" for p in function.get("param_types", [])],
                param_names=[p or "" for p in function.get("param_names", [])],
                type_params=[p for p in function.get("type_params", []) if p],
            )

        for class_info in context.get("classes", []):
            if not isinstance(class_info, dict):
                continue
            name = class_info.get("name")
            if not name:
                continue
            global_scope[str(name)] = SymbolInfo(
                name=str(name),
                kind="class",
                declared_type=str(name),
                type_params=[p for p in class_info.get("type_params", []) if p],
                constructors=[
                    [p or "" for p in ctor]
                    for ctor in class_info.get("constructors", [])
                    if isinstance(ctor, list)
                ],
                fields=dict(class_info.get("fields", {})),
            )

        for interface in context.get("interfaces", []):
            if not isinstance(interface, dict):
                continue
            name = interface.get("name")
            if not name:
                continue
            global_scope[str(name)] = SymbolInfo(
                name=str(name),
                kind="interface",
                declared_type=str(name),
                type_params=[p for p in interface.get("type_params", []) if p],
            )

    def process(self, token: Token) -> SemanticResult:
        """Process one token. Returns SemanticResult."""
        tt = token.type
        text = token.text

        # Clear type tracking when starting a new statement
        if tt in _STATEMENT_START_TOKENS:
            # P1-1: Apply comparison→Bool conversion before type check
            resolved_type = self._resolve_expr_type()
            # Check deferred type compatibility before clearing
            if (self._expected_type is not None
                    and resolved_type is not None
                    and self._expected_type != resolved_type
                    and not _are_types_compatible(self._expected_type, resolved_type)):
                err_msg = (f"Type mismatch: expected '{self._expected_type}', "
                           f"got '{resolved_type}'")
                self._expected_type = None
                self._current_expr_type = None
                self._expr_has_comparison = False
                return SemanticResult(ok=False, error=err_msg, token_text=text)
            # Clear on statement boundary (next statement or block end)
            self._expected_type = None
            self._current_expr_type = None
            self._expr_has_comparison = False

        # Reset package/import path on tokens that can't be part of a path
        if self._in_package_path or self._in_import_path:
            if tt not in (TokenType.IDENTIFIER, TokenType.OP_DOT, TokenType.OP_STAR):
                self._in_package_path = False
                self._in_import_path = False

        # P1-3: Lambda prefix unwind — if we see a token that can't be part of
        # a lambda param list, this block is not a lambda. Validate any
        # identifiers that were collected as tentative param names.
        if self._in_lambda_prefix and tt not in _LAMBDA_PREFIX_VALID_TOKENS:
            unwind_err = self._unwind_lambda_prefix()
            if unwind_err is not None:
                self._advance(tt, text)
                return unwind_err
            # Fall through: the current token is processed normally below

        if self._constructor_return_pending:
            if tt in (TokenType.SEMICOLON, TokenType.RBRACE):
                self._constructor_return_pending = False
            else:
                self._constructor_return_pending = False
                self._advance(tt, text)
                return SemanticResult(
                    ok=False,
                    error="Constructor 'init' cannot return a value",
                    token_text=text,
                )

        if self._in_generic_construct_type_args:
            if tt == TokenType.IDENTIFIER:
                self._generic_type_args.append(text)
                self._advance(tt, text)
                return SemanticResult(ok=True, token_text=text)
            if tt == TokenType.COMMA:
                self._advance(tt, text)
                return SemanticResult(ok=True, token_text=text)
            if tt == TokenType.OP_GT:
                if not self._generic_type_args:
                    self._advance(tt, text)
                    return SemanticResult(
                        ok=False,
                        error="Generic construct requires at least one type argument",
                        token_text=text,
                    )
                self._in_generic_construct_type_args = False
                self._generic_construct_waiting_lparen = True
                self._advance(tt, text)
                return SemanticResult(ok=True, token_text=text)
            self._in_generic_construct_type_args = False
            self._generic_construct_waiting_lparen = False
            self._advance(tt, text)
            return SemanticResult(
                ok=False,
                error="Malformed generic construct: expected type argument or '>'",
                token_text=text,
            )

        if self._generic_construct_waiting_lparen and tt != TokenType.LPAREN:
            self._generic_construct_waiting_lparen = False
            self._generic_construct_name = None
            self._generic_type_args.clear()
            self._advance(tt, text)
            return SemanticResult(
                ok=False,
                error="Malformed generic construct: expected '(' after type arguments",
                token_text=text,
            )

        # --- Brace ---
        if tt == TokenType.LBRACE:
            return self._enter_brace(token)
        elif tt == TokenType.RBRACE:
            return self._exit_brace(token)

        # --- Paren ---
        elif tt == TokenType.LPAREN:
            self._paren_depth += 1
            if self._generic_construct_waiting_lparen:
                if self._generic_construct_name is None:
                    self._advance(tt, text)
                    return SemanticResult(
                        ok=False,
                        error="Malformed generic construct",
                        token_text=text,
                    )
                self._start_call(
                    self._generic_construct_name,
                    "generic_constructor",
                    self._generic_type_args,
                )
                self._generic_construct_name = None
                self._generic_type_args = []
                self._generic_construct_waiting_lparen = False
            elif self._decl_kw == TokenType.KW_FUNC and self._decl_name:
                self._in_params = True
                self._expecting_param_name = True
            elif (self._prev_type == TokenType.KW_THIS
                    and not self._in_params
                    and not self._in_call_args):
                current_class = self._current_class_name()
                if self.scopes.in_constructor == 0 or current_class is None:
                    self._advance(tt, text)
                    return SemanticResult(
                        ok=False,
                        error="'this(...)' constructor delegation outside init",
                        token_text=text,
                    )
                self._start_call(current_class, "constructor")
            # P1-2: Detect function call: IDENTIFIER followed by LPAREN
            elif (self._prev_type == TokenType.IDENTIFIER
                    and not self._in_params
                    ):
                func_name = self._prev_text
                sym = self.scopes.lookup(func_name)
                if sym is not None and sym.kind == "function":
                    self._start_call(func_name, "function")
                elif sym is not None and sym.kind == "class":
                    self._start_call(func_name, "constructor")
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        elif tt == TokenType.RPAREN:
            # P1-2: Collect last argument type before closing paren
            if self._in_call_args and self._paren_depth == self._call_paren_depth:
                resolved = self._resolve_expr_type()
                if resolved is not None:
                    self._call_arg_types.append(resolved)
                elif self._call_arg_types:
                    pass  # No expression before ) — e.g., f() with 0 args
                # Check for zero-arg call: if no commas were seen, arg_types is empty
                # Trigger signature check
                result = self._check_call_args(token)
                # Set current expr type to function's return type for nested calls
                func_sym = self.scopes.lookup(self._call_func_name) if self._call_func_name else None
                result_type = self._last_call_return_type
                if not result_type and func_sym and func_sym.declared_type:
                    result_type = func_sym.declared_type
                self._in_call_args = False
                self._call_func_name = None
                self._call_arg_types = []
                self._call_kind = "function"
                self._call_type_args = []
                if not result.ok:
                    self._paren_depth -= 1
                    return result
                if self._call_stack:
                    (self._call_func_name,
                     self._call_arg_types,
                     self._call_paren_depth,
                     self._call_kind,
                     self._call_type_args) = self._call_stack.pop()
                    self._in_call_args = True
                if result_type:
                    self._current_expr_type = result_type
                self._last_call_return_type = None
                self._expr_has_comparison = False
            # P1-1: Apply comparison→Bool at subexpression boundary
            elif self._expr_has_comparison and self._current_expr_type is not None:
                self._current_expr_type = "Bool"
                self._expr_has_comparison = False
            self._paren_depth -= 1
            if self._paren_depth == 0:
                self._in_params = False
                self._expecting_param_name = False
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Package / Import ---
        elif tt == TokenType.KW_PACKAGE:
            self._in_package_path = True
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        elif tt == TokenType.KW_IMPORT:
            self._in_import_path = True
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Modifier keywords (public, private, static) ---
        elif tt in _MODIFIER_KEYWORDS:
            self._in_package_path = False
            self._in_import_path = False
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Declaration keywords ---
        elif tt in _DECL_KEYWORDS:
            self._in_package_path = False
            self._in_import_path = False
            # init is special: no identifier, goes straight to params
            if tt == TokenType.KW_INIT:
                self._start_decl(tt)
                self._decl_name = "init"  # implicit name
                self._in_params = True
                self._expecting_param_name = True
                self._paren_depth = 0  # will be incremented by LPAREN
            else:
                self._start_decl(tt)
            return SemanticResult(ok=True, token_text=text)

        # --- Loop keywords ---
        elif tt in (TokenType.KW_WHILE, TokenType.KW_FOR, TokenType.KW_DO):
            self._entering_loop = True
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Identifier ---
        elif tt == TokenType.IDENTIFIER:
            result = self._handle_identifier(text, token)
            self._advance(tt, text)
            return result

        # --- Assignment operator ---
        elif tt == TokenType.OP_ASSIGN:
            # If in a var/let decl with a type annotation, expect that type
            if self._decl_kw in (TokenType.KW_VAR, TokenType.KW_LET) and self._decl_type:
                self._expected_type = self._decl_type
            self._current_expr_type = None  # Reset for RHS
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Colon ---
        elif tt == TokenType.COLON:
            # If we have a pending class ident, register it as a field now
            if self._pending_class_ident is not None:
                name = self._pending_class_ident
                ok, err = self.scopes.declare(name, kind="field")
                if not ok:
                    self._pending_class_ident = None
                    self._advance(tt, text)
                    return SemanticResult(ok=False, error=err, token_text=text)
                self._decl_name = name
                self._decl_kw = None  # Not a keyword decl, just a field
                self._pending_class_ident = None
                self._record_current_class_field(name)
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Comma in params / call args ---
        elif tt == TokenType.COMMA:
            if self._in_params:
                self._expecting_param_name = True
                self._decl_name = None
                self._decl_type = None
            # P1-2: Collect argument type at comma in call args
            if self._in_call_args:
                resolved = self._resolve_expr_type()
                if resolved is not None:
                    self._call_arg_types.append(resolved)
                self._expr_has_comparison = False
                self._current_expr_type = None
            # P1-1: Apply comparison→Bool at subexpression boundary
            elif self._expr_has_comparison and self._current_expr_type is not None:
                self._current_expr_type = "Bool"
                self._expr_has_comparison = False
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Semicolon ---
        elif tt == TokenType.SEMICOLON:
            self._in_package_path = False
            self._in_import_path = False
            # P1-1: Apply comparison→Bool conversion
            resolved_type = self._resolve_expr_type()
            # Type inference: if var/let without type annotation, infer from RHS
            if (self._decl_kw in (TokenType.KW_VAR, TokenType.KW_LET)
                    and self._decl_name
                    and not self._decl_type
                    and resolved_type):
                self.scopes.update_type(self._decl_name, resolved_type)
            # Check assignment type compatibility
            result = self._check_assignment_type(token)
            if not result.ok:
                return result
            if self._paren_depth == 0:
                self._end_decl()
            self._current_expr_type = None
            self._expected_type = None
            self._expr_has_comparison = False
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Break/Continue (P1-3) ---
        elif tt == TokenType.KW_BREAK:
            self._advance(tt, text)
            if self.scopes.in_loop == 0:
                return SemanticResult(
                    ok=False, error="'break' outside of loop", token_text=text
                )
            return SemanticResult(ok=True, token_text=text)

        elif tt == TokenType.KW_CONTINUE:
            self._advance(tt, text)
            if self.scopes.in_loop == 0:
                return SemanticResult(
                    ok=False, error="'continue' outside of loop", token_text=text
                )
            return SemanticResult(ok=True, token_text=text)

        # --- Return (P1-3 + P1-2) ---
        elif tt == TokenType.KW_RETURN:
            self._advance(tt, text)
            if self.scopes.in_func == 0 and self.scopes.in_constructor == 0:
                return SemanticResult(
                    ok=False, error="'return' outside of function",
                    token_text=text
                )
            if self.scopes.in_constructor > 0 and self.scopes.in_func == 0:
                self._constructor_return_pending = True
                self._expected_type = None
                self._current_expr_type = None
                return SemanticResult(ok=True, token_text=text)
            # Set expected type for return expression checking
            self._expected_type = self._func_return_type
            self._current_expr_type = None
            return SemanticResult(ok=True, token_text=text)

        # --- this ---
        elif tt == TokenType.KW_THIS:
            current_class = self._current_class_name()
            if current_class is None:
                self._advance(tt, text)
                return SemanticResult(
                    ok=False, error="'this' outside of class",
                    token_text=text
                )
            self._current_expr_type = current_class
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Literals: track expression type ---
        elif tt in _LITERAL_TYPES:
            self._current_expr_type = _LITERAL_TYPES[tt]
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        elif tt in _BOOL_LITERAL_TYPES:
            self._current_expr_type = "Bool"
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Lambda arrow ---
        elif tt == TokenType.OP_FAT_ARROW:
            # Register pending lambda params in the current scope
            if self._in_lambda_prefix:
                for pname, ptype in self._lambda_pending_params:
                    if pname:
                        self.scopes.declare(pname, kind="param", declared_type=ptype)
                self._lambda_pending_params.clear()
                self._in_lambda_prefix = False
                self._entering_lambda_body = True
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Type parameter start / Less-than comparison <T> ---
        elif tt == TokenType.OP_LT:
            # Enter type parameter mode if in a declaration that supports generics
            if (self._decl_kw in (TokenType.KW_FUNC, TokenType.KW_CLASS, TokenType.KW_STRUCT,
                                  TokenType.KW_ENUM, TokenType.KW_INTERFACE)
                    and self._decl_name is not None
                    and not self._in_params):
                self._in_type_params = True
                self._pending_type_params.clear()
            elif self._can_start_generic_construct():
                self._start_generic_construct(self._prev_text)
            else:
                # P1-1: Outside type params context, < is a comparison operator
                self._expr_has_comparison = True
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Type parameter end ---
        elif tt == TokenType.OP_GT:
            if self._in_type_params:
                # P1-4: Function generic params belong to the function symbol.
                # Other declaration kinds keep the previous scope-visible behavior.
                if self._decl_kw == TokenType.KW_FUNC and self._func_decl_name:
                    func_sym = self.scopes.lookup(self._func_decl_name)
                    if func_sym and func_sym.kind == "function":
                        func_sym.type_params = list(self._pending_type_params)
                elif self._decl_kw in (TokenType.KW_CLASS, TokenType.KW_STRUCT,
                                       TokenType.KW_ENUM, TokenType.KW_INTERFACE) and self._decl_name:
                    class_sym = self.scopes.lookup(self._decl_name)
                    if class_sym and class_sym.kind == "class":
                        class_sym.type_params = list(self._pending_type_params)
                else:
                    for tp_name in self._pending_type_params:
                        self.scopes.declare(tp_name, kind="class", declared_type=tp_name)
                self._pending_type_params.clear()
                self._in_type_params = False
            else:
                # P1-1: Outside type params, > is a comparison operator
                self._expr_has_comparison = True
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Inheritance <: ---
        elif tt == TokenType.OP_LT_COLON:
            self._in_inheritance = True
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Bit-and for type list separators ---
        elif tt == TokenType.OP_BIT_AND:
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Comparison operators: result type is Bool ---
        elif tt in _COMPARISON_OPS or tt in _LOGICAL_OPS:
            self._expr_has_comparison = True
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Arithmetic operators: keep numeric, doesn't change result type ---
        elif tt in _ARITHMETIC_OPS:
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

        # --- Default ---
        else:
            self._advance(tt, text)
            return SemanticResult(ok=True, token_text=text)

    def finalize(self) -> SemanticResult:
        """Check any deferred type compatibility at end of input."""
        if self._in_generic_construct_type_args or self._generic_construct_waiting_lparen:
            return SemanticResult(
                ok=False,
                error="Malformed generic construct",
                token_text="<end>",
            )
        resolved = self._resolve_expr_type()
        if (self._expected_type is not None
                and resolved is not None
                and self._expected_type != resolved
                and not _are_types_compatible(self._expected_type, resolved)):
            return SemanticResult(
                ok=False,
                error=f"Type mismatch: expected '{self._expected_type}', "
                      f"got '{resolved}'",
                token_text="<end>",
            )
        return SemanticResult(ok=True)

    # ── Internal: state tracking ──────────────────────────────────────────

    def _resolve_expr_type(self) -> Optional[str]:
        """Apply comparison→Bool conversion to current expression type (P1-1)."""
        if self._expr_has_comparison and self._current_expr_type is not None:
            return "Bool"
        return self._current_expr_type

    def _advance(self, tt: TokenType, text: str = "") -> None:
        self._prev2_type = self._prev_type
        self._prev_type = tt
        if text:
            self._prev_text = text

    def _start_decl(self, tt: TokenType) -> None:
        self._decl_kw = tt
        self._decl_name = None
        self._decl_type = None
        self._pending_params.clear()

    def _end_decl(self) -> None:
        self._decl_kw = None
        self._decl_name = None
        self._decl_type = None
        self._func_decl_name = None
        self._pending_params.clear()

    def _current_class_name(self) -> Optional[str]:
        return self._class_stack[-1] if self._class_stack else None

    def _start_call(
        self, name: str, kind: str = "function",
        type_args: Optional[List[str]] = None,
    ) -> None:
        if self._in_call_args:
            self._call_stack.append((
                self._call_func_name,
                list(self._call_arg_types),
                self._call_paren_depth,
                self._call_kind,
                list(self._call_type_args),
            ))
        self._in_call_args = True
        self._call_func_name = name
        self._call_kind = kind
        self._call_arg_types = []
        self._call_type_args = list(type_args or [])
        self._call_paren_depth = self._paren_depth
        self._last_call_return_type = None
        self._expr_has_comparison = False
        self._current_expr_type = None

    def _start_generic_construct(self, name: str) -> None:
        self._generic_construct_name = name
        self._generic_type_args = []
        self._in_generic_construct_type_args = True
        self._generic_construct_waiting_lparen = False
        self._expr_has_comparison = False
        self._current_expr_type = None

    def _can_start_generic_construct(self) -> bool:
        if self._prev_type != TokenType.IDENTIFIER:
            return False
        name = self._prev_text
        if name in _BUILTIN_GENERIC_ARITY:
            return True
        sym = self.scopes.lookup(name)
        return sym is not None and sym.kind == "class"

    def _record_current_class_field(
        self, name: str, declared_type: Optional[str] = None
    ) -> None:
        class_name = self._current_class_name()
        if class_name is None:
            return
        class_sym = self.scopes.lookup(class_name)
        if class_sym is not None and class_sym.kind == "class":
            class_sym.fields[name] = declared_type or class_sym.fields.get(name, "")

    def _register_constructor_signature(self, token: Token) -> SemanticResult:
        class_name = self._current_class_name()
        if class_name is None:
            return SemanticResult(
                ok=False, error="'init' outside of class", token_text=token.text
            )

        class_sym = self.scopes.lookup(class_name)
        if class_sym is None or class_sym.kind != "class":
            return SemanticResult(ok=True, token_text=token.text)

        signature = [ptype or "" for _, ptype in self._pending_params]
        if signature in class_sym.constructors:
            return SemanticResult(
                ok=False,
                error=f"Duplicate constructor in '{class_name}' with signature {signature}",
                token_text=token.text,
            )
        class_sym.constructors.append(signature)

        init_sym = self.scopes.lookup("init")
        if init_sym is None:
            ok, err = self.scopes.declare(
                "init", kind="constructor", declared_type=class_name
            )
            if not ok:
                return SemanticResult(ok=False, error=err, token_text=token.text)
            init_sym = self.scopes.lookup("init")
        if init_sym is not None and init_sym.kind != "constructor":
            return SemanticResult(
                ok=False,
                error=f"Duplicate declaration: 'init' (already declared as {init_sym.kind})",
                token_text=token.text,
            )
        if init_sym is not None:
            init_sym.param_types = signature
            init_sym.param_names = [pname for pname, _ in self._pending_params]
        return SemanticResult(ok=True, token_text=token.text)

    def _unwind_lambda_prefix(self) -> Optional[SemanticResult]:
        """P1-3: Clear lambda prefix mode and validate collected identifiers.

        Called when a non-lambda-prefix token proves this block is not a lambda.
        Any identifiers collected as tentative param names are looked up as
        regular variable references. Returns an error if any is undefined.
        Returns None if all identifiers are valid (caller falls through).
        """
        for pname, _ in self._lambda_pending_params:
            if pname:
                sym = self.scopes.lookup(pname)
                if sym is None and pname not in _BUILTIN_NAMES:
                    self._in_lambda_prefix = False
                    self._lambda_pending_params.clear()
                    return SemanticResult(
                        ok=False, error=f"Undefined variable: '{pname}'",
                        token_text=pname
                    )
                if sym is not None and sym.declared_type:
                    self._current_expr_type = sym.declared_type
        self._in_lambda_prefix = False
        self._lambda_pending_params.clear()
        return None

    # ── Internal: brace handling ──────────────────────────────────────────

    def _enter_brace(self, token: Token) -> SemanticResult:
        # Determine scope tag
        tag = "block"
        class_name_for_scope: Optional[str] = None

        if self._entering_loop:
            tag = "loop"
            self._entering_loop = False

        # Lambda body: block after => gets func tag for return support.
        # Also track that we entered a lambda body — this allows nested lambda
        # detection (P1-3).
        entered_lambda_body = self._entering_lambda_body
        if self._entering_lambda_body:
            tag = "func"
            self._entering_lambda_body = False

        # Func body: only tag the outermost func body, not nested blocks
        if tag == "block" and self._decl_kw == TokenType.KW_FUNC and self._decl_name is not None:
            tag = "func"

        if tag == "block" and self._decl_kw == TokenType.KW_INIT:
            tag = "constructor"

        # Class/struct/enum/interface body
        if tag == "block" and self._decl_kw in (TokenType.KW_CLASS, TokenType.KW_STRUCT,
                                                  TokenType.KW_ENUM, TokenType.KW_INTERFACE):
            tag = "class"
            class_name_for_scope = self._decl_name

        # Detect struct init: IDENT { ... } in expression context
        if (tag == "block"
                and not self._in_params
                and self._decl_kw in (None, TokenType.KW_VAR, TokenType.KW_LET)
                and self._prev_type == TokenType.IDENTIFIER
                and self._paren_depth == 0):
            # Likely struct init: Point { x: 0.0, y: 0.0 }
            self._in_struct_init = True

        # P1-3: Detect potential lambda context: { params => ... }
        # Also applicable when entering a lambda body (the body itself might
        # be a nested lambda expression like { y => x + y }).
        allow_lambda = (
            tag == "block"
            or (tag == "func" and entered_lambda_body)
        )
        if (allow_lambda
                and not self._in_struct_init
                and not self._in_params
                and self._decl_kw in (None, TokenType.KW_VAR, TokenType.KW_LET)):
            self._in_lambda_prefix = True
            self._lambda_pending_params.clear()

        # Clear inheritance context on entering body
        self._in_inheritance = False

        if tag == "constructor":
            result = self._register_constructor_signature(token)
            if not result.ok:
                self._pending_params.clear()
                self._end_decl()
                self._advance(TokenType.LBRACE)
                return result

        # Push scope
        self.scopes.push(tag)
        if tag == "class" and class_name_for_scope:
            self._class_stack.append(class_name_for_scope)

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

        # P1-2: Save param info to function's SymbolInfo for later call checking
        if tag == "func" and self._func_decl_name:
            func_sym = self.scopes.lookup(self._func_decl_name)
            if func_sym and func_sym.kind == "function":
                func_sym.param_types = [ptype or "" for _, ptype in self._pending_params]
                func_sym.param_names = [pname for pname, _ in self._pending_params]

        self._pending_params.clear()

        # Save func return type for return-statement checking
        if tag == "func" and self._decl_type:
            self._func_return_type = self._decl_type

        # Clear declaration context after entering body scope
        if tag in ("func", "class", "constructor"):
            self._end_decl()

        self._advance(TokenType.LBRACE)
        return SemanticResult(ok=True, token_text=token.text)

    def _exit_brace(self, token: Token) -> SemanticResult:
        tag = self.scopes.pop()
        self._in_struct_init = False
        self._pending_class_ident = None
        if tag == "constructor":
            self._constructor_return_pending = False
        # P1-3: If lambda prefix was never confirmed (no => seen), validate
        # the collected identifiers as regular variable references.
        if self._in_lambda_prefix:
            for pname, _ in self._lambda_pending_params:
                if pname:
                    sym = self.scopes.lookup(pname)
                    if sym is None and pname not in _BUILTIN_NAMES:
                        self._in_lambda_prefix = False
                        self._lambda_pending_params.clear()
                        if tag in ("func", "class"):
                            self._end_decl()
                        self._advance(TokenType.RBRACE)
                        return SemanticResult(
                            ok=False, error=f"Undefined variable: '{pname}'",
                            token_text=pname
                        )
            self._in_lambda_prefix = False
            self._lambda_pending_params.clear()
        if tag == "class" and self._class_stack:
            self._class_stack.pop()
        if tag in ("func", "class", "constructor"):
            self._end_decl()
        self._advance(TokenType.RBRACE)
        return SemanticResult(ok=True, token_text=token.text)

    # ── Internal: identifier handling ─────────────────────────────────────

    def _handle_identifier(self, text: str, token: Token) -> SemanticResult:
        # Case -3: Type parameter names in <T, U>
        if self._in_type_params:
            self._pending_type_params.append(text)
            return SemanticResult(ok=True, token_text=text)

        # Case -2: Lambda param prefix — collect param name, don't look up
        if self._in_lambda_prefix:
            # After COLON, this is the type of the last param
            if self._prev_type == TokenType.COLON and self._lambda_pending_params:
                last_name, _ = self._lambda_pending_params[-1]
                self._lambda_pending_params[-1] = (last_name, text)
            elif self._prev_type in (TokenType.COMMA, TokenType.LBRACE, None):
                # New lambda param name
                self._lambda_pending_params.append((text, None))
            return SemanticResult(ok=True, token_text=text)

        # Case -1: Struct init field label — don't look up
        if self._in_struct_init:
            return SemanticResult(ok=True, token_text=text)

        # Case -1b: Package/import path — skip lookup
        if self._in_package_path or self._in_import_path:
            return SemanticResult(ok=True, token_text=text)

        # Case -1c: Inheritance clause — identifiers are type references
        if self._in_inheritance:
            # Clear after seeing the first non-identifier, non-BIT_AND token
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
            self.scopes.update_type(self._func_decl_name or self._decl_name, text)
            return SemanticResult(ok=True, token_text=text)

        # Case 2: Type annotation (after colon in var/let decl)
        if (self._prev_type == TokenType.COLON
                and self._decl_name is not None
                and self._decl_kw in (TokenType.KW_VAR, TokenType.KW_LET, None)):
            self._decl_type = text
            self.scopes.update_type(self._decl_name, text)
            self._expected_type = text  # For assignment type checking
            if self.scopes.in_class_body:
                self._record_current_class_field(self._decl_name, text)
            return SemanticResult(ok=True, token_text=text)

        # Case 3: For-loop variable
        if self._prev2_type == TokenType.KW_FOR and self._prev_type == TokenType.LPAREN:
            self.scopes.declare(text, kind="variable")
            return SemanticResult(ok=True, token_text=text)

        # Case 3b: this.field access
        if self._prev_type == TokenType.OP_DOT and self._prev2_type == TokenType.KW_THIS:
            return self._lookup_this_field(text)

        # Case 3c: Dot notation member access (prev was DOT)
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
        elif kw in (TokenType.KW_VAR, TokenType.KW_LET) and self.scopes.in_class_body:
            kind = "field"

        ok, err = self.scopes.declare(text, kind=kind)
        if not ok:
            return SemanticResult(ok=False, error=err, token_text=text)

        self._decl_name = text
        if kind == "field":
            self._record_current_class_field(text)
        if kw == TokenType.KW_FUNC:
            self._func_decl_name = text  # P1-2: track func name separately
        return SemanticResult(ok=True, token_text=text)

    def _check_assignment_type(self, token: Token) -> SemanticResult:
        """Check type compatibility for assignments and returns."""
        resolved = self._resolve_expr_type()
        if (self._expected_type is not None
                and resolved is not None
                and self._expected_type != "Void"  # Void from no return type annotation
                and resolved != self._expected_type):
            if not _are_types_compatible(self._expected_type, resolved):
                return SemanticResult(
                    ok=False,
                    error=f"Type mismatch: expected '{self._expected_type}', "
                          f"got '{resolved}'",
                    token_text=token.text,
                )
        return SemanticResult(ok=True, token_text=token.text)

    def _lookup_this_field(self, text: str) -> SemanticResult:
        class_name = self._current_class_name()
        if class_name is None:
            return SemanticResult(
                ok=False, error="'this' outside of class", token_text=text
            )
        class_sym = self.scopes.lookup(class_name)
        if class_sym is None or class_sym.kind != "class":
            return SemanticResult(ok=True, token_text=text)
        if text not in class_sym.fields:
            return SemanticResult(
                ok=False,
                error=f"Unknown field '{text}' on '{class_name}'",
                token_text=text,
            )
        field_type = class_sym.fields.get(text)
        if field_type:
            self._current_expr_type = field_type
        return SemanticResult(ok=True, token_text=text)

    def _check_constructor_call_args(self, token: Token) -> SemanticResult:
        if not self._call_func_name:
            return SemanticResult(ok=True, token_text=token.text)

        class_name = self._call_func_name
        if class_name in _BUILTIN_GENERIC_ARITY:
            return self._check_builtin_generic_constructor_args(token)

        class_sym = self.scopes.lookup(class_name)
        if class_sym is None or class_sym.kind != "class":
            return SemanticResult(ok=True, token_text=token.text)

        if self._call_type_args:
            if len(self._call_type_args) != len(class_sym.type_params):
                return SemanticResult(
                    ok=False,
                    error=f"Generic constructor '{class_name}' expects "
                          f"{len(class_sym.type_params)} type arguments, "
                          f"got {len(self._call_type_args)}",
                    token_text=token.text,
                )
            type_bindings = dict(zip(class_sym.type_params, self._call_type_args))
        else:
            type_bindings = {}

        signatures = class_sym.constructors
        actual_count = len(self._call_arg_types)
        if not signatures:
            if actual_count == 0:
                self._last_call_return_type = class_name
                return SemanticResult(ok=True, token_text=token.text)
            return SemanticResult(
                ok=False,
                error=f"Constructor argument count mismatch in call to '{class_name}': "
                      f"expected 0, got {actual_count}",
                token_text=token.text,
            )

        count_matches = [sig for sig in signatures if len(sig) == actual_count]
        if not count_matches:
            expected_counts = sorted({len(sig) for sig in signatures})
            return SemanticResult(
                ok=False,
                error=f"Constructor argument count mismatch in call to '{class_name}': "
                      f"expected one of {expected_counts}, got {actual_count}",
                token_text=token.text,
            )

        first_type_error = ""
        for sig in count_matches:
            sig = [type_bindings.get(expected, expected) for expected in sig]
            ok = True
            for i, (expected, actual) in enumerate(zip(sig, self._call_arg_types)):
                if expected and actual and expected != actual:
                    if not _are_types_compatible(expected, actual):
                        ok = False
                        if not first_type_error:
                            first_type_error = (
                                f"Constructor argument {i + 1} type mismatch in call to "
                                f"'{class_name}': expected '{expected}', got '{actual}'"
                            )
                        break
            if ok:
                self._last_call_return_type = class_name
                return SemanticResult(ok=True, token_text=token.text)

        return SemanticResult(
            ok=False,
            error=first_type_error or f"No matching constructor for '{class_name}'",
            token_text=token.text,
        )

    def _check_builtin_generic_constructor_args(self, token: Token) -> SemanticResult:
        name = self._call_func_name or ""
        expected_arity = _BUILTIN_GENERIC_ARITY[name]
        if len(self._call_type_args) != expected_arity:
            return SemanticResult(
                ok=False,
                error=f"Generic constructor '{name}' expects {expected_arity} "
                      f"type arguments, got {len(self._call_type_args)}",
                token_text=token.text,
            )

        actual_count = len(self._call_arg_types)
        if name == "Array":
            if actual_count > 1:
                return SemanticResult(
                    ok=False,
                    error=f"Array constructor expects 0 or 1 arguments, got {actual_count}",
                    token_text=token.text,
                )
            if actual_count == 1 and self._call_arg_types[0] != "Int64":
                return SemanticResult(
                    ok=False,
                    error=f"Array constructor size expects 'Int64', got "
                          f"'{self._call_arg_types[0]}'",
                    token_text=token.text,
                )
        elif name == "Map":
            if actual_count != 0:
                return SemanticResult(
                    ok=False,
                    error=f"Map constructor expects 0 arguments, got {actual_count}",
                    token_text=token.text,
                )

        self._last_call_return_type = name
        return SemanticResult(ok=True, token_text=token.text)

    def _check_call_args(self, token: Token) -> SemanticResult:
        """P1-2/P1-4: Check function call args and infer generic return type."""
        self._last_call_return_type = None
        if self._call_kind in ("constructor", "generic_constructor"):
            return self._check_constructor_call_args(token)

        if not self._call_func_name:
            return SemanticResult(ok=True, token_text=token.text)

        func_sym = self.scopes.lookup(self._call_func_name)
        if func_sym is None or func_sym.kind != "function":
            return SemanticResult(ok=True, token_text=token.text)

        expected_params = func_sym.param_types
        expected_count = len(expected_params)
        actual_count = len(self._call_arg_types)

        if actual_count != expected_count:
            return SemanticResult(
                ok=False,
                error=f"Argument count mismatch in call to '{self._call_func_name}': "
                      f"expected {expected_count}, got {actual_count}",
                token_text=token.text,
            )

        type_bindings: Dict[str, str] = {}
        type_params = set(func_sym.type_params)

        for i, (expected, actual) in enumerate(zip(expected_params, self._call_arg_types)):
            if expected in type_params:
                if not actual:
                    return SemanticResult(
                        ok=False,
                        error=f"Cannot infer generic type parameter '{expected}' "
                              f"in call to '{self._call_func_name}'",
                        token_text=token.text,
                    )
                bound = type_bindings.get(expected)
                if bound is None:
                    type_bindings[expected] = actual
                elif bound != actual:
                    return SemanticResult(
                        ok=False,
                        error=f"Generic type parameter '{expected}' mismatch in "
                              f"call to '{self._call_func_name}': "
                              f"expected '{bound}', got '{actual}'",
                        token_text=token.text,
                    )
            elif expected and actual and expected != actual:
                if not _are_types_compatible(expected, actual):
                    return SemanticResult(
                        ok=False,
                        error=f"Argument {i + 1} type mismatch in call to "
                              f"'{self._call_func_name}': "
                              f"expected '{expected}', got '{actual}'",
                        token_text=token.text,
                    )

        return_type = func_sym.declared_type
        if return_type in type_params:
            inferred = type_bindings.get(return_type)
            if inferred is None:
                return SemanticResult(
                    ok=False,
                    error=f"Cannot infer generic return type '{return_type}' "
                          f"in call to '{self._call_func_name}'",
                    token_text=token.text,
                )
            self._last_call_return_type = inferred
        else:
            self._last_call_return_type = return_type

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
    TokenType.KW_INIT,
})

_MODIFIER_KEYWORDS = frozenset({
    TokenType.KW_PUBLIC, TokenType.KW_PRIVATE, TokenType.KW_STATIC,
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

# P1-1: Operator type classification
_COMPARISON_OPS = frozenset({
    TokenType.OP_EQ, TokenType.OP_NE,
    TokenType.OP_LT, TokenType.OP_GT,
    TokenType.OP_LE, TokenType.OP_GE,
})

_LOGICAL_OPS = frozenset({
    TokenType.OP_AND, TokenType.OP_OR,
})

_ARITHMETIC_OPS = frozenset({
    TokenType.OP_PLUS, TokenType.OP_MINUS,
    TokenType.OP_STAR, TokenType.OP_SLASH, TokenType.OP_PERCENT,
    TokenType.OP_POW, TokenType.OP_SHL, TokenType.OP_SHR,
    TokenType.OP_BIT_AND, TokenType.OP_BIT_OR, TokenType.OP_BIT_XOR,
})

_BUILTIN_NAMES: frozenset[str] = frozenset({
    "Int8", "Int16", "Int32", "Int64", "IntNative",
    "UInt8", "UInt16", "UInt32", "UInt64", "UIntNative",
    "Float16", "Float32", "Float64",
    "Bool", "Rune", "String", "Unit", "Nothing",
    "VArray", "This", "Array", "Map",
    "print", "println", "io", "math", "std",
    "_",
})

_BUILTIN_GENERIC_ARITY: dict[str, int] = {
    "Array": 1,
    "Map": 2,
}

# P1-3: Tokens that are valid inside a lambda param list (before => is seen)
_LAMBDA_PREFIX_VALID_TOKENS = frozenset({
    TokenType.IDENTIFIER,
    TokenType.COLON,
    TokenType.COMMA,
    TokenType.OP_FAT_ARROW,  # confirms lambda
    TokenType.OP_DOT,        # dotted type names like module.Type
    TokenType.RBRACE,        # handled by _exit_brace, not unwound here
})
