#!/usr/bin/env python
#
# Shotgun change sync daemon
#
# Largely copied from P4 example change review daemon from here:
#  http://public.perforce.com/wiki/P4Review
#
# If run directly with the <repeat> configuration variable = 1, the script
# will sleep for "sleeptime" seconds and then run again.  On UNIX you can
# run the script from cron by setting <repeat> = 0 and adding the following
# line to the cron table with "crontab -e:"
#
#        * * * * * /path/to/shotgun_revision_create.py
#
# This will run the script every minute.  Note that if you use cron you
# should be sure that the script will complete within the time allotted.
#
# The CONFIGURATION VARIABLES below should be examined and in some
# cases changed.
#
#
# Common errors and debugging tips:
#
# -> Error: "command not found" (Windows) or "name: not found" (UNIX) errors.
#
#     - On Windows, check that "p4" is on your PATH or set:
#       p4='"c:/program files/perforce/p4"' (or to the appropriate path).
#       (NOTE the use of " inside the string to prevent interpretation of
#       the command as "run c:/program with arguments files/perforce/p4...")
#
#     - On UNIX, set p4='/usr/local/bin/p4' (or to the appropriate path)
#
# -> Error: "You don't have permission for this operation"
#
#     - Check that the user you set os.environ['P4USER'] to (see below)
#       has "review" or "super" permission via "p4 protect".
#       This user should be able to run "p4 -u username counter test 42"
#       (this sets the value of a counter named "test" to 42)
#


import sys, os, string, re, time, traceback
from shotgun_api3 import Shotgun


##########################################################################
#############                                                    #########
#############      CONFIGURATION VARIABLES: CHANGE AS NEEDED     #########
#############                                                    #########

# Enable debug to print out more details of what the script is doing
debug = 1

# Shotgun server config
shotgun_server = ""
shotgun_script_name = ""
shotgun_script_key = ""

# Must always have some project to create a Revision, so set a default
# one if we can't figure out the right project from the file path
shotgun_default_project = { 'type':'Project', 'id':64 }

os.environ['P4PORT'] = ''
# This user must have Perforce review privileges (via "p4 protect")
os.environ['P4USER'] = '' 

# The path of your p4 executable. You can use
# just 'p4' if the executable is in your path.
# NOTE: Use forward slashes EVEN ON WINDOWS,
# since backslashes have a special meaning in Python)
p4 = 'p4'

# Set to 1 to repeat every <sleeptime> seconds.
# Set to 0 to run just once - do this if running from cron.
repeat  = 1

# Number of seconds to sleep between invocations
# Irrelevant if <repeat>, above, is 0.
sleeptime = 1

#############                                                    ##########
#############           END OF CONFIGURATION VARIABLES           ##########
#############                                                    ##########
###########################################################################


def complain(complaint):
  '''
  Send a plaintive message to the human looking after this script if we
  have any difficulties.
  '''
  complaint = complaint + '\n'
  sys.stderr.write(complaint)
    

def set_counter(counter,value):
  if debug: print 'setting counter %s to %s' % (counter,repr(value))
  set_result = os.system('%s counter %s %s' % (p4,counter,value)) 
  if set_result !=0:
    complain('Unable to set counter %s - check user %s ' \
                       + 'has review privileges\n(use p4 protect)"' \
                       % (counter,os.environ['P4USER']))


def sync_change(line):
  if debug: print line[:-1]
  (change_num,author,email,fullname) = \
    re.match( r'^Change (\d+) (\S+) <(\S+)> \(([^\)]+)\)', line).groups()
  description =  os.popen(p4 + ' describe -s ' + change_num,'r').read()
  
  path = get_common_path_for_change(description)
  (project, entity) = get_shotgun_entities_from_path(path)
  
  if not project:
    project = shotgun_default_project
  
  user = sg.find_one("HumanUser", [['login', 'is', author]])
  
  # Create Revision
  parameters = {'project':project,
                 'code':str(change_num),
                 'sg_asset': entity,
                 'description':description,
                 'created_by':user
                 }
  if debug: print "Creating revision in Shotgun: %s" % parameters
  revision = sg.create("Revision", parameters)
  
  return change_num

def sync_changes():
  '''
  Update the "shotgun_sync" counter to reflect the last change synced.
  '''
  if debug:
    current_change=int(os.popen(p4 + ' counter change').read())
    current_sync=int(os.popen(p4 + ' counter shotgun_sync').read())
    print 'Looking for changes to review after change %d and up to %d.' \
           % (current_sync, current_change)

    if current_sync==0:
      print 'The shotgun_sync counter is set to zero.  You may want to set \
it to the last change with\n\n  %s -p %s -u %s counter shotgun_sync %d\n\nor \
set it to a value close to this for initial testing. (The -p and -u may \
not be necessary, but they are printed here for accuracy.)'\
% (p4,os.environ['P4PORT'],os.environ['P4USER'],current_change)
  change = None

  for line in os.popen(p4 + ' review -t shotgun_sync','r').readlines():
    # sample line: Change 1194 jamesst <js@perforce.com> (James Strickland)
    #              change #    author   email             fullname
    change = sync_change(line)

  # if there were change(s) synced in the above loop, update the counter
  if change: set_counter('shotgun_sync',change)

def get_shotgun_entities_from_path(path):
  '''
  Parse the given path and figure out relevant Project, Shot/Asset, and Task 
  info.  This needs implementation to match the way your paths look because
  every studio manages their files differently.
  '''
  project_name = project = entity = None
  #path = "//depot/projects/Road/assets/couch/art/concept1.jpg"
  re_pattern = r"//depot/projects/(\w+)/(\w*)/?(\w*)/?"
  if re.match(re_pattern, path):
    (project_name,entity_type,entity_name) = re.match(re_pattern, path).groups()
  if project_name:
    project = sg.find_one("Project",[['name','is',project_name]])
  if project:
    if entity_type == 'assets':
      entity = sg.find_one("Asset",[['project','is',project],['code','is',entity_name]])
    elif entity_type == 'shots':
      entity = sg.find_one("Shot",[['project','is',project],['code','is',entity_name]])
  return (project, entity)
  

def allAreEqual(strlist):
  '''
  Returns True iff all elements of strlist compare equal (case insensitive).
  '''
  s0 = strlist[0].lower()
  for s in strlist:
    if s0 != s.lower():
      return 0
  return 1

def get_common_path(items):
  '''
  Returns the common base path for the given list of paths.
  '''
  # Break each item into parts and zip the resulting list of lists
  # Each element of zitems is a tuple containing the n-th part from each element in items
  zitems = apply(zip, [item.split('/') for item in items])
  result = []
  for parts in zitems:
    if allAreEqual(parts):
      result.append(parts[0])
    else:
      break
  return '/'.join(result)

def get_common_path_for_change(description):
  '''
  Returns the common (base) path for all files in the given change description.
  The return value is truncated to a maximum length.
  '''
  items = re.findall('(?m)^\.\.\. (//.*)#[0-9]+ ', description)
  if len(items) == 0:
    result = 'Error: no files found!'
  elif len(items) == 1:
    result = items[0]
  else:
    result = get_common_path(items) + '/...'
  if len(result) > 60:
    return result[:57] + '...'
  else:
    return result


def loop_body():
  # Note: there's a try: wrapped around everything so that the program won't
  # halt.  Unfortunately, as a result you don't get the full traceback.
  # If you're debugging this script, remove the special exception handlers
  # to get the real traceback, or figure out how to get a real traceback,
  # by importing the traceback module and defining a file object that
  # will take the output of traceback.print_exc(file=mailfileobject)
  # and mail it (see the example in cgi.py)
  try:
    sync_changes()
  except:
    complain('Shotgun sync daemon problem:\n\n%s' % \
                string.join(apply(traceback.format_exception,\
                sys.exc_info()),''))


if __name__ == '__main__':
  sg = Shotgun(shotgun_server,shotgun_script_name,shotgun_script_key)
  if debug: print 'Entering main loop.'
  while(repeat):
    loop_body()
    if debug: print 'Sleeping for %d seconds.' % sleeptime
    time.sleep(sleeptime)
  else:
    loop_body()
  if debug: print 'Done.'