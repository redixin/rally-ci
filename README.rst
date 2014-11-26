
Configuration file
##################

Projects section
****************

name
====

A project org/name, e.g. openstack/nova.


job-common-attrs
================

This attributes will be copued to every job::

    projects:
        - name: openstack/nova
          job-common-attrs:
            driver: local-docker
          jobs:
           - name: pep8
             test-commands: ["tox -epep8"]
           - name: py27
             test-commands: ["tox -epy27"]

is equevalent to::

    projects:
        - name: openstack/nova
          jobs:
           - name: pep8
             test-commands: ["tox -epep8"]
             driver: local-docker
           - name: py27
             test-commands: ["tox -epy27"]
             driver: local-docker


jobs
====

Job definitions

name
----

Job name. Should be unique across the project.

driver
------

Driver module to be used for job

driver-args
-----------

Driver specific arguments to be passed to driver

test-commands
-------------

List of commands to be executed



Nginx
#####

Sample config::

    location / {
            fancyindex on;
    }
    location ~ \.txt\.gz$ {
            add_header Content-type text/plain;
            add_header Content-encoding gzip;
    }
