#!/usr/bin/python

# satprep_snapshot.py - a script for creating a snapshot
# report of available errata available to systems managed
# with Spacewalk, Red Hat Satellite or SUSE Manager.
#
# 2014 By Christian Stankowic
# <info at stankowic hyphen development dot net>
# https://github.com/stdevel
#

from optparse import OptionParser
import sys
import xmlrpclib
import os
import stat
import getpass
import time
import csv

#TODO: string + " " + string ==>  string,string
#TODO: escaping ==> r'\tbla}t'



#list of supported API levels
supportedAPI = ["11.1","12","13","13.0","14","14.0","15","15.0"]


def parse_options(args=None):
	desc='''%prog is used to create snapshot CSV reports of errata available to your systems managed with Spacewalk, Red Hat Satellite and SUSE Manager. You can use two snapshot reports to create delta reports using satprep_diff.py. Login credentials are assigned using the following shell variables:

SATELLITE_LOGIN  username
SATELLITE_PASSWORD  password

It is also possible to create an authfile (permissions 0600) for usage with this script. The first line needs to contain the username, the second line should consist of the appropriate password.
If you're not defining variables or an authfile you will be prompted to enter your login information.

Checkout the GitHub page for updates: https://github.com/stdevel/satprep'''
	parser = OptionParser(description=desc,version="%prog version 0.1")

	#-a / --authfile
	parser.add_option("-a", "--authfile", dest="authfile", metavar="FILE", default="", help="defines an auth file to use instead of shell variables")

	#-s / --server
	parser.add_option("-s", "--server", dest="server", metavar="SERVER", default="localhost", help="defines the server to use")

	#-q / --quiet
	parser.add_option("-q", "--quiet", action="store_false", dest="verbose", default=True, help="don't print status messages to stdout")

	#-d / --debug
	parser.add_option("-d", "--debug", dest="debug", default=False, action="store_true", help="enable debugging outputs")

	#-o / --output
	parser.add_option("-o", "--output", action="store", type="string", dest="output", default="foobar", help="define CSV report filename. (default: errata-snapshot-report-RHNhostname-Ymd.csv)", metavar="FILE")

	#-f / --fields
	parser.add_option("-f", "--field", action="append", type="choice", dest="fields", choices=["hostname", "ip", "errata_name", "errata_type", "errata_desc", "errata_date", "errata_reboot", "system_owner", "system_cluster","system_virt","system_monitoring","system_monitoring_notes","system_backup","system_backup_notes","system_antivir","system_antivir_notes"], help="defines which fields should be integrated in the report", metavar="FIELDS")

	#-p / --include-patches
	parser.add_option("-p", "--include-patches", action="store_true", default=False, dest="includePatches", help="defines whether package updates that are not part of an erratum shall be included")

	#-r / --reconnect-threshold
	parser.add_option("-r", "--reconnect-threshold", action="store", type="int", default=5, dest="reconnectThreshold", metavar="THRESHOLD", help="defines after how many host scans a re-login should be done (XMLRPC API timeout workaround)")

	#parse arguments
	(options, args) = parser.parse_args()

	#set some useful default options if not set
	if options.output is 'foobar':
		options.output = "errata-snapshot-report-" + options.server + "-" + time.strftime("%Y%m%d-%H%M") + ".csv"
	if options.fields is None:
		options.fields = ["hostname","ip","errata_name","errata_type","errata_date","errata_desc","errata_reboot","system_owner","system_cluster","system_virt","system_monitoring","system_monitoring_notes","system_backup","system_backup_notes","system_antivir","system_antivir_notes"]

	#print parameters
	if options.debug: print "DEBUG: " + str(options) + str(args)


def main(options):
	#define URL and login information
	SATELLITE_URL = "http://"+options.server+"/rpc/api"

	#setup client and key depending on mode
	client = xmlrpclib.Server(SATELLITE_URL, verbose=options.debug)
	s_username=""
	s_password=""
	if options.authfile:
		#use authfile
		if options.debug: print "DEBUG: using authfile"
		try:
			#check filemode and read file
			filemode = oct(stat.S_IMODE(os.lstat(options.authfile).st_mode))
			if filemode == "0600":
				if options.debug: print "DEBUG: file permission ("+filemode+") matches 0600"
				fo = open(options.authfile, "r")
				s_username=fo.readline()
				s_password=fo.readline()
			else:
				if options.verbose: print "ERROR: file permission ("+filemode+") not matching 0600!"
				exit(1)
		except OSError:
			print "ERROR: file non-existent or permissions not 0600!"
			exit(1)
	elif "SATELLITE_LOGIN" in os.environ and "SATELLITE_PASSWORD" in os.environ:
		#shell variables
		if options.debug: print "DEBUG: checking shell variables"
		s_username=os.environ["SATELLITE_LOGIN"]
		s_password=os.environ["SATELLITE_PASSWORD"]
		#key = client.auth.login(os.environ["SATELLITE_LOGIN"], os.environ["SATELLITE_PASSWORD"])
	else:
		#prompt user
		if options.debug: print "DEBUG: prompting for login credentials"
		s_username = raw_input("Username: ")
		s_password = getpass.getpass("Password: ")
		#key = client.auth.login(s_username, s_password)
	#login
	key = client.auth.login(s_username, s_password)

	#check whether the API version matches the minimum required
	api_level = client.api.getVersion()
	if not api_level in supportedAPI:
		print "ERROR: your API version ("+api_level+") does not support the required calls. You'll need API version 1.8 (11.1) or higher!"
		exit(1)
	else:
		if options.debug: print "INFO: supported API version ("+api_level+") found."

	#check whether the output directory/file is writable
	if os.access(os.path.dirname(options.output), os.W_OK) or os.access(os.getcwd(), os.W_OK):
		if options.verbose: print "INFO: output file/directory writable!"

		#create CSV report, open file
		csv.register_dialect("default", delimiter=";", quoting=csv.QUOTE_NONE)
		writer = csv.writer(open(options.output, "w"), 'default')

		# STYLE DISCLAIMER
		# ----------------
		# I know that the following code is just a mess from the view of an advanced Python coder.
		# I'm quite new to Python and still learning. So if you have any relevant hints let me know.

		#create header and scan _all_ the systems
		writer.writerow(options.fields)
		systems = client.system.listSystems(key)
		#counter variable for XMLRPC timeout workaround (https://github.com/stdevel/satprep/issues/5)
		hostCounter=0
		for system in systems:
			if options.verbose: print "INFO: found host " + `system["name"]` + " (SID " + `system["id"]` + ")"
			#scan errata per system
			errata = client.system.getRelevantErrata(key, system["id"])
			#write information if errata available
			if len(errata) > 0:
				for i,erratum in enumerate(errata):
					if options.verbose: print "INFO: Having a look at relevant errata #"+str(i+1)+" for host " + `system["name"]` + " (SID " + `system["id"]` + ")..."
					#clear value set and set information depending on given fields
					valueSet = []
					this_errataReboot=0
					for column in options.fields:
						if column == "hostname":
							valueSet.append(system["name"])
						elif column == "ip":
							temp = client.system.getNetwork(key, system["id"])
							valueSet.append(temp["ip"])
						elif column == "errata_name":
							valueSet.append(errata[i]["advisory_name"])
						elif column == "errata_type":
							valueSet.append(errata[i]["advisory_type"])
						elif column == "errata_desc":
							valueSet.append(errata[i]["advisory_synopsis"])
						elif column == "errata_date":
							valueSet.append(errata[i]["update_date"])
						elif column == "errata_reboot":
							temp = client.errata.listKeywords(key, errata[i]["advisory_name"])
							if "reboot_suggested" in temp:
								valueSet.append("1")
							else:
								valueSet.append("0")
						elif column == "system_owner":
							#set system owner if information available
							temp = client.system.getCustomValues(key, system["id"])
							if len(temp) > 0 and "SYSTEM_OWNER" in temp:
								#replace new lines
								tmp = temp["SYSTEM_OWNER"].split()
								tmp = ' '.join(tmp)
								valueSet.append(tmp)
							else:
								valueSet.append("null")
						elif column == "system_cluster":
							#set system cluster bit if information available
							temp = client.system.getCustomValues(key, system["id"])
							if len(temp) > 0 and "SYSTEM_CLUSTER" in temp:
							if temp["SYSTEM_CLUSTER"] == "1":
								valueSet.append(1)
							else:
								valueSet.append(0)
							else:
								valueSet.append(0)
						elif column == "system_virt":
							#set system virtualization bit if information available
							temp = client.system.getDetails(key, system["id"])
							if len(temp) > 0 and "virtualization" in temp:
								valueSet.append(1)
							else:
								valueSet.append(0)
						elif column == "system_monitoring":
							#set system monitoring information if information available
							temp = client.system.getCustomValues(key, system["id"])
							if len(temp) > 0 and "SYSTEM_MONITORING" in temp:
								if temp["SYSTEM_MONITORING"] == "1":
									valueSet.append(1)
								else:
									valueSet.append(0)
							else:
								valueSet.append(0)
						elif column == "system_monitoring_notes":
							#set system monitoring notes if information available
							temp = client.system.getCustomValues(key, system["id"])
							if len(temp) > 0 and "SYSTEM_MONITORING_NOTES" in temp:
								if temp["SYSTEM_MONITORING_NOTES"] != "":
									valueSet.append(temp["SYSTEM_MONITORING_NOTES"])
								else: valueSet.append("")
							else: valueSet.append("")
						elif column == "system_backup":
							#set system backup information if available
							temp = client.system.getCustomValues(key, system["id"])
							if len(temp) > 0 and "SYSTEM_BACKUP" in temp:
								if temp["SYSTEM_BACKUP"] == "1":
									valueSet.append(1)
								else:
									valueSet.append(0)
							else:
								valueSet.append(0)
						elif column == "system_backup_notes":
							#set system backup notes if information available
							temp = client.system.getCustomValues(key, system["id"])
							if len(temp) > 0 and "SYSTEM_BACKUP_NOTES" in temp:
								if temp["SYSTEM_BACKUP_NOTES"] != "":
									valueSet.append(temp["SYSTEM_BACKUP_NOTES"])
								else: valueSet.append("")
							else: valueSet.append("")
						elif column == "system_antivir":
							#set system backup information if available
							temp = client.system.getCustomValues(key, system["id"])
							if len(temp) > 0 and "SYSTEM_ANTIVIR" in temp:
								if temp["SYSTEM_ANTIVIR"] == "1":
									valueSet.append(1)
								else:
									valueSet.append(0)
							else:
								valueSet.append(0)
						elif column == "system_antivir_notes":
							#set system antivir notes if information available
							temp = client.system.getCustomValues(key, system["id"])
							if len(temp) > 0 and "SYSTEM_ANTIVIR_NOTES" in temp:
								if temp["SYSTEM_ANTIVIR_NOTES"] != "":
									valueSet.append(temp["SYSTEM_ANTIVIR_NOTES"])
								else: valueSet.append("")
							else: valueSet.append("")

					#write CSV row if information found
					#if len(valueSet) > 0: writer.writerow(valueSet)
					writer.writerow(valueSet)
			else:
				#no errata relevant for system
				if options.debug: print "DEBUG: host " + `system["name"]` + "(SID " + `system["id"]` + ") has no relevant errata."
			if options.includePatches:
				#include non-errata updates
				updates = client.system.listLatestUpgradablePackages(key, system["id"])
				#print updates
				if len(updates) > 0:
					for i,update in enumerate(updates):
						if options.verbose: print "INFO: Having a look at relevant package update #"+str(i+1)+" for host " + `system["name"]` + " (SID " + `system["id"]` + ")..."
						#only add update information if not already displayed as part of an erratum
						temp = client.packages.listProvidingErrata(key, update["to_package_id"])
						if len(temp) == 0:
							#not part of an erratum - clear value set and set information depending on given fields
							valueSet = []
							for column in options.fields:
								if column == "hostname":
									valueSet.append(system["name"])
								elif column == "ip":
									temp = client.system.getNetwork(key, system["id"])
									valueSet.append(temp["ip"])
								elif column == "errata_name":
									valueSet.append(update["name"])
								elif column == "errata_type":
									valueSet.append("Regular update")
								elif column == "errata_desc":
									valueSet.append(update["from_version"] + "-" + update["from_release"] + " to " + update["to_version"] + "-" + update["to_release"])
								elif column == "errata_date":
									valueSet.append("unknown")
								elif column == "errata_reboot":
									valueSet.append("0")
								elif column == "system_owner":
									#set system owner if information available
									temp = client.system.getCustomValues(key, system["id"])
									if len(temp) > 0 and "SYSTEM_OWNER" in temp:
										#valueSet.append(temp["SYSTEM_OWNER"])
										tmp = temp["SYSTEM_OWNER"].split()
										tmp = ' '.join(tmp)
										valueSet.append(tmp)
									else:
										valueSet.append("unknown")
								elif column == "system_cluster":
									#set system cluster bit if information available
									temp = client.system.getCustomValues(key, system["id"])
									if len(temp) > 0 and "SYSTEM_CLUSTER" in temp:
										if temp["SYSTEM_CLUSTER"] == "1":
											valueSet.append(1)
										else:
											valueSet.append(0)
									else:
										valueSet.append(0)
								elif column == "system_virt":
									#set system virtualization bit if information available
									temp = client.system.getDetails(key, system["id"])
									if len(temp) > 0 and "virtualization" in temp:
										valueSet.append(1)
									else:
										valueSet.append(0)
								elif column == "system_monitoring":
									#set system monitoring information if information available
									temp = client.system.getCustomValues(key, system["id"])
									if len(temp) > 0 and "SYSTEM_MONITORING" in temp:
										if temp["SYSTEM_MONITORING"] == "1":
											valueSet.append(1)
										else:
											valueSet.append(0)
									else:
										valueSet.append(0)
								elif column == "system_monitoring_notes":
									#set system monitoring notes if information available
									temp = client.system.getCustomValues(key, system["id"])
									if len(temp) > 0 and "SYSTEM_MONITORING_NOTES" in temp:
										if temp["SYSTEM_MONITORING_NOTES"] != "":
											valueSet.append(temp["SYSTEM_MONITORING_NOTES"])
										else: valueSet.append("")
									else: valueSet.append("")
								elif column == "system_backup":
									#set system backup information if available
									temp = client.system.getCustomValues(key, system["id"])
									if len(temp) > 0 and "SYSTEM_BACKUP" in temp:
										if temp["SYSTEM_BACKUP"] == "1":
											valueSet.append(1)
										else:
											valueSet.append(0)
									else:
										valueSet.append(0)
								elif column == "system_backup_notes":
									#set system backup notes if information available
									temp = client.system.getCustomValues(key, system["id"])
									if len(temp) > 0 and "SYSTEM_BACKUP_NOTES" in temp:
										if temp["SYSTEM_BACKUP_NOTES"] != "":
											valueSet.append(temp["SYSTEM_BACKUP_NOTES"])
										else: valueSet.append("")
									else: valueSet.append("")
								elif column == "system_antivir":
									#set system backup information if available
									temp = client.system.getCustomValues(key, system["id"])
									if len(temp) > 0 and "SYSTEM_ANTIVIR" in temp:
										if temp["SYSTEM_ANTIVIR"] == "1":
											valueSet.append(1)
										else:
											valueSet.append(0)
									else:
										valueSet.append(0)
								elif column == "system_antivir_notes":
									#set system antivir notes if information available
									temp = client.system.getCustomValues(key, system["id"])
									if len(temp) > 0 and "SYSTEM_ANTIVIR_NOTES" in temp:
										if temp["SYSTEM_ANTIVIR_NOTES"] != "":
											valueSet.append(temp["SYSTEM_ANTIVIR_NOTES"])
										else: valueSet.append("")
									else: valueSet.append("")

							#write CSV row if information found
							if len(valueSet) > 0:
								writer.writerow(valueSet)
						else:
							#part of an erratum
							if options.debug: print "DEBUG: dropping update " + update["name"] + "(" + str(update["to_package_id"]) + ") as it's already part of an erratum."
				else:
					#no updates relevant for system
					if options.debug: print "DEBUG: host " + `system["name"]` + "(SID " + `system["id"]` + ") has no relevant updates."

			#increase counter and re-login if necessary
			if hostCounter == (options.reconnectThreshold-1):
				#re-login
				if options.verbose: print "INFO: Re-login due to XMLRPC timeout workaround!"
				client.auth.logout(key)
				key = client.auth.login(s_username, s_password)
				hostCounter=0
			else:
				#increase counter
				hostCounter = hostCounter + 1

	else:
		#output file/directory not writable
		print >> sys.stderr,  "ERROR: Output file/directory ("+options.output+") not writable"

	#logout and exit
	client.auth.logout(key)


if __name__ == "__main__":
	(options, args) = parse_options()

	main(options)
