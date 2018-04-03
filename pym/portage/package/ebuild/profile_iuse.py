# Copyright 2012-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['profile_iuse']


def profile_iuse(env):
	"""
	Calculate the set of implicit IUSE elements contributed by profile
	variables for EAPI 5 and later.

	@param env: Ebuild environment
	@type env: Mapping
	@rtype: frozenset
	@return: set of implicit IUSE elements contributed by profile variables
	"""
	iuse_effective = []
	iuse_effective.extend(env.get("IUSE_IMPLICIT", "").split())

	# USE_EXPAND_IMPLICIT should contain things like ARCH, ELIBC,
	# KERNEL, and USERLAND.
	use_expand_implicit = frozenset(
		env.get("USE_EXPAND_IMPLICIT", "").split())

	# USE_EXPAND_UNPREFIXED should contain at least ARCH, and
	# USE_EXPAND_VALUES_ARCH should contain all valid ARCH flags.
	for v in env.get("USE_EXPAND_UNPREFIXED", "").split():
		if v not in use_expand_implicit:
			continue
		iuse_effective.extend(
			env.get("USE_EXPAND_VALUES_" + v, "").split())

	use_expand = frozenset(env.get("USE_EXPAND", "").split())
	for v in use_expand_implicit:
		if v not in use_expand:
			continue
		lower_v = v.lower()
		for x in env.get("USE_EXPAND_VALUES_" + v, "").split():
			iuse_effective.append(lower_v + "_" + x)

	return frozenset(iuse_effective)
