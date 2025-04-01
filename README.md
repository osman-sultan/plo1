# PLO1 Project Setup Guide

This repository contains a service that processes emails using Microsoft Graph API and Azure OpenAI to provide automated responses based on email templates.

> **Note:** This system has only been tested on Windows 11. While it should work on other operating systems, you may encounter environment-specific issues that require troubleshooting.

## Prerequisites

- Python 3.10 or higher
- PostgreSQL database with pgvector extension
- Microsoft Azure account with Graph API access
- Azure OpenAI service

## Installation

1. Clone the repository:

```
git clone <repository-url>
cd plo1
```

2. Create and activate a virtual environment:

   **Windows:**

   ```
   python -m venv venv
   venv\Scripts\activate
   ```

   **macOS/Linux:**

   ```
   python3 -m venv venv
   source venv/bin/activate
   ```

   You should see `(venv)` at the beginning of your terminal prompt, indicating the virtual environment is active.

3. Install the required packages:

```
pip install -r requirements.txt
```

If you encounter any issues, try upgrading pip first:

```
pip install --upgrade pip
```

4. Set up environment variables by creating a `.env` file with the following variables:

```
OPENAI_API_KEY=your_openai_api_key
OPENAI_ENDPOINT=your_openai_endpoint
DB_CONNECTION=your_postgres_connection_string
CLIENT_SECRET=your_ms_graph_client_secret
APPLICATION_ID=your_ms_graph_application_id
TENANT_ID=your_ms_tenant_id
USER_ID=your_outlook_email
```

## Database Setup

1. Ensure your PostgreSQL database has the pgvector extension installed.
2. Run the script to create embeddings from email templates:

```
python scripts/create_embeddings.py
```

This step is crucial as it:

- Creates vector embeddings of all email templates
- Stores them in the database for similarity matching
- Must be run before starting the FastAPI application

## Azure Setup

> **Disclaimer:** You may choose any Azure pricing model that meets your needs, but we recommend the Pay-As-You-Go model for most users, especially when starting with this project.

### 1. Create a Resource Group

1. Log in to the [Azure Portal](https://portal.azure.com).
2. Navigate to "Resource Groups" and click "Create".
3. Provide a name for the resource group and select a region.
4. Click "Review + Create" and then "Create".

### 2. Create a Logic App

1. In the Azure Portal, navigate to "Logic Apps" and click "Create".
2. Select the resource group created earlier, provide a name for the Logic App, and choose a region.
3. Click "Review + Create" and then "Create".
4. Once deployed, open the Logic App Designer.

#### Add Triggers and Actions

1. Add the **"When a new email arrives (V3)"** trigger:
   - Sign in with your Microsoft account.
   - Configure the trigger to monitor your inbox.
2. Add an **HTTP POST** action:
   - URI: `http://<your-server-uri>/email` (For local development, this will likely be a URL from a service like ngrok)
   - Method: `POST`
   - Headers: `Content-Type: application/json`
   - Body: Map the email fields (e.g., `subject`, `body`, `from`, etc.) to the JSON payload.
3. Add a **Delay** action:
   - Set the delay duration to 30 seconds.
4. Add another **HTTP POST** action:
   - URI: `http://<your-server-uri>/move-notification-emails` (Same URI base as above)
   - Method: `POST`.

Save the Logic App.

### 3. Create an App Registration

1. In the Azure Portal, navigate to "Azure Active Directory" > "App Registrations" and click "New Registration".
2. Provide a name for the application.
3. Set the "Supported account types" to "Accounts in this organizational directory only".
4. Click "Register".

#### Configure API Permissions

1. Go to "API Permissions" and click "Add a permission".
2. Select "Microsoft Graph".
3. **Permission Type:**

   - This project uses **Delegated Permissions** by default, which is suitable for personal email accounts.
   - If you're using a business account (work or school account), we recommend using **Application Permissions** instead as it provides better long-term reliability.
   - Note: Application Permissions are only available for work or school email accounts, not personal accounts.
   - Application Permissions do not require user sign-in and operate independently of user presence, making them ideal for background services and automation. However, remember they only work with work or school accounts (Microsoft 365/Office 365), not with personal Microsoft accounts.

4. Add the following permissions:
   - For **Delegated Permissions**:
     - `Mail.ReadWrite`
     - `Mail.Send`
     - `User.Read`
   - For **Application Permissions** (work/school accounts only):
     - `Mail.ReadWrite`
     - `Mail.Send`
     - `User.Read.All`
5. Click "Grant admin consent".

#### Generate a Client Secret

1. Go to "Certificates & Secrets" and click "New client secret".
2. Provide a description and expiration period, then click "Add".
3. Copy the client secret value and update the `.env` file.

## Authentication Setup

1. The application uses refresh tokens for authentication.

2. **Important:** If using Delegated Permissions, you must first generate a refresh token by running:

   ```
   python scripts/token_manager.py
   ```

   This step must be completed before running the API. The script will prompt you to authorize the application via browser-based login and will store the refresh token for future use.

   - Delegated permissions require this initial user authentication to generate a refresh token.
   - Refresh tokens expire after a set number of days (typically 90 days for Microsoft), but they automatically renew themselves each time you use the API.
   - As long as you regularly use the application (at least once before the token expiration), the refresh token will keep renewing itself and remain valid.

3. For Application Permissions (work/school accounts only), no manual token generation is needed.

## Running the Application

Start the FastAPI server:

```
fastapi dev main.py
```

## Key Features

- `/email` endpoint: Processes incoming emails, finds matching templates, and sends automated responses.
- `/move-notification-emails` endpoint: Organizes notification emails into priority folders.

## Testing

You can test the Microsoft Graph API connection with:

```
python scripts/test.py
```

## Project Structure

- `main.py`: FastAPI application
- `scripts/`: Helper scripts
  - `create_embeddings.py`: Creates vector embeddings for email templates
  - `outlook.py`: Functions for interacting with Microsoft Outlook/Graph API
  - `token_manager.py`: Handles OAuth token management
- `data/`: Data files including email templates
