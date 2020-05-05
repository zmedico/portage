# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.package.fetch import FilenameHashLayout
from portage.repository.storage.interface import (
	KeyValueStorageException,
	KeyValueStorageInterface,
)
from portage.util.futures.compat_coroutine import coroutine, coroutine_return


class FilenameHashKeyValueStorage(KeyValueStorageInterface):
	"""
	Key-value storage using filename hash.
	"""
	def __init__(self, location, **kwargs):
		"""
		@param location: storage location
		@type location: str
		"""
		self._location = location

	@coroutine
	def garbage_collection(self):
		coroutine_return()
		yield None
