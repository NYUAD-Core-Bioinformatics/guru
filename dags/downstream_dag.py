from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.ssh.hooks.ssh import SSHHook
from downstream_dags.prepare_custom_workflows import prepare_custom_workflows
from downstream_dags.submit_downstream_workflow_seq import submit_downstream_workflow_to_slurm
from downstream_dags.email_post import run_post_email_task


def print_inputs(**context):
    conf = context["dag_run"].conf

    print("=" * 80)
    print("Scratch Directory :", conf.get("scratch_dir"))
    print("Email Address     :", conf.get("email_address"))
    print("Downstream Analysis:")
    print(conf.get("downstream_analysis"))
    print("=" * 80)


"""Defining dag profiles, schedule_interval is set to None, since it is based on trigger based dagrun"""

dag = DAG(
    'downstream_dag',
    description='Downstream Analysis DAG',
    schedule_interval=None,
    start_date=datetime(2026, 9, 1),
    catchup=False
)

ssh_hook = SSHHook(ssh_conn_id='guru_ssh')
ssh_hook.no_host_key_check = True


"""Print inputs received from plugin"""
display_params = PythonOperator(
    dag=dag,
    task_id='Display_Parameters',
    python_callable=print_inputs,
)

prepare_custom_workflow = PythonOperator(
    dag=dag,
    task_id="prepare_custom_workflow",
    python_callable=prepare_custom_workflows,
)


# # """Triggering a email notication and update jira ticket during the finishing"""
email_post_sent_task = PythonOperator(
    task_id='email_post_sent',
    retries=1,
    provide_context=True,
    python_callable=run_post_email_task,
    dag=dag
)

submit_downstream_workflow_task = PythonOperator(
    dag=dag,
    task_id='submit_downstream_workflow',
    retries=1,
    provide_context=True,
    python_callable=submit_downstream_workflow_to_slurm,
)

display_params >> prepare_custom_workflow >> submit_downstream_workflow_task >> email_post_sent_task

