# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
from typing import AsyncGenerator

from portage.kv.interface import (
    ConfigurationException,
    KeyValueStoreException,
    KeyValueStoreInterface,
)
from portage.util import (
    atomic_ofstream,
    ensure_dirs,
)


class FilesystemKeyValueStore(KeyValueStoreInterface):
    """
    Filesystem key-value store.
    """

    def __init__(self, config: dict):
        """
        @param config: config
        @type config: dict
        """
        self._data_dir = config.get("data_dir")
        if self._data_dir is None:
            raise ConfigurationException('Missing "data_dir" parameter')

    def _build_filename(self, key):
        # TODO: support FlatLayout and FilenameHashLayout
        return os.path.abspath(os.path.join(self._data_dir, key))

    async def put(self, key: str, data: bytes):
        """
        @param key: key
        @type key: str
        @param data: data
        @type data: bytes
        """
        path = self._build_filename(key)
        ensure_dirs(os.path.basename(path))
        with atomic_ofstream(path, "wb") as f:
            f.write(data)

    async def get(self, key: str) -> bytes:
        """
        @param key: key
        @type key: str

        @rtype: bytes
        @return: value
        """
        with open(self._build_filename(key), "rb") as f:
            return f.read()

    async def iter_keys(self) -> AsyncGenerator[str, None]:
        """
        Available in Python 3.6:
        PEP 525 -- Asynchronous Generators
        https://www.python.org/dev/peps/pep-0525/
        @rtype: AsyncGenerator[str, None]
        @return: key iterator
        """
        # TODO: support FlatLayout and FilenameHashLayout
        for parent, dirs, files in os.walk(self._data_dir):
            for filename in files:
                yield os.path.join(parent[len(self._data_dir) + 1 :], filename)
