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
)


class EmailData(BaseModel):
    sender: str
    recipient: str
    subject: str
    body: str
    message_id: Optional[str] = None


@app.post("/email")
async def process_email(email: EmailData):

    DB_CONNECTION = os.getenv("DB_CONNECTION")
    conn = psycopg.connect(DB_CONNECTION)
    register_vector(conn)

    print("Received email")
    # Use application permissions (client credentials flow)
    access_token = get_access_token(
        os.environ.get("APPLICATION_ID"),
        os.environ.get("CLIENT_SECRET"),
        ["User.Read", "Mail.ReadWrite", "Mail.Send"],
    )
    print("Access token obtained")
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
            content, metadata, distance = result

            # Remove the subject from the template if it exists.
            if content.strip().lower().startswith("subject:"):
                idx = content.lower().find("body:")
                if idx != -1:
                    content = content[idx + len("body:") :].strip()

            # Replace literal "\n" sequences with HTML <br> tags.
            reply_body = content.replace("\\n", "<br>")

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
