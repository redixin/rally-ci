FROM ubuntu:14.04
MAINTAINER Sergey Skripnick <sskripnick@mirantis.com>
RUN apt-get update && apt-get --force-yes -y install python3-pip libyaml-dev openssh-server nginx-extras supervisor
RUN sed -i '1s/^/daemon off;\n/' /etc/nginx/nginx.conf
RUN useradd -u 65510 -m rally
RUN mkdir /var/run/sshd
COPY . /tmp/rallyci
COPY etc/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY etc/nginx.conf /etc/nginx/sites-enabled/rally-ci-logs.conf
RUN cd /tmp/rallyci && python3 setup.py install
EXPOSE 22 80 8000
WORKDIR /home/rally
CMD ["/usr/bin/supervisord"]
