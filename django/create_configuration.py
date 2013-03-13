#!/usr/bin/env python

import tempfile
import os.path as op
import os
import re
import sys
from random import choice

# Import everything from the configuration file
from configuration import *

def exit_err(msg):
    print(msg)
    sys.exit(1)

# Make sure trailing and leading slashes are where they are expected.
if abs_catmaid_path[-1] == '/':
    exit_err("abs_catmaid_path should not have a trailing slash! Aborting.")
if catmaid_servername[-1] == '/':
    exit_err("catmaid_servername should not have a trailing slash! Aborting.")
if catmaid_servername.startswith('http://'):
    exit_err("catmaid_servername should not start with 'http://'! Aborting.")
if len(catmaid_subdirectory) > 0:
    if catmaid_subdirectory[-1] == '/':
        exit_err("catmaid_subdirectory should not have a trailing slash! Aborting.")
    if catmaid_subdirectory[0] == '/':
        exit_err("catmaid_subdirectory should not have a leading slash! Aborting.")

in_configfile = op.join('projects/mysite/django.wsgi.example')
out_configfile = op.join('projects/mysite/django.wsgi')

o = open( out_configfile ,'w')
data = open( in_configfile, 'r' ).read()
data = re.sub('CATMAIDPATH', abs_catmaid_path, data)
data = re.sub('PYTHONLIBPATH', abs_virtualenv_python_library_path, data)
o.write( data )
o.close()

# Create a secret key for Django
alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
catmaid_secret_key = ''.join([choice(alphabet) for i in range(50)])

for f in ['', '_apache']:
    in_configfile = op.join('projects/mysite/settings{0}.py.example'.format(f))
    out_configfile = op.join('projects/mysite/settings{0}.py'.format(f))
    o = open( out_configfile ,'w')
    data = open( in_configfile, 'r' ).read()
    data = re.sub('CATMAIDPATH', abs_catmaid_path, data)
    data = re.sub('CATMAID_DATABASE_NAME', catmaid_database_name, data)
    data = re.sub('CATMAID_DATABASE_USERNAME', catmaid_database_username, data)
    data = re.sub('CATMAID_DATABASE_PASSWORD', catmaid_database_password, data)
    data = re.sub('CATMAID_SECRET_KEY', catmaid_secret_key, data)
    data = re.sub('CATMAID_TIMEZONE', catmaid_timezone, data)
    data = re.sub('CATMAID_WRITABLE_PATH', catmaid_writable_path, data)
    data = re.sub('CATMAID_HDF5_SUBDIR', catmaid_hdf5_subdir, data)
    data = re.sub('CATMAID_CROP_SUBDIR', catmaid_crop_subdir, data)
    data = re.sub('CATMAID_SERVERNAME', catmaid_servername, data)
    data = re.sub('CATMAID_SUBDIR', catmaid_subdirectory, data)
    # If CATMAID doesn't live in a sub-directery, double-slashes can occur
    # in the generated configurations. Remove those:
    data = re.sub('//', '/', data)
    # Write out the configuration
    o.write( data )
    o.close()


out = """
Alias /{subdir}/dj-static/ {cmpath}/django/static/
Alias /{subdir}/dj-static-admin/ {cmpath}/django/static-admin/

Alias /{subdir}/dj {cmpath}/django/projects/mysite/django.wsgi
<Location /catmaid/dj>
SetHandler wsgi-script
Options +ExecCGI
</Location>

Alias /{subdir}/ {cmpath}/httpdocs/
<Directory {cmpath}/httpdocs/>

php_admin_value register_globals off
php_admin_value include_path ".:{cmpath}/inc"
php_admin_value session.use_only_cookies 1
php_admin_value error_reporting 2047
php_admin_value display_errors true

Options FollowSymLinks
AllowOverride AuthConfig Limit FileInfo
Order deny,allow
Allow from all

</Directory>

""".format(cmpath = abs_catmaid_path, subdir = catmaid_subdirectory)
print('Apache configuration settings')
print('-----------------------------')
print(out)
