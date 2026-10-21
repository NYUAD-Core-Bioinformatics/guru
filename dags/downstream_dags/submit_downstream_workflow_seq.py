import posixpath
from jinja2 import Environment, BaseLoader
import logging

from airflow.providers.ssh.hooks.ssh import SSHHook
from downstream_dags.ssh_helpers import execute_ssh_command_return_stdout_stderr
from downstream_dags.biosails_helpers import poll_biosails_submissions


logger = logging.getLogger("submit_downstream_workflow")
logger.setLevel(logging.DEBUG)


NO_DOWNSTREAM = "There is no downstream analysis chosen."


def build_downstream_summary(conf, sftp):
    downstream_analysis = conf.get("downstream_analysis", [])
    scratch_dir = conf.get("scratch_dir")

    if not downstream_analysis:
        return NO_DOWNSTREAM

    if conf.get("view_mode") == "custom":
        workflow_names = [
            posixpath.basename(item.get("workflow", ""))
            for item in downstream_analysis
            if item.get("workflow")
        ]
        return "Custom FASTQ analysis submitted for: " + ", ".join(workflow_names)

    existing_netids = []
    missing_netids = []

    for item in downstream_analysis:
        netid = item.get("netid")

        if not netid:
            continue

        analysis_path = f"{scratch_dir}/Unaligned/data/analysis_{netid}"

        try:
            sftp.listdir(analysis_path)
            existing_netids.append(netid)
        except FileNotFoundError:
            missing_netids.append(netid)

    summary_parts = []

    if missing_netids:
        summary_parts.append(
            "The following Net-ID(s) do not match any sample names:\n"
            + "\n".join([f"- {netid}" for netid in missing_netids])
        )

    if existing_netids:
        summary_parts.append(
            "Downstream analysis selected for the following Net-ID(s):\n"
            + "\n".join([f"- {netid}" for netid in existing_netids])
        )

    if not summary_parts:
        return NO_DOWNSTREAM

    return "\n\n".join(summary_parts)


run_downstream_workflow_command = """
#!/usr/bin/env bash

set -e

{% if working_dir %}
echo "Working Directory: {{ working_dir }}"
cd {{ working_dir }}
{% else %}
echo "There is no working directory specified. Exiting"
exit 256
{% endif %}

{% if workflow %}
echo "Rendering downstream workflow: {{ workflow }}"
{% if netid %}echo "Net-ID: {{ netid }}"{% else %}echo "Custom FASTQ matching with R1/R2 suffixes"{% endif %}

workflow_file=$(basename "{{ workflow }}")
if [ ! -f "${workflow_file}" ]; then
    cp "{{ workflow }}" ./
fi

{% if netid %}
echo "Updating Net-ID in workflow file"
sed -i "s/netid/{{ netid }}/g" "${workflow_file}"
{% endif %}

module load gencore/1
module load gencore_biosails

workflow_stem="${workflow_file%.*}"
workflow_stem=$(printf '%s\n' "${workflow_stem}" | sed -E 's/_v[0-9]+([.][0-9]+)*$//')
shell_file="${workflow_stem}.sh"

biox run -w "${workflow_file}" -o "${shell_file}"

hpcrunner.pl submit_jobs --infile "${shell_file}" --project {{ project_name }}

{% else %}
echo "There is no downstream workflow specified. Skipping"
exit 0
{% endif %}
"""


def submit_downstream_workflow_to_slurm(ds, **kwargs):
    dag_run = kwargs["dag_run"]
    conf = dag_run.conf

    downstream_analysis = conf.get("downstream_analysis", [])
    prepared_workflows = kwargs["ti"].xcom_pull(
        task_ids="prepare_custom_workflow",
        key="prepared_custom_workflows",
    ) or []

    ssh_hook = SSHHook(ssh_conn_id="guru_ssh")
    ssh = ssh_hook.get_conn()
    sftp = ssh.open_sftp()

    try:
        if not downstream_analysis:
            summary = NO_DOWNSTREAM
            print(summary)
            kwargs["ti"].xcom_push(
                key="downstream_analysis_summary",
                value=summary
            )
            return

        for index, analysis in enumerate(downstream_analysis, start=1):
            netid = analysis.get("netid")
            workflow = (
                prepared_workflows[index - 1]
                if index <= len(prepared_workflows)
                else analysis.get("workflow")
            )

            is_custom = conf.get("view_mode") == "custom"
            if not workflow or workflow == "None" or (not is_custom and not netid):
                print(f"Skipping downstream analysis #{index}: missing workflow or required Net-ID")
                continue

            print(f"Submitting downstream analysis #{index}")
            if netid:
                print(f"Net-ID: {netid}")
            print(f"Workflow: {workflow}")

            rtemplate = Environment(loader=BaseLoader).from_string(
                run_downstream_workflow_command
            )

            run_dir = conf.get("scratch_dir")
            if conf.get("view_mode") != "custom":
                run_dir = posixpath.join(run_dir, "Unaligned") if run_dir else None

            project_name = (
                f"{netid}-downstream"
                if netid
                else f"custom-{dag_run.run_id}-downstream"
            )
            rendered_command = rtemplate.render(
                working_dir=run_dir,
                jira_ticket=conf.get("jira_ticket"),
                netid=netid,
                workflow=workflow,
                project_name=project_name,
            )

            agg_output = execute_ssh_command_return_stdout_stderr(
                ssh,
                rendered_command,
                logger
            )

            if agg_output:
                from pprint import pprint
                pprint(agg_output)

                # This must finish before summary is created
                poll_biosails_submissions(ssh, sftp, agg_output, kwargs)
            else:
                raise Exception(
                    f"No output from downstream biosails submission found for {netid or workflow}"
                )

        # IMPORTANT: only after all downstream jobs finish
        summary = build_downstream_summary(conf, sftp)

        print(summary)

        kwargs["ti"].xcom_push(
            key="downstream_analysis_summary",
            value=summary
        )

    finally:
        try:
            sftp.close()
        except Exception:
            pass

        try:
            ssh.close()
        except Exception:
            pass
