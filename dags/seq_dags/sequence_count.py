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
        f"methods_report/{jira_ticket}_qc_summary.tsv"
    )
    output_file = f"{scratch_dir}/Unaligned/sequence_reads.txt"

    sample_col = "sample"
    count_col = "raw_read_pairs"

    ssh_hook = SSHHook(ssh_conn_id="guru_ssh")
    ssh = ssh_hook.get_conn()
    sftp = ssh.open_sftp()

    try:
        try:
            sftp.stat(input_file)
        except FileNotFoundError as exc:
            raise AirflowException(
                f"Input file does not exist on remote server: {input_file}"
            ) from exc

        with sftp.open(input_file, "r") as remote_file:
            file_content = remote_file.read()

        if isinstance(file_content, bytes):
            file_content = file_content.decode("utf-8")

        reader = csv.DictReader(StringIO(file_content), delimiter="\t")

        if not reader.fieldnames:
            raise AirflowException(f"Input TSV is empty or has no header: {input_file}")

        missing_columns = [
            column
            for column in (sample_col, count_col)
            if column not in reader.fieldnames
        ]
        if missing_columns:
            raise AirflowException(
                f"Missing required column(s) in {input_file}: "
                f"{', '.join(missing_columns)}. "
                f"Found: {', '.join(reader.fieldnames)}"
            )

        lines = [f"Threshold: {threshold:g}", ""]

        for line_number, row in enumerate(reader, start=2):
            sample = (row.get(sample_col) or "").strip()
            count_value = (row.get(count_col) or "").strip()

            if not sample:
                lines.append(f"⚠️  Line {line_number}: missing sample name")
                continue

            try:
                total_seq = float(count_value)
            except ValueError:
                lines.append(
                    f"⚠️  {sample}: invalid {count_col} value {count_value!r}"
                )
                continue

            status = "❌" if total_seq < threshold else "✅"
            lines.append(f"{status} - {sample} - {total_seq:,.0f}")

        output_text = "\n".join(lines) + "\n"

        with sftp.open(output_file, "w") as remote_output:
            remote_output.write(output_text)

        try:
            output_stat = sftp.stat(output_file)
        except FileNotFoundError as exc:
            raise AirflowException(
                f"Output file was not created on remote server: {output_file}"
            ) from exc

        if output_stat.st_size == 0:
            raise AirflowException(
                f"Output file is empty on remote server: {output_file}"
            )

        return output_text

    finally:
        sftp.close()
        ssh.close()
