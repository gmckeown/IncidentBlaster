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

logLevel = logging.DEBUG if DEBUG_FLAG else logging.INFO
logging.basicConfig(stream=sys.stdout, level=logLevel)

configFolder = Path(sys.path[0]) / 'config'
rcFile = configFolder / 'RestConfig.json'
scFile = configFolder / 'StandardConfig.json'
ccFile = configFolder / 'CustomerConfig.json'
rvFile = configFolder / 'RuntimeValues.json'

# Load Configuration (Connectivity)
with open(rcFile) as rc:
    restConfig = json.load(rc)

# Load Configuration (Standard Remedy Elements)
with open(scFile) as sc:
    remedyConfig = json.load(sc)

# Load Configuration (Customer Specific Elements)
with open(ccFile) as cc:
    customerConfig = json.load(cc)

# Load Configuration (Runtime Values)
with open(rvFile) as rv:
    runtimeValues = json.load(rv)


def main():
    ''' Main routine to generate incidents with values randomly selected from the
        supplied configuration data (see config files)
    '''
    remedyUrl = restConfig.get('remedyApiUrl')
    remedyUser = restConfig.get('remedyUser')
    remedyPassword = base64.b64decode(restConfig.get('remedyBase64Password'))

    authToken = loginToRemedy(remedyUrl, remedyUser, remedyPassword)
    if authToken:
        errorCount = 0
        for _ in range(runtimeValues.get('incidentsToCreate')):
            incidentRequest = createRandomIncident(
                runtimeValues.get('nextIncidentNumber'))
            jsonBody = json.dumps(incidentRequest, indent=4)
            incidentData = incidentRequest.get('values')
            logging.info(" * Creating incident {} for company {}...".format(
                runtimeValues.get('nextIncidentNumber'), incidentData.get('Company')))
            logging.debug(jsonBody)
            try:
                incidentNumber, incidentId = createRemedyIncident(
                    remedyUrl, authToken, jsonBody)
                logging.info(
                    "   +-- Incident {} created with status Assigned ({})".format(incidentNumber, incidentId))
                status = incidentData.get('Status')
                if (status in ['In Progress', 'Pending']):
                    values = {"Status": status}
                    if (status == 'Pending'):
                        values['Status_Reason'] = incidentData.get(
                            'Status_Reason')

                    updateBody = {"values": values}
                    jsonUpdate = json.dumps(updateBody, indent=4)
                    result = modifyRemedyIncident(remedyUrl,
                                                  authToken, jsonUpdate, incidentId)
                    logging.info(
                        "   +-- Incident {} modified to status {}".format(incidentNumber, status))

                runtimeValues['nextIncidentNumber'] += 1
            except Exception as err:
                logging.error("Error: {}".format(err))
                logging.error(traceback.format_exc())
                errorCount += 1

        logoutFromRemedy(authToken)
        if (errorCount > 0):
            errorText = "error" if errorCount == 1 else "errors"
            logging.info(
                "**** Total of {} {} occurred during execution ****".format(errorCount, errorText))

        # Save runtime Values to file
        with open(rvFile, 'w') as rv:
            json.dump(runtimeValues, rv, indent=4)

    else:
        logging.critical("Failed to login to Remedy.")


def createRandomIncident(incidentCounter):
    ''' This function generates a data structure containing ticket data in a format
        that is ready to push to Remedy's REST API.

        The ticket data is mostly randomly chosen from values provided in the config
        files, though some is calculated on-the-fly.

        Inputs
            incidentCounter: A number used to ensure each incident summary is unique.

        Outputs
            incidentRequest: Dictionary containing the generated incident structure
    '''

    description = "Test incident {} created with Incident Blaster: {}".format(
        incidentCounter, datetime.datetime.today())

    # Standard Remedy Elements
    status = random.choice(remedyConfig.get('Statuses'))

    # Customer-specific Elements
    company = random.choice(list(customerConfig.keys()))
    companyConfig = customerConfig.get(company)
    assigneeGroup = random.choice(list(companyConfig.get('Assignees').keys()))
    supportDetails = companyConfig.get('Assignees').get(assigneeGroup)

    # Generate a random time from (now + 60 seconds) to a defined maximum
    target_epoch = int(time.time()) + \
        random.randint(60, runtimeValues.get(
            'targetMaxDaysAhead') * 24 * 60 * 60)
    target_human = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.localtime(target_epoch))

    values = {
        'Login_ID': random.choice(companyConfig.get('ContactLogonIDs')),
        'Description': description,
        'Impact': random.choice(remedyConfig.get('Impacts')),
        'Urgency': random.choice(remedyConfig.get('Urgencies')),
        'Status': status,
        'Reported Source': random.choice(remedyConfig.get('Sources')),
        'Service_Type': random.choice(remedyConfig.get('IncidentTypes')),
        'Company': company,
        'z1D_Action': "CREATE",
        'ServiceCI': random.choice(companyConfig.get('Services')),
        'CI Name': random.choice(companyConfig.get('CIs')),
        'Assigned Support Company': supportDetails.get('Support Company'),
        'Assigned Support Organization': supportDetails.get('Support Organisation'),
        'Assigned Group': assigneeGroup,
        'Estimated Resolution Date': target_human
    }
    if (status in ['In Progress', 'Pending']):
        values['Assignee'] = random.choice(
            supportDetails.get('Support Assignees'))
    if (status == 'Pending'):
        values['Status_Reason'] = random.choice(
            remedyConfig.get('PendingReasons'))

    return {'values': values}


if __name__ == "__main__":
    main()
