"""Lark Transformer that lowers expression trees to ``expr_ast`` nodes."""

from __future__ import annotations

from typing import Dict, List, Tuple, Union

from lark import Token
from lark.tree import Tree
from lark.visitors import Transformer

from typechecker.ast import (
    ArrayExpr,
    AssignExpr,
    BinaryExpr,
    BlockExpr,
    BreakExpr,
    CallArgs,
    CallSuffix,
    ContinueExpr,
    Expr,
    ForExpr,
    IfExpr,
    IndexSuffix,
    LambdaExpr,
    LambdaParam,
    LiteralExpr,
    MemberSuffix,
    NameExpr,
    NamedArg,
    PostfixExpr,
    RangeExpr,
    ReturnExpr,
    TupleExpr,
    TypeArgsSuffix,
    UnaryExpr,
    VarDeclExpr,
    WhileExpr,
)
from typechecker.error_codes import E_INTERNAL_UNKNOWN_SYNTAX_MESSAGE, EXPR_SYNTAX_CODES
from typechecker.errors import internal_error, syntax_error



def _syntax(key: str, message: str, node: object = None):
    code = EXPR_SYNTAX_CODES.get(key)
    if code is None:
        raise internal_error(E_INTERNAL_UNKNOWN_SYNTAX_MESSAGE, f"unknown expr syntax key: {key}")
    return syntax_error(code, message, node)


class ExprTransformer(Transformer):
    @staticmethod
    def _require_expr(node: object, where: str) -> Expr:
        if not isinstance(node, Expr):
            raise _syntax("EXPECTED_EXPRESSION", f"{where}: expected expression")
        return node

    @classmethod
    def _require_expr_list(cls, nodes: List[object], where: str) -> Tuple[Expr, ...]:
        out: list[Expr] = []
        for node in nodes:
            out.append(cls._require_expr(node, where))
        return tuple(out)

    @classmethod
    def _fold_binary_chain(cls, children: List[object], where: str) -> Expr:
        if not children:
            raise _syntax("EMPTY_CHAIN", f"{where}: empty chain")
        acc = cls._require_expr(children[0], where)
        i = 1
        while i + 1 < len(children):
            op = children[i]
            rhs = children[i + 1]
            if not isinstance(op, Token):
                raise _syntax("EXPECTED_OPERATOR_TOKEN", f"{where}: expected operator token")
            acc = BinaryExpr(op, acc, cls._require_expr(rhs, where))
            i += 2
        return acc

    def number(self, children: List[object]) -> Expr:
        if len(children) == 1:
            (token,) = children
            if isinstance(token, Token):
                return LiteralExpr(token)
        raise _syntax("BAD_NUMBER_LITERAL", "bad number literal")

    def literal(self, children: List[object]) -> Expr:
        if len(children) == 1:
            (child,) = children
            if isinstance(child, Expr):
                return child
            if isinstance(child, Token) and child.type in (
                "INTEGER",
                "FLOAT",
                "TRUE",
                "FALSE",
            ):
                return LiteralExpr(child)
        raise _syntax("BAD_LITERAL", "bad literal")

    def name_expression(self, children: List[object]) -> NameExpr:
        if len(children) != 1:
            raise _syntax("NAME_EXPECTED_IDENT", "name_expression: expected IDENT")
        (ident,) = children
        if not isinstance(ident, Token) or ident.type != "IDENT":
            raise _syntax("NAME_EXPECTED_IDENT", "name_expression: expected IDENT")
        return NameExpr(ident)

    def string_literal(self, children: List[object]) -> LiteralExpr:
        if len(children) != 1:
            raise _syntax("STRING_EXPECTED_STRING", "string_literal: expected STRING")
        (string_token,) = children
        if not isinstance(string_token, Token) or string_token.type != "STRING":
            raise _syntax("STRING_EXPECTED_STRING", "string_literal: expected STRING")
        return LiteralExpr(string_token)

    def argument(self, children: List[object]) -> object:
        if len(children) != 1:
            raise _syntax("BAD_ARGUMENT_SHAPE", "bad argument shape")
        (c0,) = children
        if isinstance(c0, NamedArg):
            return c0
        return self._require_expr(c0, "argument")

    def named_argument(self, children: List[object]) -> NamedArg:
        if len(children) != 2:
            raise _syntax("BAD_NAMED_ARGUMENT_SHAPE", "bad named_argument shape")
        name_token, value_node = children
        if not isinstance(name_token, Token) or name_token.type != "IDENT":
            raise _syntax("BAD_NAMED_ARGUMENT_SHAPE", "bad named_argument shape")
        return NamedArg(str(name_token.value), self._require_expr(value_node, "named_argument"))

    def argument_list(self, children: List[object]) -> CallArgs:
        pos: List[Expr] = []
        named: Dict[str, Expr] = {}
        for child in children:
            if isinstance(child, NamedArg):
                named[child.name] = child.value
                continue
            pos.append(self._require_expr(child, "argument_list"))
        return CallArgs(tuple(pos), named)

    def variable_declaration(self, children: List[object]) -> VarDeclExpr:
        if not children or not isinstance(children[0], Token) or children[0].type not in ("LET", "VAR"):
            raise _syntax("VAR_DECL_EXPECTED_KIND", "variable_declaration: expected let/var")
        kind = str(children[0].value)
        if len(children) < 2 or not isinstance(children[1], Token) or children[1].type != "IDENT":
            raise _syntax("VAR_DECL_EXPECTED_NAME", "variable_declaration: expected name")
        name = str(children[1].value)
        annot: Tree | None = None
        if len(children) >= 4 and isinstance(children[2], Tree) and children[2].data == "type_annotation":
            if len(children[2].children) != 1:
                raise _syntax("VAR_DECL_MALFORMED_ANNOT", "variable_declaration: malformed type_annotation")
            type_node = children[2].children[0]
            if isinstance(type_node, Tree):
                annot = type_node
            elif isinstance(type_node, Token):
                annot = Tree("type", [type_node])
            else:
                raise _syntax("VAR_DECL_MALFORMED_ANNOT", "variable_declaration: malformed type_annotation")
        if len(children) < 3:
            raise _syntax("VAR_DECL_MISSING_INIT", "variable_declaration missing initializer")
        init = self._require_expr(children[-1], "variable_declaration")
        return VarDeclExpr(kind, name, annot, init, Tree("variable_declaration", children))

    def block_expression(self, children: List[object]) -> BlockExpr:
        items: List[Union[VarDeclExpr, Expr]] = []
        for child in children:
            if isinstance(child, VarDeclExpr):
                items.append(child)
            elif isinstance(child, Expr):
                items.append(child)
            else:
                raise _syntax("BLOCK_EXPECTED_ITEM", f"block_expression: expected Expr or VarDeclExpr, got {type(child)}")
        return BlockExpr(tuple(items))

    def if_expression(self, children: List[object]) -> IfExpr:
        if len(children) == 2:
            cond, then_branch = children
            else_branch = None
        elif len(children) == 3:
            cond, then_branch, else_branch = children
        else:
            raise _syntax("IF_BAD_ARITY", "if_expression must have 2 or 3 children")
        cond = self._require_expr(cond, "if_expression")
        then_branch = self._require_expr(then_branch, "if_expression")
        if else_branch is not None:
            else_branch = self._require_expr(else_branch, "if_expression")
        return IfExpr(cond, then_branch, else_branch)

    def while_expression(self, children: List[object]) -> WhileExpr:
        if len(children) != 2:
            raise _syntax("WHILE_BAD_ARITY", "while_expression must have condition and body")
        cond_node, body_node = children
        cond = self._require_expr(cond_node, "while_expression")
        body = self._require_expr(body_node, "while_expression")
        if not isinstance(body, BlockExpr):
            raise _syntax("WHILE_BODY_NOT_BLOCK", "while body must be block")
        return WhileExpr(cond, body)

    def range_expression(self, children: List[object]) -> RangeExpr:
        if len(children) < 3 or len(children) > 4:
            raise _syntax("RANGE_BAD_SHAPE", "range_expression: bad shape")
        lo_node, op, hi_node = children[:3]
        lo = self._require_expr(lo_node, "range_expression")
        hi = self._require_expr(hi_node, "range_expression")
        step = self._require_expr(children[3], "range_expression") if len(children) == 4 else None
        if not isinstance(op, Token):
            raise _syntax("RANGE_MISSING_OP", "range_expression missing operator")
        return RangeExpr(lo, hi, op, step)

    def for_expression(self, children: List[object]) -> ForExpr:
        if len(children) != 3:
            raise _syntax("FOR_BAD_ARITY", "for_expression expects loop var, rhs, and body")
        loop_var, rhs_node, body_node = children
        if not isinstance(loop_var, Token) or loop_var.type != "IDENT":
            raise _syntax("FOR_MISSING_NAME", "for_expression missing var name")
        rhs = self._require_expr(rhs_node, "for_expression")
        body = self._require_expr(body_node, "for_expression")
        if not isinstance(body, BlockExpr):
            raise _syntax("FOR_BODY_NOT_BLOCK", "for body must be block")
        return ForExpr(str(loop_var.value), rhs, body)

    def lambda_expression(self, children: List[object]) -> LambdaExpr:
        params: List[LambdaParam] = []
        body_child: object
        if len(children) == 2 and isinstance(children[0], Tree) and children[0].data == "lambda_parameters":
            params_tree, body_child = children
            for p in params_tree.children:
                if isinstance(p, Tree) and p.data == "lambda_param":
                    ids = [c for c in p.children if isinstance(c, Token) and c.type == "IDENT"]
                    if ids:
                        params.append(LambdaParam(str(ids[0].value), p))
        elif len(children) == 1:
            (body_child,) = children
        else:
            raise _syntax("LAMBDA_MISSING_BODY", "lambda missing body")
        return LambdaExpr(tuple(params), self._require_expr(body_child, "lambda_expression"))

    def break_expression(self, children: List[object]) -> BreakExpr:
        if len(children) != 1:
            raise _syntax("BREAK_EXPECTED_TOKEN", "break_expression: expected BREAK")
        (break_token,) = children
        if not isinstance(break_token, Token) or break_token.type != "BREAK":
            raise _syntax("BREAK_EXPECTED_TOKEN", "break_expression: expected BREAK")
        return BreakExpr(break_token)

    def continue_expression(self, children: List[object]) -> ContinueExpr:
        if len(children) != 1:
            raise _syntax("CONTINUE_EXPECTED_TOKEN", "continue_expression: expected CONTINUE")
        (continue_token,) = children
        if not isinstance(continue_token, Token) or continue_token.type != "CONTINUE":
            raise _syntax("CONTINUE_EXPECTED_TOKEN", "continue_expression: expected CONTINUE")
        return ContinueExpr(continue_token)

    def return_expression(self, children: List[object]) -> ReturnExpr:
        if len(children) == 1:
            (ret_token,) = children
            if isinstance(ret_token, Token) and ret_token.type == "RETURN":
                return ReturnExpr(None)
        if len(children) == 2:
            ret_token, ret_value = children
            if isinstance(ret_token, Token) and ret_token.type == "RETURN":
                return ReturnExpr(self._require_expr(ret_value, "return_expression"))
        raise _syntax("RETURN_BAD_SHAPE", "return_expression: bad shape")

    def tuple_literal(self, children: List[object]) -> TupleExpr:
        return TupleExpr(self._require_expr_list(children, "tuple_literal"))

    def array_literal(self, children: List[object]) -> ArrayExpr:
        return ArrayExpr(self._require_expr_list(children, "array_literal"))

    def primary_expression(self, children: List[object]) -> Expr:
        if len(children) == 1:
            (child,) = children
            return self._require_expr(child, "primary_expression")
        raise _syntax("PRIMARY_BAD_SHAPE", "unsupported primary expression shape")

    def atom_suffix(self, children: List[object]) -> object:
        if len(children) != 1:
            raise _syntax("ATOM_SUFFIX_BAD_ARITY", "atom_suffix should have one transformed child")
        (first,) = children
        if isinstance(first, (MemberSuffix, IndexSuffix, CallSuffix, TypeArgsSuffix)):
            return first
        if isinstance(first, Tree) and first.data in ("type_arguments", "expr_type_arguments"):
            return TypeArgsSuffix(first)
        raise _syntax("ATOM_SUFFIX_UNSUPPORTED", "unsupported atom_suffix")

    def member_suffix(self, children: List[object]) -> MemberSuffix:
        if not children or not isinstance(children[0], Token) or children[0].type != "IDENT":
            raise _syntax("MEMBER_SUFFIX_MISSING_NAME", "member_suffix missing field name")
        field_name = str(children[0].value)
        type_args_tree: Tree | None = None
        call_args: CallArgs | None = None
        for child in children[1:]:
            if isinstance(child, Tree) and child.data in ("type_arguments", "expr_type_arguments"):
                type_args_tree = child
            elif isinstance(child, CallSuffix):
                call_args = child.args
        return MemberSuffix(field_name, type_args_tree, call_args)

    def index_suffix(self, children: List[object]) -> IndexSuffix:
        if len(children) != 1:
            raise _syntax("INDEX_SUFFIX_BAD_ARITY", "index_suffix expects one index expression")
        (index_expr,) = children
        return IndexSuffix(self._require_expr(index_expr, "index_suffix"))

    def call_suffix(self, children: List[object]) -> CallSuffix:
        if not children:
            return CallSuffix(CallArgs((), {}))
        if len(children) == 1:
            (call_args,) = children
            if isinstance(call_args, CallArgs):
                return CallSuffix(call_args)
        raise _syntax("CALL_SUFFIX_BAD_SHAPE", "call_suffix has unexpected shape")

    def postfix_chain(self, children: List[object]) -> PostfixExpr:
        if not children:
            raise _syntax("POSTFIX_MISSING_PRIMARY", "postfix_chain missing primary")
        primary_node, *suffix_nodes = children
        primary = self._require_expr(primary_node, "postfix_chain")
        suffixes = tuple(
            c for c in suffix_nodes if isinstance(c, (MemberSuffix, IndexSuffix, CallSuffix, TypeArgsSuffix))
        )
        return PostfixExpr(primary, suffixes)

    def assign_expression(self, children: List[object]) -> Expr:
        if len(children) == 1:
            return self._require_expr(children[0], "assign_expression")
        if len(children) >= 2:
            return AssignExpr(
                self._require_expr(children[0], "assign_expression"),
                self._require_expr(children[-1], "assign_expression"),
            )
        raise _syntax("ASSIGN_BAD_SHAPE", "assign_expression: bad shape")

    def logic_or_expr(self, children: List[object]) -> Expr:
        return self._fold_binary_chain(children, "logic_or_expr")

    def logic_and_expr(self, children: List[object]) -> Expr:
        return self._fold_binary_chain(children, "logic_and_expr")

    def equality_expr(self, children: List[object]) -> Expr:
        return self._fold_binary_chain(children, "equality_expr")

    def relational_expr(self, children: List[object]) -> Expr:
        return self._fold_binary_chain(children, "relational_expr")

    def additive_expr(self, children: List[object]) -> Expr:
        return self._fold_binary_chain(children, "additive_expr")

    def multiplicative_expr(self, children: List[object]) -> Expr:
        return self._fold_binary_chain(children, "multiplicative_expr")

    def unary_expr(self, children: List[object]) -> Expr:
        if len(children) == 2 and isinstance(children[0], Token):
            op, operand = children
            return UnaryExpr(op, self._require_expr(operand, "unary_expr"))
        if len(children) == 1:
            (child,) = children
            return self._require_expr(child, "unary_expr")
        raise _syntax("UNARY_BAD_SHAPE", "bad unary_expr shape")


def lower_expr_tree(tree: Tree) -> Expr:
    out = ExprTransformer().transform(tree)
    if not isinstance(out, Expr):
        raise _syntax("LOWER_EXPECTED_EXPR_OUT", f"expected Expr from transformer, got {type(out)}", tree)
    return out
