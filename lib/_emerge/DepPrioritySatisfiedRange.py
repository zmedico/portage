# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.DepPriority import DepPriority
class DepPrioritySatisfiedRange(object):
	"""
	DepPriority                         Index      Category

	not satisfied and buildtime                    HARD
	not satisfied and runtime              7       MEDIUM
	satisfied and buildtime_slot_op        6       SATISFIED
	satisfied and buildtime                5       SATISFIED
	satisfied and runtime                  4       SATISFIED
	not satisfied and runtime_post         3       MEDIUM_SOFT
	satisfied and runtime_post             2       MEDIUM_SOFT
	optional                               1       SOFT
	(none of the above)                    0       NONE
	"""
	MEDIUM      = 7
	MEDIUM_SOFT = 3
	SOFT        = 1
	NONE        = 0

	@classmethod
	def _ignore_optional(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		return bool(priority.optional)

	@classmethod
	def _ignore_satisfied_runtime_post(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.optional:
			return True
		if not priority.satisfied:
			return False
		return bool(priority.runtime_post)

	@classmethod
	def _ignore_runtime_post(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.buildtime or priority.runtime:
			return False
		return bool(priority.optional or \
			priority.runtime_post)

	@classmethod
	def _ignore_satisfied_runtime(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.optional or priority.runtime_post:
			return True
		if not priority.satisfied:
			return False
		return not priority.buildtime

	@classmethod
	def _ignore_satisfied_buildtime(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.buildtime_slot_op:
			return False
		return bool(priority.optional or \
			priority.satisfied or priority.runtime_post)

	@classmethod
	def _ignore_satisfied_buildtime_slot_op(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		return bool(priority.optional or \
			priority.satisfied or priority.runtime_post)

	@classmethod
	def _ignore_runtime(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		return bool(priority.satisfied or \
			priority.optional or \
			not priority.buildtime)

	ignore_medium      = _ignore_runtime
	ignore_medium_soft = _ignore_runtime_post
	ignore_soft        = _ignore_optional


DepPrioritySatisfiedRange.ignore_priority = (
	None,
	DepPrioritySatisfiedRange._ignore_optional,
	DepPrioritySatisfiedRange._ignore_satisfied_runtime_post,
	DepPrioritySatisfiedRange._ignore_runtime_post,
	DepPrioritySatisfiedRange._ignore_satisfied_runtime,
	DepPrioritySatisfiedRange._ignore_satisfied_buildtime,
	DepPrioritySatisfiedRange._ignore_satisfied_buildtime_slot_op,
	DepPrioritySatisfiedRange._ignore_runtime
)
