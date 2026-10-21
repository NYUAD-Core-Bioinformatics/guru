from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.ssh.hooks.ssh import SSHHook

#Loading custom dag scripts
from status_dags.down_status import downstream_status


"""Defining dag profiles, schedule_interval is set to None, since it is based on trigger based dagrun"""

dag = DAG('downstat_dag', description='Downstream Status DAG',
          schedule_interval=None,
          start_date=datetime(2025, 10, 1), catchup=False)

ssh_hook = SSHHook(ssh_conn_id='guru_ssh')
ssh_hook.no_host_key_check = True

"""Defining QC workflow using Python operator"""
downstream_analysis_task = PythonOperator(
    dag=dag,
    task_id='Downstream_status',
    python_callable=downstream_status,
)

downstream_analysis_task
