FROM ubuntu:14.04
MAINTAINER Sergey Skripnick <sskripnick@mirantis.com>
RUN apt-get update && apt-get --force-yes -y install python3-pip libyaml-dev
RUN useradd -m rally
COPY . /tmp/rallyci
RUN cd /tmp/rallyci && python3 setup.py install
WORKDIR /home/rally
