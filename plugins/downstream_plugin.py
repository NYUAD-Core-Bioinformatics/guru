from airflow.plugins_manager import AirflowPlugin
from airflow.www.app import csrf
from airflow.models import DagBag, DagRun
from airflow.utils.state import State
from airflow.utils import timezone
from flask_appbuilder import expose, BaseView as AppBuilderBaseView
from flask import Flask, Blueprint, render_template, request, flash, jsonify, send_file
from wtforms import Form, StringField, IntegerField, EmailField, RadioField, SelectField, validators
from wtforms.validators import ValidationError, InputRequired, EqualTo
import os
import posixpath
import stat as stat_module
import fnmatch
from datetime import datetime
import pandas as pd
import io
import re
from werkzeug.utils import secure_filename
from airflow.providers.ssh.hooks.ssh import SSHHook



# Blueprints for the plugin
bp = Blueprint(
    "downstream_plugin",
    __name__,
    template_folder="templates",
)

"""Function to select/choose the downstream_workflow file from jubail."""
def downstream_workflow():    
    # sftp = ssh.open_sftp()
    # Below 3 lines based on airflow ssh connection defined.
    ssh_hook = SSHHook(ssh_conn_id='guru_ssh')
    ssh_client = ssh_hook.get_conn()
    sftp = ssh_client.open_sftp()
    try:
        dir = os.environ.get('DOWN_WORKDIR')
        workflow_files = sorted(
            (filename for filename in sftp.listdir(dir)
             if fnmatch.fnmatch(filename.lower(), "*.yml")
             and not fnmatch.fnmatch(filename.lower(), "qc-qt*.yml")),
            key=str.casefold,
        )
        down_file = [("None", "None")] + [
            (os.path.join(dir, filename), filename)
            for filename in workflow_files
        ]
        sftp.close()
    except FileNotFoundError as e:
        raise ValidationError('Downstream_Workflow path not visible, Contact Airflow admin')
    return down_file

"""Validate the active view's user-supplied remote working directory over SFTP."""
def file_validate(form, field):
    selected_mode = form.view_mode.data
    field_mode = "custom" if field.name.startswith("custom_") else "default"
    if selected_mode != field_mode:
        return

    if not field.data or not field.data.strip():
        raise ValidationError("Working Directory is required.")

    working_dir = posixpath.normpath(field.data.strip())
    # Default users may enter either the run directory or its Unaligned folder.
    # Keep the canonical run directory in the DAG config, which appends Unaligned
    # when preparing the workflow copy.
    if selected_mode == "default" and posixpath.basename(working_dir) == "Unaligned":
        working_dir = posixpath.dirname(working_dir)

    ssh_hook = SSHHook(ssh_conn_id="guru_ssh")
    ssh_hook.no_host_key_check = True
    ssh_client = None
    sftp = None

    try:
        ssh_client = ssh_hook.get_conn()
        sftp = ssh_client.open_sftp()
        try:
            attributes = sftp.stat(working_dir)
        except OSError:
            raise ValidationError(
                f"Directory does not exist on the remote server: {working_dir}"
            )

        if not stat_module.S_ISDIR(attributes.st_mode):
            raise ValidationError(f"The remote path is not a directory: {working_dir}")

        if selected_mode == "default":
            parts = [part for part in working_dir.split("/") if part]
            if len(parts) != 4:
                raise ValidationError(
                    "Default view requires exactly 4 directory levels, e.g. "
                    "/scratch/gencore/novaseq/260515_A00534_0233_AHFG3JDRX7"
                )

            for required_path in (
                posixpath.join(working_dir, "Unaligned"),
                posixpath.join(working_dir, "Unaligned/data/processed"),
            ):
                try:
                    required_attributes = sftp.stat(required_path)
                except OSError:
                    raise ValidationError(f"Directory does not exist: {required_path}")
                if not stat_module.S_ISDIR(required_attributes.st_mode):
                    raise ValidationError(f"Path is not a directory: {required_path}")
    finally:
        if sftp:
            sftp.close()
        if ssh_client:
            ssh_client.close()

    field.data = working_dir


def validate_custom_extension(form, field):
    if form.view_mode.data != "custom":
        return
    value = (field.data or "").strip()
    if not value:
        raise ValidationError(f"{field.label.text} is required for Custom view.")
    if any(char in value for char in ("/", "\\", "\n", "\r")):
        raise ValidationError("Enter a filename suffix, not a path.")
    field.data = value


def validate_project_name(form, field):
    selected_mode = form.view_mode.data
    field_mode = "custom" if field.name.startswith("custom_") else "default"
    if selected_mode != field_mode:
        return

    value = (field.data or "").strip()
    if not value:
        raise ValidationError("Project Name is required.")

    # Keep only letters and digits; replace each run of other characters with
    # one underscore so the value is safe and readable in workflow metadata.
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    if not normalized:
        raise ValidationError("Project Name must contain at least one letter or number.")
    field.data = normalized


def validate_emails(form, field):
    selected_mode = form.view_mode.data
    field_mode = "custom" if field.name.startswith("custom_") else "default"
    if selected_mode != field_mode:
        return

    emails = (field.data or "").strip()
    if not emails:
        raise ValidationError("Email Address is required.")

    email_ids = emails.split(",")
    regex = r"^\S+@\S+\.\S+$"
    invalid_emails = [email.strip() for email in email_ids if not re.match(regex, email.strip())]
    if invalid_emails:
        raise ValidationError("Invalid email address format: {}".format(", ".join(invalid_emails)))
    field.data = emails


WORKFLOW_CHOICES = downstream_workflow()


class MyForm(Form):
    view_mode = RadioField(
        "View",
        choices=[("default", "Default"), ("custom", "Custom")],
        default="default",
        validators=[InputRequired()],
    )
    project_name = StringField(
        "Project Name",
        [validate_project_name],
        render_kw={"placeholder": "Enter a project name"},
    )
    custom_project_name = StringField(
        "Project Name",
        [validate_project_name],
        render_kw={"placeholder": "Enter a project name"},
    )
    scratch_dir = StringField(
        "Working Directory",
        [file_validate],
        render_kw={"placeholder": "Working directory, e.g. /scratch/gencore/novaseq/260515_A00534_0233_AHFG3JDRX7"},
    )
    custom_scratch_dir = StringField(
        "Working Directory",
        [file_validate],
        render_kw={"placeholder": "Specify the path of FASTQ-containing working directory"},
    )
    email_address = StringField(
        "Email Address",
        [validate_emails],
        render_kw={"placeholder": "Specify email by one or many separated by comma"},
    )
    custom_email_address = StringField(
        "Email Address",
        [validate_emails],
        render_kw={"placeholder": "Specify email by one or many separated by comma"},
    )
    downstream_netid = StringField("Net-ID", render_kw={"placeholder": "Enter your net-id"})
    custom_r1_extension = StringField(
        "R1 extension",
        [validate_custom_extension],
        render_kw={"placeholder": "e.g. _read1.fastq.gz"},
    )
    custom_r2_extension = StringField(
        "R2 extension",
        [validate_custom_extension],
        render_kw={"placeholder": "e.g. _read2.fastq.gz"},
    )
    downstream_workflow = SelectField("Downstream Workflow", choices=WORKFLOW_CHOICES)
    custom_downstream_workflow = SelectField("Downstream Workflow", choices=WORKFLOW_CHOICES)


class DownstreamBaseView(AppBuilderBaseView):
    default_view = "downstreamrun"

    @expose("/", methods=["GET", "POST"])
    @csrf.exempt
    def downstreamrun(self):
        form = MyForm(request.form)

        def collect_extra_analysis(netid_prefix, workflow_prefix):
            keys = [key for key in request.form.keys() if key.startswith(netid_prefix)]
            keys.sort(key=lambda key: int(key[len(netid_prefix):]))
            items = []
            for netid_key in keys:
                index = netid_key[len(netid_prefix):]
                items.append({
                    "index": index,
                    "netid": request.form.get(netid_key, ""),
                    "workflow": request.form.get(f"{workflow_prefix}{index}", ""),
                })
            return items

        extra_analysis = collect_extra_analysis("extra_netid_", "extra_down_workflow_")
        custom_extra_analysis = collect_extra_analysis(
            "custom_extra_netid_", "custom_extra_down_workflow_"
        )

        if request.method == "POST" and form.validate():
            is_custom = form.view_mode.data == "custom"
            working_dir = (
                form.custom_scratch_dir.data if is_custom else form.scratch_dir.data
            )
            project_name = (
                form.custom_project_name.data if is_custom else form.project_name.data
            )
            email_address = (
                form.custom_email_address.data if is_custom else form.email_address.data
            )
            downstream_analysis = []
            if not is_custom:
                primary_netid = form.downstream_netid.data
                primary_workflow = form.downstream_workflow.data
                if primary_netid and primary_workflow and primary_workflow != "None":
                    downstream_analysis.append({
                        "netid": primary_netid.strip(),
                        "workflow": primary_workflow,
                    })
                for item in extra_analysis:
                    if item["netid"].strip() and item["workflow"] and item["workflow"] != "None":
                        downstream_analysis.append({
                            "netid": item["netid"].strip(),
                            "workflow": item["workflow"],
                        })

            uploaded_workflow = request.files.get("custom_workflow_upload") if is_custom else None
            upload_name = (uploaded_workflow.filename or "").strip() if uploaded_workflow else ""
            selected_custom_workflow = form.custom_downstream_workflow.data

            if is_custom and upload_name and not upload_name.lower().endswith((".yml", ".yaml")):
                form.custom_downstream_workflow.errors.append("Upload a .yml or .yaml workflow file.")
                return self.render_template(
                    "downstream.html",
                    form=form,
                    extra_analysis=extra_analysis,
                    custom_extra_analysis=custom_extra_analysis,
                )

            if is_custom and not upload_name and selected_custom_workflow in (None, "", "None"):
                form.custom_downstream_workflow.errors.append(
                    "Select a workflow or upload a YAML file for Custom view."
                )
                return self.render_template(
                    "downstream.html",
                    form=form,
                    extra_analysis=extra_analysis,
                    custom_extra_analysis=custom_extra_analysis,
                )

            run_id = "test_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            dagbag = DagBag(
                dag_folder=os.path.join("dags", "downstream_dag.py"),
                include_examples=False,
            )
            dag = dagbag.get_dag("downstream_dag")
            if dag is None:
                raise ValueError("DAG 'downstream_dag' was not found in dags/downstream_dag.py")

            if is_custom:
                if upload_name:
                    safe_upload_name = secure_filename(upload_name)
                    if not safe_upload_name:
                        raise ValueError("The uploaded workflow filename is not valid.")
                    staged_path = posixpath.join(
                        working_dir, f".airflow_upload_{run_id}_{safe_upload_name}"
                    )
                    ssh_hook = SSHHook(ssh_conn_id="guru_ssh")
                    ssh_hook.no_host_key_check = True
                    ssh_client = ssh_hook.get_conn()
                    sftp = ssh_client.open_sftp()
                    try:
                        sftp.putfo(uploaded_workflow.stream, staged_path)
                    finally:
                        sftp.close()
                        ssh_client.close()
                    custom_workflow = staged_path
                    workflow_label = safe_upload_name
                else:
                    custom_workflow = selected_custom_workflow
                    workflow_label = posixpath.basename(custom_workflow)
                downstream_analysis = [{
                    "netid": "",
                    "workflow": custom_workflow,
                    "workflow_label": workflow_label,
                    "uploaded_workflow": bool(upload_name),
                }]

            dag.create_dagrun(
                run_id=run_id,
                state=State.RUNNING,
                conf={
                    "scratch_dir": working_dir,
                    "project_name": project_name,
                    "view_mode": form.view_mode.data,
                    "email_address": email_address,
                    "downstream_analysis": downstream_analysis,
                    "r1_extension": form.custom_r1_extension.data if is_custom else None,
                    "r2_extension": form.custom_r2_extension.data if is_custom else None,
                },
            )

            response_working_dir = (
                working_dir
                if is_custom
                else posixpath.join(working_dir, "Unaligned")
            )
            data = {
                "scratch_dir": response_working_dir,
                "view_mode": form.view_mode.data,
                "project_name": project_name,
                "email_address": email_address,
                "downstream_analysis": [
                    {
                        **item,
                        "workflow": (
                            item.get("workflow_label")
                            or (
                                posixpath.basename(item.get("workflow", ""))
                                if is_custom
                                else item.get("workflow", "")
                            )
                        ),
                    }
                    for item in downstream_analysis
                ],
            }
            data["status_url"] = (
                f"http://{os.environ['AIRFLOW_URL']}:{os.environ['AIRFLOW_PORT']}"
                "/dags/downstream_dag/graph"
            )
            return self.render_template("downstream_response.html", data=data)

        return self.render_template(
            "downstream.html",
            form=form,
            extra_analysis=extra_analysis,
            custom_extra_analysis=custom_extra_analysis,
        )

# AppBuilder View and Plugin Registration
v_appbuilder_view = DownstreamBaseView()
# Register this view without an automatic menu entry. The ordered menu link below
# controls its position alongside the status view.
v_appbuilder_package = {"view": v_appbuilder_view}

if v_appbuilder_view.blueprint is None:
    v_appbuilder_view.blueprint = Blueprint("downstream_plugin", __name__)




class AirflowPlugin(AirflowPlugin):
    name = "downstream_plugin"
    operators = []
    flask_blueprints = [bp]
    hooks = []
    executors = []
    admin_views = []
    appbuilder_views = [v_appbuilder_package]
    appbuilder_menu_items = [{
        "name": "Downstream Analysis",
        "href": "/downstreambaseview/",
        "category": "Downstream Runs",
    }]
