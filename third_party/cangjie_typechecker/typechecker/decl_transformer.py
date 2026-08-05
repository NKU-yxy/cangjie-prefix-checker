# Vendored from the competition reference implementation:
# https://gitcode.com/bhzhan/cangjie-fragment-checker
# Not claimed as team-original code; provenance and adaptations are documented
# in ../README.md and the repository-level THIRD_PARTY_NOTICES.md.

"""Lark ``Transformer`` helpers for declaration/header lowering (params/class/method/ctors)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from lark import Token
from lark.tree import Tree
from lark.visitors import Transformer

from typechecker.ast import (
    ClassDecl,
    ConstructorDecl,
    Expr,
    FuncDecl,
    InterfaceDecl,
    MethodDecl,
    ProgramDecls,
    Ty,
    TyNominal,
)
from typechecker.error_codes import E_INTERNAL_UNKNOWN_SYNTAX_MESSAGE, DECL_SYNTAX_CODES
from typechecker.errors import internal_error, syntax_error
from typechecker.expr_transformer import lower_expr_tree
from typechecker.type_transformer import parse_type, parse_wrapped_type

_TYPE_SHAPES = frozenset({"simple_type", "primitive_type", "paren_type_form", "func_suffix", "type"})


def _syntax(key: str, message: str, node: object = None):
    code = DECL_SYNTAX_CODES.get(key)
    if code is None:
        raise internal_error(E_INTERNAL_UNKNOWN_SYNTAX_MESSAGE, f"unknown decl syntax key: {key}")
    return syntax_error(code, message, node)


def _parse_type_node(node: object, tset: set[str]) -> Ty:
    if isinstance(node, Token):
        return parse_type(node, tset)
    if isinstance(node, Tree):
        return parse_wrapped_type(node, tset)
    raise _syntax("EXPECTED_TYPE_NODE", "expected type node", node)


class DeclTransformer(Transformer):
    """Lower declaration subtrees to checker-ready Python values."""

    def __init__(self, tparams: set[str]) -> None:
        super().__init__()
        self.tparams = tparams

    def _coerce_type_child(self, c: object) -> Ty | None:
        if isinstance(c, Tree) and c.data in _TYPE_SHAPES:
            return parse_wrapped_type(c, self.tparams)
        if isinstance(c, Tree) and c.data == "type_annotation":
            if len(c.children) != 1:
                raise _syntax("TYPE_ANNOT_MALFORMED", "type_annotation: malformed")
            return _parse_type_node(c.children[0], self.tparams)
        if isinstance(c, Token):
            if c.type in {"IDENT", "INT64", "FLOAT64", "BOOL", "RUNE", "UNIT"}:
                return parse_type(c, self.tparams)
            return None
        return None

    def type_list(self, children: list[object]) -> List[Ty]:
        out: List[Ty] = []
        for c in children:
            ty = self._coerce_type_child(c)
            if ty is not None:
                out.append(ty)
        return out

    def parameter(self, children: list[object]) -> Tuple[Optional[str], Ty]:
        if len(children) != 1 or not isinstance(children[0], tuple) or len(children[0]) != 2:
            raise _syntax("PARAM_EXPECTED_TYPED", "parameter: expected lowered typed parameter")
        return children[0]

    def typed_parameter(self, children: list[object]) -> Tuple[Optional[str], Ty]:
        if not children or not isinstance(children[0], Token) or children[0].type != "IDENT":
            raise _syntax("TYPED_PARAM_EXPECTED_IDENT", "typed_parameter: expected identifier")
        vn = str(children[0].value)
        for c in children[1:]:
            ty = self._coerce_type_child(c)
            if ty is not None:
                return vn, ty
        raise _syntax("TYPED_PARAM_MISSING_TYPE", "typed_parameter: missing parameter type")

    def parameter_list(self, children: list[object]) -> Tuple[Tuple[Optional[str], ...], Tuple[Ty, ...]]:
        names: List[Optional[str]] = []
        tys: List[Ty] = []
        for c in children:
            if isinstance(c, tuple) and len(c) == 2:
                names.append(c[0])
                tys.append(c[1])
        return tuple(names), tuple(tys)


def parse_params(plist: Optional[Tree], tparams: set[str]) -> Tuple[Tuple[Optional[str], ...], Tuple[Ty, ...]]:
    if plist is None:
        return (), ()
    out = DeclTransformer(tparams).transform(plist)
    if not isinstance(out, tuple) or len(out) != 2:
        raise _syntax("PARAM_LIST_BAD_OUT", "parameter_list did not transform to (names, types)", plist)
    return out


@dataclass(frozen=True)
class ParsedFunction:
    name: str
    type_params: Tuple[str, ...]
    param_names: Tuple[Optional[str], ...]
    param_types: Tuple[Ty, ...]
    ret: Ty
    body: Expr


@dataclass(frozen=True)
class ParsedMethod:
    name: str
    is_static: bool
    type_params: Tuple[str, ...]
    param_names: Tuple[Optional[str], ...]
    param_types: Tuple[Ty, ...]
    ret: Ty
    body: Expr


@dataclass(frozen=True)
class ParsedInterface:
    name: str
    type_params: Tuple[str, ...]
    supers: Tuple[TyNominal, ...]
    body: Tree


@dataclass(frozen=True)
class ParsedClassHeader:
    name: str
    type_params: Tuple[str, ...]
    supers: Tuple[TyNominal, ...]
    body: Tree


@dataclass(frozen=True)
class ParsedClassMembers:
    fields: Dict[str, Ty]
    static_fields: Dict[str, Ty]
    method_defs: Tuple[Tree, ...]
    constructors: Tuple[Tree, ...]


@dataclass(frozen=True)
class _FieldMember:
    is_static: bool
    name: str
    ty: Ty


@dataclass(frozen=True)
class _MethodMember:
    tree: Tree


@dataclass(frozen=True)
class _ConstructorMember:
    tree: Tree


class _ClassMemberTransformer(Transformer):
    def __init__(self, tset: set[str]) -> None:
        super().__init__()
        self.tset = tset

    def class_member(self, children: list[object]) -> object:
        if len(children) != 1:
            raise _syntax("CLASS_MEMBER_MALFORMED", "class_member: malformed")
        return children[0]

    def class_field_member(self, children: list[object]) -> _FieldMember:
        if len(children) != 1:
            raise _syntax("CLASS_FIELD_MEMBER_MALFORMED", "class_field_member: malformed")
        field_tree = _expect_tree(children[0], "field_let_decl", "class_field_member")
        is_static, name, ty = _parse_field_decl(field_tree, self.tset)
        return _FieldMember(is_static, name, ty)

    def class_method_member(self, children: list[object]) -> _MethodMember:
        if len(children) != 1:
            raise _syntax("CLASS_METHOD_MEMBER_MALFORMED", "class_method_member: malformed")
        method_tree = _expect_tree(children[0], "method_definition", "class_method_member")
        return _MethodMember(method_tree)

    def class_constructor_member(self, children: list[object]) -> _ConstructorMember:
        if len(children) != 1:
            raise _syntax("CLASS_CTOR_MEMBER_MALFORMED", "class_constructor_member: malformed")
        ctor_tree = _expect_tree(children[0], "constructor_definition", "class_constructor_member")
        return _ConstructorMember(ctor_tree)


def _expect_tree(node: object, rule_name: str, context: str) -> Tree:
    if not isinstance(node, Tree) or node.data != rule_name:
        raise _syntax("EXPECTED_TREE_RULE", f"{context}: expected {rule_name}", node)
    return node


def _unwrap_optional_child(node: object, opt_rule: str, child_rule: str, context: str) -> Optional[Tree]:
    opt = _expect_tree(node, opt_rule, context)
    if not opt.children:
        return None
    if len(opt.children) != 1:
        raise _syntax("MALFORMED_OPTIONAL_WRAPPER", f"{context}: malformed {opt_rule}", opt)
    child = opt.children[0]
    return _expect_tree(child, child_rule, context)


def _parse_opt_type_parameters(node: Tree) -> Tuple[str, ...]:
    tp = _unwrap_optional_child(node, "opt_type_parameters", "type_parameters", "opt_type_parameters")
    if tp is None:
        return ()
    return tuple(str(c.value) for c in tp.children if isinstance(c, Token) and c.type == "IDENT")


def _as_nominal(t: Ty, where: object) -> TyNominal:
    if not isinstance(t, TyNominal):
        raise _syntax("EXPECTED_NOMINAL_TYPE", "expected nominal type", where)
    return t


def _parse_nominal_type_list(tl: object, tset: set[str]) -> List[TyNominal]:
    out: List[TyNominal] = []
    if isinstance(tl, Tree) and tl.data == "type_list":
        for c in tl.children:
            if isinstance(c, Tree) and c.data in _TYPE_SHAPES:
                out.append(_as_nominal(parse_wrapped_type(c, tset), c))
    return out


def parse_type_after_colon(children: Tuple[object, ...], tset: set[str]) -> Ty:
    # lambda_param: IDENT [type_annotation]
    for c in children[1:]:
        if isinstance(c, Tree) and c.data == "type_annotation":
            if len(c.children) != 1:
                raise _syntax("TYPE_ANNOT_MALFORMED", "type_annotation: malformed")
            return _parse_type_node(c.children[0], tset)
        if isinstance(c, Tree) and c.data in _TYPE_SHAPES:
            return parse_wrapped_type(c, tset)
        if isinstance(c, Token):
            return parse_type(c, tset)
    raise _syntax("TYPE_AFTER_COLON_NOT_FOUND", "type after colon not found")


def _parse_ret_clause(node: Tree, tset: set[str]) -> Ty:
    if node.data != "ret_clause" or len(node.children) != 1 or not isinstance(node.children[0], Tree):
        raise _syntax("RET_CLAUSE_MALFORMED", "ret_clause: malformed", node)
    annot = node.children[0]
    if annot.data != "type_annotation" or len(annot.children) != 1:
        raise _syntax("RET_CLAUSE_MISSING_ANNOT", "ret_clause: missing type_annotation", node)
    return _parse_type_node(annot.children[0], tset)


def _extract_ident_from_named_node(node: Tree, kind: str) -> str:
    if node.data != kind or len(node.children) != 1 or not isinstance(node.children[0], Token) or node.children[0].type != "IDENT":
        raise _syntax("MALFORMED_NAMED_NODE", f"{kind}: malformed", node)
    return str(node.children[0].value)


def _extract_parameter_list_from_param_wrapper(node: Tree, kind: str) -> Optional[Tree]:
    wrapper = _expect_tree(node, kind, kind)
    if len(wrapper.children) != 1:
        raise _syntax("MALFORMED_NAMED_NODE", f"{kind}: malformed", wrapper)
    clause = _expect_tree(wrapper.children[0], "param_clause", kind)
    if len(clause.children) != 1:
        raise _syntax("MALFORMED_PARAM_CLAUSE", f"{kind}: malformed param_clause", clause)
    return _unwrap_optional_child(clause.children[0], "opt_parameter_list", "parameter_list", kind)


def parse_function_decl(fd: Tree) -> ParsedFunction:
    """Lower ``function_definition`` tree to a typed header/body record."""

    ch = fd.children
    if len(ch) != 2 or not isinstance(ch[1], Tree) or ch[1].data != "block_expression":
        raise _syntax("FUNC_DEF_BAD_SHAPE", "function_definition: expected header + block body", fd)
    hdr, body = ch
    if isinstance(hdr, Tree) and hdr.data == "main_header":
        if len(hdr.children) != 2:
            raise _syntax("MAIN_HEADER_MALFORMED", "main_header: malformed", hdr)
        ret_clause = _expect_tree(hdr.children[1], "ret_clause", "main_header")
        rt = _parse_ret_clause(ret_clause, set())
        return ParsedFunction("main", (), (), (), rt, body)
    if not isinstance(hdr, Tree) or hdr.data != "function_header":
        raise _syntax("FUNC_DEF_EXPECTED_HEADER", "function_definition: expected function_header/main_header", fd)
    if len(hdr.children) != 5:
        raise _syntax("FUNC_HEADER_MALFORMED", "function_header: malformed", hdr)
    lead, name_node, tps_node, params_node, r_clause = hdr.children
    if not isinstance(lead, Tree) or lead.data != "function_lead":
        raise _syntax("FUNC_HEADER_MISSING_LEAD", "function_header: missing function_lead", hdr)
    if not isinstance(name_node, Tree) or name_node.data != "function_name":
        raise _syntax("FUNC_HEADER_EXPECTED_NAME", "function_header: expected function name", hdr)
    name = _extract_ident_from_named_node(name_node, "function_name")
    tps = _parse_opt_type_parameters(_expect_tree(tps_node, "opt_type_parameters", "function_header"))
    tset = set(tps)
    if not isinstance(params_node, Tree) or params_node.data != "function_params":
        raise _syntax("FUNC_HEADER_EXPECTED_PARAMS", "function_header: expected function_params", hdr)
    plist = _extract_parameter_list_from_param_wrapper(params_node, "function_params")
    if not isinstance(r_clause, Tree) or r_clause.data != "ret_clause":
        raise _syntax("FUNC_HEADER_EXPECTED_RET", "function_header: expected ret_clause", hdr)
    rt = _parse_ret_clause(r_clause, tset)
    pn, pt = parse_params(plist, tset)
    return ParsedFunction(name, tps, pn, pt, rt, body)


def parse_method_decl(m: Tree, ambient: set[str], *, body_stub: bool) -> ParsedMethod:
    """Lower ``method_definition`` / ``abstract_method`` tree to a typed header/body record."""

    header_children = m.children
    body_node: Tree | None = None
    if m.data == "method_definition":
        if len(m.children) != 2 or not isinstance(m.children[0], Tree) or m.children[0].data != "method_header":
            raise _syntax("METHOD_DEF_BAD_SHAPE", "method_definition: expected method_header + block body", m)
        header_children = m.children[0].children
        if isinstance(m.children[1], Tree) and m.children[1].data == "block_expression":
            body_node = m.children[1]
    elif m.data == "abstract_method":
        header_children = m.children
    elif m.data == "method_header":
        header_children = m.children

    ch = header_children
    if len(ch) != 5:
        raise _syntax("METHOD_HEADER_MALFORMED", "method header: malformed", m)
    if m.data == "abstract_method":
        lead, name_node, tps_node, params_node, r_clause = ch
        if not isinstance(lead, Tree) or lead.data != "abstract_method_lead":
            raise _syntax("ABSTRACT_METHOD_MISSING_LEAD", "abstract_method: missing abstract_method_lead", m)
        st = False
    else:
        lead, name_node, tps_node, params_node, r_clause = ch
        if not isinstance(lead, Tree) or lead.data != "method_lead":
            raise _syntax("METHOD_DEF_MISSING_LEAD", "method_definition: missing method_lead", m)
        st = any(isinstance(c, Token) and c.type == "STATIC" for c in lead.children)
    if not isinstance(name_node, Tree) or name_node.data != "method_name":
        raise _syntax("METHOD_DEF_EXPECTED_NAME", "method_definition: expected method name", m)
    nm = _extract_ident_from_named_node(name_node, "method_name")
    mtps = _parse_opt_type_parameters(_expect_tree(tps_node, "opt_type_parameters", "method_definition"))
    mset = set(ambient) | set(mtps)
    params_kind = "method_params"
    if not isinstance(params_node, Tree) or params_node.data != params_kind:
        raise _syntax("METHOD_DEF_EXPECTED_PARAMS", "method_definition: expected method_params", m)
    plist = _extract_parameter_list_from_param_wrapper(params_node, params_kind)
    if not isinstance(r_clause, Tree) or r_clause.data != "ret_clause":
        raise _syntax("METHOD_DEF_EXPECTED_RET", "method_definition: expected ret_clause", m)
    rt = _parse_ret_clause(r_clause, mset)
    body = Tree("block_expression", []) if body_stub else body_node
    if body is None:
        raise _syntax("METHOD_DEF_EXPECTED_BODY", "method_definition: expected block body", m)
    pn, pt = parse_params(plist, mset)
    return ParsedMethod(nm, st, mtps, pn, pt, rt, body)


def parse_interface_decl(it: Tree) -> ParsedInterface:
    """Lower ``interface_declaration`` header/body."""

    ch = it.children
    if len(ch) != 5:
        raise _syntax("INTERFACE_DECL_MALFORMED", "interface_declaration: malformed", it)
    lead, name_node, tps_node, subtype_node, body = ch
    if not isinstance(lead, Tree) or lead.data != "interface_lead":
        raise _syntax("INTERFACE_DECL_MISSING_LEAD", "interface_declaration: missing interface_lead", it)
    if not isinstance(name_node, Tree) or name_node.data != "interface_name":
        raise _syntax("INTERFACE_DECL_EXPECTED_NAME", "interface_declaration: expected interface_name", it)
    name = _extract_ident_from_named_node(name_node, "interface_name")
    tps = _parse_opt_type_parameters(_expect_tree(tps_node, "opt_type_parameters", "interface_declaration"))
    tset = set(tps)
    subtype_clause = _unwrap_optional_child(
        subtype_node, "opt_interface_subtype_clause", "interface_subtype_clause", "interface_declaration"
    )
    supers: List[TyNominal] = []
    if subtype_clause is not None and subtype_clause.children:
        supers.extend(_parse_nominal_type_list(subtype_clause.children[0], tset))
    if not isinstance(body, Tree) or body.data != "interface_body":
        raise _syntax("INTERFACE_DECL_EXPECTED_BODY", "interface_declaration: expected interface_body", it)
    return ParsedInterface(name, tps, tuple(supers), body)


def parse_class_header(ct: Tree) -> ParsedClassHeader:
    """Lower ``class_definition`` header/body."""

    ch = ct.children
    if len(ch) != 5:
        raise _syntax("CLASS_DECL_MALFORMED", "class_definition: malformed", ct)
    lead, name_node, tps_node, subtype_node, body = ch
    if not isinstance(lead, Tree) or lead.data != "class_lead":
        raise _syntax("CLASS_DECL_MISSING_LEAD", "class_definition: missing class_lead", ct)
    if not isinstance(name_node, Tree) or name_node.data != "class_name":
        raise _syntax("CLASS_DECL_EXPECTED_NAME", "class_definition: expected class_name", ct)
    name = _extract_ident_from_named_node(name_node, "class_name")
    tps = _parse_opt_type_parameters(_expect_tree(tps_node, "opt_type_parameters", "class_definition"))
    tset = set(tps)
    clause = _unwrap_optional_child(subtype_node, "opt_class_subtype_clause", "class_subtype_clause", "class_definition")
    supers: List[TyNominal] = []
    if clause is not None:
        if not clause.children:
            raise _syntax("CLASS_SUBTYPE_MISSING_SUPER", "class_subtype_clause: missing superclass", clause)
        supers.append(_as_nominal(_parse_type_node(clause.children[0], tset), clause.children[0]))
        if len(clause.children) > 1:
            supers.extend(_parse_nominal_type_list(clause.children[1], tset))
    if not isinstance(body, Tree) or body.data != "class_body":
        raise _syntax("CLASS_DECL_EXPECTED_BODY", "class_definition: expected class_body", ct)
    return ParsedClassHeader(name, tps, tuple(supers), body)


def _parse_field_decl(mem: Tree, tset: set[str]) -> tuple[bool, str, Ty]:
    if mem.data != "field_let_decl":
        raise _syntax("FIELD_EXPECTED_DECL", "field_let_decl expected", mem)
    if len(mem.children) < 2 or not isinstance(mem.children[0], Tree) or mem.children[0].data != "field_lead":
        raise _syntax("FIELD_MISSING_LEAD", "field_let_decl: missing field_lead", mem)
    lead = mem.children[0]
    is_static = any(isinstance(c, Token) and c.type == "STATIC" for c in lead.children)
    if not isinstance(mem.children[1], Tree) or mem.children[1].data != "typed_name":
        raise _syntax("FIELD_TYPED_NAME_NOT_FOUND", "field_let_decl: typed_name not found", mem)
    typed = mem.children[1]
    if len(typed.children) != 2 or not isinstance(typed.children[0], Token) or typed.children[0].type != "IDENT":
        raise _syntax("FIELD_TYPED_NAME_MALFORMED", "field_let_decl: malformed typed_name", typed)
    if not isinstance(typed.children[1], Tree) or typed.children[1].data != "type_annotation":
        raise _syntax("FIELD_TYPED_NAME_MISSING_ANNOT", "field_let_decl: typed_name missing type_annotation", typed)
    annot = typed.children[1]
    if len(annot.children) != 1:
        raise _syntax("FIELD_ANNOT_MALFORMED", "field_let_decl: malformed type_annotation", annot)
    return is_static, str(typed.children[0].value), _parse_type_node(annot.children[0], tset)


def parse_class_members(body: Tree, tset: set[str]) -> ParsedClassMembers:
    """Lower class body members: fields/static fields + ctor/method buckets."""
    if body.data != "class_body":
        raise _syntax("CLASS_MEMBERS_EXPECTED_BODY", "parse_class_members: expected class_body", body)
    fields: Dict[str, Ty] = {}
    static_fields: Dict[str, Ty] = {}
    method_defs: List[Tree] = []
    constructors: List[Tree] = []
    member_transformer = _ClassMemberTransformer(tset)
    for mem in body.children:
        if not isinstance(mem, Tree):
            continue
        lowered = member_transformer.transform(mem)
        if isinstance(lowered, _FieldMember):
            (static_fields if lowered.is_static else fields)[lowered.name] = lowered.ty
            continue
        if isinstance(lowered, _MethodMember):
            method_defs.append(lowered.tree)
            continue
        if isinstance(lowered, _ConstructorMember):
            constructors.append(lowered.tree)
            continue
        raise _syntax("CLASS_MEMBERS_UNKNOWN_LOWERED", "parse_class_members: unknown lowered class member", mem)
    return ParsedClassMembers(fields, static_fields, tuple(method_defs), tuple(constructors))


def _parse_constructor_decl(ctor_tree: Tree, tset: set[str]) -> ConstructorDecl:
    if ctor_tree.data != "constructor_definition":
        raise _syntax("CTOR_EXPECTED_DEF", "constructor_definition expected", ctor_tree)
    if len(ctor_tree.children) != 3:
        raise _syntax("CTOR_MALFORMED", "constructor_definition: malformed", ctor_tree)
    _, params_node, body_node = ctor_tree.children
    if not isinstance(params_node, Tree) or params_node.data != "constructor_params":
        raise _syntax("CTOR_MISSING_PARAMS", "constructor missing params", ctor_tree)
    plist = _extract_parameter_list_from_param_wrapper(params_node, "constructor_params")
    if not isinstance(body_node, Tree) or body_node.data != "constructor_body":
        raise _syntax("CTOR_MISSING_BODY", "constructor missing body", ctor_tree)
    if len(body_node.children) != 1 or not isinstance(body_node.children[0], Tree):
        raise _syntax("CTOR_MISSING_BODY", "constructor missing body", ctor_tree)
    body = body_node.children[0]
    if body.data != "block_expression":
        raise _syntax("CTOR_BODY_NOT_BLOCK", "constructor body must be block_expression", ctor_tree)
    return ConstructorDecl(*parse_params(plist, tset), lower_expr_tree(body))


def _lower_method_decl(m: Tree, ambient: set[str], *, body_stub: bool) -> MethodDecl:
    hdr = parse_method_decl(m, ambient, body_stub=body_stub)
    return MethodDecl(
        hdr.name,
        hdr.is_static,
        hdr.type_params,
        hdr.param_names,
        hdr.param_types,
        hdr.ret,
        lower_expr_tree(hdr.body),
    )


def _lower_class_decl(ct: Tree) -> ClassDecl:
    chd = parse_class_header(ct)
    tset: set[str] = set(chd.type_params)
    mb = parse_class_members(chd.body, tset)

    methods = [
        _lower_method_decl(mem, tset, body_stub=False)
        for mem in mb.method_defs
    ]

    constructors = tuple(_parse_constructor_decl(ctor_tree, tset) for ctor_tree in mb.constructors)

    return ClassDecl(
        chd.name,
        chd.type_params,
        list(chd.supers),
        dict(mb.fields),
        dict(mb.static_fields),
        methods,
        constructors,
    )


def _lower_interface_decl(it: Tree) -> InterfaceDecl:
    ih = parse_interface_decl(it)
    tset: set[str] = set(ih.type_params)
    methods = [
        _lower_method_decl(m, tset, body_stub=True)
        for m in ih.body.children
        if isinstance(m, Tree) and m.data == "abstract_method"
    ]
    return InterfaceDecl(ih.name, ih.type_params, list(ih.supers), methods)


def lower_program(prog: Tree) -> ProgramDecls:
    """Lower parsed program tree to declaration IR consumed by the checker."""
    funcs: Dict[str, List[FuncDecl]] = {}
    classes: Dict[str, ClassDecl] = {}
    interfaces: Dict[str, InterfaceDecl] = {}
    ordered_funcs: List[FuncDecl] = []
    ordered_class_names: List[str] = []

    for item in prog.children:
        if not isinstance(item, Tree):
            continue
        if item.data == "function_definition":
            hdr = parse_function_decl(item)
            fd = FuncDecl(
                hdr.name,
                hdr.type_params,
                hdr.param_names,
                hdr.param_types,
                hdr.ret,
                lower_expr_tree(hdr.body),
            )
            funcs.setdefault(fd.name, []).append(fd)
            ordered_funcs.append(fd)
            continue
        if item.data == "interface_declaration":
            idecl = _lower_interface_decl(item)
            interfaces[idecl.name] = idecl
            continue
        if item.data == "class_definition":
            cdecl = _lower_class_decl(item)
            classes[cdecl.name] = cdecl
            ordered_class_names.append(cdecl.name)

    return ProgramDecls(
        tuple(ordered_funcs),
        tuple(ordered_class_names),
        funcs,
        classes,
        interfaces,
    )




