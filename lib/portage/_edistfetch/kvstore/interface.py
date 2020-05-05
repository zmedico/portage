# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.exception import PortageException
from portage.util.futures.compat_coroutine import coroutine


class KeyValueStorageException(PortageException):
	"""
	Base class for exceptions raised by KeyValueStorageInterface.
	"""


class KeyValueStorageInterface(object):
	"""
	Abstract key-value storage interface.
	"""
	def __init__(self, location, **kwargs):
		"""
		@param location: storage location
		@type location: str
		"""
		raise NotImplementedError

	@coroutine
	def garbage_collection(self):
		"""
		Remove expired data.
		"""
		raise NotImplementedError
