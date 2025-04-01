from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from openai import AzureOpenAI
import psycopg
from pgvector.psycopg import register_vector
import httpx
import json
from typing import Optional
from scripts.token_manager import get_access_token
from scripts.outlook import (
    reply_to_message,
    is_reply_email,
    send_notification_email,
    move_notification_emails,
)

# Load environment variables from .env file.
load_dotenv()

MS_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
app = FastAPI()

# Instantiate the AzureOpenAI client.
client = AzureOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    api_version="2024-10-21",
    azure_endpoint=os.environ.get("OPENAI_ENDPOINT"),
)


class EmailData(BaseModel):
    sender: str
    recipient: str
    subject: str
    body: str
    message_id: Optional[str] = None

class SystemOutput(BaseModel):
    sender: str
    subject: str
    body: str
    email_embedding: list[float]
    template_metadata: str
    distance: float
    notification_result: dict


def log_results(conn, output_data):
    try:
        with conn.cursor() as cursor:
            query = """
                INSERT INTO outputs (sender, subject, body, email_embedding, template_metadata, distance)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (output_data.sender, output_data.subject, output_data.body, output_data.email_embedding, 
                                   output_data.template_metadata, output_data.distance))
            print("Successfully logged output info to database")
    except Exception as e:
        print("Error logging info:", str(e))


@app.post("/email")
async def process_email(email: EmailData):

    print("Received email")

    if email.sender.lower() == "osman_sultan1128@outlook.com":
        print(
            "Notification email detected from self. Skipping processing to prevent infinite loop."
        )
        return {"status": "Notification email ignored"}

    # Use application permissions (client credentials flow)
    access_token = get_access_token(
        os.environ.get("APPLICATION_ID"),
        os.environ.get("CLIENT_SECRET"),
        ["User.Read", "Mail.ReadWrite", "Mail.Send"],
    )
    print("Access token obtained")
    headers = {"Authorization": f"Bearer {access_token}"}

    # Fetch message data if message_id is available
    message_data = None
    if email.message_id:
        message_endpoint = f"{MS_GRAPH_BASE_URL}/me/messages/{email.message_id}"
        message_response = httpx.get(message_endpoint, headers=headers)
        if message_response.status_code == 200:
            message_data = message_response.json()

    # Check if the email is a reply
    if is_reply_email(email.subject, message_data):
        return {"status": "Skipped processing", "reason": "Email is a reply"}

    DB_CONNECTION = os.getenv("DB_CONNECTION")
    conn = psycopg.connect(DB_CONNECTION)
    register_vector(conn)

    # Combine subject and body for embedding.
    combined_text = f"{email.subject}\n{email.body}"

    try:
        # 1. Create an embedding for the incoming email.
        embedding_response = client.embeddings.create(
            model=os.environ.get(
                "AZURE_OPENAI_DEPLOYMENT"
            ),  # Use your deployment name here.
            input=combined_text,
        )
        incoming_embedding = embedding_response.data[0].embedding
        print("Embedding created")

        # 2. Perform similarity search in the templates table.
        with conn.cursor() as cursor:
            query = """
                SELECT content, metadata, (embedding <=> %s::vector) AS distance
                FROM templates
                ORDER BY embedding <=> %s::vector
                LIMIT 1;
            """
            cursor.execute(query, (incoming_embedding, incoming_embedding))
            result = cursor.fetchone()
            print("Similarity search performed")

        if result is None:
            return {"status": "No matching template found"}
        else:
            content, metadata_json, distance = result

            # Parse metadata JSON (assuming it’s already a dict)
            metadata = metadata_json
            priority = metadata.get("priority", "no action")

            print(f"Template found with priority: {priority}")

            # Use the body from metadata (instead of content) and replace literal "/n" sequences with HTML <br> tags.
            reply_body = metadata.get("body", "").replace("/n", "<br>")

            # 3. Determine the message ID.
            message_id = email.message_id
            if not message_id:
                search_endpoint = f"{MS_GRAPH_BASE_URL}/me/messages"
                params = {"$filter": f"subject eq '{email.subject}'", "$top": "1"}
                search_response = httpx.get(
                    search_endpoint, headers=headers, params=params
                )
                search_response.raise_for_status()
                messages = search_response.json().get("value", [])
                if not messages:
                    raise HTTPException(
                        status_code=404, detail="Original message not found"
                    )
                message_id = messages[0].get("id")

            # 4. Send the reply using the reply_to_message function.
            success = reply_to_message(headers, message_id, reply_body)

            # 5. Send notification based on priority only if reply was successful
            notification_result = None
            if success:
                notification_result = send_notification_email(email, priority)

                # Log results
                output_data = SystemOutput(email.sender, email.subject, email.body, incoming_embedding, 
                                           metadata, distance, notification_result)
                log_results(conn, output_data)

                return {
                    "status": "Email processed and reply sent successfully",
                    "template": content,
                    "notification": notification_result,
                    "priority": priority,
                    "distance": distance,
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to send reply")
    except Exception as e:
        print("Error processing email:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/move-notification-emails")
async def move_notifications():
    """
    Endpoint to find notification emails in inbox and move them to appropriate folders.
    """
    try:
        # Get access token for Microsoft Graph API
        access_token = get_access_token(
            os.environ.get("APPLICATION_ID"),
            os.environ.get("CLIENT_SECRET"),
            ["Mail.ReadWrite"],
        )

        headers = {"Authorization": f"Bearer {access_token}"}

        # Move notification emails to appropriate folders
        results = move_notification_emails(headers)

        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
