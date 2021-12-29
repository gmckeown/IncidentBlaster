import json
import logging
from json.decoder import JSONDecoder
from typing import Tuple

import requests

entry_path = '/arsys/v1/entry/'
login_path = '/jwt/login'
logout_path = '/jwt/logout'


class RemedyException(Exception):
    pass


class RemedyLoginException(RemedyException):
    pass


class RemedyLogoutException(RemedyException):
    pass


class RemedySession():
    ''' Define a Remedy session class to allow operations to be performed against the Remedy server '''

    def __init__(self, api_url: str, username: str, password: str):
        ''' Init function: log in to Remedy and retrieve an authentication token

            Inputs
                url: Remedy API base URL
                username: Remedy user with suitable form permissions
                password: Password for the Remedy user
        '''
        self.remedy_base_url = api_url
        logging.info(f"Logging in to Remedy as {username}")
        logging.info(f"========================{'=' * len(username)}")

        payload = {"username": username, "password": password}
        r = requests.post(f"{self.remedy_base_url}{login_path}", data=payload)

        if r.ok:
            self.auth_token = f"AR-JWT {r.text}"
        else:
            raise RemedyLoginException('Failed to login to Remedy server')

    def __enter__(self):
        ''' Context manager entry method '''
        return self

    def __exit__(self, type, value, traceback):
        ''' Context manager exit method '''
        if self.auth_token:
            self.logout()
        if type:
            logging.info(f"Exception type was specified! {type}")
        return True

    def logout(self):
        if self.auth_token:
            headers = {'Authorization': self.auth_token}
            r = requests.post(f"{self.remedy_base_url}{logout_path}", headers=headers)

            logging.info("=============================")
            if r.ok:
                logging.info("Successful logout from Remedy")
                self.auth_token = None
            else:
                raise RemedyLogoutException(
                    f'Failed to log out of Remedy server: ({r.status_code}) {r.text}"')
        else:
            raise RemedyLogoutException('No active login session; cannot logout.')

    def create_entry(self, form: str, field_values: dict, return_fields: list[str] | None) -> Tuple[str, dict]:
        ''' Method to create a Remedy form entry

            Inputs
                form: Name of the Remedy form in which to create an entry
                field_values: Structured Dict containing the entry field values
                return_fields: list of fields we'll ask Remedy to return from the created entry

            Outputs
                location: URL identifying the created entry
                json: Any JSON returned by Remedy
        '''
        if not self.auth_token:
            raise RemedyException('Unable to create entry without a valid login session')

        target_url = f"{self.remedy_base_url}{entry_path}{form}"
        headers = {'Authorization': self.auth_token}
        if return_fields:
            fields = ",".join(return_fields)
            params = {'fields': f'values({fields})'}
        else:
            params = None

        r = requests.post(target_url, json=json.dumps(field_values),
                          headers=headers, params=params)

        if r.ok:
            location = r.headers.get('Location') or ""
            return location, r.json()
        else:
            raise RemedyException(f'Failed to create entry: {r.text}')

    def modify_entry(self, form: str, field_values: dict, entry_id: str) -> bool:
        ''' Function to modify fields on an existing Remedy incident.

            Inputs
                field_values: Structured Dict containing the entry field values to modify
                request_id: Request ID identifying the incident in the interface form
        '''

        if not self.auth_token:
            raise RemedyException('Unable to modify entry without a valid login session')

        logging.debug(f"Going to modify incident ref: {entry_id}")
        logging.debug(field_values)
        target_url = f"{self.remedy_base_url}{entry_path}{form}/{entry_id}"
        logging.debug(f"URL: {target_url}")

        headers = {'Authorization': self.auth_token}
        r = requests.put(target_url, json=json.dumps(field_values), headers=headers)
        if r.ok:
            logging.debug(f"Incident modified: {target_url}")
            return True
        else:
            logging.error(f"Error modifying incident: {r.text}")
            return False

    def get_entry(self, form: str, query: str, return_fields: list[str] | None) -> dict:
        ''' Retrieves entries on a form based on a provided search qualification

            Inputs
                form: Remedy form name
                query: Remedy query to identify the entry/entries to retrieve
                return_fields: list of fields we'll ask Remedy to return from the entry/entries

            Outputs
                json: JSON object containing the returned entries
        '''

        if not self.auth_token:
            raise RemedyException('Unable to get entry without a valid login session')

        target_url = f"{self.remedy_base_url}{entry_path}{form}"
        logging.debug(f"Target URL: {target_url}")
        headers = {'Authorization': self.auth_token}
        params = {'q': query}
        if return_fields:
            fields = ",".join(return_fields)
            params['fields'] = f'values({fields})'
        r = requests.get(target_url, headers=headers, params=params)

        if r.ok:
            return r.json()
        else:
            raise RemedyException(f"Error getting entry: {r.text}")
