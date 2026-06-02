import csv
from io import StringIO

from airflow.exceptions import AirflowException
from airflow.providers.ssh.hooks.ssh import SSHHook


def sequence_count_task(ds, **kwargs):
    dag_run = kwargs["dag_run"]

    scratch_dir = dag_run.conf["scratch_dir"]
    jira_ticket = dag_run.conf["jira_ticket"]
    threshold = float(dag_run.conf.get("threshold", 50000))

    input_file = (
        f"{scratch_dir}/Unaligned/data/processed/"
        f"{jira_ticket}_data/multiqc_general_stats.txt"
    )

    output_file = f"{scratch_dir}/Unaligned/sequence_reads.txt"

    sample_col = "Sample"
    count_col = "FastQC_mqc-generalstats-fastqc-total_sequences"

    ssh_hook = SSHHook(ssh_conn_id="guru_ssh")
    ssh = ssh_hook.get_conn()
    sftp = ssh.open_sftp()

    try:
        # Check input file exists on remote server
        try:
            sftp.stat(input_file)
        except FileNotFoundError:
            raise AirflowException(
                f"Input file does not exist on remote server: {input_file}"
            )

        # Read remote input file
        with sftp.open(input_file, "r") as remote_file:
            file_content = remote_file.read()

        if isinstance(file_content, bytes):
            file_content = file_content.decode("utf-8")

        reader = csv.DictReader(StringIO(file_content), delimiter="\t")

        lines = []
        lines.append(f"Threshold: {threshold}")
        lines.append("")

        for row in reader:
            sample = row[sample_col]
            total_seq = float(row[count_col])

            if "R1" in sample or "R2" in sample:
                if total_seq < threshold:
                    lines.append(f"❌ - {sample} - {total_seq}")
                else:
                    lines.append(f"✅ - {sample} - {total_seq}")

        output_text = "\n".join(lines) + "\n"

        # Write output file on remote server
        with sftp.open(output_file, "w") as remote_output:
            remote_output.write(output_text)

        # Verify output file exists and has content
        try:
            output_stat = sftp.stat(output_file)
        except FileNotFoundError:
            raise AirflowException(
                f"Output file was not created on remote server: {output_file}"
            )

        if output_stat.st_size == 0:
            raise AirflowException(
                f"Output file is empty on remote server: {output_file}"
            )

        # This return is stored automatically in XCom
        return output_text

    finally:
        sftp.close()
        ssh.close()
