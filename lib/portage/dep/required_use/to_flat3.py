#!/usr/bin/env python
# 3rd version of flattening algo, most trivial by design

import sys

from .exception import (
    InvalidRequiredUse,
)

from .parser import (
    parse_string,
    Flag,
    Implication,
    NaryOperator,
    AnyOfOperator,
    ExactlyOneOfOperator,
    AtMostOneOfOperator,
)


def flatten3(ast, conditions=[]):
    for expr in ast:
        if isinstance(expr, Flag):
            yield (conditions, expr)
        elif isinstance(expr, Implication):
            for x in flatten3(expr.constraint, conditions+expr.condition):
                yield x
        elif isinstance(expr, AnyOfOperator):
            # || ( a b c ... ) -> [!b !c ...]? ( a )
            yield (conditions+[x.negated() for x in expr.constraint[1:]], expr.constraint[0])
        elif isinstance(expr, AtMostOneOfOperator):
            # ?? ( a b c ... ) -> a? ( !b !c ... ) b? ( !c ... ) ...
            for i in range(0, len(expr.constraint)-1):
                new_cond = conditions + expr.constraint[i:i+1]
                for x in expr.constraint[i+1:]:
                    yield (new_cond, x.negated())
        elif isinstance(expr, ExactlyOneOfOperator):
            for x in flatten3([AnyOfOperator(expr.constraint)], conditions):
                yield x
            for x in flatten3([AtMostOneOfOperator(expr.constraint)], conditions):
                yield x
        else:
            raise InvalidRequiredUse('Unknown AST expr: %s' % expr)


if __name__ == '__main__':
    print(list(flatten3(parse_string(sys.argv[1]))))
