FROM apache/airflow:2.11.2
USER root
#Setting Dubai TZ
ENV TZ=Asia/Dubai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN apt-get update \
  && apt-get install vim -y --no-install-recommends \
  && apt-get autoremove -yqq --purge \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*
USER airflow
RUN echo "alias ll='ls -lah'" >> ~/.bashrc
ADD requirements.txt .
RUN pip install -r requirements.txt
#Copy custom build jira python module
ADD pkgs /opt/airflow/pkgs
USER root
RUN chmod -R 777 /opt/airflow/pkgs
USER airflow
WORKDIR /opt/airflow/pkgs
#Install custom build jira python module
RUN sh pip_docker_jira.sh
RUN pip install -U  --force-reinstall PyJWT
COPY img/navbar.html /home/airflow/.local/lib/python3.12/site-packages/airflow/www/templates/appbuilder/navbar.html
COPY img/mylogo.png /home/airflow/.local/lib/python3.12/site-packages/airflow/www/static/mylogo.png
COPY img/favicon.ico /home/airflow/.local/lib/python3.12/site-packages/airflow/www/static/pin_32.png
RUN sed -i 's|flask_app.config\["APP_NAME"\] = instance_name|flask_app.config["APP_NAME"] = "GURU"|' /home/airflow/.local/lib/python3.12/site-packages/airflow/www/app.py
WORKDIR /opt/airflow
