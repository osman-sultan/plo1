from fastapi import FastAPI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from openai import AzureOpenAI
import psycopg
from pgvector.psycopg import register_vector

# Load environment variables from .env file.
load_dotenv()

# Instantiate the AzureOpenAI client.
client = AzureOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    api_version="2024-10-21",  # use the proper API version for your deployment
    azure_endpoint=os.environ.get("OPENAI_ENDPOINT"),
    azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
)

app = FastAPI()


# Define the expected payload structure.
class EmailData(BaseModel):
    sender: str  # The "from" address.
    recipient: str  # The "to" address.
    subject: str
    body: str


# Setup a persistent connection to your Supabase/Postgres database.
DB_CONNECTION = os.getenv("DB_CONNECTION")
conn = psycopg.connect(DB_CONNECTION)
register_vector(conn)  # Register the vector type with psycopg


@app.post("/email")
async def process_email(email: EmailData):
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
        # Cast the parameter to vector type using ::vector for both use cases.
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
            return {
                "status": "Email processed successfully",
                "template": content,
                "metadata": metadata,
                "distance": distance,
            }
    except Exception as e:
        print("Error processing email:", str(e))
        return {"status": "Error", "detail": str(e)}
