import os, time
from portage_data import portage_uid, portage_gid

def process(mysettings, cpv, logentries, fulltext):
	if mysettings["PORT_LOGDIR"] != "":
		elogdir = os.path.join(mysettings["PORT_LOGDIR"], "elog")
	else:
		elogdir = os.path.join(os.sep, "var", "log", "portage", "elog")
	if not os.path.exists(elogdir):
		os.makedirs(elogdir)
	os.chown(elogdir, portage_uid, portage_gid)
	os.chmod(elogdir, 02770)

	# TODO: Locking
	elogfilename = elogdir+"/summary.log"
	elogfile = open(elogfilename, "a")
	elogfile.write(">>> Messages generated by process %d on %s for package %s:\n\n" % \
			(os.getpid(), time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time())), cpv))
	elogfile.write(fulltext)
	elogfile.write("\n")
	elogfile.close()

	return elogfilename
