import httpx
from dotenv import load_dotenv
import os
from scripts.token_manager import get_access_token
import re

load_dotenv()

MS_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def reply_to_message(headers, message_id, reply_body, user_id=None):
    if user_id is None:
        user_id = os.getenv("USER_ID")

    # Updated endpoint for application permissions
    endpoint = f"{MS_GRAPH_BASE_URL}/users/{user_id}/messages/{message_id}/reply"
    data = {"comment": reply_body}
    response = httpx.post(endpoint, headers=headers, json=data)
    response.raise_for_status()
    return response.status_code == 202


def get_folder(headers, user_id, folder_id):
    # Already using the correct format for application permissions
    endpoint = f"{MS_GRAPH_BASE_URL}/users/{user_id}/mailFolders/{folder_id}"
    response = httpx.get(endpoint, headers=headers)
    response.raise_for_status()
    return response.json()


def move_email_to_folder(headers, message_id, destination_folder_id, user_id=None):
    if user_id is None:
        user_id = os.getenv("USER_ID")

    # Updated endpoint for application permissions
    endpoint = f"{MS_GRAPH_BASE_URL}/users/{user_id}/messages/{message_id}/move"
    params = {"destinationId": destination_folder_id}

    response = httpx.post(endpoint, headers=headers, json=params)
    response.raise_for_status()
    return response.json()


def search_folder(headers, folder_name="drafts", user_id=None):
    if user_id is None:
        user_id = os.getenv("USER_ID")

    # Updated endpoint for application permissions
    endpoint = f"{MS_GRAPH_BASE_URL}/users/{user_id}/mailFolders"
    response = httpx.get(endpoint, headers=headers)
    response.raise_for_status()
    folders = response.json().get("value", [])
    for folder in folders:
        if folder["displayName"].lower() == folder_name.lower():
            return folder
    return None


def draft_message_body(
    subject,
    body_content,
    to_emails,
    cc_emails=None,
    attachments=None,
    importance="normal",
):
    # This function doesn't need modification as it just formats the message
    message = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body_content},
        "toRecipients": [{"emailAddress": {"address": email}} for email in to_emails],
        "importance": importance,
    }

    if cc_emails:
        message["ccRecipients"] = [
            {"emailAddress": {"address": email}} for email in cc_emails
        ]

    if attachments:
        message["attachments"] = attachments

    return message


def send_notification_email(customer_email, priority, user_id=None):
    """
    Send notification email based on priority without moving to folders.
    """
    if user_id is None:
        user_id = os.getenv("USER_ID")

    # If priority is "no action", do nothing
    if priority == "no action":
        print("Template priority is 'no action'. No notification sent.")
        return {"status": "No notification needed"}

    # Validate priority is either "high priority" or "low priority"
    if priority not in ["high priority", "low priority"]:
        print(
            f"Invalid priority: {priority}. Must be 'high priority' or 'low priority'"
        )
        return {"status": "Invalid priority value"}

    # Get access token for Microsoft Graph API using application permissions
    access_token = get_access_token(
        os.environ.get("APPLICATION_ID"),
        os.environ.get("CLIENT_SECRET"),
        ["https://graph.microsoft.com/.default"],
        os.environ.get("TENANT_ID"),
    )

    headers = {"Authorization": f"Bearer {access_token}"}

    # Format the customer's email content as HTML
    body_html = customer_email.body.replace("\n", "<br>")
    email_content = f"""
    <p><strong>From:</strong> {customer_email.sender}</p>
    <p><strong>Subject:</strong> {customer_email.subject}</p>
    <hr>
    <p>{body_html}</p>
    """

    # Create notification email
    to_emails = [user_id]  # Using USER_ID from .env
    subject = f"[{priority.upper()}] Customer Email: {customer_email.subject}"

    # Prepare message data
    message = draft_message_body(subject, email_content, to_emails)

    # Send the email using application permissions
    data = {"message": message, "saveToSentItems": True}
    endpoint = f"{MS_GRAPH_BASE_URL}/users/{user_id}/sendMail"
    response = httpx.post(endpoint, headers=headers, json=data)

    if response.status_code != 202:
        print(f"Failed to send notification email: {response.text}")
        return {"status": "Failed to send notification"}

    print(f"Notification email sent successfully with subject: '{subject}'")

    return {
        "status": "Notification email sent successfully",
        "priority": priority,
        "subject": subject,
    }


def is_reply_email(subject, message_data=None):
    # This utility function doesn't need modification
    if re.match(r"^(re:|fw:|fwd:)", subject.lower().strip()):
        return True
    if message_data and message_data.get("conversationIndex"):
        if len(message_data.get("conversationIndex", "")) > 22:
            return True
    return False


def move_notification_emails(headers, user_id=None):
    """
    Search inbox for notification emails and move them to appropriate priority folders.
    """
    if user_id is None:
        user_id = os.getenv("USER_ID")

    results = {
        "high_priority": {"found": 0, "moved": 0},
        "low_priority": {"found": 0, "moved": 0},
        "errors": [],
    }

    # Find the inbox folder
    inbox_folder = search_folder(headers, "inbox", user_id)
    if not inbox_folder:
        return {"status": "error", "message": "Could not find Inbox folder"}

    # Find priority folders
    high_priority_folder = search_folder(headers, "high priority", user_id)
    low_priority_folder = search_folder(headers, "low priority", user_id)

    if not high_priority_folder or not low_priority_folder:
        return {
            "status": "error",
            "message": "Could not find one or both priority folders",
            "high_priority_found": high_priority_folder is not None,
            "low_priority_found": low_priority_folder is not None,
        }

    # Get messages from inbox with application permissions
    get_messages_endpoint = (
        f"{MS_GRAPH_BASE_URL}/users/{user_id}/mailFolders/{inbox_folder['id']}/messages"
        f"?$top=50&$select=id,subject"
    )

    messages_response = httpx.get(get_messages_endpoint, headers=headers)
    if messages_response.status_code != 200:
        return {
            "status": "error",
            "message": f"Failed to fetch messages: {messages_response.text}",
        }

    messages = messages_response.json().get("value", [])

    # Process each message
    for message in messages:
        subject = message.get("subject", "")
        message_id = message.get("id")

        if "[HIGH PRIORITY]" in subject.upper():
            results["high_priority"]["found"] += 1
            try:
                move_email_to_folder(
                    headers, message_id, high_priority_folder["id"], user_id
                )
                results["high_priority"]["moved"] += 1
            except Exception as e:
                results["errors"].append(
                    f"Error moving high priority message {message_id}: {str(e)}"
                )

        elif "[LOW PRIORITY]" in subject.upper():
            results["low_priority"]["found"] += 1
            try:
                move_email_to_folder(
                    headers, message_id, low_priority_folder["id"], user_id
                )
                results["low_priority"]["moved"] += 1
            except Exception as e:
                results["errors"].append(
                    f"Error moving low priority message {message_id}: {str(e)}"
                )

    results["status"] = "success" if not results["errors"] else "partial_success"
    return results
