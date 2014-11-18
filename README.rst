
Nginx sample config::

        location / {
                fancyindex on;
        }
        location ~ \.txt\.gz$ {
                add_header Content-type text/plain;
                add_header Content-encoding gzip;
        }

