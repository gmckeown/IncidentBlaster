import logging
import requests

remedyCreateForm = 'HPD:IncidentInterface_Create'
remedyModifyForm = 'HPD:IncidentInterface'
entryPath = '/arsys/v1/entry/'
loginPath = '/jwt/login'
logoutPath = '/jwt/logout'


def loginToRemedy(url, username, password):
    ''' Function to log in to Remedy and retrieve an authentication token

        Inputs
            url: Remedy API base URL
            username: Remedy user with suitable form permissions
            password: Password for the Remedy user
        Outputs
            authToken: The "AR-JWT xxxx" token used to authorise further requests
    '''

    logging.info(f"Logging in to Remedy as {username}")
    logging.info(f"========================{'=' * len(username)}")

    loginUrl = f"{url}{loginPath}"
    payload = {"username": username, "password": password}

    r = requests.post(loginUrl, data=payload)
    return f"AR-JWT {r.text}" if (r.status_code == 200) else ""


def logoutFromRemedy(url, token):
    ''' Function to logout from Remedy, invalidating the given token

        Inputs
            authToken: Remedy AR-JWT authentication token
    '''

    logoutUrl = f"{url}{logoutPath}"
    headers = {'Authorization': token}
    r = requests.post(logoutUrl, headers=headers)

    logging.info("=============================")
    if (200 <= r.status_code <= 299):
        logging.info("Successful logout from Remedy")
    else:
        logging.error(
            "Failed to logout from Remedy: ({r.status_code}) {r.text}")


def getRemedyRequestId(url, token, incidentNumber):
    ''' Retrieves the Request ID from the incident interface form for a given
        incident number. This ID is required when modifying an incident record.

        Inputs
            authToken: A current Remedy AR-JWT authentication token
            incidentNumber: The Remedy incident number (INCnnnnn...)

        Outputs
            requestId: The interface form request ID (INCnnnn...|INCnnnn...)
    '''

    requestId = ""
    remedyQuery = f"""('Incident Number'="{incidentNumber}")"""
    targetUrl = f"{url}{entryPath}{remedyModifyForm}"
    logging.debug(f"Target URL: {targetUrl}")
    headers = {'Authorization': token}
    # r.add_header('Content-Type', 'application/json')
    parameters = {'q': remedyQuery}
    r = requests.get(targetUrl, headers=headers, params=parameters)

    if (r.status_code == 200):
        responseJson = r.json()
        responseRecord = responseJson.get('entries')[0]
        requestId = responseRecord.get('values').get('Request ID')
        logging.debug(f"Request ID: {requestId}")
    else:
        logging.error(f"Error getting request ID: {r.text}")

    return requestId


def modifyRemedyIncident(url, token, jsonBody, requestId):
    ''' Function to modify fields on an existing Remedy incident.

        Inputs
            authToken: A current Remedy AR-JWT authentication token
            jsonBody: JSON string containing the new field values
            requestId: Request ID identifying the incident in the interface form
    '''

    logging.debug(f"Going to modify incident ref: {requestId}")
    logging.debug(jsonBody)
    targetUrl = f"{url}{entryPath}{remedyModifyForm}/{requestId}"
    logging.debug(f"URL: {targetUrl}")

    headers = {'Authorization': token}
    r = requests.put(targetUrl, json=jsonBody, headers=headers)
    if (200 <= r.status_code <= 299):
        logging.debug(f"Incident modified: {targetUrl}")
    else:
        logging.error(f"Error modifying incident: {r.text}")


def createRemedyIncident(url, token, jsonBody):
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
    targetUrl = f"{url}{entryPath}{remedyCreateForm}"
    headers = {'Authorization': token}
    returnFields = ",".join(('Incident Number', 'Request ID'))
    params = {'fields': f'values({returnFields})'}
    r = requests.post(targetUrl, json=jsonBody, headers=headers, params=params)

    if (r.status_code == 201):
        incidentUrl = r.headers.get('Location')
        responseJson = r.json()
        incidentNumber = responseJson.get('values').get('Incident Number')
        logging.debug(f"Incident {incidentNumber} created: {incidentUrl}")

        requestId = getRemedyRequestId(url, token, incidentNumber)
    else:
        logging.error(f"Error creating incident: {r.text}")

    return incidentNumber, requestId
