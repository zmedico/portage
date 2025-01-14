#!/usr/bin/env python

import sys

from .exception import (
    InvalidRequiredUse,
)

from .parser import (
    parse_string,
    Flag,
    Implication,
    NaryOperator,
    AllOfOperator,
)


def validate_ast_passthrough(ast):
    for expr in ast:
        if isinstance(expr, Flag):
            pass
        elif isinstance(expr, Implication):
            assert len(expr.condition) == 1
            assert isinstance(expr.condition[0], Flag)
            validate_ast(expr.constraint)
        elif isinstance(expr, AllOfOperator):
            raise InvalidRequiredUse('All-of operator forbidden')
        elif isinstance(expr, NaryOperator):
            for x in expr.constraint:
                if isinstance(x, Flag):
                    pass
                elif isinstance(x, Implication):
                    raise InvalidRequiredUse('USE-conditional group in %s operator forbidden' % expr.op)
                elif isinstance(x, NaryOperator):
                    raise InvalidRequiredUse('%s group in %s operator forbidden' % (x.op, expr.op))
                else:
                    raise InvalidRequiredUse('Unknown AST subexpr: %s' % x)
            if len(expr.constraint) == 0:
                raise InvalidRequiredUse('Empty %s group forbidden' % expr.op)
        else:
            raise InvalidRequiredUse('Unknown AST subexpr: %s' % expr)
        yield expr


def validate_ast(ast):
    for x in validate_ast_passthrough(ast):
        pass


if __name__ == '__main__':
    validate_ast(parse_string(sys.argv[1]))
