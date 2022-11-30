""" Remedy REST API Functions Wrapper Module """

import json
import logging
from typing import List, Optional, Tuple

import requests

ENTRY_PATH = "/arsys/v1/entry/"
LOGIN_PATH = "/jwt/login"
LOGOUT_PATH = "/jwt/logout"
REMEDY_TIMEOUT = 60


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
        logging.info(f"Logging in to Helix ITSM as {username}")
        logging.info(f"============================{'=' * len(username)}")

        payload = {"username": username, "password": password}
        login_url = f"{self.remedy_base_url}{LOGIN_PATH}"
        logging.debug(login_url)
        response = requests.post(login_url, data=payload, timeout=REMEDY_TIMEOUT)

        if not response.ok:
            raise RemedyLoginException(
                f"Failed to login to Remedy server: HTTP {response.status_code} ({response.reason})"
            )

        self.auth_token = f"AR-JWT {response.text}"

    def __enter__(self):
        """Context manager entry method"""
        return self

    def __exit__(self, exctype, excvalue, traceback):
        """Context manager exit method"""
        if self.auth_token:
            self.logout()
        if exctype:
            logging.info(f"Exception type was specified! {type}")
        return True

    def logout(self):
        """Request destruction of an active login token"""
        if not self.auth_token:
            raise RemedyLogoutException("No active login session; cannot logout.")
        headers = {"Authorization": self.auth_token}
        response = requests.post(
            f"{self.remedy_base_url}{LOGOUT_PATH}",
            headers=headers,
            timeout=REMEDY_TIMEOUT,
        )

        logging.info("=================================")

        if not response.ok:
            raise RemedyLogoutException(
                f'Failed to log out of Helix ITSM server: ({response.status_code}) {response.text}"'
            )
        logging.info("Successful logout from Helix ITSM")
        self.auth_token = None

    def create_entry(
        self, form: str, field_values: dict, fields: Optional[List[str]]
    ) -> Tuple[str, dict]:
        """Method to create a Remedy form entry

        Inputs
            form: Name of the Remedy form in which to create an entry
            field_values: Structured Dict containing the entry field values
            fields: list of fields we'll ask Remedy to return from the created entry

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
        params = {"fields": f"values({','.join(fields)})"} if fields else None

        logging.debug(json.dumps(field_values, indent=4))
        logging.debug(target_url)
        logging.debug(headers)
        logging.debug(params)

        response = requests.post(
            target_url,
            json=field_values,
            headers=headers,
            params=params,
            timeout=REMEDY_TIMEOUT,
        )

        if not response.ok:
            raise RemedyException(f"Failed to create entry: {response.text}")

        location = response.headers.get("Location") or ""
        return location, response.json()

    def modify_entry(self, form: str, field_values: dict, entry_id: str) -> None:
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
        response = requests.put(
            target_url, json=field_values, headers=headers, timeout=REMEDY_TIMEOUT
        )
        if response.ok:
            logging.debug(f"Incident modified: {target_url}")
            return

        logging.error(f"Error modifying incident: {response.text}")
        raise RemedyException("Failed to modify the incident")

    def query_form(
        self,
        form: str,
        query: Optional[str],
        fields: Optional[List[str]],
        limit: Optional[int],
    ) -> dict:
        """Retrieves entries on a form based on a provided search qualification

        Inputs
            form: Remedy form name
            query_form: Remedy query_form to identify the entry/entries to retrieve
            fields: list of fields we'll ask Remedy to return from the entry/entries

        Outputs
            dict: Dictionary object containing the returned entries
        """

        if not self.auth_token:
            raise RemedyException("Unable to get entry without a valid login session")

        target_url = f"{self.remedy_base_url}{ENTRY_PATH}{form}"
        logging.debug(f"Target URL: {target_url}")
        headers = {"Authorization": self.auth_token}

        params = {}
        if query:
            params["q"] = query
        if limit:
            params["limit"] = limit
        if fields:
            params["fields"] = f"values({','.join(fields)})"
        response = requests.get(
            target_url, headers=headers, params=params, timeout=REMEDY_TIMEOUT
        )

        if response.ok:
            return response.json()

        raise RemedyException(f"Error getting entry: {response.text}")
