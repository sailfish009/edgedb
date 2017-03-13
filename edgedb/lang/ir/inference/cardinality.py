##
# Copyright (c) 2008-present MagicStack Inc.
# All rights reserved.
#
# See LICENSE for details.
##


import functools
import math

from edgedb.lang.edgeql import ast as qlast
from edgedb.lang.edgeql import errors as ql_errors
from edgedb.lang.ir import ast as irast


ONE = 1
MANY = math.inf


def _common_cardinality(args, singletons, schema):
    if all(infer_cardinality(a, singletons, schema) == ONE for a in args):
        return ONE
    else:
        return MANY


@functools.singledispatch
def _infer_cardinality(ir, singletons, schema):
    raise ValueError(f'infer_cardinality: cannot handle {ir!r}')


@_infer_cardinality.register(type(None))
def __infer_none(ir, singletons, schema):
    # Here for debugging purposes.
    raise ValueError('invalid infer_cardinality(None, schema) call')


@_infer_cardinality.register(irast.Set)
def __infer_set(ir, singletons, schema):
    if ir.expr is not None:
        return infer_cardinality(ir.expr, singletons, schema)
    elif ir.rptr is not None:
        if ir.rptr.ptrcls.singular(ir.rptr.direction):
            return infer_cardinality(ir.rptr.source, singletons, schema)
        else:
            return MANY
    else:
        return MANY


@_infer_cardinality.register(irast.FunctionCall)
def __infer_func_call(ir, singletons, schema):
    # XXX: fix function result cardinality with respect to
    # set-returning functions when they are supported.
    return ONE


@_infer_cardinality.register(irast.Constant)
@_infer_cardinality.register(irast.Parameter)
def __infer_const_or_param(ir, singletons, schema):
    return ONE


@_infer_cardinality.register(irast.Coalesce)
def __infer_coalesce(ir, singletons, schema):
    return _common_cardinality(ir.args, singletons, schema)


@_infer_cardinality.register(irast.SetOp)
def __infer_setop(ir, singletons, schema):
    if ir.op == qlast.UNION:
        result = MANY
    else:
        result = infer_cardinality(ir.left, singletons, schema)

    return result


@_infer_cardinality.register(irast.BinOp)
def __infer_binop(ir, singletons, schema):
    return _common_cardinality([ir.left, ir.right], singletons, schema)


@_infer_cardinality.register(irast.UnaryOp)
def __infer_unaryop(ir, singletons, schema):
    return infer_cardinality(ir.expr, singletons, schema)


@_infer_cardinality.register(irast.IfElseExpr)
def __infer_ifelse(ir, singletons, schema):
    return _common_cardinality([ir.if_expr, ir.else_expr, ir.condition],
                               singletons, schema)


@_infer_cardinality.register(irast.TypeCast)
def __infer_typecast(ir, singletons, schema):
    return infer_cardinality(ir.expr, singletons, schema)


@_infer_cardinality.register(irast.TypeFilter)
def __infer_typefilter(ir, singletons, schema):
    return infer_cardinality(ir.expr, singletons, schema)


@_infer_cardinality.register(irast.Stmt)
def __infer_stmt(ir, singletons, schema):
    if ir.singleton:
        return ONE
    else:
        return infer_cardinality(ir.result, singletons, schema)


@_infer_cardinality.register(irast.ExistPred)
def __infer_exist(ir, singletons, schema):
    return ONE


@_infer_cardinality.register(irast.SliceIndirection)
def __infer_slice(ir, singletons, schema):
    return infer_cardinality(ir.expr, singletons, schema)


@_infer_cardinality.register(irast.IndexIndirection)
def __infer_index(ir, singletons, schema):
    return infer_cardinality(ir.expr, singletons, schema)


@_infer_cardinality.register(irast.Array)
@_infer_cardinality.register(irast.Mapping)
@_infer_cardinality.register(irast.Sequence)
@_infer_cardinality.register(irast.Struct)
@_infer_cardinality.register(irast.StructIndirection)
def __infer_map(ir, singletons, schema):
    return ONE


def infer_cardinality(ir, singletons, schema):
    if ir in singletons:
        return ONE

    try:
        return ir._inferred_cardinality_
    except AttributeError:
        pass

    result = _infer_cardinality(ir, singletons, schema)

    if result not in {ONE, MANY}:
        raise ql_errors.EdgeQLError(
            'could not determine the cardinality of '
            'set produced by expression',
            context=ir.context)

    ir._inferred_cardinality_ = result
    return result
