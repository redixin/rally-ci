FROM ubuntu:14.04
MAINTAINER Sergey Skripnick <sskripnick@mirantis.com>
RUN apt-get update && apt-get --force-yes -y install python3-pip libyaml-dev openssh-server \
                                             nginx-extras supervisor sudo
RUN pip3 install pyyaml websockets
COPY . /tmp/rallyci
RUN cd /tmp/rallyci && python3 setup.py install
RUN useradd -u 65510 -m rally
RUN echo 'rally ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/rally-42
RUN mkdir -p /var/run/sshd /var/www/rally-ci
COPY html/index.html /var/www/rally-ci/index.html
COPY etc/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN rm /etc/nginx/sites-enabled/*
COPY etc/nginx.conf /etc/nginx/sites-enabled/rally-ci-logs.conf
RUN sed -i '1s/^/daemon off;\n/' /etc/nginx/nginx.conf
EXPOSE 22 80 8000
WORKDIR /home/rally
CMD ["/usr/bin/supervisord"]
