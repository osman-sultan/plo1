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


@app.post("/email")
async def process_email(email: EmailData):
    print("Received email")

    user_id = os.environ.get("USER_ID")

    if email.sender.lower() == user_id.lower():
        print(
            "Notification email detected from self. Skipping processing to prevent infinite loop."
        )
        return {"status": "Notification email ignored"}

    # Use application permissions (client credentials flow)
    access_token = get_access_token(
        os.environ.get("APPLICATION_ID"),
        os.environ.get("CLIENT_SECRET"),
        ["https://graph.microsoft.com/.default"],
        os.environ.get("TENANT_ID"),
    )
    print("Access token obtained")
    headers = {"Authorization": f"Bearer {access_token}"}

    # Fetch message data if message_id is available
    message_data = None
    if email.message_id:
        # Update to use application permissions endpoint
        message_endpoint = (
            f"{MS_GRAPH_BASE_URL}/users/{user_id}/messages/{email.message_id}"
        )
        message_response = httpx.get(message_endpoint, headers=headers)
        if message_response.status_code == 200:
            message_data = message_response.json()

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
            """
            cursor.execute(query, (incoming_embedding, incoming_embedding))
            all_results = cursor.fetchall()
            print("Similarity search performed")

            # Print all template matches and scores
            print("\n=== All Template Matches ===")
            for idx, template_result in enumerate(all_results):
                template_content, template_metadata, template_distance = template_result
                template_subject = template_metadata.get("subject", "Unknown")
                similarity_score = (
                    1 - template_distance
                )  # Convert distance to similarity
                print(
                    f"{idx+1}. '{template_subject}' - Similarity: {similarity_score:.4f}"
                )
            print("===========================\n")

        if not all_results:
            return {"status": "No matching template found"}
        else:
            # Get the best match (first result)
            result = all_results[0]
            content, metadata_json, distance = result
            best_similarity = 1 - distance

            # Define threshold for good matches
            SIMILARITY_THRESHOLD = 0.25

            # Check if best similarity is below threshold
            if best_similarity < SIMILARITY_THRESHOLD:
                print(
                    f"Best match similarity ({best_similarity:.4f}) below threshold ({SIMILARITY_THRESHOLD})"
                )

                # Find the generic template in the results
                generic_template = None
                for template_result in all_results:
                    template_content, template_metadata, template_distance = (
                        template_result
                    )
                    if (
                        template_metadata.get("subject")
                        == "General Customer Inquiry Acknowledgment"
                    ):
                        generic_template = template_result
                        break

                # Use the generic template if found
                if generic_template:
                    print("Falling back to Generic Customer Inquiry template")
                    result = generic_template
                    content, metadata_json, distance = result
                else:
                    print(
                        "WARNING: Generic template not found in results, using best match anyway"
                    )

            # Parse metadata JSON (assuming it's already a dict)
            metadata = metadata_json
            priority = metadata.get("priority", "no action")

            # Print best match information
            print(f"Selected template: '{metadata.get('subject', 'Unknown')}'")
            print(f"Final similarity score: {1 - distance:.4f}")
            print(f"Template found with priority: {priority}")

            # Continue with the existing code...
            reply_body = metadata.get("body", "").replace("/n", "<br>")

            # 3. Determine the message ID.
            message_id = email.message_id
            if not message_id:
                # Update search endpoint for application permissions
                search_endpoint = f"{MS_GRAPH_BASE_URL}/users/{user_id}/messages"
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
            success = reply_to_message(headers, message_id, reply_body, user_id)

            # 5. Send notification based on priority only if reply was successful
            notification_result = None
            if success:
                notification_result = send_notification_email(email, priority, user_id)
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
        user_id = os.environ.get("USER_ID")

        # Get access token for Microsoft Graph API with application permissions
        access_token = get_access_token(
            os.environ.get("APPLICATION_ID"),
            os.environ.get("CLIENT_SECRET"),
            ["https://graph.microsoft.com/.default"],
            os.environ.get("TENANT_ID"),
        )

        headers = {"Authorization": f"Bearer {access_token}"}

        # Move notification emails to appropriate folders
        results = move_notification_emails(headers, user_id)

        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
