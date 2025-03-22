import httpx
from dotenv import load_dotenv
import os

load_dotenv()

MS_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def reply_to_message(headers, message_id, reply_body):
    # Fix the headers bug: use "headers=headers" in the httpx.post call.
    endpoint = f"{MS_GRAPH_BASE_URL}/me/messages/{message_id}/reply"
    data = {"comment": reply_body}
    response = httpx.post(endpoint, headers=headers, json=data)
    response.raise_for_status()
    return response.status_code == 202


def get_folder(headers, user_id, folder_id):
    # Corrected endpoint for mail folders with application permissions
    endpoint = f"{MS_GRAPH_BASE_URL}/users/{user_id}/mailFolders/{folder_id}"
    response = httpx.get(endpoint, headers=headers)
    response.raise_for_status()
    return response.json()
