from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from openai import AzureOpenAI
import psycopg
from pgvector.psycopg import register_vector
import httpx
from typing import Optional
from scripts.generate_token import get_access_token

# Load environment variables from .env file.
load_dotenv()

MS_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

# Instantiate the AzureOpenAI client.
client = AzureOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    api_version="2024-10-21",  # use the proper API version for your deployment
    azure_endpoint=os.environ.get("OPENAI_ENDPOINT"),
    azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
)

app = FastAPI()


# Extend the EmailData model to include an optional message_id.
class EmailData(BaseModel):
    sender: str  # The "from" address.
    recipient: str  # The "to" address.
    subject: str
    body: str
    message_id: Optional[str] = None  # Optional: provided by the caller if available.


# Setup a persistent connection to your Supabase/Postgres database.
DB_CONNECTION = os.getenv("DB_CONNECTION")
conn = psycopg.connect(DB_CONNECTION)
register_vector(conn)  # Register the vector type with psycopg


def reply_to_message(headers, message_id, reply_body):
    # Fix the headers bug: use "headers=headers" in the httpx.post call.
    endpoint = f"{MS_GRAPH_BASE_URL}/me/messages/{message_id}/reply"
    data = {"comment": reply_body}
    response = httpx.post(endpoint, headers=headers, json=data)
    response.raise_for_status()
    return response.status_code == 202


@app.post("/email")
async def process_email(email: EmailData):
    access_token = get_access_token(
        os.environ.get("APPLICATION_ID"),
        os.environ.get("CLIENT_SECRET"),
        ["User.Read", "Mail.ReadWrite", "Mail.Send"],
    )
    headers = {"Authorization": f"Bearer {access_token}"}

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

        # 2. Perform similarity search in the email_templates table.
        with conn.cursor() as cursor:
            query = """
                SELECT content, metadata, (embedding <=> %s::vector) AS distance
                FROM email_templates
                ORDER BY embedding <=> %s::vector
                LIMIT 1;
            """
            cursor.execute(query, (incoming_embedding, incoming_embedding))
            result = cursor.fetchone()

        if result is None:
            return {"status": "No matching template found"}
        else:
            content, metadata, distance = result
            reply_body = content  # Use the template content as the reply.

            # 3. Determine the message ID.
            message_id = email.message_id
            if not message_id:
                # If the message_id isn't provided, try to locate the message using the subject.
                # Note: This assumes that the subject uniquely identifies the message.
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

            # 4. Send the reply using the reply function.
            success = reply_to_message(headers, message_id, reply_body)
            if success:
                return {
                    "status": "Email processed and reply sent successfully",
                    "template": content,
                    "metadata": metadata,
                    "distance": distance,
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to send reply")
    except Exception as e:
        print("Error processing email:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
