import logging
import requests
from typing import Tuple

remedy_create_form = 'HPD:IncidentInterface_Create'
remedy_modify_form = 'HPD:IncidentInterface'
entry_path = '/arsys/v1/entry/'
login_path = '/jwt/login'
logout_path = '/jwt/logout'


def login_to_remedy(url: str, username: str, password: str) -> str:
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

    login_url = f"{url}{login_path}"
    payload = {"username": username, "password": password}

    r = requests.post(login_url, data=payload)
    return f"AR-JWT {r.text}" if (r.status_code == 200) else ""


def logout_from_remedy(url: str, token: str) -> bool:
    ''' Function to logout from Remedy, invalidating the given token

        Inputs
            authToken: Remedy AR-JWT authentication token
    '''

    logout_url = f"{url}{logout_path}"
    headers = {'Authorization': token}
    r = requests.post(logout_url, headers=headers)

    logging.info("=============================")
    if (200 <= r.status_code <= 299):
        logging.info("Successful logout from Remedy")
        return True
    else:
        logging.error(
            "Failed to logout from Remedy: ({r.status_code}) {r.text}")
        return False


def get_remedy_request_id(url: str, token: str, incident_number: str) -> str:
    ''' Retrieves the Request ID from the incident interface form for a given
        incident number. This ID is required when modifying an incident record.

        Inputs
            authToken: A current Remedy AR-JWT authentication token
            incident_number: The Remedy incident number (INCnnnnn...)

        Outputs
            request_id: The interface form request ID (INCnnnn...|INCnnnn...)
    '''

    request_id = ""
    remedy_query = f"""('Incident Number'="{incident_number}")"""
    target_url = f"{url}{entry_path}{remedy_modify_form}"
    logging.debug(f"Target URL: {target_url}")
    headers = {'Authorization': token}
    # r.add_header('Content-Type', 'application/json')
    parameters = {'q': remedy_query}
    r = requests.get(target_url, headers=headers, params=parameters)

    if (r.status_code == 200):
        response_json = r.json()
        response_record = response_json.get('entries')[0]
        request_id = response_record.get('values').get('Request ID')
        logging.debug(f"Request ID: {request_id}")
    else:
        logging.error(f"Error getting request ID: {r.text}")

    return request_id


def modify_remedy_incident(url: str, token: str, json_body: str, request_id: str) -> bool:
    ''' Function to modify fields on an existing Remedy incident.

        Inputs
            authToken: A current Remedy AR-JWT authentication token
            json_body: JSON string containing the new field values
            request_id: Request ID identifying the incident in the interface form
    '''

    logging.debug(f"Going to modify incident ref: {request_id}")
    logging.debug(json_body)
    target_url = f"{url}{entry_path}{remedy_modify_form}/{request_id}"
    logging.debug(f"URL: {target_url}")

    headers = {'Authorization': token}
    r = requests.put(target_url, json=json_body, headers=headers)
    if (200 <= r.status_code <= 299):
        logging.debug(f"Incident modified: {target_url}")
        return True
    else:
        logging.error(f"Error modifying incident: {r.text}")
        return False


def create_remedy_incident(url: str, token: str, json_body: str) -> Tuple[str, str]:
    ''' Function to create a Remedy incident

        Inputs
            authToken: A current Remedy AR-JWT authentication token
            json_body: JSON string containing the incident field values

        Outputs
            incident_number: The Remedy incident number (INCnnnnn...)
            request_id: Request ID identifying the incident in the interface form
    '''

    request_id = ""
    incident_number = ""
    target_url = f"{url}{entry_path}{remedy_create_form}"
    headers = {'Authorization': token}
    return_fields = ",".join(('Incident Number', 'Request ID'))
    params = {'fields': f'values({return_fields})'}
    r = requests.post(target_url, json=json_body,
                      headers=headers, params=params)

    if (r.status_code == 201):
        incident_url = r.headers.get('Location')
        response_json = r.json()
        incident_number = response_json.get('values').get('Incident Number')
        logging.debug(f"Incident {incident_number} created: {incident_url}")

        request_id = get_remedy_request_id(url, token, incident_number)
    else:
        logging.error(f"Error creating incident: {r.text}")

    return incident_number, request_id
