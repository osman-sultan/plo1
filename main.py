from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from openai import AzureOpenAI
import psycopg
from pgvector.psycopg import register_vector
import httpx
from typing import Optional
from scripts.token_manager import get_access_token
from scripts.outlook import reply_to_message

# Load environment variables from .env file.
load_dotenv()

MS_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
app = FastAPI()

# Instantiate the AzureOpenAI client.
client = AzureOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    api_version="2024-10-21",
    azure_endpoint=os.environ.get("OPENAI_ENDPOINT"),
    azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
)


class EmailData(BaseModel):
    sender: str
    recipient: str
    subject: str
    body: str
    message_id: Optional[str] = None


# Setup a persistent connection to your Supabase/Postgres database.
DB_CONNECTION = os.getenv("DB_CONNECTION")
conn = psycopg.connect(DB_CONNECTION)
register_vector(conn)


@app.post("/email")
async def process_email(email: EmailData):
    print("Received email:", email)
    # Use application permissions (client credentials flow)
    access_token = get_access_token(
        os.environ.get("APPLICATION_ID"),
        os.environ.get("CLIENT_SECRET"),
        ["https://graph.microsoft.com/.default"],
        os.environ.get("TENANT_ID"),
    )
    print("Access token:", access_token)
    headers = {"Authorization": f"Bearer {access_token}"}

    # Combine subject and body for embedding.
    combined_text = f"{email.subject}\n{email.body}"

    try:
        # 1. Create an embedding for the incoming email.
        embedding_response = client.embeddings.create(
            model=os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
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
            if content.strip().lower().startswith("subject:"):
                idx = content.lower().find("body:")
                if idx != -1:
                    content = content[idx + len("body:") :].strip()
            formatted_content = content.replace("\\n", "<br>")
            reply_body = f"{formatted_content}<br><br>[THIS IS AN AUTOMATED MESSAGE]"

            # 3. Determine the message ID.
            # In application permission flows, there is no "me" so use a designated mailbox.
            mailbox = os.environ.get("MAILBOX")
            if not mailbox:
                raise HTTPException(
                    status_code=500, detail="MAILBOX environment variable is missing"
                )
            message_id = email.message_id
            if not message_id:
                search_endpoint = f"{MS_GRAPH_BASE_URL}/users/{mailbox}/messages"
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
                message_id = messages[0]["id"]

            # 4. Send the reply.
            success = reply_to_message(headers, mailbox, message_id, reply_body)
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
