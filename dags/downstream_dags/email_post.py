import argparse
import io
import logging
import os
import sys
import smtplib
import posixpath
import re
from email.message import EmailMessage
from airflow.hooks.base import BaseHook
from airflow.providers.ssh.hooks.ssh import SSHHook
import yaml


def _custom_analysis_output_dir(sftp, workflow_path, working_dir):
    """Resolve a custom workflow's data/analysis_* output directory."""
    with sftp.open(workflow_path, "r") as workflow_file:
        workflow_text = workflow_file.read()
    if isinstance(workflow_text, bytes):
        workflow_text = workflow_text.decode("utf-8")

    workflow_data = yaml.safe_load(workflow_text)
    global_entries = workflow_data.get("global") if isinstance(workflow_data, dict) else None
    if not isinstance(global_entries, list):
        raise ValueError(f"Workflow YAML has no list-valued 'global' section: {workflow_path}")

    outdir = next(
        (entry.get("outdir") for entry in global_entries
         if isinstance(entry, dict) and isinstance(entry.get("outdir"), str)),
        None,
    )
    if not outdir:
        raise ValueError(f"Workflow YAML has no string-valued outdir: {workflow_path}")

    if posixpath.isabs(outdir):
        output_dir = posixpath.normpath(outdir)
    else:
        match = re.search(r"(?:^|/)data/(analysis_[^/]+)(?:/|$)", outdir)
        if not match:
            raise ValueError(
                f"Custom workflow outdir does not contain data/analysis_<name>: {outdir}"
            )
        output_dir = posixpath.join(working_dir, "data", match.group(1))
    return output_dir


def _methods_report_paths(conf, prepared_workflows, sftp):
    scratch_dir = (conf.get("scratch_dir") or "").rstrip("/")
    project_name = (conf.get("project_name") or "").strip()
    analyses = conf.get("downstream_analysis") or []
    if not scratch_dir or not project_name:
        raise ValueError("Working directory and project name are required to locate methods reports.")

    report_name = f"{project_name}_methods_report.html"
    if conf.get("view_mode") == "custom":
        if not prepared_workflows:
            raise ValueError("No prepared custom workflow is available to locate its methods report.")
        output_dir = _custom_analysis_output_dir(sftp, prepared_workflows[0], scratch_dir)
        return [posixpath.join(output_dir, "methods_report", report_name)]

    report_paths = []
    for analysis in analyses:
        netid = (analysis.get("netid") or "").strip()
        if not netid:
            continue
        safe_netid = re.sub(r"[^A-Za-z0-9._-]+", "_", netid).strip("._")
        report_paths.append(posixpath.join(
            scratch_dir, "Unaligned", "data", f"analysis_{safe_netid}",
            "methods_report", report_name,
        ))
    return report_paths


def generate_post_email_task(ds, **kwargs):
    dag_run = kwargs['dag_run']
    conf = dag_run.conf or {}
    email_id = conf.get('email_address')
    if not email_id:
        raise ValueError("Email address is missing from the DAG run configuration.")

    scratch_dir = conf.get('scratch_dir', '')
    if conf.get('view_mode') == 'custom':
        selected_path = scratch_dir
    else:
        selected_path = os.path.join(scratch_dir, 'Unaligned')

    analyses = conf.get('downstream_analysis') or []
    prepared_workflows = kwargs['ti'].xcom_pull(
        task_ids='prepare_custom_workflow',
        key='prepared_custom_workflows',
    ) or []
    ssh = None
    sftp = None
    attachments = []
    report_status = []
    try:
        ssh = SSHHook(ssh_conn_id="guru_ssh").get_conn()
        sftp = ssh.open_sftp()
        try:
            report_paths = _methods_report_paths(conf, prepared_workflows, sftp)
        except Exception as exc:
            report_paths = []
            report_status.append(
                f"Methods report could not be attached because its path could not be determined: {exc}"
            )

        if not report_paths and not report_status:
            report_status.append("No methods report paths were available for this submission.")

        for report_path in report_paths:
            try:
                with sftp.open(report_path, "rb") as report_file:
                    report_content = report_file.read()
                attachments.append((posixpath.basename(report_path), report_content))
                report_status.append(
                    f"Attached successfully: {posixpath.basename(report_path)}"
                )
            except Exception as exc:
                report_status.append(
                    f"Could not attach methods report at {report_path}: {exc}"
                )
    except Exception as exc:
        report_status.append(
            f"Methods report attachment was skipped because the SFTP server could not be reached: {exc}"
        )
    finally:
        if sftp:
            try:
                sftp.close()
            except Exception:
                pass
        if ssh:
            try:
                ssh.close()
            except Exception:
                pass

    workflow_lines = []
    for index, analysis in enumerate(analyses):
        workflow_path = (
            prepared_workflows[index]
            if index < len(prepared_workflows)
            else analysis.get('workflow', '')
        )
        workflow_name = os.path.basename(workflow_path) if workflow_path else 'Not selected'
        netid = analysis.get('netid', '')
        workflow_lines.append(f"- {netid}: {workflow_name}" if netid else f"- {workflow_name}")
    workflow_summary = "\n".join(workflow_lines) if workflow_lines else "No workflow selected"

    subject = "Downstream Analysis Completed"
    body = (
        "Your recent downstream analysis has successfully completed.\n\n"
        f"Selected workflow(s):\n{workflow_summary}\n\n"
        f"Selected Downstream Path: {selected_path}\n\n"
        "Methods report attachment status:\n"
        f"{chr(10).join(f'- {status}' for status in report_status)}\n\n"
        "Note that this is an automated message please do not respond to this email as it is not monitored.\n\n"
        "Regards\n"
        "NYU Abu Dhabi Core Bioinformatics\n"
    )

    smtp_hook = BaseHook.get_connection('guru_email')
    smtp_server = smtp_hook.host
    smtp_port = smtp_hook.port
    smtp_username = smtp_hook.login
    smtp_password = smtp_hook.password

    msg = EmailMessage()
    msg['From'] = "Downstream Analysis Notification"
    recipients = [address.strip() for address in email_id.split(',') if address.strip()]
    msg['To'] = ', '.join(recipients)
    msg['Subject'] = subject
    msg.set_content(body)
    for filename, content in attachments:
        msg.add_attachment(
            content,
            maintype="text",
            subtype="html",
            filename=filename,
        )
    with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, recipients, msg.as_string())


def run_post_email_task(ds, **kwargs):
    return generate_post_email_task(ds, **kwargs)
