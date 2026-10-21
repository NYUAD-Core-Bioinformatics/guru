import json
import posixpath
import re
import shlex
import stat

import yaml
from airflow.providers.ssh.hooks.ssh import SSHHook


def prepare_custom_workflows(**context):
    """Prepare per-run copies of selected workflows for the active view."""
    conf = context["dag_run"].conf
    view_mode = conf.get("view_mode")
    if view_mode not in {"default", "custom"}:
        print(f"Unknown view mode {view_mode!r}; skipping workflow preparation.")
        return

    working_dir = conf.get("scratch_dir")
    analyses = conf.get("downstream_analysis") or []
    project_name = (conf.get("project_name") or "").strip()
    if not project_name:
        raise ValueError("A project name is required for workflow preparation.")
    if not working_dir:
        raise ValueError("A working directory is required for workflow preparation.")
    if not analyses:
        print(f"No workflow selected in {view_mode} view; skipping workflow preparation.")
        return

    # Default YAML paths are relative to the run's Unaligned directory. Custom
    # workflows use the user-provided FASTQ-containing working directory itself.
    target_dir = (
        working_dir
        if view_mode == "custom"
        else posixpath.join(working_dir, "Unaligned")
    )

    hook = SSHHook(ssh_conn_id="guru_ssh")
    hook.no_host_key_check = True
    ssh = hook.get_conn()
    sftp = None
    prepared_paths = []

    try:
        sftp = ssh.open_sftp()
        directory_attrs = sftp.stat(target_dir)
        if not stat.S_ISDIR(directory_attrs.st_mode):
            raise ValueError(f"Remote workflow destination is not a directory: {target_dir}")

        selected_sources = [item.get("workflow") for item in analyses]
        duplicate_names = {
            posixpath.basename(source)
            for source in selected_sources
            if source and selected_sources.count(source) > 1
        }

        for item in analyses:
            source_path = item.get("workflow")
            netid = (item.get("netid") or "").strip()
            if not source_path or (view_mode == "default" and not netid):
                raise ValueError("Default workflows require both a workflow and Net-ID.")

            safe_netid = re.sub(r"[^A-Za-z0-9._-]+", "_", netid).strip("._") or "custom"
            filename = posixpath.basename(source_path)
            stem, extension = posixpath.splitext(filename)

            if view_mode == "default":
                # Keep each run's customized YAML separate from the shared source
                # and from other Net-ID selections using the same workflow.
                filename = f"{safe_netid}_{stem}{extension}"
            elif item.get("uploaded_workflow"):
                # Keep the user's uploaded filename in the working directory;
                # the temporary staging filename is only used during preparation.
                filename = item.get("workflow_label") or filename

            destination_path = posixpath.join(target_dir, filename)
            if (
                view_mode == "default"
                and posixpath.normpath(source_path) == posixpath.normpath(destination_path)
            ):
                destination_path = posixpath.join(
                    target_dir, f"{safe_netid}_{stem}{extension}"
                )
            if destination_path in prepared_paths:
                if view_mode == "custom":
                    raise ValueError(
                        f"Multiple custom workflows resolve to the same filename: {filename}"
                    )
                destination_path = posixpath.join(
                    target_dir,
                    f"{safe_netid}_{stem}_{len(prepared_paths) + 1}{extension}",
                )

            if view_mode == "custom":
                source_is_destination = (
                    posixpath.normpath(source_path) == posixpath.normpath(destination_path)
                )
                try:
                    sftp.stat(destination_path)
                except FileNotFoundError:
                    pass
                else:
                    raise FileExistsError(
                        f"Custom workflow destination already exists and was left unchanged: "
                        f"{destination_path}"
                    )
                if source_is_destination:
                    raise ValueError(
                        "Custom workflow source is already in the working directory; "
                        "select a source workflow outside that directory to preserve the original file."
                    )

            with sftp.open(source_path, "r") as source_file:
                source_text = source_file.read()
            if isinstance(source_text, bytes):
                source_text = source_text.decode("utf-8")

            workflow_yaml = yaml.safe_load(source_text)
            global_entries = workflow_yaml.get("global") if isinstance(workflow_yaml, dict) else None
            if not isinstance(global_entries, list):
                raise ValueError(f"Workflow YAML has no list-valued 'global' section: {source_path}")

            global_values = {}
            for entry in global_entries:
                if isinstance(entry, dict):
                    global_values.update(entry)

            if view_mode == "custom":
                r1_extension = (conf.get("r1_extension") or "").strip()
                r2_extension = (conf.get("r2_extension") or "").strip()
                if not r1_extension or not r2_extension:
                    raise ValueError("Custom workflow preparation requires R1 and R2 extensions.")
                sample_rule = f"(.*){r1_extension}"
                yaml_sample_rule = json.dumps(sample_rule)
                yaml_project_name = json.dumps(project_name)
                yaml_r1_extension = json.dumps(r1_extension)
                yaml_r2_extension = json.dumps(r2_extension)
                awk_script = r"""
function add_missing_fields() {
    if (!found_indir) { print "  - indir: ./"; found_indir = 1 }
    if (!found_root_in_dir) { print "  - root_in_dir: ./"; found_root_in_dir = 1 }
    if (!found_find_by_dir) { print "  - find_by_dir: 0"; found_find_by_dir = 1 }
    if (!found_jira_ticket) { print "  - jira_ticket: " jira_ticket; found_jira_ticket = 1 }
    if (!found_fastp_dir) { print "  - fastp_dir: ./"; found_fastp_dir = 1 }
    if (!found_sample_rule) { print "  - sample_rule: " sample_rule; found_sample_rule = 1 }
    if (!found_r1_suffix) { print "  - r1_suffix: " r1_suffix; found_r1_suffix = 1 }
    if (!found_r2_suffix) { print "  - r2_suffix: " r2_suffix; found_r2_suffix = 1 }
}
BEGIN {
    in_global = 0
    sample_rule = ENVIRON["CUSTOM_SAMPLE_RULE"]
    jira_ticket = ENVIRON["CUSTOM_JIRA_TICKET"]
    r1_suffix = ENVIRON["CUSTOM_R1_SUFFIX"]
    r2_suffix = ENVIRON["CUSTOM_R2_SUFFIX"]
}
/^global:[[:space:]]*$/ { in_global = 1; print; next }
in_global && /^rules:[[:space:]]*$/ { add_missing_fields(); in_global = 0 }
{
    if (in_global && /^[[:space:]]*-[[:space:]]*indir:/) {
        sub(/:.*/, ": ./")
        found_indir = 1
    }
    if (in_global && /^[[:space:]]*-[[:space:]]*root_in_dir:/) {
        sub(/:.*/, ": ./")
        found_root_in_dir = 1
    }
    if (in_global && /^[[:space:]]*-[[:space:]]*find_by_dir:/) {
        sub(/:.*/, ": 0")
        found_find_by_dir = 1
    }
    if (in_global && /^[[:space:]]*-[[:space:]]*jira_ticket:/) {
        $0 = substr($0, 1, index($0, ":")) " " jira_ticket
        found_jira_ticket = 1
    }
    if (in_global && /^[[:space:]]*-[[:space:]]*fastp_dir:/) {
        sub(/:.*/, ": ./")
        found_fastp_dir = 1
    }
    if (in_global && /^[[:space:]]*-[[:space:]]*sample_rule:/) {
        $0 = substr($0, 1, index($0, ":")) " " sample_rule
        found_sample_rule = 1
    }
    if (in_global && /^[[:space:]]*-[[:space:]]*r1_suffix:/) {
        $0 = substr($0, 1, index($0, ":")) " " r1_suffix
        found_r1_suffix = 1
    }
    if (in_global && /^[[:space:]]*-[[:space:]]*r2_suffix:/) {
        $0 = substr($0, 1, index($0, ":")) " " r2_suffix
        found_r2_suffix = 1
    }
    print
}
END {
    if (in_global) add_missing_fields()
    if (!found_indir || !found_root_in_dir || !found_find_by_dir ||
        !found_fastp_dir || !found_sample_rule || !found_r1_suffix || !found_r2_suffix) exit 42
}
"""
                awk_environment = (
                    f"CUSTOM_SAMPLE_RULE={shlex.quote(yaml_sample_rule)} "
                    f"CUSTOM_JIRA_TICKET={shlex.quote(yaml_project_name)} "
                    f"CUSTOM_R1_SUFFIX={shlex.quote(yaml_r1_extension)} "
                    f"CUSTOM_R2_SUFFIX={shlex.quote(yaml_r2_extension)} "
                )
            else:
                required_fields = {"outdir", "sample_rule"}
                missing_keys = required_fields - global_values.keys()
                if missing_keys:
                    raise ValueError(
                        f"Workflow YAML is missing expected global fields: {', '.join(sorted(missing_keys))}"
                    )
                outdir = global_values["outdir"]
                if not isinstance(outdir, str):
                    raise ValueError(f"Workflow outdir must be a string: {source_path}")
                analysis_path_match = re.search(r"data/analysis_[A-Za-z0-9_.-]+", outdir)
                if not analysis_path_match:
                    raise ValueError(
                        f"Workflow outdir does not contain a data/analysis_* path: {source_path}"
                    )
                source_analysis_path = analysis_path_match.group(0)
                replacement_analysis_path = f"data/analysis_{safe_netid}"
                if source_analysis_path not in source_text:
                    raise ValueError(
                        f"Workflow outdir path was not found in the YAML text: {source_path}"
                    )

                sample_rule = f"({re.escape(netid)}.*)"
                yaml_project_name = json.dumps(project_name)
                awk_script = r"""
function replace_literal(text, old, replacement, result, position) {
    result = ""
    while ((position = index(text, old)) > 0) {
        result = result substr(text, 1, position - 1) replacement
        text = substr(text, position + length(old))
    }
    return result text
}
BEGIN {
    in_global = 0
    old_path = ENVIRON["ANALYSIS_SOURCE_PATH"]
    new_path = ENVIRON["ANALYSIS_TARGET_PATH"]
    sample_rule = ENVIRON["ANALYSIS_SAMPLE_RULE"]
    jira_ticket = ENVIRON["ANALYSIS_JIRA_TICKET"]
}
{
    $0 = replace_literal($0, old_path, new_path)
    if (/^global:[[:space:]]*$/) { in_global = 1; print; next }
    if (in_global && /^rules:[[:space:]]*$/) {
        if (!found_jira_ticket) {
            print "  - jira_ticket: " jira_ticket
            found_jira_ticket = 1
        }
        in_global = 0
    }
    if (in_global && /^[[:space:]]*-[[:space:]]*jira_ticket:/) {
        $0 = substr($0, 1, index($0, ":")) " " jira_ticket
        found_jira_ticket = 1
    }
    if (in_global && /^[[:space:]]*-[[:space:]]*sample_rule:/) {
        sub(/:.*/, ": " sample_rule)
        found_sample_rule = 1
    }
    print
}
END {
    if (in_global && !found_jira_ticket) {
        print "  - jira_ticket: " jira_ticket
        found_jira_ticket = 1
    }
    if (!found_sample_rule || !found_jira_ticket) exit 42
}
"""
                awk_environment = (
                    f"ANALYSIS_SOURCE_PATH={shlex.quote(source_analysis_path)} "
                    f"ANALYSIS_TARGET_PATH={shlex.quote(replacement_analysis_path)} "
                    f"ANALYSIS_SAMPLE_RULE={shlex.quote(sample_rule)} "
                    f"ANALYSIS_JIRA_TICKET={shlex.quote(yaml_project_name)} "
                )

            temporary_path = f"{destination_path}.tmp_{context['dag_run'].run_id}"
            remote_command = (
                f"tmp={shlex.quote(temporary_path)}; "
                "trap 'rm -f \"$tmp\"' EXIT; "
                f"{awk_environment}awk {shlex.quote(awk_script)} {shlex.quote(source_path)} "
                f"> \"$tmp\" && mv \"$tmp\" {shlex.quote(destination_path)}"
            )

            _, stdout, stderr = ssh.exec_command(remote_command)
            stdout_text = stdout.read().decode("utf-8", errors="replace")
            stderr_text = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
            if exit_code:
                raise RuntimeError(
                    f"Remote YAML copy/edit failed ({exit_code}): {stderr_text or stdout_text}"
                )

            if item.get("uploaded_workflow") and posixpath.normpath(source_path) != posixpath.normpath(destination_path):
                sftp.remove(source_path)

            prepared_paths.append(destination_path)
            print(f"Prepared {view_mode} workflow: {destination_path}")

        context["ti"].xcom_push(key="prepared_custom_workflows", value=prepared_paths)
    finally:
        if sftp:
            sftp.close()
        ssh.close()
