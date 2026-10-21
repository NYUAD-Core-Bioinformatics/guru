import re
import logging
from jinja2 import Environment, BaseLoader
from airflow.providers.ssh.hooks.ssh import SSHHook

logger = logging.getLogger("down_status")
logger.setLevel(logging.INFO)

submit_script = """
module load gencore gencore_biosails
hpcrunner.pl stats --data_dir {{ status_dir }}
"""

def downstream_status(**kwargs):
    """Run hpcrunner remotely and extract JobName / Complete / Running summary."""

    conf = kwargs.get("dag_run").conf 
    status_dir = conf.get("status_dir")
    if not status_dir:
        raise ValueError("status_dir not provided in dag_run.conf")

    cmd = Environment(loader=BaseLoader).from_string(submit_script).render(status_dir=status_dir)
    logger.info(f"Executing hpcrunner on {status_dir}")

    ssh = SSHHook(ssh_conn_id="guru_ssh").get_conn()
    try:
        _, stdout, stderr = ssh.exec_command(cmd)
        output, err = stdout.read().decode(), stderr.read().decode()
        if err.strip():
            logger.warning(f"Remote stderr: {err}")
        if "does not contain any submission info" in output:
            raise RuntimeError(f"No submission info found in {status_dir}")

        lines = [l for l in output.splitlines() if l.strip().startswith("|") and "Time:" not in l and "SubmissionID" not in l]
        if not lines:
            raise RuntimeError(f"No hpcrunner table found in {status_dir}")

        # find the header and rows
        header_line = next((l for l in lines if "JobName" in l and "Complete" in l), None)
        if not header_line:
            raise RuntimeError(f"No valid header found in hpcrunner output at {status_dir}")
        header = [h.strip() for h in header_line.strip("| ").split("|")]
        rows = lines[lines.index(header_line) + 1:]

        wanted = ["JobName", "Complete", "Running"]
        header_map = {h.lower(): i for i, h in enumerate(header)}
        idx = [header_map[c.lower()] for c in wanted if c.lower() in header_map]
        if len(idx) < 3:
            raise RuntimeError(f"Expected columns {wanted} not found. Got: {header}")

        summary = ["| JobName | Complete | Running |", "+--------------+----------+---------+"]
        for line in rows:
            parts = [p.strip() for p in line.strip("| ").split("|")]
            vals = [parts[i] for i in idx if i < len(parts)]
            if len(vals) == len(idx):
                summary.append("| {:<12} | {:<8} | {:<7} |".format(*vals))

        if len(summary) <= 2:
            raise RuntimeError(f"No valid job data found in {status_dir}")

        summary_text = "\n".join(summary)
        logger.info("---- Downstream Summary ----\n" + summary_text)
        logger.info("\n")
        return {"summary_text": summary_text}
        logger.info("\n")

    except Exception as e:
        logger.error(f"Downstream status failed: {e}")
        raise
    finally:
        ssh.close()
