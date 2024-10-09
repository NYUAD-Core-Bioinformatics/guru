from airflow.plugins_manager import AirflowPlugin
from airflow.www.app import csrf
from airflow.models import DagBag, DagRun
from airflow.utils.state import State
from airflow.utils import timezone
from flask_appbuilder import expose, BaseView as AppBuilderBaseView
from flask import Flask, Blueprint, render_template, request, flash
from wtforms.validators import ValidationError, InputRequired, EqualTo
from wtforms import Form, StringField, IntegerField, EmailField, RadioField, FileField, SelectField, validators
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
               "10X_run",
               __name__,
               template_folder="templates", 
               )

"""Function for checking the miso ID exist in the mysql database"""
def validate_miso_id(form, field):
    """Defining the mysql access information""" 
    # Using mysqlhook module loaded mysql connections to get the credentials.
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

"""Function to check if the work directory given is exist or not."""
def file_validate(form, field):
    # Get the path and assign to a list
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


"""Function to check the jira ticket existance"""
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
    projname = StringField('Project Name', [InputRequired()], render_kw={"placeholder": "Enter your Project name"})
    miso_number = StringField('Miso ID', [InputRequired(), validate_miso_id], render_kw={"placeholder": "Type miso ID number"})
    workflow  = RadioField('10X Workflow',  choices=[('cellranger','cellranger'),('supernova','supernova'),('longranger','longranger'),('cellranger_atac','cellranger_atac')], validators=[validators.InputRequired(message='Please select an option')])
    email_address = StringField('Email Address', [InputRequired(),validate_emails], render_kw={"placeholder": "Specify email by one or many seperated by comma"})
    work_dir = StringField('Working Directory',[InputRequired(),file_validate], render_kw={"placeholder": "Specify the work directory path - eg:- /archive/gencoreseq/XXXX"})
    jira_ticket = StringField('Jira Ticket', [InputRequired(),validate_jira_ticket], render_kw={"placeholder": "Enter the Jira ticket number: (eg:- NCS-222)"})
    scratch_dir = StringField('Scratch Directory')
    archive_dir = StringField('Archive Directory')


class Singlecell_10XBaseView(AppBuilderBaseView):
    default_view = "seqrun"
    @expose("/", methods=['GET', 'POST'])
    @csrf.exempt 
    def seqrun(self):
        now = datetime.now()
        dt_string = now.strftime("%d-%m-%Y-%H:%M:%S")
        form = MyForm(request.form)
        if  request.method == 'POST' and form.validate():
            scratch_dir_value = form.work_dir.data.replace("/archive/gencoreseq", "/scratch/gencore")
            form.scratch_dir.data = scratch_dir_value
            archive_dir_value = form.work_dir.data.replace("/archive/gencoreseq", "/archive/gencore")
            form.archive_dir.data = archive_dir_value
            run_id = form.projname.data + "_" + dt_string
            issue, description = validate_jira_ticket(form, form.jira_ticket)
            #Using Airflow DagBag module, we are establish the connection to Airflow Dag.
            dagbag = DagBag('dags')
            dag = dagbag.get_dag('10X_sequence')
            #We are triggering the dag here with passing the input variable and run_id.
            dag.create_dagrun(
                run_id=run_id,        
                state=State.RUNNING,
                conf={'miso_id':form.miso_number.data, 'scratch_dir':form.scratch_dir.data, 'archive_dir':form.archive_dir.data, 'work_dir':form.work_dir.data, 'archive_dir':form.archive_dir.data, 'jira_ticket':form.jira_ticket.data, 'projname':form.projname.data, 'email_id':form.email_address.data, 'workflow':form.workflow.data }
            )
            data = {}
            data['projname'] = form.projname.data
            data['miso_number'] = form.miso_number.data
            data['workflow'] = form.workflow.data
            data['email_address'] = form.email_address.data
            data['work_dir'] = form.work_dir.data
            data['jira_ticket'] = form.jira_ticket.data
            data['jira_ticket_des'] = description
            data['scratch_dir'] = form.scratch_dir.data
            data['archive_dir'] = form.archive_dir.data
            data['status_url'] = f"http://{os.environ['AIRFLOW_URL']}:{os.environ['AIRFLOW_PORT']}/dags/10X_sequence/graph"
            pprint(dagbag)          
            return self.render_template("10x_response.html", data = data)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{error}')
            return self.render_template("10x.html", form = form)
        

"""Defining the custom UI"""
v_appbuilder_view = Singlecell_10XBaseView()
v_appbuilder_package = {
    "name": "10X Sequence Run",    # this is the sub tab name under the main
    "category": "Demultiplex Runs", # This is the main tab name under which we have our custom view
    "view": v_appbuilder_view
}

"""Specifying the Plugin parameters"""
class AirflowPlugin(AirflowPlugin):
    name = "10X_run"
    operators = []
    flask_blueprints = [bp]
    hooks = []
    executors = []
    admin_views = []
    appbuilder_views = [v_appbuilder_package]
