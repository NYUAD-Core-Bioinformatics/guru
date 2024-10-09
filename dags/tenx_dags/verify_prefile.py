import logging
import smtplib
from email.message import EmailMessage
from airflow.hooks.base import BaseHook
from nyuad_cgsb_jira_client.jira_client import jira_client
from airflow.exceptions import AirflowFailException
from airflow.providers.ssh.hooks.ssh import SSHHook

def verify_file_exists(**kwargs):
    dag_run = kwargs['dag_run']
    work_dir = dag_run.conf['work_dir']
    scratch_dir = dag_run.conf['scratch_dir']
    email_id = dag_run.conf['email_id']
    miso_id = dag_run.conf['miso_id']
    jira_ticket = dag_run.conf['jira_ticket']
    
        #Defining SSH connection
    ssh_hook = SSHHook(ssh_conn_id='guru_ssh')
    ssh = ssh_hook.get_conn()

#   Here copy the file from remote server and write as open file
    sftp = ssh.open_sftp()
    filename=f"{scratch_dir}/RTAComplete.txt"

    try: 
        sftp.stat(filename)
        logging.info("File exists, resuming operation.")
    except FileNotFoundError:
        logging.warning("File doesn't exist. Initiating the email notification.")

        subject = f"Processing sequencing run {jira_ticket} / Miso ID {miso_id}"
        body = (f"Your recent run {jira_ticket} / Miso ID {miso_id} has failed. \n"
                    "Your run failed because the copy operation was not fully completed.\n"
                    "Please resubmit a new task in GURU once the sequencing copy operation is finished.\n"
                    "Note that this is an automated message please do not respond to this email as it is not monitored.\n"
                    "\n"
                    "Regards\n")

        # Set the SMTP Connection ID
        smtp_conn_id = 'guru_email'  
        smtp_hook = BaseHook.get_connection(smtp_conn_id)

        # SMTP credentials
        smtp_server = smtp_hook.host
        smtp_port = smtp_hook.port
        smtp_username = smtp_hook.login
        smtp_password = smtp_hook.password

        # Compose the template
        msg = EmailMessage()
        msg['From'] = "Sequencing Run Notification"
        to = (f"{email_id}")
        msg['To'] = to
        msg['Subject'] = subject
        msg.set_content(body)

        # Initiate the send
        with smtplib.SMTP_SSL(smtp_server, smtp_port)as server:
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, to.split(','), msg.as_string())
        
        #Raise exception for the file path doesn't exist
        raise AirflowFailException("File not found. Email sent, and DAG is now marked as failed.")
    finally:
        sftp.close()
        ssh.close()
