from dotenv import load_dotenv
import msal
import webbrowser
import os
import time
from datetime import datetime, timedelta

MS_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

# Global variables to cache token information
_access_token = None
_token_expiry = None
_refresh_token = None


def _load_refresh_token():
    """Load refresh token from file if it exists"""
    if os.path.exists("refresh_token.txt"):
        with open("refresh_token.txt", "r") as file:
            return file.read().strip()
    return None


def _save_refresh_token(refresh_token):
    """Save refresh token to file"""
    with open("refresh_token.txt", "w") as file:
        file.write(refresh_token)


def get_access_token(application_id, client_secret, scopes):
    """
    Get an access token, refreshing it automatically if needed.
    Uses cached token if it's still valid.
    """
    global _access_token, _token_expiry, _refresh_token

    # Check if we have a valid cached token
    current_time = datetime.now()
    if _access_token and _token_expiry and current_time < _token_expiry:
        return _access_token  # Remove the validation - Microsoft tokens are valid but not JWT format

    # If we have a refresh token but no valid access token, try to refresh
    if not _refresh_token:
        _refresh_token = _load_refresh_token()
        print(
            f"Loaded refresh token from file: {'Found' if _refresh_token else 'Not found'}"
        )

    client = msal.ConfidentialClientApplication(
        client_id=application_id,
        client_credential=client_secret,
        authority="https://login.microsoftonline.com/consumers/",
    )

    token_response = None

    if _refresh_token:
        # Try to acquire a new access token using the refresh token
        print("Attempting to refresh token...")
        token_response = client.acquire_token_by_refresh_token(
            _refresh_token, scopes=scopes
        )
        if "error" in token_response:
            print(
                f"Error refreshing token: {token_response.get('error_description', token_response)}"
            )
        else:
            print("Token refresh successful")

    # If we couldn't get a token via refresh token, go through auth code flow
    if not token_response or "error" in token_response:
        # No refresh token or refresh failed, proceed with the authorization code flow
        auth_request_url = client.get_authorization_request_url(scopes)
        print(
            f"Please authenticate in the browser window that will open momentarily..."
        )
        webbrowser.open(auth_request_url)
        authorization_code = input("Enter the authorization code: ")

        if not authorization_code:
            raise ValueError("Authorization code is empty")

        token_response = client.acquire_token_by_authorization_code(
            code=authorization_code, scopes=scopes
        )

    if "access_token" in token_response:
        # Validate the token format
        token = token_response["access_token"]
        # if token.count(".") != 2:
        #     print(f"WARNING: Received malformed token from Microsoft: {token[:20]}...")

        # Store tokens in memory
        _access_token = token_response["access_token"]

        # Calculate token expiry time (subtract 5 minutes for safety margin)
        expires_in = token_response.get(
            "expires_in", 3600
        )  # Default to 1 hour if not specified
        _token_expiry = current_time + timedelta(seconds=expires_in - 300)

        # Store refresh token for future use
        if "refresh_token" in token_response:
            _refresh_token = token_response["refresh_token"]
            _save_refresh_token(_refresh_token)

        return _access_token
    else:
        error_message = token_response.get("error_description", str(token_response))
        raise Exception(f"Failed to obtain access token: {error_message}")


def ensure_valid_token(headers, application_id, client_secret, scopes):
    """
    Utility function to ensure headers contain a valid token.
    Can be called before any API request.
    """
    # Get a fresh token if needed
    access_token = get_access_token(application_id, client_secret, scopes)

    # Make sure the token is not None or empty
    if not access_token:
        raise ValueError("Could not obtain a valid access token")

    # Create a new headers dictionary to avoid reference issues
    new_headers = headers.copy() if headers else {}

    # Update the authorization header
    new_headers["Authorization"] = f"Bearer {access_token}"

    # Debug the token to make sure it's well-formed (should have 2 dots in it)
    # if access_token.count(".") != 2:
    #     print(
    #         f"WARNING: Token appears malformed! Token preview: {access_token[:20]}..."
    #     )

    return new_headers


def main():
    # For testing the token manager
    load_dotenv()
    APPLICATION_ID = os.environ.get("APPLICATION_ID")
    CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
    SCOPES = ["User.Read", "Mail.ReadWrite", "Mail.Send"]

    try:
        # Get initial token
        access_token = get_access_token(APPLICATION_ID, CLIENT_SECRET, SCOPES)
        print(f"Access token obtained: {access_token[:15]}...")

        # Test token refresh
        headers = {"Authorization": f"Bearer {access_token}"}

        # Simulate token expiry
        global _token_expiry
        _token_expiry = datetime.now() - timedelta(minutes=5)

        # This should trigger a refresh
        updated_headers = ensure_valid_token(
            headers, APPLICATION_ID, CLIENT_SECRET, SCOPES
        )
        print(f"Refreshed token: {updated_headers['Authorization'][7:22]}...")

        # Test if the token is well-formed
        token = updated_headers["Authorization"][7:]  # Remove "Bearer " prefix
        if token.count(".") != 2:
            print("WARNING: Token is not well-formed JWT!")
        else:
            print("Token is well-formed JWT")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
