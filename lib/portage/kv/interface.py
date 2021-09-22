# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from typing import AsyncGenerator

from portage.exception import PortageException


class KeyValueStoreException(PortageException):
    """
    Base class for exceptions raise by KeyValueStoreInterface.
    """


class ConfigurationException(KeyValueStoreException):
    """
    Base class for configuration exceptions.
    """


class KeyValueStoreInterface:
    """
    Abstract key-value store interface.
    """

    def __init__(self, config: dict):
        """
        @param config: config
        @type config: dict
        """
        raise NotImplementedError

    async def put(self, key: str, data: bytes):
        """
        @param key: key
        @type key: str
        @param data: data
        @type data: bytes
        """
        raise NotImplementedError

    async def get(self, key: str) -> bytes:
        """
        @param key: key
        @type key: str

        @rtype: bytes
        @return: value
        """
        raise NotImplementedError

    async def iter_keys(self) -> AsyncGenerator[str, None]:
        """
        Available in Python 3.6:
        PEP 525 -- Asynchronous Generators
        https://www.python.org/dev/peps/pep-0525/
        @rtype: AsyncGenerator[str, None]
        @return: key iterator
        """
        raise NotImplementedError
