from datetime import datetime
from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.ssh.hooks.ssh import SSHHook

"""Loading python dag run scripts"""
from seq_dags.archive_seq  import archive_scratch_dir_folder
from seq_dags.demultiplex_seq import run_demultiplex_task
from seq_dags.email_pre_seq import run_pre_email_task
from seq_dags.email_post_seq import run_post_email_task
from seq_dags.submit_qc_workflow_seq import submit_qc_workflow_to_slurm
from seq_dags.verify_prefile import verify_file_exists 

"""Loading jira module"""
from nyuad_cgsb_jira_client.jira_client import jira_client


"""Defining dag profiles, schedule_interval is set to None, since it is based on trigger based dagrun"""

dag = DAG('default_sequence', description='Default Sequence DAG',
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
        chgrp users {{ dag_run.conf["scratch_dir"] }}
"""

rsync_work_to_scratch_task = SSHOperator(
    task_id='rsync_work_to_scratch',
    ssh_hook=ssh_hook,
    command=rsync_work_to_scratch_command,
    dag=dag
)


"""Defining samplesheet generate task, using SSHoperator which triggered a python script on remote machine.
for eg:-
$rsync /scratch/scripts/miso_samplesheet_10X.py /scratch/test/
cd /scratch/test/
module load python/3.9.0
python miso_samplesheet_10X.py <num>
"""

verify_prefile_task = PythonOperator(
    dag=dag,
    task_id='run_verify_file',
    retries=1,
    provide_context=True,
    python_callable=verify_file_exists,
)

miso_samplesheet_generate_command = """
        rsync -av /scratch/gencore/workflows/latest/miso_samplesheet_gen.py "{{ dag_run.conf["scratch_dir"] }}/"
        cd "{{ dag_run.conf["scratch_dir"] }}/"
        module load python/3.9.0
        python miso_samplesheet_gen.py {{ dag_run.conf["miso_id"]}}
"""

miso_samplesheet_generate_task = SSHOperator(
    task_id='miso_samplesheet_generate',
    ssh_hook=ssh_hook,
    command=miso_samplesheet_generate_command,
    dag=dag
)

"""Enabled the reverse complement script"""

demux_rev_comp_command = """
        rsync -av /scratch/gencore/workflows/latest/demux-revComp.sh "{{ dag_run.conf["scratch_dir"] }}/"
        cd "{{ dag_run.conf["scratch_dir"] }}/"
        "{{ dag_run.conf["scratch_dir"] }}/"demux-revComp.sh {{ dag_run.conf["reverse_id"]}} 
"""
demux_rev_comp_task = SSHOperator(
    task_id='demux_rev_comp',
    ssh_hook=ssh_hook,
    command=demux_rev_comp_command,
    retries=1,
    dag=dag
)

"""Enabled the adapter string replace"""

adapter_string_replace_command = """
        cd "{{ dag_run.conf["scratch_dir"] }}/"
        sed -i s/adpread1/{{ dag_run.conf["adpone"]}}/g SampleSheet.csv
        sed -i s/adpread2/{{ dag_run.conf["adptwo"]}}/g SampleSheet.csv
"""
adapter_string_replace_task = SSHOperator(
    task_id='adapter_string_replace',
    ssh_hook=ssh_hook,
    command=adapter_string_replace_command,
    retries=1,
    dag=dag
)

"""Validating sample name '_' charactor"""

validate_samplename_command = """
        rsync -av /scratch/gencore/workflows/latest/miso_samplename_validation.sh "{{ dag_run.conf["scratch_dir"] }}/"
        cd "{{ dag_run.conf["scratch_dir"] }}/"
        "{{ dag_run.conf["scratch_dir"] }}/"miso_samplename_validation.sh
"""
validate_samplename_task = SSHOperator(
    task_id='validate_samplename',
    ssh_hook=ssh_hook,
    command=validate_samplename_command,
    retries=1,
    dag=dag
)


"""Defining the demultiplex task using Python operator"""
demultiplex_task = PythonOperator(
    task_id='demultiplex',
    retries=1,
    python_callable=run_demultiplex_task,
    provide_context=True,
    dag=dag
)

"""Verify the output of demux, whether it processed correctly"""
demux_validation = """
        grep "Processing completed with 0 errors and 0 warnings"  {{ dag_run.conf["scratch_dir"] }}/*.err" 
"""

demux_validation_task = SSHOperator(
    task_id='demux_validation',
    ssh_hook=ssh_hook,
    command=demux_validation,
    dag=dag
)

"""Defining QC workflow using Python operator"""
submit_qc_workflow_task = PythonOperator(
    dag=dag,
    task_id='submit_qc_workflow',
    retries=1,
    provide_context=True,
    python_callable=submit_qc_workflow_to_slurm,
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
rsync_work_to_scratch_task >> verify_prefile_task >> email_pre_sent_task  >> miso_samplesheet_generate_task >> demux_rev_comp_task >> adapter_string_replace_task >> validate_samplename_task >> demultiplex_task >> demux_validation_task >> submit_qc_workflow_task >> email_post_sent_task >> archive_scratch_folder_task


"""Procedure ends"""
