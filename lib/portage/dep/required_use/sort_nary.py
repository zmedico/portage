#!/usr/bin/env python

import sys

from .exception import (
    InvalidRequiredUse,
)

from .parser import (
    Flag,
    Implication,
    NaryOperator,
    AllOfOperator,
    parse_string,
    parse_immutables,
)


class immutability_sort(object):
    def __init__(self, immutable_flags):
        self.immutable_flags = immutable_flags

    def __call__(self, key):
        # support recurrence into n-ary operators
        if isinstance(key, NaryOperator):
            for x in key.constraint:
                if self(x) != 1:
                    return self(x)
            else:
                return 1

        # forced = 0 [go first]
        # normal = 1
        # masked = 2 [go last]
        if key.name not in self.immutable_flags:
            return 1
        if self.immutable_flags[key.name]:
            return 0
        else:
            return 2


def sort_nary(ast, sort_key):
    for expr in ast:
        if isinstance(expr, Flag):
            yield expr
        elif isinstance(expr, Implication):
            yield Implication(expr.condition, list(sort_nary(expr.constraint, sort_key)))
        elif isinstance(expr, AllOfOperator):
            # no point in sorting all-of
            yield expr
        elif isinstance(expr, NaryOperator):
            # sort subexpressions first, if any
            constraint = list(sort_nary(expr.constraint, sort_key))
            constraint.sort(key=sort_key)
            yield expr.__class__(constraint)
        else:
            raise InvalidRequiredUse('Unknown AST expr: %s' % expr)


if __name__ == '__main__':
    print(repr(list(sort_nary(parse_string(sys.argv[1]),
        immutability_sort(parse_immutables(sys.argv[2]))))))
