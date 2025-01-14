
import unittest

from portage.dep.required_use.exception import (
    InfiniteLoopError,
    MaxIterationsError,
)
from portage.dep.required_use.parser import (
    parse_string,
    parse_immutables,
    Implication,
)
from portage.dep.required_use.sort_nary import (
    immutability_sort,
    sort_nary,
)
from portage.dep.required_use.to_flat3 import flatten3
from portage.dep.required_use.validate_ast import validate_ast_passthrough

from portage.dep.required_use.solve import (
    apply_solving,
    do_solving,
    get_all_flags,
    implication_form,
    validate_constraint,
)

class RequiredUseApplySolvingTests(unittest.TestCase):
    def testNaryOperator(self):
        cases = (
            {
                'required_use': '|| ( a b c )',
                'cases': (
                    {
                        'expected': {'a': True, 'b': False, 'c': False},
                    },
                    {
                        'immutables': '!a',
                        'expected': {'a': False, 'b': True, 'c': False},
                    },
                    {
                        'input': {'a': False, 'b': True, 'c': False},
                        'expected': {'a': False, 'b': True, 'c': False},
                    },
                    {
                        'input': {'a': False, 'b': False, 'c': True},
                        'expected': {'a': False, 'b': False, 'c': True},
                    },
                )
            },
            {
                'required_use': '^^ ( a b c )',
                'cases': (
                    {
                        'expected': {'a': True, 'b': False, 'c': False},
                    },
                    {
                        'input': {'a': False, 'b': True, 'c': False},
                        'expected': {'a': False, 'b': True, 'c': False},
                    },
                    {
                        'input': {'a': False, 'b': True, 'c': True},
                        'expected': {'a': False, 'b': True, 'c': False},
                    },
                    {
                        'input': {'a': True, 'b': True, 'c': True},
                        'expected': {'a': True, 'b': False, 'c': False},
                    },
                )
            },
            {
                'required_use': '?? ( a b c )',
                'cases': (
                    {
                        'expected': {'a': False, 'b': False, 'c': False},
                    },
                    {
                        'input': {'a': False, 'b': True, 'c': False},
                        'expected': {'a': False, 'b': True, 'c': False},
                    },
                    {
                        'input': {'a': False, 'b': True, 'c': True},
                        'expected': {'a': False, 'b': True, 'c': False},
                    },
                    {
                        'input': {'a': True, 'b': True, 'c': True},
                        'expected': {'a': True, 'b': False, 'c': False},
                    },
                )
            },
            {
                'required_use': 'a a? ( b ) b? ( !a )',
                'cases': (
                    {
                        'exception': InfiniteLoopError,
                        'max_iterations': 2,
                    },
                    {
                        'exception': MaxIterationsError,
                        'max_iterations': 1,
                    },
                )
            },
        )
        for case in cases:
            for c in case['cases']:
                ast = list(parse_string(case['required_use']))

                input_flags = c.get('input')
                if input_flags is None:
                    input_flags = dict((x.name, False) for x in get_all_flags(ast))

                # Transformation into implication form
                # https://www.gentoo.org/glep/glep-0073.html#transformation-into-implication-form
                immutables = parse_immutables(c.get('immutables', ''))
                impl_ast = list(implication_form(ast, immutables, validate=True))

                max_iterations = c.get('max_iterations', case.get('max_iterations', 1))
                self.assertEqual(isinstance(max_iterations, int), True)

                if 'exception' in c:
                    self.assertRaises(c['exception'], do_solving,
                        input_flags, impl_ast, immutables,
                        max_iterations=max_iterations)
                else:
                    out_flags, iteration = do_solving(
                        input_flags, impl_ast, immutables,
                        max_iterations=max_iterations)
                    self.assertTrue(validate_constraint(out_flags, ast))

                    self.assertEqual(out_flags, c['expected'],
                        'required_use: {} data: {}'.format(case['required_use'], c))
