ARG WEBTREES_BASE
ARG PHP_BASE
ARG COMPOSER_BASE
FROM ${WEBTREES_BASE} AS upstream
FROM ${COMPOSER_BASE} AS composer
FROM ${PHP_BASE}
LABEL org.opencontainers.image.source="https://github.com/harrywesterman/openvoorouders"
# Reuse the patched upstream application, with an independently pinned PHP runtime.
ENV WEBTREES_HOME=/var/www/webtrees
WORKDIR /var/www/webtrees
COPY tools/imagick/ /opt/imagick/
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 curl mariadb-client postgresql-client unzip ca-certificates \
      libmagickwand-dev libpq-dev libzip-dev libicu-dev libfreetype6-dev libjpeg62-turbo-dev libpng-dev \
      autoconf g++ make pkg-config \
 && cd /opt/imagick && phpize && ./configure && make -j2 && make install \
 && docker-php-ext-enable imagick \
 && docker-php-ext-configure gd --with-freetype --with-jpeg \
 && docker-php-ext-install -j2 pdo_mysql pdo_pgsql zip intl gd exif opcache \
 && mv "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini" \
 && rm -rf /var/lib/apt/lists/* /etc/apache2/sites-enabled/000-*.conf /var/www/html \
 && a2enmod rewrite ssl
COPY --from=upstream /var/www/webtrees/ /var/www/webtrees/
COPY --from=upstream /bak/ /bak/
COPY --from=upstream /docker-entrypoint.py /docker-healthcheck.sh /
COPY --from=upstream /etc/apache2/sites-available/ /etc/apache2/sites-available/
COPY --from=composer /usr/bin/composer /usr/local/bin/composer
COPY modules/ /opt/managed-modules/
COPY module/ /opt/managed-modules/openvoorouders/
COPY containers/webtrees/ /opt/openvoorouders/
COPY release.json /opt/openvoorouders/release.json
# Upstream API contains composer.lock. Other plugins use install-ready release assets.
RUN cd /opt/managed-modules/api-mcp \
 && composer install --no-dev --prefer-dist --no-interaction --classmap-authoritative \
 && rm /usr/local/bin/composer \
 && chown -R root:root /opt/managed-modules \
 && chmod -R a-w /opt/managed-modules \
 && groupadd -g 10001 ovo && usermod -a -G ovo www-data \
 && mkdir -p /opt/ovo-data /opt/ovo-control
COPY containers/webtrees/maintenance.conf /etc/apache2/conf-enabled/ovo-maintenance.conf
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=24 CMD /docker-healthcheck.sh
ENTRYPOINT ["python3", "/opt/openvoorouders/start.py"]
