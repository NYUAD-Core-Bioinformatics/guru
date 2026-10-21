import os
import re
import time
import logging
import smtplib
from email.message import EmailMessage
from jinja2 import Environment, BaseLoader
from airflow.providers.ssh.hooks.ssh import SSHHook
from airflow.hooks.base import BaseHook

from downstream_dags.ssh_helpers import execute_ssh_command_return_stdout_stderr, initialize_ssh
from downstream_dags.biosails_helpers import poll_biosails_submissions

# Logging
logger = logging.getLogger('submit_qc_workflow')
logger.setLevel(logging.DEBUG)

submit_script = """
module load gencore gencore_biosails
cd {{ output_path }}
biox run --samples {{ selected_items }} -w {{ selected_workflow }} -o {{ out }}.sh
hpcrunner.pl submit_jobs -i {{ out }}.sh --project {{ out }}
"""

def downstream_qc_workflow_to_slurm(ds, **kwargs):
    """
    Render a QC workflow with biox, submit via hpcrunner,
    then extract the Stats dir, send an email, and finally poll SLURM jobs.
    """
    dag_run = kwargs.get('dag_run')
    conf = dag_run.conf

    email_id = conf.get("email_address")
    selected_workflow = conf.get("selected_workflow")
    selected_items = conf.get("selected_items")
    output_path = conf.get("output_path")
    base_path = conf.get("base_path")

    if not all([email_id, selected_workflow, selected_items, output_path]):
        raise ValueError("Missing workflow parameters!")

    out = f"{os.path.splitext(os.path.basename(selected_workflow))[0]}_{time.strftime('%Y%m%d_%H%M')}"

    # Setup SSH connection
    ssh_hook = SSHHook(ssh_conn_id='guru_ssh')
    ssh = ssh_hook.get_conn()
    sftp = ssh.open_sftp()

    
    # Update YML search and replace. 

    remote_yaml_path = f"{output_path}/{selected_workflow}"
    try:
        with sftp.open(remote_yaml_path, 'r') as f:
            content = f.read().decode()
        updated_yaml = content.replace("dont_change_this_output_value", output_path)
        updated_yaml = updated_yaml.replace("dont_change_this_input_value", base_path)
        with sftp.open(remote_yaml_path, 'w') as f:
            f.write(updated_yaml)
        print(f" Updated YAML successfully at {remote_yaml_path}")
    except Exception as e:
        print(f" Error updating YAML: {e}")
        raise


    #Render & Run Submission Script
    template = Environment(loader=BaseLoader).from_string(submit_script)
    rendered_command = template.render(
        selected_workflow=selected_workflow,
        output_path=output_path,
        selected_items=selected_items,
        out=out
    )
    logger.info("Rendered SLURM submission command:")
    logger.info(rendered_command)

    try:
        agg_output = execute_ssh_command_return_stdout_stderr(ssh, rendered_command, logger)
    except Exception as e:
        logger.error(f"Error during SSH command execution: {e}")
        raise
    if not agg_output:
        raise Exception("No output from hpcrunner.pl submission found!")


    #Extracting 'Stats dir' from output.
    stats_dir = None
    for line in agg_output:
        if "Stats dir is" in line:
            stats_dir = line.strip().split("Stats dir is")[-1].strip()
            break
    if not stats_dir:
        match = re.search(r"(/scratch/.*/000_hpcrunner_logs/stats)", "\n".join(agg_output))
        stats_dir = match.group(1) if match else "N/A"
    print(f" Extracted Stats dir: {stats_dir}")


    #Store stats_dir in XCom
    ti = kwargs['ti']
    ti.xcom_push(key="stats_dir", value=stats_dir)


    #Triggered email function with the stats_dir
    send_stats_email(email_id, base_path, output_path, selected_items, stats_dir)

    #Initiated slurm polling.
    poll_biosails_submissions(ssh, sftp, agg_output, kwargs)
    ssh.close()

def send_stats_email(email_id, base_path, output_path, samples, stats_dir):
    """Send a notification email after extracting Stats dir."""
    smtp_conn_id = 'guru_email'
    smtp_hook = BaseHook.get_connection(smtp_conn_id)

    smtp_server = smtp_hook.host
    smtp_port = smtp_hook.port
    smtp_username = smtp_hook.login
    smtp_password = smtp_hook.password

    subject = "Downstream Analysis Initiated"
    body = (
        f"Your downstream analysis has started processing.\n\n"
        f"Selected samples: {samples}\n"
        f"Sequence path: {base_path}\n"
        f"Output path: {output_path}\n\n"
        "You can track the status of jobs at localhost:8080/downseqstatview, Simply paste the below path.\n"
        f"Stats directory: {stats_dir}\n\n"
        "You will automatically be notified once the run completes successfully.\n"
        "This is an automated message — please do not reply.\n\n"
        "Regards,\nNYU Abu Dhabi Core Bioinformatics\n"
    )

    msg = EmailMessage()
    msg['From'] = "Downstream Analysis Notification"
    msg['To'] = email_id
    msg['Subject'] = subject
    msg.set_content(body)

    print(f"📧 Sending email to {email_id} with stats dir: {stats_dir}")

    with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, email_id.split(','), msg.as_string())
