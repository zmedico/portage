#!/usr/bin/python -b
# Copyright 2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging
import os

import portage
from portage.const import VDB_PATH
from portage.util.iterators.MultiIterGroupBy import MultiIterGroupBy


def regen(args):
	logging.debug("config root: %s", args.config_root)
	logging.debug("dest distdir: %s", args.dest_distdir)
	logging.debug("dest repo: %s", args.dest_repo)
	logging.debug("source dir: %s", args.source_dir)

	src_dbs = []
	for source_dir in args.source_dir:
		if os.path.isdir(os.path.join(source_dir, VDB_PATH)):
			settings = portage.config(
				config_root=args.config_root,
				target_root=source_dir)
			src_dbs.append(portage.vartree(settings=quickpkg_settings).dbapi)
		else:
			src_dbs.append(portage.binarytree(pkgdir=source_dir, settings=portage.config()).dbapi)

	# Use MultiIterGroupBy to compare src and dest repo
	#src_dbs.append(dest_repo)

	iterators = []
	for db in src_dbs:
		# MultiIterGroupBy requires sorted input
		i = db.cp_all(sort=True)
		try:
			i = iter(i)
		except TypeError:
			pass
		iterators.append(i)
	for group in MultiIterGroupBy(iterators):
		#yield group[0]
		pass
