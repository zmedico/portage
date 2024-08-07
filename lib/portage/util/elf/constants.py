# Copyright 2015-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
#
# These constants are available from elfutils:
# https://sourceware.org/git/?p=elfutils.git;a=blob;f=libelf/elf.h;hb=HEAD

EI_CLASS = 4
ELFCLASS32 = 1
ELFCLASS64 = 2

EI_DATA = 5
ELFDATA2LSB = 1
ELFDATA2MSB = 2

E_TYPE = 16
ET_REL = 1
ET_EXEC = 2
ET_DYN = 3
ET_CORE = 4

E_MACHINE = 18
EM_SPARC = 2
EM_386 = 3
EM_68K = 4
EM_MIPS = 8
EM_PARISC = 15
EM_SPARC32PLUS = 18
EM_PPC = 20
EM_PPC64 = 21
EM_S390 = 22
EM_ARM = 40
EM_SH = 42
EM_SPARCV9 = 43
EM_ARC = 45
EM_IA_64 = 50
EM_X86_64 = 62
EM_ARC_COMPACT = 93
EM_ALTERA_NIOS2 = 113
EM_AARCH64 = 183
EM_ARC_COMPACT2 = 195
EM_AMDGPU = 224
EM_RISCV = 243
EM_BPF = 247
EM_ARC_COMPACT3_64 = 253
EM_ARC_COMPACT3 = 255
EM_LOONGARCH = 258
EM_ALPHA = 0x9026

E_ENTRY = 24
EF_MIPS_ABI = 0x0000F000
EF_MIPS_ABI2 = 0x00000020
E_MIPS_ABI_O32 = 0x00001000
E_MIPS_ABI_O64 = 0x00002000
E_MIPS_ABI_EABI32 = 0x00003000
E_MIPS_ABI_EABI64 = 0x00004000

EF_RISCV_RVC = 0x0001
EF_RISCV_FLOAT_ABI = 0x0006
EF_RISCV_FLOAT_ABI_SOFT = 0x0000
EF_RISCV_FLOAT_ABI_SINGLE = 0x0002
EF_RISCV_FLOAT_ABI_DOUBLE = 0x0004
EF_RISCV_FLOAT_ABI_QUAD = 0x0006

EF_LOONGARCH_ABI_LP64_SOFT_FLOAT = 0b001
EF_LOONGARCH_ABI_LP64_SINGLE_FLOAT = 0b010
EF_LOONGARCH_ABI_LP64_DOUBLE_FLOAT = 0b011
EF_LOONGARCH_ABI_ILP32_SOFT_FLOAT = 0b101
EF_LOONGARCH_ABI_ILP32_SINGLE_FLOAT = 0b110
EF_LOONGARCH_ABI_ILP32_DOUBLE_FLOAT = 0b111
EF_LOONGARCH_ABI_MASK = 0x07
