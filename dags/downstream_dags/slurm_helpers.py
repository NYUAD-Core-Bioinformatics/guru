import logging
from downstream_dags.ssh_helpers import execute_ssh_command_return_stdout_stderr
from pprint import pprint
import time

logger = logging.getLogger('slurm-helper')
logger.setLevel(logging.DEBUG)


def submit_slurm_job(ssh):
    output = execute_ssh_command_return_stdout_stderr(ssh, 'sbatch {}', logger)
    output = output[0]


def get_job_status(ssh, job_id):
    output = execute_ssh_command_return_stdout_stderr(ssh, 'sacct -a -j {}'.format(job_id), logger)
    # Output is read in by bytes, so sometimes its split funny
    try:
        output = ''.join(output)
        output = output.split("\n")
        status_line = output[-1]
        status = status_line.split()[4]
        if status.isdigit():
            status = "PENDING"
    except:
        raise Exception('Unable to parse slurm job status')

    return status

def get_job_status_qc(ssh, job_id):
    output = execute_ssh_command_return_stdout_stderr(ssh, 'sacct -a -j {}'.format(job_id), logger)
    # Output is read in by bytes, so sometimes its split funny
    try:
        output = ''.join(output)
        output = output.split("\n")
        status_line = output[-1]
        status = status_line.split()[5]
    except:
        raise Exception('Unable to parse slurm job status')

    return status

def parse_slurm_submission(output):
    output = output[0].split("\n")
    slurm_job_id = output[0].split().pop()
    return slurm_job_id

##In demux task it check out sacct 4th byte -> Adjusted in get_job_status
def poll_slurm_job(ssh, slurm_job_id):
    # Don't start polling too quickly
    # It's baaaaad
    time.sleep(60)
    logger.info('Polling slurm job {}'.format(slurm_job_id))

    job_status = 'RUNNING'
    x = 0
    while str(job_status) == 'RUNNING' or str(job_status) == 'PENDING':
        try:
            job_status = get_job_status(ssh, slurm_job_id)
        except:
            x = x + 1
            logger.warning('Unable to get job status. Retrying...')
        logger.info('Current job status: {}'.format(job_status))
        # Have a retry loop
        # But once we hit more than 5 retries give up
        if x > 5:
            logger.warning('Hit maximum number of retries!')
            # TODO Break or throw exception?
            break
        # Poll the job every 5 minutes
        time.sleep(300)

    logger.info('Job completed with status {}'.format(job_status))
    return job_status

#In QC task it check out sacct 5th byte -> Adjusted in get_job_status_qc 
def poll_slurm_job_qc(ssh, slurm_job_id):
    # Don't start polling too quickly
    # It's baaaaad
    time.sleep(60)
    logger.info('Polling slurm job {}'.format(slurm_job_id))

    job_status = 'RUNNING'
    x = 0
    while str(job_status) == 'RUNNING' or str(job_status) == 'PENDING':
        try:
            job_status = get_job_status_qc(ssh, slurm_job_id)
        except:
            x = x + 1
            logger.warning('Unable to get job status. Retrying...')
        logger.info('Current job status: {}'.format(job_status))
        # Have a retry loop
        # But once we hit more than 5 retries give up
        if x > 5:
            logger.warning('Hit maximum number of retries!')
            # TODO Break or throw exception?
            break
        # Poll the job every 5 minutes
        time.sleep(300)

    logger.info('Job completed with status {}'.format(job_status))
    return job_status