import io
import os
import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook
from airflow.providers.ssh.hooks.ssh import SSHHook

from nyuad_cgsb_jira_client.jira_client import jira_client


NO_DOWNSTREAM = "There is no downstream analysis chosen."


def validate_sequence_count_xcom(kwargs):
    ti = kwargs["ti"]

    output_text = ti.xcom_pull(task_ids="sequence_count_sent")

    if not output_text:
        raise AirflowException("No XCom output found from sequence_count_sent")

    failed_lines = [
        line for line in output_text.splitlines()
        if line.strip().startswith("❌")
    ]

    has_failed_samples = len(failed_lines) > 0

    return output_text, failed_lines, has_failed_samples


def get_downstream_analysis_summary(kwargs):
    ti = kwargs["ti"]

    summary = ti.xcom_pull(
        task_ids="submit_downstream_workflow",
        key="downstream_analysis_summary"
    )

    if summary:
        return summary

    downstream_analysis = kwargs["dag_run"].conf.get("downstream_analysis", [])

    if not downstream_analysis:
        return NO_DOWNSTREAM

    selected_netids = [
        item.get("netid")
        for item in downstream_analysis
        if item.get("netid")
    ]

    if not selected_netids:
        return NO_DOWNSTREAM

    return (
        "Downstream analysis selected for the following Net-ID(s):\n"
        + "\n".join([f"- {netid}" for netid in selected_netids])
    )


def get_remote_file_as_bytes(sftp, file_path):
    try:
        sftp.stat(file_path)
    except FileNotFoundError:
        raise AirflowException(
            f"The file does not exist on remote server: {file_path}"
        )

    remote_file = sftp.open(file_path, "rb")
    file_bytes = remote_file.read()
    remote_file.close()

    return io.BytesIO(file_bytes)


def generate_email_task(ds, **kwargs):
    dag_run = kwargs["dag_run"]

    scratch_dir = dag_run.conf["scratch_dir"]
    email_id = dag_run.conf["email_id"]
    miso_id = dag_run.conf["miso_id"]
    jira_ticket = dag_run.conf["jira_ticket"]

    output_text, failed_lines, has_failed_samples = validate_sequence_count_xcom(kwargs)
    downstream_summary = get_downstream_analysis_summary(kwargs)

    # multiqc_file_path = f"{scratch_dir}/Unaligned/data/processed/{jira_ticket}.html"
    # multiqc_file_name = os.path.basename(multiqc_file_path)
    methods_report_file_path = (
        f"{scratch_dir}/Unaligned/data/processed/methods_report/"
        f"{jira_ticket}_methods_report.html"
    )
    methods_report_file_name = os.path.basename(methods_report_file_path)

    unknown_barcodes_path = f"{scratch_dir}/Unaligned/Reports/Top_Unknown_Barcodes.csv"
    unknown_barcodes_name = os.path.basename(unknown_barcodes_path)

    ssh_hook = SSHHook(ssh_conn_id="guru_ssh")
    ssh = ssh_hook.get_conn()
    sftp = ssh.open_sftp()

    attachments = []

    try:
        # multiqc_file_obj = get_remote_file_as_bytes(sftp, multiqc_file_path)
        # attachments.append((multiqc_file_name, multiqc_file_obj, "html"))

        methods_report_file_obj = get_remote_file_as_bytes(
            sftp, methods_report_file_path
        )
        attachments.append(
            (methods_report_file_name, methods_report_file_obj, "html")
        )

        if has_failed_samples:
            unknown_file_obj = get_remote_file_as_bytes(sftp, unknown_barcodes_path)
            attachments.append((unknown_barcodes_name, unknown_file_obj, "csv"))

    finally:
        sftp.close()
        ssh.close()

    subject = f"Processing sequencing run {jira_ticket} / Miso ID {miso_id}"

    body = (
        f"Your recent run {jira_ticket} / Miso ID {miso_id} has successfully completed.\n\n"
        f"Run Path:- {scratch_dir}/Unaligned\n\n"
        "The methods report is attached. The MultiQC report is available on the Jira ticket.\n\n"
        "Downstream Analysis Summary\n\n"
        f"{downstream_summary}\n\n"
    )

    if has_failed_samples:
        body += (
            "Sequence count validation found one or more samples below the threshold:\n\n"
            + "\n".join(failed_lines)
            + "\n\n"
            "Top_Unknown_Barcodes.csv is also attached for review.\n\n"
        )

    body += (
        "For any further inquiries regarding this run, or for further downstream analysis "
        "please contact a member of the Core Bioinformatics Team at nyuad.cgsb.cb@nyu.edu\n"
        "Note that this is an automated message please do not respond to this email as it is not monitored.\n\n"
        "Regards\n"
        "NYU Abu Dhabi Core Bioinformatics\n"
    )

    smtp_conn_id = "guru_email"
    smtp_hook = BaseHook.get_connection(smtp_conn_id)

    smtp_server = smtp_hook.host
    smtp_port = smtp_hook.port
    smtp_username = smtp_hook.login
    smtp_password = smtp_hook.password

    default = "Specify_group_email"
    to = f"{email_id},{default}"
    recipients = [e.strip() for e in to.split(",")]

    msg = MIMEMultipart()
    msg["From"] = "Sequencing Run Notification"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body))

    for filename, file_obj, subtype in attachments:
        file_obj.seek(0)
        attachment = MIMEApplication(file_obj.read(), _subtype=subtype)
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=filename
        )
        msg.attach(attachment)

    with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, recipients, msg.as_string())


def email_jira_ticket_success(context):
    miso_id = context["dag_run"].conf["miso_id"]
    jira_ticket = context["dag_run"].conf["jira_ticket"]
    scratch_dir = context["dag_run"].conf["scratch_dir"]

    output_text, failed_lines, has_failed_samples = validate_sequence_count_xcom(context)
    downstream_summary = get_downstream_analysis_summary(context)

    comment = (
        f"Your recent run {jira_ticket} / Miso ID {miso_id} has successfully completed.\n\n"
        "Run Path\n"
        "{code}\n"
        f"{scratch_dir}/Unaligned/\n"
        "{code}\n"
        "The MultiQC summary and methods report are attached.\n"
    )

    if has_failed_samples:
        failed_sample_text = "\n".join(failed_lines)

        comment += (
            "\nSequence count validation found one or more samples below the threshold:\n\n"
            "{code}\n"
            f"{failed_sample_text}\n"
            "{code}\n\n"
            "Top_Unknown_Barcodes.csv has been attached for review.\n"
        )

    comment += (
        "\nDownstream Analysis Summary\n"
        "{code}\n"
        f"{downstream_summary}\n"
        "{code}\n"
    )

    comment += (
        "\nRegards,\n"
        "NYU Abu Dhabi Core Bioinformatics\n"
    )

    jira_client.add_comment(jira_ticket, comment)

    multiqc_file_path = f"{scratch_dir}/Unaligned/data/processed/{jira_ticket}.html"
    methods_report_file_path = (
        f"{scratch_dir}/Unaligned/data/processed/methods_report/"
        f"{jira_ticket}_methods_report.html"
    )
    unknown_barcodes_path = f"{scratch_dir}/Unaligned/Reports/Top_Unknown_Barcodes.csv"

    ssh_hook = SSHHook(ssh_conn_id="guru_ssh")
    ssh = ssh_hook.get_conn()
    sftp = ssh.open_sftp()

    try:
        multiqc_file_obj = get_remote_file_as_bytes(sftp, multiqc_file_path)
        multiqc_file_obj.seek(0)

        jira_client.add_attachment(
            jira_ticket,
            attachment=multiqc_file_obj,
            filename=os.path.basename(multiqc_file_path)
        )

        methods_report_file_obj = get_remote_file_as_bytes(
            sftp, methods_report_file_path
        )
        methods_report_file_obj.seek(0)
        jira_client.add_attachment(
            jira_ticket,
            attachment=methods_report_file_obj,
            filename=os.path.basename(methods_report_file_path),
        )

        if has_failed_samples:
            unknown_file_obj = get_remote_file_as_bytes(sftp, unknown_barcodes_path)
            unknown_file_obj.seek(0)

            jira_client.add_attachment(
                jira_ticket,
                attachment=unknown_file_obj,
                filename=os.path.basename(unknown_barcodes_path)
            )

    finally:
        sftp.close()
        ssh.close()


def run_post_email_task(ds, **kwargs):
    email_jira_ticket_success(kwargs)
    generate_email_task(ds, **kwargs)

