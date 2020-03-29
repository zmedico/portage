# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import struct

from portage.util.endian.decode import (decode_uint16_le,
	decode_uint32_le, decode_uint16_be, decode_uint32_be)
from portage.util.elf.constants import (E_ENTRY, E_MACHINE, E_TYPE,
	EI_CLASS, ELFCLASS32, ELFCLASS64, ELFDATA2LSB, ELFDATA2MSB)

class ELFHeader(object):

	__slots__ = ('e_flags', 'e_phentsize', 'e_phnum', 'e_phoff',
		'e_machine', 'e_type', 'ei_class',
		'ei_data')

	@classmethod
	def read(cls, f):
		"""
		@param f: an open ELF file
		@type f: file
		@rtype: ELFHeader
		@return: A new ELFHeader instance containing data from f
		"""
		f.seek(EI_CLASS)
		ei_class = ord(f.read(1))
		ei_data = ord(f.read(1))

		if ei_class == ELFCLASS32:
			width = 32
		elif ei_class == ELFCLASS64:
			width = 64
		else:
			width = None

		if ei_data == ELFDATA2LSB:
			uint16 = decode_uint16_le
			uint32 = decode_uint32_le
			uint64 = lambda data: struct.unpack_from("<Q", data)[0]
		elif ei_data == ELFDATA2MSB:
			uint16 = decode_uint16_be
			uint32 = decode_uint32_be
			uint64 = lambda data: struct.unpack_from(">Q", data)[0]
		else:
			uint16 = None
			uint32 = None

		if width is None or uint16 is None:
			e_flags = None
			e_phentsize = None
			e_phnum = None
			e_phoff = None
			e_machine = None
			e_type = None
			e_flags = None
		else:
			f.seek(E_TYPE)
			e_type = uint16(f.read(2))
			f.seek(E_MACHINE)
			e_machine = uint16(f.read(2))

			# E_ENTRY + sizeof(uintN)
			f.seek(E_ENTRY + width)
			e_phoff = uint32(f.read(4)) if ei_class == ELFCLASS32 else uint64(f.read(8))

			# E_ENTRY + 3 * sizeof(uintN)
			e_flags_offset = E_ENTRY + 3 * width // 8
			f.seek(e_flags_offset)
			e_flags = uint32(f.read(4))

			# decode_uint16_le + 3 * sizeof(short)
			f.seek(e_flags_offset + 6)
			e_phentsize = uint16(f.read(2))
			e_phnum = uint16(f.read(2))


		obj = cls()
		obj.e_flags = e_flags
		obj.e_phentsize = e_phentsize
		obj.e_phnum = e_phnum
		obj.e_phoff = e_phoff
		obj.e_machine = e_machine
		obj.e_type = e_type
		obj.ei_class = ei_class
		obj.ei_data = ei_data

		return obj
