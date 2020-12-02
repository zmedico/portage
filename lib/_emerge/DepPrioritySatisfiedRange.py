# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.DepPriority import DepPriority
class DepPrioritySatisfiedRange:
	"""
	DepPriority                         Index      Category
	not satisfied and buildtime                    HARD
	not satisfied and runtime             11       MEDIUM
	satisfied and buildtime_slot_op and   10       MEDIUM_SOFT
		new_slot
	satisfied and buildtime and            9       MEDIUM_SOFT
		new_slot
	satisfied and buildtime and            8       MEDIUM_SOFT
		new_ver
	satisfied and buildtime and            7       MEDIUM_SOFT
		new_rev
	satisfied and buildtime_slot_op        6       MEDIUM_SOFT
	satisfied and buildtime                5       MEDIUM_SOFT
	satisfied and runtime                  4       MEDIUM_SOFT
	runtime_post                           3       MEDIUM_POST
	satisfied and runtime_post             2       MEDIUM_POST
	optional                               1       SOFT
	(none of the above)                    0       NONE
	"""
	MEDIUM      = 11
	MEDIUM_SOFT = 10
	MEDIUM_POST = 3
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
		if priority.buildtime or priority.runtime:
			return False
		return bool(priority.runtime_post)

	@classmethod
	def _ignore_runtime_post(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.optional:
			return True
		if priority.buildtime or priority.runtime:
			return False
		return bool(priority.runtime_post)

	@classmethod
	def _ignore_satisfied_runtime(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.optional:
			return True
		if priority.buildtime:
			return False
		if not priority.runtime:
			return True
		return bool(priority.satisfied)

	@classmethod
	def _ignore_satisfied_buildtime(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.optional:
			return True
		if priority.buildtime_slot_op:
			return False
		if priority.buildtime:
			if priority.new_slot or priority.new_rev or priority.new_ver:
				return False
		return bool(priority.satisfied)

	@classmethod
	def _ignore_satisfied_buildtime_slot_op(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.optional:
			return True
		if priority.buildtime_slot_op and priority.new_slot:
			return False
		if priority.buildtime:
			if priority.new_slot or priority.new_rev or priority.new_ver:
				return False
		return bool(priority.satisfied)

	@classmethod
	def _ignore_satisfied_buildtime_and_new_rev(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.optional:
			return True
		if priority.buildtime_slot_op and priority.new_slot:
			return False
		if priority.buildtime:
			if priority.new_slot or priority.new_ver:
				return False
		return bool(priority.satisfied)

	@classmethod
	def _ignore_satisfied_buildtime_and_new_ver(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.optional:
			return True
		if priority.buildtime_slot_op and priority.new_slot:
			return False
		if priority.buildtime and priority.new_slot:
			return False
		return bool(priority.satisfied)

	@classmethod
	def _ignore_satisfied_buildtime_and_new_slot(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.optional:
			return True
		if priority.buildtime_slot_op and priority.new_slot:
			return False
		return bool(priority.satisfied)

	@classmethod
	def _ignore_satisfied_buildtime_slot_op_and_new_slot(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		if priority.optional:
			return True
		if priority.satisfied:
			return True
		return not priority.buildtime and not priority.runtime

	@classmethod
	def _ignore_runtime(cls, priority):
		if priority.__class__ is not DepPriority:
			return False
		return bool(priority.satisfied or \
			priority.optional or \
			not priority.buildtime)

	ignore_medium      = _ignore_runtime
	ignore_medium_soft = _ignore_satisfied_buildtime_slot_op_and_new_slot
	ignore_medium_post = _ignore_runtime_post
	ignore_medium_post_satisifed = _ignore_satisfied_runtime_post
	ignore_soft        = _ignore_optional


DepPrioritySatisfiedRange.ignore_priority = (
	None,
	DepPrioritySatisfiedRange._ignore_optional,
	DepPrioritySatisfiedRange._ignore_satisfied_runtime_post,
	DepPrioritySatisfiedRange._ignore_runtime_post,
	DepPrioritySatisfiedRange._ignore_satisfied_runtime,
	DepPrioritySatisfiedRange._ignore_satisfied_buildtime,
	DepPrioritySatisfiedRange._ignore_satisfied_buildtime_slot_op,
	DepPrioritySatisfiedRange._ignore_satisfied_buildtime_and_new_rev,
	DepPrioritySatisfiedRange._ignore_satisfied_buildtime_and_new_ver,
	DepPrioritySatisfiedRange._ignore_satisfied_buildtime_and_new_slot,
	DepPrioritySatisfiedRange._ignore_satisfied_buildtime_slot_op_and_new_slot,
	DepPrioritySatisfiedRange._ignore_runtime
)
