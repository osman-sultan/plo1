import msal
import os
from dotenv import load_dotenv

load_dotenv()


def get_access_token(application_id, client_secret, scopes, tenant_id):
    if not tenant_id:
        raise ValueError("TENANT_ID environment variable is missing.")
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    client = msal.ConfidentialClientApplication(
        client_id=application_id,
        authority=authority,
        client_credential=client_secret,
    )
    token_response = client.acquire_token_for_client(scopes=scopes)
    if "access_token" in token_response:
        return token_response["access_token"]
    else:
        raise ValueError("Failed to obtain access token: " + str(token_response))


def main():
    APPLICATION_ID = os.getenv("APPLICATION_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    TENANT_ID = os.getenv("TENANT_ID")
    SCOPES = ["https://graph.microsoft.com/.default"]
    try:
        access_token = get_access_token(
            APPLICATION_ID, CLIENT_SECRET, SCOPES, TENANT_ID
        )
        headers = {"Authorization": f"Bearer {access_token}"}
        print(headers)
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
