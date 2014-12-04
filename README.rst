
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
             runner: local-docker
             runner-args:
               dockerfilepath: "~/conf/docker/rally/"
          jobs:
           - name: pep8
             test-scripts: ["epep8"]
           - name: py27
             test-scripts: ["epy27"]

is equevalent to::

    projects:
        - name: openstack/nova
          jobs:
           - name: pep8
             test-scripts: ["epep8"]
             runner: local-docker
           - name: py27
             test-scripts: ["epy27"]
             runner: local-docker


jobs
====

Job definitions

name
----

Job name. Should be unique across the project.

runner
------

Runner to be used for job

runner-args
-----------

Runner specific arguments to be passed to runner's "setup" method

test-scripts
------------

List of scripts to be executed



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
