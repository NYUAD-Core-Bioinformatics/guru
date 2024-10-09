from airflow.plugins_manager import AirflowPlugin
from airflow.www.app import csrf
from airflow.models import DagBag, DagRun
from airflow.utils.state import State
from airflow.utils import timezone
from flask_appbuilder import expose, BaseView as AppBuilderBaseView
from flask import Flask, Blueprint, render_template, request, flash
from wtforms.validators import ValidationError, InputRequired, EqualTo
from wtforms import Form, StringField, IntegerField, EmailField, RadioField, SelectField, validators
from airflow.providers.ssh.hooks.ssh import SSHHook
from airflow.providers.mysql.hooks.mysql import MySqlHook
import os
import fnmatch
from pprint import pprint
from datetime import datetime
import mysql.connector
import re
from nyuad_cgsb_jira_client.jira_client import jira_client




bp = Blueprint(
               "default_sequence",
               __name__,
               template_folder="templates", 
               )

"""Function for checking the miso ID exist in the mysql database"""
def validate_miso_id(form, field):
    """Defining the mysql access information""" 
    """ Using mysqlhook module loaded mysql connections to get the credentials."""
    mysql_hook = MySqlHook(mysql_conn_id='guru_mysql')
    conn = mysql_hook.get_conn()
    cursor = conn.cursor()

    """Checking the runID table from miso database to check whether the count(runID) exist or not"""
    query = "select count(*) from Run where runId = %s"
    cursor.execute(query, (field.data,))
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    misoid = field.data
    """Defining the error condition if fails """
    if count == 0:
        raise ValidationError(f"Miso Run ID {misoid} not found in database.")

"""Function to select/choose the qc_workflow file from jubail."""
def qc_workflow():    
    # sftp = ssh.open_sftp()
    # Below 3 lines based on airflow ssh connection defined.
    ssh_hook = SSHHook(ssh_conn_id='guru_ssh')
    ssh_client = ssh_hook.get_conn()
    sftp = ssh_client.open_sftp()
    qc_file = [None]
    try:
        dir = os.environ.get('QC_WORKDIR')
        for filename in sftp.listdir(dir):
            if fnmatch.fnmatch(filename, "qc-qt-noconcat*.yml"):
                qc_file.append('{}{}'.format(dir, filename))
        sftp.close()
    except FileNotFoundError as e:
        raise ValidationError('QC_Workflow path not visible, Contact Airflow admin')
    return qc_file



"""Function to check if the work directory given is exist or not."""
def file_validate(form, field):
    # Below 3 lines based on airflow ssh connection defined.
    ssh_hook = SSHHook(ssh_conn_id='guru_ssh')
    ssh_client = ssh_hook.get_conn()
    sftp = ssh_client.open_sftp()
    dir = field.data
    try:
        files = sftp.listdir(dir)
    except FileNotFoundError as e:
        raise ValidationError(f'Directory path {dir} does not exist on the remote server')
    sftp.close()

"""Function to validate multiple email address syntax."""
def validate_emails(form, field):
    emails = field.data
    email_id = field.data.split(',')
    regex = r'^\S+@\S+\.\S+$'
    invalid_emails = []
    for email in email_id:
        if not re.match(regex, email.strip()):
            invalid_emails.append(email.strip())
    if invalid_emails:
        raise ValidationError('Invalid email address format: {}'.format(', '.join(invalid_emails)))

"""Function to check the jira ticket existence"""
def validate_jira_ticket(form, field):
    ticket_id = field.data
    try:
        issue = jira_client.issue(id=ticket_id)
        description = issue.fields.description
        return issue, description
    except Exception as e:
            print(f"Error connecting to Jira: {e}")
            raise ValidationError(f'Jira Ticket ID {ticket_id} not found in the system')


"""Defining the class for each directives"""
class MyForm(Form):
    projname = StringField('Project Name', render_kw={"placeholder": "Enter your Project name"})
    miso_number = StringField('Miso ID', [InputRequired(), validate_miso_id], render_kw={"placeholder": "Type miso ID number"})
    reverse_complement  = RadioField('Reverse Complement',  choices=[('yes','Enabled'),('no','Disabled')], validators=[validators.InputRequired(message='Please select an option')])
    email_address = StringField('Email Address', [InputRequired(),validate_emails], render_kw={"placeholder": "Specify email by one or many seperated by comma"})
    qc_workflow = SelectField('Workflow', choices=[(choice, choice) for choice in qc_workflow()])
    adaptor_seqone = SelectField('Adapter Sequence 1', choices=[('None','None'),('AAACTYAAAKRAATTGRCGGCCCTGGCTGACTA','16S_EMP_read_1'),('AGATCGGAAGAGCACACGTCTGAACTCCAGTCA','NEB_Read_1'),('CTGTCTCTTATACACATCT','Nextera_Read_1'),('AGATCGGAAGAGCACACGTCTGAACTCCAGTCA','TruSeq_read_1')], validators=[validators.InputRequired(message='Please select an option')] )
    adaptor_seqtwo = SelectField('Adapter Sequence 2', choices=[('None','None'),('TTACCGCGGCKGCTGRCACACAATTACCAT','16S_EMP_read_2'),('AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT','NEB_Read_2'),('CTGTCTCTTATACACATCT','Nextera_Read_2'),('AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT','TruSeq_Read_2')], validators=[validators.InputRequired(message='Please select an option')])
    #adaptor_seqone = RadioField('Adapter Sequence 1', choices=[('None','None'),('AAACTYAAAKRAATTGRCGGCCCTGGCTGACTA','16S_EMP_read_1'),('AGATCGGAAGAGCACACGTCTGAACTCCAGTCA','NEB_Read_1'),('CTGTCTCTTATACACATCT','Nextera_Read_1'),('AGATCGGAAGAGCACACGTCTGAACTCCAGTCA','TruSeq_read_1')], validators=[validators.InputRequired(message='Please select an option')])
    #adaptor_seqtwo = RadioField('Adapter Sequence 2', choices=[('None','None'),('TTACCGCGGCKGCTGRCACACAATTACCAT','16S_EMP_read_2'),('AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT','NEB_Read_2'),('CTGTCTCTTATACACATCT','Nextera_Read_2'),('AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT','TruSeq_Read_2')], validators=[validators.InputRequired(message='Please select an option')])
    work_dir = StringField('Working Directory',[InputRequired(),file_validate], render_kw={"placeholder": "Specify the work directory path - eg:- /archive/gencoreseq/XXXX"})
    jira_ticket = StringField('Jira Ticket', [InputRequired(),validate_jira_ticket], render_kw={"placeholder": "Enter the Jira ticket number: (eg:- NCS-222)"})
    scratch_dir = StringField('Scratch Directory')
    archive_dir = StringField('Archive Directory')

class SequenceBaseView(AppBuilderBaseView):
    default_view = "seqrun"
    @expose("/", methods=['GET', 'POST'])
    @csrf.exempt 
    def seqrun(self):
        now = datetime.now()
        dt_string = now.strftime("%d-%m-%Y-%H:%M:%S")
        form = MyForm(request.form)
        if  request.method == 'POST' and form.validate():
            run_id = form.projname.data + dt_string
            scratch_dir_value = form.work_dir.data.replace("/archive/gencoreseq", "/scratch/gencore")
            form.scratch_dir.data = scratch_dir_value
            archive_dir_value = form.work_dir.data.replace("/archive/gencoreseq", "/archive/gencore")
            form.archive_dir.data = archive_dir_value
            issue, description = validate_jira_ticket(form, form.jira_ticket)
            dagbag = DagBag('dags')
            dag = dagbag.get_dag('default_sequence')
            dag.create_dagrun(
                run_id=run_id,        
                state=State.RUNNING,
                conf={'miso_id':form.miso_number.data, 'scratch_dir':form.scratch_dir.data, 'archive_dir':form.archive_dir.data, 'work_dir':form.work_dir.data, 'jira_ticket':form.jira_ticket.data, 'projname':form.projname.data, 'email_id':form.email_address.data,  'reverse_id':form.reverse_complement.data, 'adpone':form.adaptor_seqone.data, 'adptwo':form.adaptor_seqtwo.data, 'qc_workflow':form.qc_workflow.data }
            )
            data = {}
            data['projname'] = form.projname.data
            data['miso_number'] = form.miso_number.data
            data['reverse_complement'] = form.reverse_complement.data
            data['qc_workflow'] = form.qc_workflow.data
            data['email_address'] = form.email_address.data
            data['adaptor_seqone'] = form.adaptor_seqone.data
            data['adaptor_seqtwo'] = form.adaptor_seqtwo.data
            data['work_dir'] = form.work_dir.data
            data['jira_ticket'] = form.jira_ticket.data
            data['jira_ticket_des'] = description
            data['scratch_dir'] = form.scratch_dir.data
            data['archive_dir'] = form.archive_dir.data
            data['status_url'] = f"http://{os.environ['AIRFLOW_URL']}:{os.environ['AIRFLOW_PORT']}/dags/default_sequence/graph"
            pprint(dagbag)          
            return self.render_template("default_response.html", data = data)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{error}')
            return self.render_template("default.html", form = form)


v_appbuilder_view = SequenceBaseView()
v_appbuilder_package = {
    "name": "Default Sequence Run",    # this is the name of the link displayed
    "category": "Demultiplex Runs", # This is the name of the tab under     which we have our view
    "view": v_appbuilder_view
}


class AirflowPlugin(AirflowPlugin):
    name = "default_sequence"
    operators = []
    flask_blueprints = [bp]
    hooks = []
    executors = []
    admin_views = []
    appbuilder_views = [v_appbuilder_package]
