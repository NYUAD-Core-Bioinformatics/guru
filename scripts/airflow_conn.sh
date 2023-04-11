#!/usr/bin/env bash

#############################################################################
# Arguments for Airflow initialization
# So far these protocols SSH / MYSQL / SMTP needed now to connect to cluster
############################################################################

## Defining SSH connection 
airflow connections add  <ssh-conn-name>   --conn-type ssh \
    --conn-host < hostname or IP address > \
    --conn-login user \
    --conn-port 22 \
    --conn-extra '{"key_file": "/home/airflow/.ssh/id_rsa", "missing_host_key_policy": "AutoAddPolicy"}'

## Defining SMTP connection 
airflow connections add <email-conn-name> --conn-type email \
    --conn-host smtp.gmail.com \ 
    --conn-login <emailID> \ 
    --conn-password <email-pass> \ 
    --conn-port <port-num>

## Defining Mysql Connection 
airflow connections add <mysql-conn-name> --conn-type mysql \ 
    --conn-login <user> \
    --conn-password <pass> \
    --conn-host <hostname or IP address > \
    --conn-port <port> \
    --conn-schema <database name> \
    --conn-extra '{"ssl_mode": "DISABLED"}'

