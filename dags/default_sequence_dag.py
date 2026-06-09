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
from seq_dags.sequence_count import sequence_count_task

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


verify_prefile_task = PythonOperator(
    dag=dag,
    task_id='run_verify_file',
    retries=1,
    provide_context=True,
    python_callable=verify_file_exists,
)

miso_samplesheet_generate_command = """
        rsync -av /scratch/gencore/workflows/guru/miso-samplesheet-bcl.py "{{ dag_run.conf["scratch_dir"] }}/"
        cd "{{ dag_run.conf["scratch_dir"] }}/"
        module load python/3.9.0
        python miso-samplesheet-bcl.py {{ dag_run.conf["miso_id"]}}
"""

miso_samplesheet_generate_task = SSHOperator(
    task_id='miso_samplesheet_generate',
    ssh_hook=ssh_hook,
    command=miso_samplesheet_generate_command,
    dag=dag
)

"""Enabled the reverse complement script"""

demux_rev_comp_command = """
        rsync -av /scratch/gencore/workflows/guru/demux-revComp-mixbp-bcl.sh "{{ dag_run.conf["scratch_dir"] }}/"
        cd "{{ dag_run.conf["scratch_dir"] }}/"
        "{{ dag_run.conf["scratch_dir"] }}/"demux-revComp-mixbp-bcl.sh {{ dag_run.conf["reverse_id"]}} 
"""
demux_rev_comp_task = SSHOperator(
    task_id='demux_rev_comp',
    ssh_hook=ssh_hook,
    command=demux_rev_comp_command,
    retries=1,
    dag=dag
)


""" Basemake injection to add Override cycles"""

base_mask_inject_command = """
         rsync -av /scratch/gencore/workflows/guru/basemask-runinfo-bcl.py "{{ dag_run.conf["scratch_dir"] }}/"
         cd "{{ dag_run.conf["scratch_dir"] }}/"
         module load python/3.9.0
         python basemask-runinfo-bcl.py
"""

base_mask_inject_task = SSHOperator(
     task_id='base_mask_inject',
     ssh_hook=ssh_hook,
     command=base_mask_inject_command,
     on_success_callback=None,
     on_failure_callback=update_failure,
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



"""Defining the demultiplex task using Python operator"""
demultiplex_task = PythonOperator(
    task_id='demultiplex',
    retries=1,
    python_callable=run_demultiplex_task,
    provide_context=True,
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

"""Generate output of sequence count"""
generate_sequence_count_task = PythonOperator(
    task_id='sequence_count_sent',
    retries=1,
    python_callable=sequence_count_task,
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
rsync_work_to_scratch_task >> verify_prefile_task >> email_pre_sent_task  >> miso_samplesheet_generate_task >> demux_rev_comp_task >> base_mask_inject_task >> adapter_string_replace_task  >> demultiplex_task >> submit_qc_workflow_task >> generate_sequence_count_task  >> email_post_sent_task >> archive_scratch_folder_task

"""Procedure ends"""
