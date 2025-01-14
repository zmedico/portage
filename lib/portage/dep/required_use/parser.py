#!/usr/bin/env python

import sys


class Flag(object):
    def __init__(self, name, enabled=True):
        self.name = name
        self.enabled = enabled

    def __repr__(self):
        return '%s%s' % ('' if self.enabled else '!', self.name)

    def __hash__(self):
        return hash(repr(self))

    def __eq__(self, other):
        return (self.name == other.name and self.enabled == other.enabled)

    def __ne__(self, other):
        return not self.__eq__(other)

    def negated(self):
        return Flag(self.name, not self.enabled)


class Implication(object):
    def __init__(self, condition, constraint):
        assert(isinstance(condition, list))
        assert(isinstance(constraint, list))

        self.condition = condition
        self.constraint = constraint

    def __repr__(self):
        return '%s? => %s' % (self.condition, self.constraint)


class NaryOperator(object):
    def __init__(self, op, constraint):
        assert op in ('||', '??', '^^', '&&')
        self.op = op
        self.constraint = constraint

    def __repr__(self):
        return '%s %s' % (self.op, self.constraint)


class AnyOfOperator(NaryOperator):
    def __init__(self, constraint):
        super(AnyOfOperator, self).__init__('||', constraint)


class ExactlyOneOfOperator(NaryOperator):
    def __init__(self, constraint):
        super(ExactlyOneOfOperator, self).__init__('^^', constraint)


class AtMostOneOfOperator(NaryOperator):
    def __init__(self, constraint):
        super(AtMostOneOfOperator, self).__init__('??', constraint)


class AllOfOperator(NaryOperator):
    def __init__(self, constraint):
        super(AllOfOperator, self).__init__('&&', constraint)


_ast_cls = {
    '||': AnyOfOperator,
    '??': AtMostOneOfOperator,
    '^^': ExactlyOneOfOperator,
    '&&': AllOfOperator,
}


def ast_cls(operator):
    return _ast_cls.get(operator)


def parse_tokens(l, nested=False):
    while l:
        # implication or n-ary operator
        if l[0] in ('||', '??', '^^', '(') or l[0].endswith('?'):
            if '(' not in l[0:2]:
                raise ValueError('"%s" must be followed by "("' % l[0])
            k = l.pop(0)
            if k != '(':
                l.pop(0)

            if k == '||':
                yield AnyOfOperator(list(parse_tokens(l, True)))
            elif k == '??':
                yield AtMostOneOfOperator(list(parse_tokens(l, True)))
            elif k == '^^':
                yield ExactlyOneOfOperator(list(parse_tokens(l, True)))
            elif k == '(':
                yield AllOfOperator(list(parse_tokens(l, True)))
            else:
                # strip ?
                assert k.endswith('?')
                k = k[:-1]
                if k.startswith('!'):
                    kf = Flag(k[1:], False)
                else:
                    kf = Flag(k)
                yield Implication([kf], list(parse_tokens(l, True)))
                
        # end of group
        elif l[0] == ')':
            if not nested:
                raise ValueError('Stray ")" at top level')
            l.pop(0)
            return
        # plain flag
        else:
            if l[0].startswith('!'):
                yield Flag(l[0][1:], False)
            else:
                yield Flag(l[0])
            l.pop(0)

    if nested:
        raise ValueError('Missing terminating ")"')


def parse_string(s):
    # tokenize & parse
    return parse_tokens(s.split())


def parse_immutables(s):
    ret = {}
    for x in s.split():
        if x.startswith('!'):
            ret[x[1:]] = False
        else:
            ret[x] = True
    return ret


if __name__ == '__main__':
    print(repr(list(parse_string(sys.argv[1]))))
