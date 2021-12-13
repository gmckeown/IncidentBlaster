#!/usr/bin/python
# Author: Gordon Mckeown - gordon.mckeown@gmail.com
#
# BE CAREFUL! Check configuration carefully before running this script; many incidents can be created in a short space of time!
# Note: this uses the Urllib module rather than Requests so that it can work in environments with only the base set of Python modules.

import json
import random
import datetime
import urllib
import urllib2
import time
import base64
import traceback
import sys
import logging
import os.path

DEBUG_FLAG = False

logLevel = logging.DEBUG if DEBUG_FLAG else logging.INFO
logging.basicConfig(stream=sys.stdout, level=logLevel)

configFolder = os.path.join(sys.path[0], 'config')
rcFile = os.path.join(configFolder, 'RestConfig.json')
scFile = os.path.join(configFolder, 'StandardConfig.json')
ccFile = os.path.join(configFolder, 'CustomerConfig.json')
rvFile = os.path.join(configFolder, 'RuntimeValues.json')

# Load Configuration (Connectivity)
with open(rcFile) as rc:
    restConfig = json.load(rc)
restConfig['remedyPassword'] = base64.b64decode(
    restConfig.get('remedyBase64Password'))

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

    errorCount = 0
    authToken = loginToRemedy()
    if authToken:
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
                    authToken, jsonBody)
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
                    result = modifyRemedyIncident(
                        authToken, jsonUpdate, incidentId)
                    logging.info(
                        "   +-- Incident {} modified to status {}".format(incidentNumber, status))

                runtimeValues['nextIncidentNumber'] += 1
            except Exception as err:
                logging.error("Error: " + str(err))
                logging.error(traceback.format_exc())
                errorCount += 1

        logoutFromRemedy(authToken)
        if (errorCount > 0):
            logging.info(
                "**** Total of {} errors occurred during execution ****".format(errorCount))

        # Save runtime Values to file
        with open(rvFile, 'w') as rv:
            json.dump(runtimeValues, rv, indent=4)

    else:
        logging.critical("Failed to login to Remedy.")


class PutRequest(urllib2.Request):
    ''' This is a hack required to allow us to perform HTTP PUT using urllib2.
    '''

    def get_method(self, *args, **kwargs):
        return 'PUT'


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

    incidentRequest = {}
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

    incidentRequest['values'] = values
    return(incidentRequest)


def loginToRemedy():
    ''' Function to log in to Remedy and retrieve an authentication token

        Outputs
            authToken: The "AR-JWT xxxx" token used to authorise further requests
    '''

    remedyUser = restConfig.get('remedyUser')
    logging.info("Logging in to Remedy as {}".format(remedyUser))
    logging.info("========================" + ("=" * len(remedyUser)))

    authToken = ""
    loginUrl = restConfig.get('remedyApiUrl') + "/jwt/login"
    payload = urllib.urlencode(
        {"username": remedyUser, "password": restConfig.get('remedyPassword')})

    r = urllib2.Request(loginUrl, payload)
    r.add_header('Content-Type', 'application/x-www-form-urlencoded')
    response = urllib2.urlopen(r)
    if (response.getcode() == 200):
        authToken = "AR-JWT " + response.read()
    return authToken


def logoutFromRemedy(authToken):
    ''' Function to logout from Remedy, invalidating the given token

        Inputs
            authToken: Remedy AR-JWT authentication token
    '''

    logoutUrl = restConfig.get('remedyApiUrl') + "/jwt/logout"
    # Dummy payload required so that urllib2 performs a POST request (defaults to GET with no payload)
    dummyPayload = "x"
    r = urllib2.Request(logoutUrl, dummyPayload)
    r.add_header('Authorization', authToken)
    response = urllib2.urlopen(r)
    logging.info("=============================")
    if (200 <= response.getcode() <= 299):
        logging.info("Successful logout from Remedy")
    else:
        logging.error("Failed to logout from Remedy: ({}) {}".format(
            response.getcode(), response.read()))


def getRemedyIncidentNumber(authToken, targetUrl):
    ''' Function to retrieve the incident number for the ticket created by
        HPD:IncidentInterface_Create. This is required because the incident
        interface form returns a record ID rather than the created incident number.

        Inputs
            authToken: A current Remedy AR-JWT authentication token
            targetUrl: The URL representing an interface form record

        Outputs
            incidentNumber: Remedy incident number pulled from the interface form
    '''

    incidentNumber = ""
    r = urllib2.Request(targetUrl)
    r.add_header('Content-Type', 'application/json')
    r.add_header('Authorization', authToken)
    response = urllib2.urlopen(r)
    if (response.getcode() == 200):
        responseBody = response.read()
        responseJson = json.loads(responseBody)
        incidentNumber = responseJson.get('values').get('Incident Number')
        logging.debug("Incident Number: {}".format(incidentNumber))
    else:
        logging.error(
            "Error getting incident number: {}".format(response.info()))
    return incidentNumber


def getRemedyRequestId(authToken, incidentNumber):
    ''' Retrieves the Request ID from the incident interface form for a given
        incident number. This ID is required when modifying an incident record.

        Inputs
            authToken: A current Remedy AR-JWT authentication token
            incidentNumber: The Remedy incident number (INCnnnnn...)

        Outputs
            requestId: The interface form request ID (INCnnnn...|INCnnnn...)
    '''

    requestId = ""
    remedyQuery = "('Incident Number'=\"" + incidentNumber + "\")"
    parameters = {'q': remedyQuery}
    targetUrl = restConfig.get('remedyApiUrl') + "/arsys/v1/entry/" + \
        restConfig.get('remedyModifyForm') + "?" + urllib.urlencode(parameters)
    logging.debug("Target URL: {}".format(targetUrl))
    r = urllib2.Request(targetUrl)
    r.add_header('Content-Type', 'application/json')
    r.add_header('Authorization', authToken)
    response = urllib2.urlopen(r)
    if (response.getcode() == 200):
        responseBody = response.read()
        responseJson = json.loads(responseBody)
        responseRecord = responseJson.get('entries')[0]
        requestId = responseRecord.get('values').get('Request ID')
        logging.debug("Request ID: {}".format(requestId))
    else:
        logging.error("Error getting request ID: {}".format(response.info()))

    return requestId


def modifyRemedyIncident(authToken, jsonBody, requestId):
    ''' Function to modify fields on an existing Remedy incident.

        Inputs
            authToken: A current Remedy AR-JWT authentication token
            jsonBody: JSON string containing the new field values
            requestId: Request ID identifying the incident in the interface form
    '''

    logging.debug("Going to modify incident ref: {}".format(requestId))
    logging.debug(jsonBody)
    targetUrl = restConfig.get('remedyApiUrl') + "/arsys/v1/entry/" + \
        restConfig.get('remedyModifyForm') + "/" + requestId
    logging.debug("URL: " + targetUrl)
    r = PutRequest(targetUrl, jsonBody, )
    r.add_header('Content-Type', 'application/json')
    r.add_header('Authorization', authToken)
    response = urllib2.urlopen(r)
    if (200 <= response.getcode() <= 299):
        logging.debug("Incident modified: " + targetUrl)
    else:
        logging.error("Error modifying incident: " + str(response.read()))


def createRemedyIncident(authToken, jsonBody):
    ''' Function to create a Remedy incident

        Inputs
            authToken: A current Remedy AR-JWT authentication token
            jsonBody: JSON string containing the incident field values

        Outputs
            incidentNumber: The Remedy incident number (INCnnnnn...)
            requestId: Request ID identifying the incident in the interface form
    '''

    requestId = ""
    incidentNumber = ""
    targetUrl = restConfig.get('remedyApiUrl') + \
        "/arsys/v1/entry/" + restConfig.get('remedyCreateForm')
    r = urllib2.Request(targetUrl, jsonBody)
    r.add_header('Content-Type', 'application/json')
    r.add_header('Authorization', authToken)
    response = urllib2.urlopen(r)
    if (response.getcode() == 201):
        headers = response.info()
        incidentUrl = headers.getheader("Location")
        logging.debug("Incident created: " + incidentUrl)
        incidentNumber = getRemedyIncidentNumber(authToken, incidentUrl)
        requestId = getRemedyRequestId(authToken, incidentNumber)
    else:
        logging.error("Error creating incident: " + response.info())

    return incidentNumber, requestId


if __name__ == "__main__":
    main()
