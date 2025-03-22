import httpx
from token_manager import get_access_token
import os
from dotenv import load_dotenv

load_dotenv()


def test_graph_connection():
    # Get token
    access_token = get_access_token(
        os.environ.get("APPLICATION_ID"),
        os.environ.get("CLIENT_SECRET"),
        ["https://graph.microsoft.com/.default"],
        os.environ.get("TENANT_ID"),
    )

    # Set up headers
    headers = {"Authorization": f"Bearer {access_token}"}

    # Test with a simple GET request
    user_id = os.environ.get("USER_ID")
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}"

    print(f"Testing connection to: {url}")
    response = httpx.get(url, headers=headers)

    print(f"Status code: {response.status_code}")
    print(f"Response: {response.text}")

    # If that works, try a mail endpoint
    if response.status_code == 200:
        mail_url = f"https://graph.microsoft.com/v1.0/users/{user_id}/messages?$top=1"
        mail_response = httpx.get(mail_url, headers=headers)
        print(f"Mail API status code: {mail_response.status_code}")
        print(f"Mail API response: {mail_response}")


if __name__ == "__main__":
    test_graph_connection()
