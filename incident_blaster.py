#!/usr/bin/python
# Author: Gordon Mckeown - gordon.mckeown@gmail.com
#
# BE CAREFUL! Check configuration carefully before running this script; many
#   incidents can be created in a short space of time!

import base64
import binascii
import datetime
import json
import logging
import random
import sys
import time
import traceback
from pathlib import Path
from typing import Dict

from bmc.remedy import RemedyException, RemedySession

DEBUG_FLAG = False

LOG_LEVEL = logging.DEBUG if DEBUG_FLAG else logging.INFO
logging.basicConfig(stream=sys.stdout, level=LOG_LEVEL)

rest_config = {}
remedy_config = {}
customer_config = {}
runtime_values = {}

DEFAULT_TARGET_DAYS = 30


def get_config_filenames() -> Dict[str, Path]:
    """Determine relative paths for config files and return as a dict"""
    config_folder = Path(sys.path[0]) / "config"
    return {
        "rc": config_folder / "RestConfig.json",
        "sc": config_folder / "StandardConfig.json",
        "cc": config_folder / "CustomerConfig.json",
        "rv": config_folder / "RuntimeValues.json",
    }


def load_config() -> None:
    """Load configuration from external JSON files"""
    # TODO: Improve configuration loading/handling
    global rest_config, remedy_config, customer_config, runtime_values
    configs = get_config_filenames()

    # Load Configuration (Connectivity)
    with open(configs["rc"], "r", encoding="UTF-8") as rcf:
        rest_config = json.load(rcf)

    # Load Configuration (Standard Remedy Elements)
    with open(configs["sc"], "r", encoding="UTF-8") as scf:
        remedy_config = json.load(scf)

    # Load Configuration (Customer Specific Elements)
    with open(configs["cc"], "r", encoding="UTF-8") as ccf:
        customer_config = json.load(ccf)

    # Load Configuration (Runtime Values)
    with open(configs["rv"], "r", encoding="UTF-8") as rvf:
        runtime_values = json.load(rvf)


def save_config() -> None:
    """Save runtime Values to file"""
    configs = get_config_filenames()

    with open(configs["rv"], "w", encoding="UTF-8") as rvw:
        json.dump(runtime_values, rvw, indent=4)


def create_incident(session: RemedySession, incident_request: dict) -> None:
    """Create Remedy incident and modify status if required"""
    return_fields = ["Incident Number", "Request ID"]
    incident_data = incident_request.get("values", {})

    # logging.info(json.dumps(incident_request, indent=4))
    # Create the base incident
    _, return_data = session.create_entry(
        rest_config.get("remedyCreateForm", "HPD:IncidentInterface_Create"),
        incident_request,
        return_fields,
    )

    values = return_data.get("values", {})
    incident_number = values.get("Incident Number")
    incident_id = values.get("Request ID")
    logging.info(
        f"   +-- Incident {incident_number} created with status Assigned ({incident_id})"
    )
    if not incident_number:
        raise RemedyException("Failed to create incident")

    status = incident_data.get("Status", "")
    if status in ["In Progress", "Pending"]:
        update_incident_status(incident_number, session, status, incident_data)


def update_incident_status(
    incident_number: str, session: RemedySession, status: str, incident_data: dict
) -> None:
    """Update the status of the incident, also setting the stats reason
    if the status is set to Pending"""

    # Find the entry ID of the incident in the Incident Modify form
    remedy_query = f"""('Incident Number'="{incident_number}")"""
    response_records = session.query_form(
        form=rest_config.get("remedyModifyForm", "HPD:IncidentInterface"),
        query=remedy_query,
        fields=["Request ID"],
        limit=None,
    )

    entries = response_records.get("entries")
    if not isinstance(entries, list):
        raise TypeError("Expected a list of entries to be returned")

    entry = entries[0]
    entry_values = entry.get("values", {})
    request_id = entry_values.get("Request ID")
    logging.debug(f"Request ID: {request_id}")

    # Modify the incident to set status if ticket is "In Progress" or "Pending"
    values = {"Status": status}
    if status == "Pending":
        values["Status_Reason"] = incident_data.get("Status_Reason", "")

    update_body = {"values": values}
    session.modify_entry(
        rest_config.get("remedyModifyForm", "HPD:IncidentInterface"),
        update_body,
        request_id,
    )
    logging.info(f"   +-- Incident {incident_number} modified to status {status}")


def main():
    """Main routine to generate incidents with values randomly selected from the
    supplied configuration data (see config files)
    """

    load_config()
    remedy_url = rest_config.get("remedyApiUrl", "")
    remedy_user = rest_config.get("remedyUser", "")
    try:
        remedy_password = base64.b64decode(
            rest_config.get("remedyBase64Password", b"")
        ).decode("UTF-8")
    except (UnicodeDecodeError, binascii.Error):
        logging.error(
            "Couldn't decode password in config file. Please check it's a valid BASE64 string!"
        )
        sys.exit("Failed to read password from config")

    script_start_time = time.perf_counter()
    incidents_created = 0

    with RemedySession(remedy_url, remedy_user, remedy_password) as session:
        error_count = 0
        for _ in range(runtime_values.get("incidentsToCreate", 0)):
            incident_counter = runtime_values.get("nextIncidentNumber", 1)
            incident_request = generate_random_incident(incident_counter)
            incident_data = incident_request.get("values")
            if not incident_data:
                raise ValueError("Incident generation failed")
            company = incident_data.get("Company")
            logging.info(
                f" * Creating incident {incident_counter} for company {company}..."
            )
            try:
                logging.debug(json.dumps(incident_request, indent=4))
                create_incident(session, incident_request)
                runtime_values["nextIncidentNumber"] += 1
                incidents_created += 1
            except RemedyException as err:
                logging.error(f"Error: {err}")
                logging.error(traceback.format_exc())
                error_count += 1
            except Exception as err:
                logging.error(f"Error: {err}")
                logging.error(traceback.format_exc())
                error_count += 1

    script_end_time = time.perf_counter()
    script_runtime = script_end_time - script_start_time
    logging.info("=================================")
    logging.info(
        f"Created a total of {incidents_created} incidents in {script_runtime:.2f} seconds."
    )

    if error_count:
        logging.info(
            f"**** Total of {error_count} error{'s'[:error_count^1]} occurred during run ****"
        )

    save_config()


def generate_random_incident(incident_counter: int) -> Dict[str, Dict[str, str]]:
    """This function generates a data structure containing ticket data in a format
    that is ready to push to Remedy's REST API.

    The ticket data is mostly randomly chosen from values provided in the config
    files, though some is calculated on-the-fly.

    Inputs
        incident_counter: A number used to ensure each incident summary is unique.

    Outputs
        incident_request: Dictionary containing the generated incident structure
    """

    description = f"Test incident {incident_counter} created with Incident Blaster: {datetime.datetime.now()}"

    notes = f"These are the notes for test incident {incident_counter}."

    # Standard Remedy Elements
    status = random.choice(remedy_config.get("Statuses", []))

    # Customer-specific Elements
    company = random.choice(list(customer_config.keys()))
    company_config = customer_config.get(company, {})
    assignee_group = random.choice(list(company_config.get("Assignees", {}).keys()))
    support_details = company_config.get("Assignees", {}).get(assignee_group, {})

    # Generate a random time from (now + 60 seconds) to a defined maximum
    # target_epoch = int(time.time()) + random.randint(
    #     60, runtime_values.get("targetMaxDaysAhead", DEFAULT_TARGET_DAYS) * 24 * 60 * 60
    # )
    # target_human = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.localtime(target_epoch))

    values = {
        "Login_ID": random.choice(company_config.get("ContactLogonIDs", [])),
        "Description": description,
        "Detailed_Decription": notes,
        "Impact": random.choice(remedy_config.get("Impacts", [])),
        "Urgency": random.choice(remedy_config.get("Urgencies", [])),
        "Status": status,
        "Reported Source": random.choice(remedy_config.get("Sources", [])),
        "Service_Type": random.choice(remedy_config.get("IncidentTypes", [])),
        "Company": company,
        "z1D_Action": "CREATE",
        "ServiceCI": random.choice(company_config.get("Services", [])),
        "CI Name": random.choice(company_config.get("CIs", [])),
        "Assigned Support Company": support_details.get("Support Company"),
        "Assigned Support Organization": support_details.get("Support Organisation"),
        "Assigned Group": assignee_group,
        # "Estimated Resolution Date": target_human,
    }
    if status in ["In Progress", "Pending"]:
        values["Assignee"] = random.choice(support_details.get("Support Assignees", []))
    if status == "Pending":
        values["Status_Reason"] = random.choice(remedy_config.get("PendingReasons", []))

    logging.debug(f"Generated incident:\n{values}")
    return {"values": values}


if __name__ == "__main__":
    main()
