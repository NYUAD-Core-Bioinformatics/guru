FROM apache/airflow:2.10.2
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
RUN sh pip_custom.sh
RUN pip install -U  --force-reinstall PyJWT
WORKDIR /opt/airflow
