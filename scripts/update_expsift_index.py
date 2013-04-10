#!/usr/bin/env python
#
# Copyright (C) 2012 Sivasankar Radhakrishnan <sivasankar@cs.ucsd.edu>
#
# This script updates the redis index database for experiments
# All directories under the base directory are recursively visited, and the
# information in their expsift_tags file is updated in the database.


import base64
import datetime
import gflags
import hashlib
import os
import redis
import stat
import sys


FLAGS = gflags.FLAGS
gflags.DEFINE_string('redis_db_host', 'localhost',
                     'Host for the redis index database')
gflags.DEFINE_integer('redis_db_port', 6379, 'Redis index database port')
gflags.DEFINE_string('base_dir', None, 'Base directory to index')
gflags.DEFINE_bool('flush', False, 'Flush index before updating')


def main(argv):
    # Parse flags
    argv = FLAGS(argv)

    # Check if the base directory is valid
    exists = os.path.exists(FLAGS.base_dir)
    isdir = os.path.isdir(FLAGS.base_dir)
    if not exists:
        print 'Base directory does not exist'
        sys.exit(1)
    if not isdir:
        print 'Base directory not valid'
        sys.exit(1)
    FLAGS.base_dir = os.path.abspath(FLAGS.base_dir)

    # Property names and values DB
    properties_db = redis.StrictRedis(host=FLAGS.redis_db_host,
                                      port=FLAGS.redis_db_port, db=0)

    # Directory to properties DB
    dir2properties_db = redis.StrictRedis(host=FLAGS.redis_db_host,
                                          port=FLAGS.redis_db_port, db=1)

    # Properties to directories DB
    properties2dir_db = redis.StrictRedis(host=FLAGS.redis_db_host,
                                          port=FLAGS.redis_db_port, db=2)

    # SHA1 to directory DB
    sha12dir_db = redis.StrictRedis(host=FLAGS.redis_db_host,
                                    port=FLAGS.redis_db_port, db=3)

    # Flush the databases if required
    if FLAGS.flush:
        properties_db.flushdb()
        dir2properties_db.flushdb()
        properties2dir_db.flushdb()
        sha12dir_db.flushdb()

    # Fill in magic key-value pairs for the databases
    properties_db.set('magic_number', 16378267)
    dir2properties_db.set('magic_number', 76378347)
    properties2dir_db.set('magic_number', 324728749)
    sha12dir_db.set('magic_number', 39916801)


    # Update the database
    print 'Exploring base directory :', FLAGS.base_dir
    for (path, dirs, files) in os.walk(FLAGS.base_dir, followlinks=True):
        # Read tags file and update the redis server
        if os.path.exists(os.path.join(path, 'expsift_tags')):
            tags_file = open(os.path.join(path, 'expsift_tags'), 'r')
            print 'Adding directory', path
            sha1 = hashlib.sha1(path)
            b64_sha1 = base64.b64encode(sha1.digest())
            old_dir = sha12dir_db.get(b64_sha1)
            if old_dir:
                print '    ERRROR: SHA1 hash collision with', old_dir
            sha12dir_db.set(b64_sha1, path)
            for line in tags_file:
                # Comment lines
                if line[0] == '#':
                    continue
                prop_val_str = line.strip()
                line = prop_val_str.split('=', 1)
                assert(len(line) == 2)
                property = line[0]
                val = line[1]
                properties_db.sadd(property, val)
                dir2properties_db.sadd(path, prop_val_str)
                properties2dir_db.sadd(prop_val_str, path)
            tags_file.close()

            # Read the experiment timestamp and GOOD/BAD info
            timestamp = ''
            if os.path.exists(os.path.join(path, 'expsift_info')):
                info_file = open(os.path.join(path, 'expsift_info'), 'r')
                for line in info_file:
                    line = line.strip()
                    if line.startswith('timestamp='):
                        # Make sure it is in valid timestamp format
                        try:
                            ts = datetime.datetime.strptime( line[10:], '%Y-%m-%d_%H:%M:%S.%f')
                            timestamp = line[10:]
                        except:
                            pass
                    elif line == 'GOOD':
                        dir2properties_db.set(path + '__goodbad', 'GOOD')
                    elif line == 'BAD':
                        dir2properties_db.set(path + '__goodbad', 'BAD')
                info_file.close()
            if not timestamp:
                timestamp = datetime.datetime.fromtimestamp( os.stat(path).st_mtime).strftime("%Y-%m-%d_%H:%M:%S.%f")
            dir2properties_db.set(path + '__timestamp', timestamp)


if __name__ == '__main__':
    main(sys.argv)
