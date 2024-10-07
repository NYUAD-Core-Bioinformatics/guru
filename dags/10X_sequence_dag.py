from datetime import datetime
from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.ssh.hooks.ssh import SSHHook

"""Loading python 10X workflow dag run scripts"""  
from tenx_dags.archive_ten  import archive_scratch_dir_folder
from tenx_dags.demultiplex_ten import run_demultiplex_task
from tenx_dags.email_pre_ten import run_pre_email_task
from tenx_dags.email_post_ten import run_post_email_task
from tenx_dags.verify_prefile import verify_file_exists 

"""Loading jira module""" 
from nyuad_cgsb_jira_client.jira_client import jira_client


 
"""Defining dag profiles,
schedule_interval is set to None, since it is based on trigger based dagrun"""
dag = DAG('10X_sequence', description='10X Sequence DAG',
          schedule_interval=None,
          start_date=datetime(2023, 4, 1), catchup=False)

"""Retriving ssh connection parameter"""
ssh_hook = SSHHook(ssh_conn_id='guru_ssh')
ssh_hook.no_host_key_check = True

"""Defining work directory to scratch rsync shell command, this is triggered via SSHOperator
for eg:- 
$mkdir /scratch/test/
$rsync -av /work/test /scratch/test
"""

rsync_work_to_scratch_command = """
        mkdir -p {{ dag_run.conf["scratch_dir"] }}
        rsync -av "{{ dag_run.conf["work_dir"] }}/" "{{ dag_run.conf["scratch_dir"] }}/"
"""

rsync_work_to_scratch_task = SSHOperator(
    task_id='rsync_work_to_scratch',
    ssh_hook=ssh_hook,
    command=rsync_work_to_scratch_command,
    dag=dag
)

verify_prefile_task = PythonOperator(
    dag=dag,
    task_id='run_verify_file',
    retries=1,
    provide_context=True,
    python_callable=verify_file_exists,
)

"""Defining samplesheet generate task, using SSHoperator which triggered a python script on remote machine.
for eg:-
$rsync /scratch/scripts/miso_samplesheet_10X.py /scratch/test/
cd /scratch/test/
module load python/3.9.0
python miso_samplesheet_10X.py <num>
"""

miso_samplesheet_generate_command = """
        rsync -av <Path-of-miso-samplesheet-folder>/miso_samplesheet_10X.py "{{ dag_run.conf["scratch_dir"] }}/"
        cd "{{ dag_run.conf["scratch_dir"] }}/"
        module load python/3.9.0
        python miso_samplesheet_gen10X.py {{ dag_run.conf["miso_id"]}}
"""

miso_samplesheet_generate_task = SSHOperator(
    task_id='miso_samplesheet_generate',
    ssh_hook=ssh_hook,
    command=miso_samplesheet_generate_command,
    retries=2,
    retry_delay=60,
    dag=dag
)

"""Defining the 10X workflow demultiplex task using Python operator"""
demultiplex_task = PythonOperator(
    task_id='demultiplex',
    retries=1,
    python_callable=run_demultiplex_task,
    provide_context=True,
    dag=dag
)


"""Triggering a email notication and update jira ticket during the starting"""
email_pre_sent_task = PythonOperator(
    task_id='email_pre_sent',
    retries=1,
    python_callable=run_pre_email_task,
    dag=dag
)

"""Defining the archive task using Python operator
$ rsync -av /scratch/test /archive/test
 """
archive_scratch_folder_task = PythonOperator(
    task_id='archive_run_dir',
    retries=2,
    python_callable=archive_scratch_dir_folder,
    dag=dag
)

"""Triggering a email notication and update jira ticket during the finishing"""
email_post_sent_task = PythonOperator(
    task_id='email_post_sent',
    retries=1,
    python_callable=run_post_email_task,
    dag=dag
)

"""Defining the DAG workflow"""
rsync_work_to_scratch_task >> verify_prefile_task >> email_pre_sent_task  >> miso_samplesheet_generate_task >> demultiplex_task >> email_post_sent_task >> archive_scratch_folder_task


"""Procedure ends"""
