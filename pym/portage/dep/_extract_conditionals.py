# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import unicode_literals

from portage.dep import paren_reduce


def extract_conditionals(dep_struct, selected):
	"""
	Extract conditionals parts of dep_struct, and return a structure
	in the same format as that returned by paren_reduce.
	"""
	if not isinstance(dep_struct, list):
		dep_struct = paren_reduce(dep_struct, _deprecation_warn=False)

	result = []

	i = iter(dep_struct)
	for x in i:
		if isinstance(x, list):
			result.extend(extract_conditionals(x, selected))
		elif x == '||':
			x_recurse = extract_conditionals(next(i), selected)
			if x_recurse:
				if len(x_recurse) > 1:
					if (len(x_recurse) == 2 and
						not isinstance(x_recurse[0], list) and
						x_recurse[0][-1] == '?'):
						result.extend(x_recurse)
					else:
						result.append('||')
						result.append(x_recurse)
				else:
					result.append(x_recurse[0])
		elif x[-1] == '?':
			x_recurse = next(i)
			if x[:-1] not in selected:
				continue
			# preserve all nested conditionals regardless of
			# whether they are currently selected
			result.append(x)
			result.append(x_recurse)

	return result
