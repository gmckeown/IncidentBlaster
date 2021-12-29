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

from integration.remedy_rest import RemedySession

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

print(rest_config)


def main():
    ''' Main routine to generate incidents with values randomly selected from the
        supplied configuration data (see config files)
    '''
    remedy_create_form = rest_config.get('remedyCreateForm')
    remedy_modify_form = rest_config.get('remedyModifyForm')

    remedy_url = rest_config.get('remedyApiUrl')
    remedy_user = rest_config.get('remedyUser')
    remedy_password = base64.b64decode(
        rest_config.get('remedyBase64Password')).decode('UTF-8')

    logging.info(f"Checking values: {remedy_user=} {remedy_password=}")

    with RemedySession(remedy_url, remedy_user, remedy_password) as session:
        error_count = 0
        for _ in range(runtime_values.get('incidentsToCreate')):
            incident_counter = runtime_values.get('nextIncidentNumber')
            incident_request = generate_random_incident(incident_counter)
            incident_data = incident_request.get('values')
            if incident_data:
                company = incident_data.get('Company')
                logging.info(" * Creating incident {} for company {}...".format(
                    incident_counter, company))
                try:
                    return_fields = ['Incident Number', 'Request ID']

                    # Create the base incident
                    incident_location, return_data = session.create_entry(
                        remedy_create_form, incident_request, return_fields)

                    values = return_data.get('values', {})
                    incident_number = values.get('Incident Number')
                    incident_id = values.get('Request ID')
                    logging.info(
                        "   +-- Incident {} created with status Assigned ({})".format(incident_number, incident_id))
                    if incident_number:
                        status = incident_data.get('Status')
                        if status in ['In Progress', 'Pending']:
                            # Find the entry ID of the incident in the Incident Modify form
                            remedy_query = f"""('Incident Number'="{incident_number}")"""
                            remedy_fields = ['Request ID']
                            response_records = session.get_entry(
                                remedy_modify_form, remedy_query, remedy_fields)

                            entries = response_records.get('entries')
                            if isinstance(entries, list):
                                entry = entries[0]
                                entry_values = entry.get('values', {})
                                request_id = entry_values.get('Request ID')
                                logging.debug(f"Request ID: {request_id}")
                            else:
                                raise TypeError("Expected a list of entries to be returned")

                            # Modify the incident to set status if ticket is "In Progress" or "Pending"
                            values = {"Status": status}
                            if status == 'Pending':
                                values['Status_Reason'] = incident_data.get(
                                    'Status_Reason')

                            update_body = {"values": values}
                            result = session.modify_entry(
                                remedy_modify_form, update_body, incident_number)
                            logging.info(
                                "   +-- Incident {} modified to status {}".format(incident_number, status))
                        else:
                            logging.error('Unable to retrieve incident number from create call')

                    runtime_values['nextIncidentNumber'] += 1
                except Exception as err:
                    logging.error("Error: {}".format(err))
                    logging.error(traceback.format_exc())
                    error_count += 1
            else:
                logging.error(
                    'Incident creation has failed -- no values found')

    if (error_count > 0):
        errorText = "error" if error_count == 1 else "errors"
        logging.info(
            "**** Total of {} {} occurred during execution ****".format(error_count, errorText))

    # Save runtime Values to file
    with open(rv_file, 'w') as rv:
        json.dump(runtime_values, rv, indent=4)


def generate_random_incident(incident_counter):
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
