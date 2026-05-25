import logging
from jinja2 import Environment, BaseLoader
import tempfile
import os
import time

from seq_dags.ssh_helpers import execute_ssh_command, initialize_ssh, execute_ssh_command_return_stdout_stderr
from seq_dags.slurm_helpers import get_job_status, poll_slurm_job, parse_slurm_submission
from airflow.providers.ssh.hooks.ssh import SSHHook

logger = logging.getLogger('submit_demultiplex')
logger.setLevel(logging.DEBUG)

def generate_demultiplex_slurm_job(kwargs):
    job_template = """#!/bin/bash
#SBATCH --output={{kwargs['dag_run'].conf["jira_ticket"]}}-demultiplex_%A.out
#SBATCH --error={{kwargs['dag_run'].conf["jira_ticket"]}}-demultiplex_%A.err
#SBATCH -J {{kwargs['dag_run'].conf["jira_ticket"]}}-demultiplex
#SBATCH --nodes=1
#SBATCH -A gencore
#SBATCH --ntasks=1
#SBATCH --partition=gencore
#SBATCH --cpus-per-task=28
#SBATCH --time=1000:00:00
#SBATCH --mem 420000


{{kwargs['ti'].xcom_pull(key='demultiplex_command') }}
"""
    rtemplate = Environment(loader=BaseLoader).from_string(job_template)
    rendered_submit_demultiplex_command = rtemplate.render(kwargs=kwargs)
    return rendered_submit_demultiplex_command


def generate_submit_demultiplex_to_slurm_command(dag_run, script):
    job_template = """
cd {{dag_run.conf["scratch_dir"]}} && chmod 777 *sh && sbatch {{script}}
"""
    rtemplate = Environment(loader=BaseLoader).from_string(job_template)
    return rtemplate.render(dag_run=dag_run, script=script)


def submit_demultiplex_job_to_slurm(ssh, sftp, kwargs):
    generate_demultiplex_command(kwargs)

    dag_run = kwargs['dag_run']
    try:
        slurm_script_str = generate_demultiplex_slurm_job(kwargs)
    except:
        raise ("Couldn't generate slurm job! Aborting mission!")

    with tempfile.NamedTemporaryFile('w+') as fp:
        print(slurm_script_str)
        try:
            fp.write(str(slurm_script_str))
        except:
            raise Exception("Unable to write slurm script to temp file!")
        fp.seek(0)
        script = os.path.join(dag_run.conf['scratch_dir'], 'demultiplex.sh')
        try:
            sftp.put(fp.name, script, callback=None)
        except:
            raise Exception("Unable to place temp script on jubail!")

    try:
        slurm_command = generate_submit_demultiplex_to_slurm_command(dag_run, script)
    except:
        raise Exception("Unable to generate slurm wrapper")
    output = execute_ssh_command_return_stdout_stderr(ssh,
                                                      slurm_command, logger)
    return output

def generate_demultiplex_command(kwargs):
    dag_run = kwargs['dag_run']
    work_dir = dag_run.conf['work_dir']
    scratch_dir = dag_run.conf['scratch_dir']
    jira_ticket = dag_run.conf['jira_ticket']

    demultiplex_command = """mkdir -p {scratch_dir}/Unaligned && \\
    cd {scratch_dir} && \\
    bcl-convert --bcl-input-directory {scratch_dir}/ \\
    --output-directory {scratch_dir}/Unaligned \\
    --sample-sheet  {scratch_dir}/SampleSheet.csv \\
    --no-lane-splitting true -f""".format(
        scratch_dir=scratch_dir,
        work_dir=work_dir,
    )
    dag_run.conf['demultiplex_command'] = demultiplex_command
    kwargs['ti'].xcom_push(key='demultiplex_command', value=demultiplex_command)



def run_demultiplex_task(ds, **kwargs):
    ssh_hook = SSHHook(ssh_conn_id='guru_ssh')
    ssh = ssh_hook.get_conn()
    sftp = ssh.open_sftp()

    output = submit_demultiplex_job_to_slurm(ssh, sftp, kwargs)
    slurm_job_id = parse_slurm_submission(output)
    poll_slurm_job(ssh, slurm_job_id)
    ssh.close()
