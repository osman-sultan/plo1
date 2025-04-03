# Delegated perms below

# from dotenv import load_dotenv
# import msal
# import webbrowser
# import os

# MS_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


# def get_access_token(application_id, client_secret, scopes):
#     client = msal.ConfidentialClientApplication(
#         client_id=application_id,
#         client_credential=client_secret,
#         authority="https://login.microsoftonline.com/consumers/",
#     )

#     # Check if there is a refresh token stored

#     refresh_token = None
#     if os.path.exists("refresh_token.txt"):
#         with open("refresh_token.txt", "r") as file:
#             refresh_token = file.read().strip()

#     if refresh_token:
#         # Try to acquire a new access token using the refresh token
#         token_response = client.acquire_token_by_refresh_token(
#             refresh_token, scopes=scopes
#         )
#     else:
#         # No refresh token, proceed with the authorization code flow
#         auth_request_url = client.get_authorization_request_url(scopes)
#         webbrowser.open(auth_request_url)
#         authorization_code = input("Enter the authorization code: ")

#         if not authorization_code:
#             raise ValueError("Authorization code is empty")

#         token_response = client.acquire_token_by_authorization_code(
#             code=authorization_code, scopes=scopes
#         )

#     if "access_token" in token_response:
#         # store refresh token for future use
#         if "refresh_token" in token_response:
#             with open("refresh_token.txt", "w") as file:
#                 file.write(token_response["refresh_token"])

#         return token_response["access_token"]
#     else:
#         raise Exception("Failed to obtain access token: " + str(token_response))


# def main():
#     # Load environment variables from .env file.
#     load_dotenv()
#     APPLICATION_ID = os.environ.get("APPLICATION_ID")
#     CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
#     SCOPES = ["User.Read", "Mail.ReadWrite", "Mail.Send"]

#     try:
#         access_token = get_access_token(APPLICATION_ID, CLIENT_SECRET, SCOPES)
#         headers = {
#             "Authorization": f"Bearer {access_token}",
#         }
#         print(headers)
#     except Exception as e:
#         print(f"Error: {e}")


# main()

############################################################################

# Application Perms below
from dotenv import load_dotenv
import msal
import os

MS_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def get_access_token(application_id, client_secret, scopes, tenant_id=None):
    """
    Acquire token using client credentials flow (for application permissions)
    """
    # Default to the tenant ID from environment variables if not provided
    if not tenant_id:
        tenant_id = os.getenv("TENANT_ID", "common")

    # For work/school accounts (not personal accounts)
    authority = f"https://login.microsoftonline.com/{tenant_id}"

    # Create the MSAL client
    app = msal.ConfidentialClientApplication(
        client_id=application_id,
        client_credential=client_secret,
        authority=authority,
    )

    # Acquire token for application
    result = app.acquire_token_for_client(scopes=scopes)

    if "access_token" in result:
        return result["access_token"]
    else:
        error_description = result.get("error_description", str(result))
        raise Exception(f"Failed to obtain access token: {error_description}")


def main():
    # Load environment variables from .env file.
    load_dotenv()
    APPLICATION_ID = os.environ.get("APPLICATION_ID")
    CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
    TENANT_ID = os.environ.get("TENANT_ID")

    # For application permissions, use the .default scope
    SCOPES = ["https://graph.microsoft.com/.default"]

    try:
        access_token = get_access_token(
            APPLICATION_ID, CLIENT_SECRET, SCOPES, TENANT_ID
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
        }
        print(f"Access token obtained successfully")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
