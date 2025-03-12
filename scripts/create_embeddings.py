from openai import AzureOpenAI
from dotenv import load_dotenv
import os
import pandas as pd
import psycopg
from pgvector.psycopg import register_vector
import json

# Load environment variables
load_dotenv()

# Initialize Azure OpenAI client with your environment variables.
client = AzureOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    api_version="2024-10-21",  # Latest GA API version for inference
    azure_endpoint=os.getenv("OPENAI_ENDPOINT"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
)

# Database connection details and setup
DB_CONNECTION = os.getenv("DB_CONNECTION")
conn = psycopg.connect(DB_CONNECTION)
register_vector(conn)

# Enable pgvector extension if not exists
with conn.cursor() as cursor:
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()

# Load the CSV file containing email templates (subject and body)
# Update the file path if needed; here, we're using the attached file "PLO1 Templates.csv"
csv_file = "data/email_templates.csv"
df = pd.read_csv(csv_file)

# Clean up the headers: remove extra spaces and set to lowercase
df.columns = df.columns.str.strip().str.lower()

# Prepare and insert embeddings for each email template.
with conn.cursor() as cursor:
    for _, row in df.iterrows():
        # Update the keys if your CSV uses different names than 'subject' and 'body'
        text = f"Subject: {row['subject']}. Body: {row['body']}."

        # Generate embedding using the Azure OpenAI client.
        response = client.embeddings.create(
            model=os.getenv(
                "AZURE_OPENAI_DEPLOYMENT"
            ),  # Use your deployment name as the model
            input=[text],
        )
        embedding = response.data[0].embedding

        # Clean metadata (convert any NaN values to None)
        metadata = row.to_dict()
        metadata = {k: (None if pd.isna(v) else v) for k, v in metadata.items()}

        # Insert the email text, its embedding, and metadata into the "email_templates" table.
        cursor.execute(
            """
            INSERT INTO email_templates (content, embedding, metadata)
            VALUES (%s, %s, %s)
            """,
            (text, embedding, json.dumps(metadata)),
        )
    conn.commit()

conn.close()
print("Email templates have been successfully added to the database.")
