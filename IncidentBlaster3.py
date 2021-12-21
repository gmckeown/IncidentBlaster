#!/usr/bin/python
# Author: Gordon Mckeown - gordon.mckeown@gmail.com
#
# BE CAREFUL! Check configuration carefully before running this script; many incidents can be created in a short space of time!
# Note: this uses the Urllib module rather than Requests so that it can work in environments with only the base set of Python modules.

import base64
import datetime
import json
import logging
import random
import sys
import time
import traceback
from pathlib import Path

from integration.remedy_rest import *

DEBUG_FLAG = False

log_level = logging.DEBUG if DEBUG_FLAG else logging.INFO
logging.basicConfig(stream=sys.stdout, level=log_level)

config_folder = Path(sys.path[0]) / 'config'
rc_file = config_folder / 'RestConfig.json'
sc_file = config_folder / 'StandardConfig.json'
cc_file = config_folder / 'CustomerConfig.json'
rv_file = config_folder / 'RuntimeValues.json'

# Load Configuration (Connectivity)
with open(rc_file) as rc:
    rest_config = json.load(rc)

# Load Configuration (Standard Remedy Elements)
with open(sc_file) as sc:
    remedy_config = json.load(sc)

# Load Configuration (Customer Specific Elements)
with open(cc_file) as cc:
    customer_config = json.load(cc)

# Load Configuration (Runtime Values)
with open(rv_file) as rv:
    runtime_values = json.load(rv)


def main():
    ''' Main routine to generate incidents with values randomly selected from the
        supplied configuration data (see config files)
    '''
    remedy_url = rest_config.get('remedyApiUrl')
    remedy_user = rest_config.get('remedy_user')
    remedy_password = base64.b64decode(
        rest_config.get('remedyBase64Password')).decode('UTF-8')

    auth_token = login_to_remedy(remedy_url, remedy_user, remedy_password)
    if auth_token:
        error_count = 0
        for _ in range(runtime_values.get('incidentsToCreate')):
            incident_counter = runtime_values.get('nextIncidentNumber')
            incident_request = create_random_incident(incident_counter)
            incident_data = incident_request.get('values')
            if incident_data:
                company = incident_data.get('Company')
                logging.info(" * Creating incident {} for company {}...".format(
                    incident_counter, company))
                try:
                    json_body = json.dumps(incident_request, indent=4)
                    logging.debug(json_body)
                    incident_number, incident_id = create_remedy_incident(
                        remedy_url, auth_token, json_body)
                    logging.info(
                        "   +-- Incident {} created with status Assigned ({})".format(incident_number, incident_id))
                    status = incident_data.get('Status')
                    if (status in ['In Progress', 'Pending']):
                        values = {"Status": status}
                        if (status == 'Pending'):
                            values['Status_Reason'] = incident_data.get(
                                'Status_Reason')

                        update_body = {"values": values}
                        json_update = json.dumps(update_body, indent=4)
                        result = modify_remedy_incident(remedy_url,
                                                        auth_token, json_update, incident_id)
                        logging.info(
                            "   +-- Incident {} modified to status {}".format(incident_number, status))

                    runtime_values['nextIncidentNumber'] += 1
                except Exception as err:
                    logging.error("Error: {}".format(err))
                    logging.error(traceback.format_exc())
                    error_count += 1
            else:
                logging.error(
                    'Incident creation has failed -- no values found')

        if logout_from_remedy(remedy_url, auth_token):
            logging.debug("Logged out from Remedy successfully")
        else:
            logging.error("Failed to logout from Remedy")

        if (error_count > 0):
            errorText = "error" if error_count == 1 else "errors"
            logging.info(
                "**** Total of {} {} occurred during execution ****".format(error_count, errorText))

        # Save runtime Values to file
        with open(rv_file, 'w') as rv:
            json.dump(runtime_values, rv, indent=4)

    else:
        logging.critical("Failed to login to Remedy.")


def create_random_incident(incident_counter):
    ''' This function generates a data structure containing ticket data in a format
        that is ready to push to Remedy's REST API.

        The ticket data is mostly randomly chosen from values provided in the config
        files, though some is calculated on-the-fly.

        Inputs
            incident_counter: A number used to ensure each incident summary is unique.

        Outputs
            incident_request: Dictionary containing the generated incident structure
    '''

    description = "Test incident {} created with Incident Blaster: {}".format(
        incident_counter, datetime.datetime.today())

    # Standard Remedy Elements
    status = random.choice(remedy_config.get('Statuses'))

    # Customer-specific Elements
    company = random.choice(list(customer_config.keys()))
    company_config = customer_config.get(company)
    assignee_group = random.choice(
        list(company_config.get('Assignees').keys()))
    support_details = company_config.get('Assignees').get(assignee_group)

    # Generate a random time from (now + 60 seconds) to a defined maximum
    target_epoch = int(time.time()) + \
        random.randint(60, runtime_values.get(
            'targetMaxDaysAhead') * 24 * 60 * 60)
    target_human = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.localtime(target_epoch))

    values = {
        'Login_ID': random.choice(company_config.get('ContactLogonIDs')),
        'Description': description,
        'Impact': random.choice(remedy_config.get('Impacts')),
        'Urgency': random.choice(remedy_config.get('Urgencies')),
        'Status': status,
        'Reported Source': random.choice(remedy_config.get('Sources')),
        'Service_Type': random.choice(remedy_config.get('IncidentTypes')),
        'Company': company,
        'z1D_Action': "CREATE",
        'ServiceCI': random.choice(company_config.get('Services')),
        'CI Name': random.choice(company_config.get('CIs')),
        'Assigned Support Company': support_details.get('Support Company'),
        'Assigned Support Organization': support_details.get('Support Organisation'),
        'Assigned Group': assignee_group,
        'Estimated Resolution Date': target_human
    }
    if (status in ['In Progress', 'Pending']):
        values['Assignee'] = random.choice(
            support_details.get('Support Assignees'))
    if (status == 'Pending'):
        values['Status_Reason'] = random.choice(
            remedy_config.get('PendingReasons'))

    return {'values': values}


if __name__ == "__main__":
    main()
