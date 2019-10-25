#!/usr/bin/env bash

set -ex

echo "Removing existing Postgres installation"
sudo systemctl stop postgresql
sudo apt-get remove -q 'postgresql-*'
echo "Installing Postgres 12"
sudo apt-get update -q
sudo apt-get install -q postgresql-12 postgresql-client-12 postgresql-12-postgis-3 postgresql-12-postgis-3-scripts

# To work better with Travis, follow their default Postgres configuration and
# set each host based authentication entry to "trust" rather than "md5" or
# "peer". Alternatively, we could copy the existing hba file:
# sudo cp /etc/postgresql/{10,12}/main/pg_hba.conf
sudo sed -i -e 's/peer/trust/g' -e 's/md5/trust/g' /etc/postgresql/12/main/pg_hba.conf

echo "Starting Postgres 12"
sudo systemctl start postgresql@12-main

echo "The following Postgres clusters are installed:"
pg_lsclusters
