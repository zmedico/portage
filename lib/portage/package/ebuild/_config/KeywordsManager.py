# Copyright 2010-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'KeywordsManager',
)

from _emerge.Package import Package
from portage import os
from portage.dep import ExtendedAtomDict, _repo_separator, _slot_separator
from portage.localization import _
from portage.package.ebuild._config.helper import ordered_by_atom_specificity
from portage.util import grabdict_package, stack_lists, writemsg
from portage.versions import _pkg_str


class KeywordsResult:

	"""
	This is a new simple class to collect both the accepted keywords calculated, as well as any
	explicitly disabled keywords, which is also useful information to know (and TRACK_KEYWORDS
	makes specific use of this.)
	"""

	def __init__(self, accepted_keywords, disabled_keywords):
		self.accepted_keywords = accepted_keywords
		self.disabled_keywords = disabled_keywords


def expand_incremental(lists):
	"""
	This function is very similar to portage.dbapi.porttree's stack_lists() function, except that we
	keep track of list elements that are explicitly disabled via "-". We return not only the effective
	list, but also the list of any explicitly disabled list elements that are still having "impact"
	on the final list. This is used by the TRACK_KEYWORDS feature, so we can know if a particular
	arch has been *explicitly* disabled for a particular ebuild or not.

	@param lists:
	@return: two sets, the first of the effective values, the second of any explicitly disabled values.
	"""

	# effective_set contains the evaluated result set of the lists. No '-' prefix tokens will be in this list.

	# disabled_set contains the set of 'disabled' tokens that are still currently 'impacting' our effective
	# set. Any '-' prefixes will be stripped. A special value of '*' indicates a '-*' was used and is still
	# impacting the effective set.

	effective_set = set()
	disabled_set = set()

	for sub_list in lists:
		for token in sub_list:
			if token is None:
				continue
			if token == "-*":
				effective_set.clear()
				disabled_set.add('*')
			else:
				if token[:1] in '~-':
					raw_token = token[1:]
				else:
					raw_token = token
				if token[:1] == '-':
					if raw_token in effective_set:
						effective_set.remove(raw_token)
					# -amd64 also turns off ~amd64:
					if '~' + raw_token in effective_set:
						effective_set.remove('~' + raw_token)
					disabled_set.add(raw_token)
				else:
					effective_set.add(token)
					if raw_token in disabled_set:
						disabled_set.remove(raw_token)
					# adding any token will wipe the special '*' disabled value:
					if '*' in disabled_set:
						disabled_set.remove('*')

	return effective_set, disabled_set


class KeywordsManager(object):
	"""Manager class to handle keywords processing and validation"""

	def __init__(self, profiles, abs_user_config, user_config=True,
							global_accept_keywords="", global_track_keywords=""):
		self._pkeywords_list = []
		self.global_accept_keywords = set(global_accept_keywords.split())
		self.global_track_keywords = set(global_track_keywords.split())
		rawpkeywords = [grabdict_package(
			os.path.join(x.location, "package.keywords"),
			recursive=x.portage1_directories,
			verify_eapi=True, eapi=x.eapi, eapi_default=None,
			allow_build_id=x.allow_build_id)
			for x in profiles]
		for pkeyworddict in rawpkeywords:
			if not pkeyworddict:
				# Omit non-existent files from the stack.
				continue
			cpdict = {}
			for k, v in pkeyworddict.items():
				cpdict.setdefault(k.cp, {})[k] = v
			self._pkeywords_list.append(cpdict)
		self._pkeywords_list = tuple(self._pkeywords_list)

		self._p_accept_keywords = []
		raw_p_accept_keywords = [grabdict_package(
			os.path.join(x.location, "package.accept_keywords"),
			recursive=x.portage1_directories,
			verify_eapi=True, eapi=x.eapi, eapi_default=None)
			for x in profiles]
		for d in raw_p_accept_keywords:
			if not d:
				# Omit non-existent files from the stack.
				continue
			cpdict = {}
			for k, v in d.items():
				cpdict.setdefault(k.cp, {})[k] = tuple(v)
			self._p_accept_keywords.append(cpdict)
		self._p_accept_keywords = tuple(self._p_accept_keywords)

		self.pkeywordsdict = ExtendedAtomDict(dict)

		if user_config:
			pkgdict = grabdict_package(
				os.path.join(abs_user_config, "package.keywords"),
				recursive=1, allow_wildcard=True, allow_repo=True,
				verify_eapi=False, allow_build_id=True)

			for k, v in grabdict_package(
				os.path.join(abs_user_config, "package.accept_keywords"),
				recursive=1, allow_wildcard=True, allow_repo=True,
				verify_eapi=False, allow_build_id=True).items():
				pkgdict.setdefault(k, []).extend(v)

			accept_keywords_defaults = global_accept_keywords.split()
			accept_keywords_defaults = tuple('~' + keyword for keyword in \
			                                 accept_keywords_defaults if keyword[:1] not in "~-")
			for k, v in pkgdict.items():
				# default to ~arch if no specific keyword is given
				if not v:
					v = accept_keywords_defaults
				else:
					v = tuple(v)
				self.pkeywordsdict.setdefault(k.cp, {})[k] = v

	def getKeywords(self, cpv, slot, keywords, repo):
		try:
			cpv.slot
		except AttributeError:
			pkg = _pkg_str(cpv, slot=slot, repo=repo)
		else:
			pkg = cpv
		cp = pkg.cp
		keywords = [[x for x in keywords.split() if x != "-*"]]
		for pkeywords_dict in self._pkeywords_list:
			cpdict = pkeywords_dict.get(cp)
			if cpdict:
				pkg_keywords = ordered_by_atom_specificity(cpdict, pkg)
				if pkg_keywords:
					keywords.extend(pkg_keywords)
		return list(expand_incremental(keywords)[0])
		#return stack_lists(keywords, incremental=True)

	def isStable(self, pkg, global_accept_keywords, backuped_accept_keywords):
		mygroups = self.getKeywords(pkg, None, pkg._metadata["KEYWORDS"], None)
		pgroups = global_accept_keywords.split()

		unmaskgroups = self.getPKeywords(pkg, None, None, global_accept_keywords)
		pgroups.extend(unmaskgroups)

		egroups = backuped_accept_keywords.split()

		if unmaskgroups or egroups:
			pgroups = self._getEgroups(egroups, pgroups)
		else:
			pgroups = set(pgroups)

		if self._getMissingKeywords(pkg, pgroups, mygroups):
			return False

		# If replacing all keywords with unstable variants would mask the
		# package, then it's considered stable for the purposes of
		# use.stable.mask/force interpretation. For unstable configurations,
		# this guarantees that the effective use.force/mask settings for a
		# particular ebuild do not change when that ebuild is stabilized.
		unstable = []
		for kw in mygroups:
			if kw[:1] != "~":
				kw = "~" + kw
			unstable.append(kw)

		return bool(self._getMissingKeywords(pkg, KeywordsResult(pgroups, set()), set(unstable)))

	def getMissingKeywords(self,
	                       cpv,
	                       slot,
	                       keywords,
	                       repo,
	                       global_accept_keywords,
	                       backuped_accept_keywords):
		"""
        Take a package and return a list of any KEYWORDS that the user may
        need to accept for the given package. If the KEYWORDS are empty
        and the the ** keyword has not been accepted, the returned list will
        contain ** alone (in order to distinguish from the case of "none
        missing").

        @param cpv: The package name (for package.keywords support)
        @type cpv: String
        @param slot: The 'SLOT' key from the raw package metadata
        @type slot: String
        @param keywords: The 'KEYWORDS' key from the raw package metadata
        @type keywords: String
        @param global_accept_keywords: The current value of ACCEPT_KEYWORDS
        @type global_accept_keywords: String
        @param backuped_accept_keywords: ACCEPT_KEYWORDS from the backup env
        @type backuped_accept_keywords: String
        @rtype: List
        @return: A list of KEYWORDS that have not been accepted.
        """
		mygroups = self.getKeywords(cpv, slot, keywords, repo)
		# Repoman may modify this attribute as necessary.
		pgroups = global_accept_keywords.split()

		unmaskgroups = self.getPKeywords(cpv, slot, repo, global_accept_keywords)
		pgroups.extend(unmaskgroups)

		# Hack: Need to check the env directly here as otherwise stacking
		# doesn't work properly as negative values are lost in the config
		# object (bug #139600)
		egroups = backuped_accept_keywords.split()

		if unmaskgroups or egroups:
			pgroups = self._getEgroups(egroups, pgroups)
		else:
			pgroups = set(pgroups)

		return self._getMissingKeywords(cpv, KeywordsResult(pgroups, set()), mygroups)

	def getRawMissingKeywords(self,
	                          cpv,
	                          slot,
	                          keywords,
	                          repo,
	                          global_accept_keywords):
		"""
        Take a package and return a list of any KEYWORDS that the user may
        need to accept for the given package. If the KEYWORDS are empty,
        the returned list will contain ** alone (in order to distinguish
        from the case of "none missing").  This DOES NOT apply any user config
        package.accept_keywords acceptance.

        @param cpv: The package name (for package.keywords support)
        @type cpv: String
        @param slot: The 'SLOT' key from the raw package metadata
        @type slot: String
        @param keywords: The 'KEYWORDS' key from the raw package metadata
        @type keywords: String
        @param global_accept_keywords: The current value of ACCEPT_KEYWORDS
        @type global_accept_keywords: String
        @rtype: List
        @return: lists of KEYWORDS that have not been accepted
        and the keywords it looked for.
        """

		mygroups = self.getKeywords(cpv, slot, keywords, repo)
		pgroups = global_accept_keywords.split()
		pgroups = set(pgroups)
		return self._getMissingKeywords(cpv, KeywordsResult(pgroups, set()), mygroups)

	@staticmethod
	def _getEgroups(egroups, mygroups):
		"""gets any keywords defined in the environment

        @param backuped_accept_keywords: ACCEPT_KEYWORDS from the backup env
        @type backuped_accept_keywords: String
        @rtype: List
        @return: list of KEYWORDS that have been accepted
        """
		mygroups = list(mygroups)
		mygroups.extend(egroups)
		inc_pgroups = set()
		for x in mygroups:
			if x[:1] == "-":
				if x == "-*":
					inc_pgroups.clear()
				else:
					inc_pgroups.discard(x[1:])
			else:
				inc_pgroups.add(x)
		return inc_pgroups

	def _getMissingKeywords(self, cpv, accepted_kwresult, ebuild_keywords):
		"""

		This method takes the effective ACCEPT_KEYWORDS and KEYWORDS settings for a particular package,
		and then determines if the package should be masked or not. The return value is a list of any
		'missing' KEYWORDS, in other words, a list of keywords where any one of them added to
		ACCEPT_KEYWORDS would allow the package to be unmasked. So for example, if the accepted_keywords
		are [], and the ebuild's keywords are [ 'x86', 'amd64' ], you would get [ 'x86', 'amd64' ]
		returned.

		If no keywords are missing, or in other words the ebuild should be visible and unmasked since
		the keywords settings are 'good', then an empty list [] is returned.

		If the ebuild has no keywords specified, so that it will always be masked, then the special
		value [ "**" ] is returned, indicating "you are missing a ** setting for the package to get
		it keyword unmasked.

		The TRACK_KEYWORDS global allows one arch to track another arch. This way, say, arm64 can
		track amd64 and have similar keyword masking. TRACK_KEYWORDS of "amd64 ~amd64" on an unstable
		arm64 system will mean that we effectively have an ACCEPT_KEYWORDS of "amd64 ~amd64 arm64
		~arm64".

		TODO: should we make this so ACCEPT_KEYWORDS is effectively "amd64 ~amd64", in other words
		      *ignore our native arch keywords too?*

		There is one exception to this rule and why we don't simply use ACCEPT_KEYWORDS for this
		purpose. With TRACK_KEYWORDS, it is still possible to have packages on an arch explicitly
		keyword masked via -arch, like "-arm64".

		If a package in our native arch is ever *explicitly* keyword masked via -arch via
		package.keywords in profiles or KEYWORDS in the ebuild, then it is truly masked on our
		arch as well *even if* it is unmasked on the TRACK_KEYWORDS arches.

		This way we still have the ability to hard-keyword-mask packages that are incompatible
		with certain arches. But in all other respects, we can have the same ebuilds available as
		another arch.

		@param cpv: package atom, not used at all, but useful to have for debugging.
		@param accepted_kwresult: effective ACCEPT_KEYWORDS for this package. Also includes
								  explicitly disabled keywords.
		@param ebuild_keywords: effective KEYWORDS for this package -- all '-' entries are already
								stripped.
		@return: A list containing missing keywords. See above for a more detailed explanation.


        """
		match = False
		hasstable = False
		hastesting = False
		pgroups = accepted_kwresult.accepted_keywords

		for gp in ebuild_keywords:
			if gp == "*":
				match = True
				break
			elif gp == "~*":
				hastesting = True
				for x in pgroups:
					if x[:1] == "~":
						match = True
						break
				if match:
					break
			elif gp in pgroups:
				match = True
				break
			elif gp.startswith("~"):
				hastesting = True
			elif not gp.startswith("-"):
				hasstable = True
		if match:
			missing = []
		elif (hastesting and "~*" in pgroups) or (hasstable and "*" in pgroups) or "**" in pgroups:
			missing = []
		elif not ebuild_keywords:
			missing = ['**']
		# TRACK_KEYWORDS functionality. See docstring.
		elif '*' not in accepted_kwresult.disabled_keywords and \
			[x for x in ebuild_keywords if x in self.global_track_keywords] and \
			not [x for x in accepted_kwresult.disabled_keywords if x in self.global_accept_keywords]:
			missing = []
		else:
			missing = ebuild_keywords
		return missing

	def getPKeywords(self, cpv, slot, repo, global_accept_keywords):
		"""Gets any package.keywords settings for cp for the given
        cpv, slot and repo

        @param cpv: The package name (for package.keywords support)
        @type cpv: String
        @param slot: The 'SLOT' key from the raw package metadata
        @type slot: String
        @param keywords: The 'KEYWORDS' key from the raw package metadata
        @type keywords: String
        @param global_accept_keywords: The current value of ACCEPT_KEYWORDS
        @type global_accept_keywords: String
        @param backuped_accept_keywords: ACCEPT_KEYWORDS from the backup env
        @type backuped_accept_keywords: String
        @rtype: List
        @return: list of KEYWORDS that have been accepted
        """

		pgroups = global_accept_keywords.split()
		try:
			cpv.slot
		except AttributeError:
			cpv = _pkg_str(cpv, slot=slot, repo=repo)
		cp = cpv.cp

		unmaskgroups = []
		if self._p_accept_keywords:
			accept_keywords_defaults = tuple('~' + keyword for keyword in \
			                                 pgroups if keyword[:1] not in "~-")
			for d in self._p_accept_keywords:
				cpdict = d.get(cp)
				if cpdict:
					pkg_accept_keywords = \
						ordered_by_atom_specificity(cpdict, cpv)
					if pkg_accept_keywords:
						for x in pkg_accept_keywords:
							if not x:
								x = accept_keywords_defaults
							unmaskgroups.extend(x)

		pkgdict = self.pkeywordsdict.get(cp)
		if pkgdict:
			pkg_accept_keywords = \
				ordered_by_atom_specificity(pkgdict, cpv)
			if pkg_accept_keywords:
				for x in pkg_accept_keywords:
					unmaskgroups.extend(x)
		return unmaskgroups
