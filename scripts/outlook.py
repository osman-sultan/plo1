import httpx
from scripts.token_manager import ensure_valid_token
import os
from dotenv import load_dotenv

MS_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

load_dotenv()


def reply_to_message(headers, message_id, reply_body):
    """
    Sends a reply to the specified message using the Graph API.
    The reply_body is assumed to contain HTML-formatted content.
    """
    # Ensure we have a valid token before making the request
    headers = ensure_valid_token(
        headers,
        os.environ.get("APPLICATION_ID"),
        os.environ.get("CLIENT_SECRET"),
        ["User.Read", "Mail.ReadWrite", "Mail.Send"],
    )

    # Debug print the headers
    auth_header = headers.get("Authorization", "")
    token_preview = (
        auth_header[7:20] + "..."
        if auth_header.startswith("Bearer ")
        else "Invalid format"
    )
    print(f"Using token for API call: {token_preview}")

    # Make sure to create a new headers dictionary to avoid mutation issues
    request_headers = {**headers, "Content-Type": "application/json"}

    endpoint = f"{MS_GRAPH_BASE_URL}/me/messages/{message_id}/reply"
    payload = {"message": {"body": {"contentType": "HTML", "content": reply_body}}}

    try:
        response = httpx.post(endpoint, headers=request_headers, json=payload)

        if response.status_code != 202:
            print(f"API error: {response.status_code}, {response.text}")

        return response.status_code == 202
    except Exception as e:
        print(f"Exception during API call: {str(e)}")
        return False


def is_parent_email(headers, message_id):
    """
    Check if a message is a parent email (not a reply).
    Returns True if it's a parent email, False if it's a reply.
    """
    # Ensure we have a valid token before making the request
    headers = ensure_valid_token(
        headers,
        os.environ.get("APPLICATION_ID"),
        os.environ.get("CLIENT_SECRET"),
        ["User.Read", "Mail.ReadWrite", "Mail.Send"],
    )

    # Get message details
    endpoint = f"{MS_GRAPH_BASE_URL}/me/messages/{message_id}"
    # Include fields we need to determine if it's a reply
    params = {"$select": "conversationId,internetMessageId,internetMessageHeaders"}

    response = httpx.get(endpoint, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Error getting message details: {response.text}")
        # If we can't determine, assume it's safe to reply
        return True

    message_data = response.json()

    # Check for common reply indicators in the subject
    if "subject" in message_data:
        subject = message_data["subject"].lower()
        if subject.startswith("re:") or "fw:" in subject:
            return False

    # Check message headers for In-Reply-To or References headers
    if "internetMessageHeaders" in message_data:
        headers = message_data["internetMessageHeaders"]
        for header in headers:
            if header["name"].lower() in ["in-reply-to", "references"]:
                return False

    # If message has a conversationId, look up the conversation thread
    if "conversationId" in message_data:
        conversation_id = message_data["conversationId"]
        thread_endpoint = f"{MS_GRAPH_BASE_URL}/me/messages"
        thread_params = {
            "$filter": f"conversationId eq '{conversation_id}'",
            "$orderby": "receivedDateTime",
            "$select": "id,receivedDateTime",
        }

        thread_response = httpx.get(
            thread_endpoint, headers=headers, params=thread_params
        )
        if thread_response.status_code == 200:
            thread_data = thread_response.json()
            # If this message is not the first in the conversation thread, it's likely a reply
            if "value" in thread_data and len(thread_data["value"]) > 0:
                oldest_message_id = thread_data["value"][0]["id"]
                if message_id != oldest_message_id:
                    return False

    # If nothing indicates it's a reply, consider it a parent email
    return True
