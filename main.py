from fastapi import FastAPI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables from .env file.
load_dotenv()

# Instantiate the AzureOpenAI client.
client = AzureOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),  # or AZURE_OPENAI_API_KEY if you prefer
    api_version="2023-07-01-preview",  # use the proper API version for your deployment
    azure_endpoint=os.environ.get("OPENAI_ENDPOINT"),
    azure_deployment=os.environ.get(
        "AZURE_OPENAI_DEPLOYMENT"
    ),  # this is your deployment_id
)

app = FastAPI()


# Define the expected payload structure.
class EmailData(BaseModel):
    sender: str  # The "from" address.
    recipient: str  # The "to" address.
    subject: str
    body: str


@app.post("/email")
async def process_email(email: EmailData):

    # Combine subject and body for embedding.
    combined_text = f"{email.subject}\n{email.body}"

    try:
        # Create an embedding using the AzureOpenAI client.
        # Note: For embeddings, the API call is similar to completions.
        embedding_response = client.embeddings.create(
            model=os.environ.get(
                "AZURE_OPENAI_DEPLOYMENT"
            ),  # Use your deployment name here.
            input=combined_text,
        )
        # The response object is similar to the standard API and contains a data list.
        embedding = embedding_response.data[0].embedding
        print("Embedding:")
        print(embedding)

        # Return a JSON response including the embedding.
        return {"status": "Email processed successfully", "embedding": embedding}
    except Exception as e:
        print("Error calling Azure OpenAI embedding:", str(e))
        return {"status": "Error", "detail": str(e)}


# For local testing, run the app with Uvicorn.
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
