import json
import logging
from json.decoder import JSONDecoder
from typing import Tuple

import requests

ENTRY_PATH = "/arsys/v1/entry/"
LOGIN_PATH = "/jwt/login"
LOGOUT_PATH = "/jwt/logout"


class RemedyException(Exception):
    """General exception to cover any Remedy-related errors"""


class RemedyLoginException(RemedyException):
    """Exception to specifically indicate a problem logging in to Remedy"""


class RemedyLogoutException(RemedyException):
    """Exception to specifically indicate a problem loogging out of Remedy"""


class RemedySession:
    """Define a Remedy session class to allow operations to be performed
    against the Remedy server"""

    def __init__(self, api_url: str, username: str, password: str):
        """Init function: log in to Remedy and retrieve an authentication token

        Inputs
            url: Remedy API base URL
            username: Remedy user with suitable form permissions
            password: Password for the Remedy user
        """
        self.remedy_base_url = api_url
        logging.info(f"Logging in to Remedy as {username}")
        logging.info(f"========================{'=' * len(username)}")

        payload = {"username": username, "password": password}
        response = requests.post(f"{self.remedy_base_url}{LOGIN_PATH}", data=payload)

        if not response.ok:
            raise RemedyLoginException("Failed to login to Remedy server")

        self.auth_token = f"AR-JWT {response.text}"

    def __enter__(self):
        """Context manager entry method"""
        return self

    def __exit__(self, type, value, traceback):
        """Context manager exit method"""
        if self.auth_token:
            self.logout()
        if type:
            logging.info(f"Exception type was specified! {type}")
        return True

    def logout(self):
        """Request destruction of an active login token"""
        if not self.auth_token:
            raise RemedyLogoutException("No active login session; cannot logout.")
        headers = {"Authorization": self.auth_token}
        response = requests.post(
            f"{self.remedy_base_url}{LOGOUT_PATH}", headers=headers
        )

        logging.info("=============================")

        if not response.ok:
            raise RemedyLogoutException(
                f'Failed to log out of Remedy server: ({response.status_code}) {response.text}"'
            )
        logging.info("Successful logout from Remedy")
        self.auth_token = None

    def create_entry(
        self, form: str, field_values: dict, return_fields: list[str] | None
    ) -> Tuple[str, dict]:
        """Method to create a Remedy form entry

        Inputs
            form: Name of the Remedy form in which to create an entry
            field_values: Structured Dict containing the entry field values
            return_fields: list of fields we'll ask Remedy to return from the created entry

        Outputs
            location: URL identifying the created entry
            json: Any JSON returned by Remedy
        """
        if not self.auth_token:
            raise RemedyException(
                "Unable to create entry without a valid login session"
            )

        target_url = f"{self.remedy_base_url}{ENTRY_PATH}{form}"
        headers = {"Authorization": self.auth_token}
        if return_fields:
            fields = ",".join(return_fields)
            params = {"fields": f"values({fields})"}
        else:
            params = None

        r = requests.post(
            target_url, json=json.dumps(field_values), headers=headers, params=params
        )

        if not r.ok:
            raise RemedyException(f"Failed to create entry: {r.text}")

        location = r.headers.get("Location") or ""
        return location, r.json()

    def modify_entry(self, form: str, field_values: dict, entry_id: str) -> bool:
        """Function to modify fields on an existing Remedy incident.

        Inputs
            field_values: Structured Dict containing the entry field values to modify
            request_id: Request ID identifying the incident in the interface form
        """

        if not self.auth_token:
            raise RemedyException(
                "Unable to modify entry without a valid login session"
            )

        logging.debug(f"Going to modify incident ref: {entry_id}")
        logging.debug(field_values)
        target_url = f"{self.remedy_base_url}{ENTRY_PATH}{form}/{entry_id}"
        logging.debug(f"URL: {target_url}")

        headers = {"Authorization": self.auth_token}
        r = requests.put(target_url, json=json.dumps(field_values), headers=headers)
        if r.ok:
            logging.debug(f"Incident modified: {target_url}")
            return True
        else:
            logging.error(f"Error modifying incident: {r.text}")
            return False

    def get_entry(self, form: str, query: str, return_fields: list[str] | None) -> dict:
        """Retrieves entries on a form based on a provided search qualification

        Inputs
            form: Remedy form name
            query: Remedy query to identify the entry/entries to retrieve
            return_fields: list of fields we'll ask Remedy to return from the entry/entries

        Outputs
            json: JSON object containing the returned entries
        """

        if not self.auth_token:
            raise RemedyException("Unable to get entry without a valid login session")

        target_url = f"{self.remedy_base_url}{ENTRY_PATH}{form}"
        logging.debug(f"Target URL: {target_url}")
        headers = {"Authorization": self.auth_token}
        params = {"q": query}
        if return_fields:
            fields = ",".join(return_fields)
            params["fields"] = f"values({fields})"
        r = requests.get(target_url, headers=headers, params=params)

        if r.ok:
            return r.json()
        else:
            raise RemedyException(f"Error getting entry: {r.text}")
