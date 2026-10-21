from select import select
from logging import Logger
import paramiko
from paramiko import SSHClient
from typing import Any


def initialize_ssh(user: str, host: str):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user)

    sftp = ssh.open_sftp()
    return ssh, sftp


def execute_ssh_command(ssh_client: SSHClient, command: str, logger: Logger, timeout: int = None) -> bool:
    """
    Execute a long running ssh command
    :param ssh_client: paramiko ssh client
        Example:     args = parser.parse_args()
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect('remote-host', username='remote-user')
    :param command: command to execute
    :param logger: logging logger
            import logging
            logger = logging.getLogger('name_of_my_logger')
            logger.setLevel(logging.DEBUG)
    :param timeout:
    :return:
    """
    try:
        if not command:
            raise Exception("no command specified so nothing to execute here.")

        # Auto apply tty when its required in case of sudo
        get_pty = False
        if command.startswith('sudo'):
            get_pty = True

        # set timeout taken as params
        logger.info('Executing command: {}'.format(command))

        stdin, stdout, stderr = ssh_client.exec_command(command=command,
                                                        get_pty=get_pty,
                                                        timeout=timeout
                                                        )
        # get channels
        channel = stdout.channel

        # closing stdin
        stdin.close()
        channel.shutdown_write()

        agg_stdout = b''
        agg_stderr = b''

        # capture any initial output in case channel is closed already
        stdout_buffer_length = len(stdout.channel.in_buffer)

        if stdout_buffer_length > 0:
            agg_stdout += stdout.channel.recv(stdout_buffer_length)

        # read from both stdout and stderr
        while not channel.closed or \
                channel.recv_ready() or \
                channel.recv_stderr_ready():
            readq, _, _ = select([channel], [], [], timeout)
            for c in readq:
                if c.recv_ready():
                    line = stdout.channel.recv(len(c.in_buffer))
                    line = line
                    agg_stdout += line
                    logger.info(line.decode('utf-8').strip('\n'))
                if c.recv_stderr_ready():
                    line = stderr.channel.recv_stderr(len(c.in_stderr_buffer))
                    line = line
                    agg_stderr += line
                    logger.warning(line.decode('utf-8').strip('\n'))
            if stdout.channel.exit_status_ready() \
                    and not stderr.channel.recv_stderr_ready() \
                    and not stdout.channel.recv_ready():
                stdout.channel.shutdown_read()
                stdout.channel.close()
                break

        stdout.close()
        stderr.close()

        exit_status = stdout.channel.recv_exit_status()
        if exit_status is 0:
            # returning output if do_xcom_push is set
            logger.info('Command exited with exitcode 0')

        else:
            error_msg = agg_stderr.decode('utf-8')
            raise Exception("error running cmd: {0}, error: {1}".format(command, error_msg))

    except Exception as e:
        raise Exception("SSH operator error: {0}".format(str(e)))

    return True


def execute_ssh_command_return_stdout_stderr(ssh_client: SSHClient, command: str, logger: Logger, timeout: int = None) -> list:
    """
    Execute a long running ssh command
    This is separate from the execute_ssh_command because sometimes these get VERY long, and so we want to explicitly
    state when we want the stdout/stderr
    :param ssh_client: paramiko ssh client
        Example:     args = parser.parse_args()
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect('remote-host', username='remote-user')
    :param command: command to execute
    :param logger: logging logger
            import logging
            logger = logging.getLogger('name_of_my_logger')
            logger.setLevel(logging.DEBUG)
    :param timeout:
    :return: list of strings containing the stdout/stderr
    """
    try:
        if not command:
            raise Exception("no command specified so nothing to execute here.")

        # Auto apply tty when its required in case of sudo
        get_pty = False
        if command.startswith('sudo'):
            get_pty = True

        # set timeout taken as params
        logger.info('====================================================')
        logger.info('Executing command: {}'.format(command))
        logger.info('====================================================')
        agg_output = []

        stdin, stdout, stderr = ssh_client.exec_command(command=command,
                                                        get_pty=get_pty,
                                                        timeout=timeout
                                                        )
        # get channels
        channel = stdout.channel

        # closing stdin
        stdin.close()
        channel.shutdown_write()

        agg_stdout = b''
        agg_stderr = b''

        # capture any initial output in case channel is closed already
        stdout_buffer_length = len(stdout.channel.in_buffer)

        if stdout_buffer_length > 0:
            agg_stdout += stdout.channel.recv(stdout_buffer_length)

        # read from both stdout and stderr
        while not channel.closed or \
                channel.recv_ready() or \
                channel.recv_stderr_ready():
            readq, _, _ = select([channel], [], [], timeout)
            for c in readq:
                if c.recv_ready():
                    line = stdout.channel.recv(len(c.in_buffer))
                    str_line = line.decode('utf').strip('\n')
                    str_line = str_line.replace('[32m', '')
                    str_line = str_line.replace('[0m', '')
                    agg_output.append(str_line)
                if c.recv_stderr_ready():
                    line = stderr.channel.recv_stderr(len(c.in_stderr_buffer))
                    str_line = line.decode('utf').strip('\n')
                    str_line = str_line.replace('[32m', '')
                    str_line = str_line.replace('[0m', '')
                    agg_output.append(str_line)
            if stdout.channel.exit_status_ready() \
                    and not stderr.channel.recv_stderr_ready() \
                    and not stdout.channel.recv_ready():
                stdout.channel.shutdown_read()
                stdout.channel.close()
                break

        logger.info("Command Output")
        logger.info('====================================================')
        logger.info("\n".join(agg_output))
        logger.info('====================================================')

        stdout.close()
        stderr.close()

        exit_status = stdout.channel.recv_exit_status()
        if exit_status is 0:
            # returning output if do_xcom_push is set
            logger.info('Command exited with exitcode 0')

        else:
            error_msg = agg_stderr.decode('utf-8')
            raise Exception("error running cmd: {0}, error: {1}".format(command, error_msg))

    except Exception as e:
        raise Exception("SSH operator error: {0}".format(str(e)))

    return agg_output