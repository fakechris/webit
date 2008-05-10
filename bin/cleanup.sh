#!/bin/sh

find /var/www/webit -name "*.pyc" -exec rm {} \;
find /var/www/webit -name "*.torrent" -exec rm {} \;
find /var/www/webit -name "*.pyo" -exec rm {} \;

