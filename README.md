# GURU: Genomics seqUencing Run aUtomation

## Contents

- [Introduction](#introduction)
    - [Key facts](#key-facts)
    - [Technologies Used](#technologies-used)
- [Installation](#installation)
    - [Installing from Docker](#installing-from-docker)
    - [Installing from PyPI](#installing-from-pypi)
- [Usage](#usage)
- [Contact](#contact)
- [Citation](#citation)
- [Acknowledgements](#acknowledgements)
- [Other Useful Links](#other-useful-links)

## Introduction

Managing and maintaining a genomics infrastructure requires a multi-layered approach. Typically, that involves a Laboratory Information Management System (LIMS), the Sequencing Instrumentation, the computational Infrastructure to store and process the data, as well as any other additional layers such as project management software (e.g. JIRA). In a production environment, all of these layers need to efficiently communicate and integrate with each other, which can be a complicated task. In addition, the approach needs to be descriptive and yet flexible enough to accommodate new additions to the existing layers. Our solution, GURU (Genomics seqUencing Run aUtomation) addresses this need. GURU is implemented using Apache Airflow that allows for the authoring, scheduling and monitoring of workflows, or DAGs (Directed Acyclic Graph). Specific DAGs have been implemented to handle various sequencing runs, from SingleCell applications, to RNA/DNA sequencing, Short reads vs Long reads, archiving of sequencing runs, initiating specific types of analysis (QC/WGS/WES/RNAseq/ATAC/CHiP etc.), as well as automatically communicate to end-users regarding the status of their samples/runs. GURU has been containerized using Docker to enable easy deployment across various configurations.

<img src="/img/guru_title.png"  align="center" />

$~~~~~~$

### Key facts 

- Customized user interface plugins using Apache Flask Web Framework, ensuring DAGs are bound to their respective plugins. 
- Airflow models (Dagbags) are used to enable the communication with the Airflow plugins, thus avoiding RESTAPIs.
- Commands are launched directly on the computational environment (Server/HPC/Cloud), and their status is monitored, meaning that GURU can be deployed anywhere and does not have to be deployed in the same  computational infrastructure where the data processing happens.
- Integration with JIRA (or other issue tracking systems) is achieved using a RESTAPI. The same approach can be implemented for any other additional layers of communication. 
- Integration with Bioinformatics Workflow Management Systems such as BioSAILs ensures more complex analyses can be supported (other WMS can also be supported e.g. Nextflow, CWL, Snakemake).

### Technologies Used

- Apache Airflow(v2.10.2)
- Docker >=26
- Python >=3.11
- Shell Scripting
- Python Flask Wtforms
- JIRA(v6.3.12)


#### Important Note
- The JIRA version we are using is outdated, and the integration is based on RESTAPI with Oauthv1. If you require assistance with other project management software or a later version of JIRA, then please contact us to see if we can help. 
- We use MISO as our LIMS. If you require assistance integrating GURU with your existing LIMS, then please contact us to see if we can help.
## Installation

You can install GURU using [pip](https://pip.pypa.io/en/stable/) or  [docker](https://www.docker.com/). The simplest way to get GURU up and running quickly is to use Docker. 


### Installing from Docker
 
#### Prerequisites

1. [Install Docker Latest Version V23.0.2+](https://docs.docker.com/engine/install/)
2. MISO LIMS ( Optional:- iskylims or other LIMS tools )
3. JIRA ( Optional:- Redmine or other project management software )

#### Cloning the repository

```
git clone https://github.com/NYUAD-Core-Bioinformatics/guru
cd guru
```

#### Setting up the environment

Defining the environment variables. 

Note:- 
- JIRA is optional, if you are not using JIRA then customize the .env file accordingly.
- Since JIRA integration is based on Oauthv1, using a private key, you should place a key called "jira.pem" in the "keys" folder.

``` bash
cat .env
### Airflow variables
AIRFLOW_UID=<Airflow USER ID - Default is 50000>
AIRFLOW_URL=<IP Address or Hostname of the host machine>
AIRFLOW_PORT=8080

### QC Work directory Path
QC_WORKDIR=<Path-to-workflow-directory>

### JIRA variables
CONSUMER_KEY=<key_name>
JIRA_SERVER=<URL or IP Address>
OAUTH_TOKEN=<token>
OAUTH_TOKEN_SECRET=<token_secret>
```

Update the ownership of the directory. (For eg:- we run Airflow as UID - 50000).
``` bash
chown -R 50000  ./guru
```

Update the Airflow connection parameters for ssh, smtp and mysql.

Note:-
- Modify the ssh key path, user credentails etc.

``` bash
$vim scripts/airflow_conn.sh
#!/bin/bash

#############################################################################
# Arguments for Airflow initialization
# So far these protocols SSH / MYSQL / SMTP needed now to connect to cluster.
############################################################################

## Defining SSH connection 
airflow connections add  guru_ssh   --conn-type ssh --conn-host < hostname or IP address > --conn-login user --conn-port 22 --conn-extra '{"key_file": "/home/airflow/.ssh/id_rsa", "missing_host_key_policy": "AutoAddPolicy"}'

## Defining SMTP connection 
airflow connections add guru_email --conn-type email --conn-host smtp.gmail.com --conn-login <emailID> --conn-password <email-pass> --conn-port <port-num>

## Defining Mysql Connection 
airflow connections add guru_mysql --conn-type mysql --conn-login <user> --conn-password <pass> --conn-host <hostname or IP address > --conn-port <port> --conn-schema <database name> --conn-extra '{"ssl_mode": "DISABLED"}'
```

To invoke the Docker based installation, issue the commands below.

``` bash
docker compose up --build -d
docker compose restart
```

Verify the services
``` bash
docker compose ps 
```

Validate the logs 
``` bash
docker compose logs -f 
```

To access the Airflow User Interface [http://IP-address:8080](http://IP-address:8080)
and use the credentials **airflow**/**airflow**.

Note:- 
- If you run this service on a server, specify the (IP-address or hostname):8080 on the browser. 
- If you run this service on a standalone machine (e.g. laptop), specify localhost:8080 on the browser.

### Installing from PyPI

Installation using pip:- 

#### Cloning the repository

```
git clone https://github.com/NYUAD-Core-Bioinformatics/guru
cd guru
```

Define the environment variable in your .bashrc or .zshrc of you favourite shell.

Note:-
- JIRA is optional, if you are not using JIRA then customize the environment file accordingly (e.g. .bashrc / .zshrc).

``` bash
### Airflow variables
export AIRFLOW_HOME=<Path-to-airflow-home>
export AIRFLOW_URL=<IP Address or Hostname of the host machine>
export AIRFLOW_PORT=8080

### QC Work directory Path
export QC_WORKDIR=<Path-to-workflow-directory>

###JIRA env variables
export CONSUMER_KEY=<key_name>
export JIRA_SERVER=<URL or IP Address>
export OAUTH_TOKEN=<token>
export OAUTH_TOKEN_SECRET=<token_secret>
```


Install the prerequisite python packages using commands below.

Note:- 
- Python >= 3.11

``` bash
pip3 install -r pip-requirements.txt
```

Install the JIRA module ( Optional )

Note:-
- Since the JIRA integration is based on Oauthv1, using a private key. You should place a key file called "jira.pem" in the ```~/.ssh/``` path. 

``` bash
cd pkgs
sh pip_jira.sh
```

Initialize airflow db and this will create airflow.cfg in the AIRFLOW_HOME directory (defined above).

``` bash
airflow db migrate
```

Update the Airflow connection parameters for ssh, smtp and mysql. Then excecute the script.

Note:-
- Modify the ssh key path, user credentails etc.

``` bash
$vim scripts/airflow_conn_pip.sh
#!/bin/bash

#############################################################################
# Arguments for Airflow initialization
# So far these protocols SSH / MYSQL / SMTP needed now to connect to cluster.
############################################################################

## Defining SSH connection
airflow connections add  guru_ssh   --conn-type ssh --conn-host < hostname or IP address > --conn-login user --conn-port 22 --conn-extra '{"key_file": "<Path-to-SSH-private-key>", "missing_host_key_policy": "AutoAddPolicy"}'

## Defining SMTP connection
airflow connections add guru_email --conn-type email --conn-host smtp.gmail.com --conn-login <emailID> --conn-password <email-pass> --conn-port <port-num>

## Defining Mysql Connection
airflow connections add guru_mysql --conn-type mysql --conn-login <user> --conn-password <pass> --conn-host <hostname or IP address > --conn-port <port> --conn-schema <database name> --conn-extra '{"ssl_mode": "DISABLED"}'
```

Create user account named airflow with admin privileges.

``` bash
airflow users create \
--username airflow \
--password airflow \
--firstname <first-name> \
--lastname <lastname> \
--role Admin \
--email <specify-email>
```

In order to start the Airflow instance (according to the instructions at [Airflow](https://airflow.apache.org/docs/apache-airflow/2.10.2/start.html))
Launch the command below. 

``` bash
airflow standalone
```


To access the Airflow User Interface, open a web browser and go to [http://IP-address:8080](http://IP-address:8080)
and use the following username/password credentials **airflow**/**airflow**.

Note:- 
- If you run this service on a server, specify the (IP-address or hostname):8080 on the browser. 
- If you run this service on a standalone machine (e.g. laptop), specify localhost:8080 on the browser.


To launch a "standard" paired end dual index (with reverse complement i7) DAG...
## Usage

- **DAGs**: Once you have successfully logged into the Airflow UI, the available Airflow DAGs should be visible.

<img src="/img/guru_dag.png"  align="left"/>

$~~~~$

- **User Interface**: Navigate to the "Demultiplex Runs" tab to see the appropriate custom UI input for the Airflow DAGs.  

<img src="/img/guru_ui_tab.png"  align="left"  />

$~~~~$

- **Sequence Run**: Select "Default Sequence Run" from the "Demultiplex Runs" tab. 

<img src="/img/guru_ui_template.png"  align="left" />

$~~~~$

- **Sequence Run Summary**: Below is just a default "standard" sequencing run setup.

<img src="/img/guru_ui_summary.png"  align="left" />

$~~~~$

Below is a description of the fields.

- `Project Name:-` (Optional) Specify a brief description of the Project eg:- "10x Single cell RNAseq for Marcus Lab".
- `Miso ID:-` Using the unique sequencing run ID number, which is defined in our MISO LIMS, GURU will automatically gather the required SampleSheet information of the sequenced samples. This is needed in order to generate a Demultiplexing sheet.
- `Reverse Complement:-` Defines whether or not to reverse complement the second index (i7). This only applies to "standard" sequencing run setups (DAGs). 
- `Email Address:-` Here, a user can specify the email address(es) of one or multiple users that need to be notified regarding the progress. The address(es) should be comma-separated (no whitspaces), and email validation is enabled.
- `Jira Ticket:-` We use JIRA for logging the run status. Currently, we are running an older version of JIRA (v6.3.12), which is integrated with Airflows using Oauth keys. 
- `Workflow:-` We use [BioSAILs](https://www.biorxiv.org/content/biorxiv/early/2019/01/02/509455.full.pdf) as our workflow management system (WMS) for processing the raw sequencing reads (QC/QT). You can choose any other WMS such as snakemake or nextflow if you so choose. In this variable we also specify the location of the appropriate QC/QT YAML formatted workflow file that BioSAILs will use.
- `Adapter Sequence 1:-` Sequence of adapter to be trimmed for read1.
- `Adapter Sequence 2:-` Sequence of adapter to be trimmed for read2.
- `Working Directory:-` Full path to the location of the sequencing run folder. 

- **Run Status**: Clicking on the "Check Run Status" button will show you the status (progress) of the specific Dagrun. 

<img src="/img/guru_dag_run.png"  align="left" />

$~~~~$


- **10X Run**: To launch a "10x sequencing run", then select the appropriate DAG.
Please note that under the "10x Sequence Run" DAG, you will have multiple options depending on the nature of your run (eg:- scRNA->cellranger, scATAC->cellranger_atac etc.).


<img src="/img/guru_ui_10xui.png"  align="left" />

- `10X Workflow:-` Here you can choose the 10X workflows by choosing the appropriate radio button.

- **10X Run Summary**: Similarly if you fill and submit the  "10X Sequence Run". You may see the status of Dagruns.

<img src="/img/guru_ui_10x.png"  align="left" />

$~~~~$

## Contact

If you need to contact us for feedback, queries, or to raise an issue, you can do so using the issues page [Github issue](https://github.com/NYUAD-Core-Bioinformatics/guru/issues).

## Citation

If you use GURU in your research or publications, please cite our [Github page](https://github.com/NYUAD-Core-Bioinformatics/guru).

## Acknowledgements

This work was supported by Tamkeen under the NYU Abu Dhabi Research Institute Award to the NYUAD Center for Genomics and Systems Biology (ADHPG-CGSB). We would also like to acknowledge the High Performance Computing department at NYU Abu Dhabi for the computational resources and their continuous support.

## Other Useful Links

- [CGSB Webpage](https://cgsb.abudhabi.nyu.edu) : for news and updates
- [BioSAILs](https://www.biorxiv.org/content/biorxiv/early/2019/01/02/509455.full.pdf)
- [Airflow](https://airflow.apache.org/) 
- [MISO LIMS](https://github.com/miso-lims/miso-lims)
- [Docker](https://www.docker.com/)
