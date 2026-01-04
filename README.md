# FinHealthMonitor

A web application that connects to Xero via OAuth 2.0 and displays your chart of accounts. Built with FastAPI and designed to be extended with charts and an LLM chatbot.

## Features

- **Xero OAuth 2.0 Integration**: Secure authentication with Xero
- **Chart of Accounts Display**: View all accounts from your Xero organization
- **Outstanding Invoices**: View outstanding invoices fetched via Xero MCP Server
- **Xero MCP Server Integration**: Uses official Xero MCP Server for data access
- **Modern UI**: Clean, responsive interface with navigation
- **Extensible Architecture**: Ready for future charts and chatbot features

## Prerequisites

- Python 3.8 or higher
- Node.js 18 or higher (for Xero MCP Server)
- A Xero Developer account
- A registered Xero application

## Setup Instructions

### 1. Register Your Application with Xero

1. Go to [Xero Developer Portal](https://developer.xero.com/)
2. Sign in or create an account
3. Navigate to "My Apps" and click "New App"
4. Fill in the application details:
   - **App name**: FinHealthMonitor (or your preferred name)
   - **Company URL**: Your website URL (can be a placeholder for development)
   - **Integration type**: Select "Web app"
5. Configure OAuth 2.0 settings:
   - **Redirect URI**: `http://localhost:8000/callback` (for local development)
   - **Scopes**: Select the following scopes:
     - `accounting.transactions` - Read transactions
     - `accounting.settings.read` - Read accounting settings
     - `offline_access` - Refresh tokens
6. After creating the app, note down:
   - **Client ID**
   - **Client Secret**

### 2. Install Dependencies

1. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Configure Environment Variables

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your Xero credentials:
   ```env
   XERO_CLIENT_ID=your_actual_client_id
   XERO_CLIENT_SECRET=your_actual_client_secret
   XERO_REDIRECT_URI=http://localhost:8000/callback
   SECRET_KEY=your_random_secret_key
   DEBUG=False
   ```

3. Generate a secret key (optional but recommended):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Copy the output and use it as your `SECRET_KEY` value.

### 4. Xero MCP Server Setup

The application uses the Xero MCP Server for fetching data. The MCP server is already cloned in the project directory.

**Note**: The MCP server is automatically started when needed by the application. No separate setup is required, but ensure Node.js is installed.

If you need to manually test the MCP server:
```bash
cd xero-mcp-server
npm install  # Already done during setup
npm run build  # Already done during setup
```

### 5. Run the Application

Start the FastAPI server:
```bash
python -m app.main
```

Or using uvicorn directly:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The application will be available at `http://localhost:8000`

## Usage

1. Open your browser and navigate to `http://localhost:8000`
2. Click "Connect with Xero" to start the OAuth flow
3. You'll be redirected to Xero to authorize the application
4. After authorization, you'll be redirected back to the application
5. You can now:
   - View your **Chart of Accounts** (default page)
   - View **Outstanding Invoices** (fetched via MCP Server) by clicking the navigation link

## Project Structure

```
finHealthMonitor/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application and routes
│   ├── config.py            # Configuration management
│   ├── xero_client.py       # Xero API client wrapper
│   └── templates/
│       ├── index.html       # Main dashboard
│       └── login.html       # Login page
├── static/
│   ├── css/
│   │   └── style.css        # Styling
│   └── js/
│       └── main.js          # Frontend JavaScript
├── requirements.txt         # Python dependencies
├── .env.example            # Environment variables template
└── README.md               # This file
```

## API Endpoints

- `GET /` - Root endpoint (redirects to login or accounts)
- `GET /login` - Initiates Xero OAuth flow
- `GET /callback` - Handles OAuth callback
- `GET /accounts` - Displays chart of accounts
- `GET /invoices` - Displays outstanding invoices (via MCP Server)
- `GET /logout` - Clears session and logs out

## Future Extensions

The application is structured to support:

1. **Charts**: Add Chart.js or similar library to visualize account data
   - Placeholder section already in `index.html`
   - JavaScript hooks ready in `main.js`

2. **LLM Chatbot**: Integrate with OpenAI or other LLM services
   - Placeholder section already in `index.html`
   - Ready for API endpoint creation in `main.py`

## Security Notes

- Never commit your `.env` file to version control
- Use HTTPS in production (required for OAuth 2.0)
- Keep your Client Secret secure
- Rotate your SECRET_KEY regularly in production

## Troubleshooting

### "Configuration error: XERO_CLIENT_ID environment variable is required"
- Make sure you've created a `.env` file with your credentials
- Check that the variable names match exactly (case-sensitive)

### "Invalid state parameter" or OAuth errors
- Clear your browser cookies/session
- Make sure the redirect URI in `.env` matches exactly what's configured in Xero Developer Portal

### "No Xero organizations connected"
- Make sure you've authorized the app with a Xero organization
- Check that you have access to at least one Xero organization

## Development

To run in development mode with auto-reload:
```bash
uvicorn app.main:app --reload
```

## License

This project is provided as-is for educational and development purposes.

## Resources

## Xero MCP Server Integration

This application integrates with the [Xero MCP Server](https://github.com/XeroAPI/xero-mcp-server) to fetch data from Xero. The MCP server:

- Provides a standardized interface to Xero's API
- Handles authentication via bearer tokens
- Supports comprehensive Xero operations (invoices, accounts, contacts, payroll, etc.)

The MCP client (`app/mcp_client.py`) communicates with the MCP server via stdio using the JSON-RPC 2.0 protocol.

## Related Projects

- [Xero MCP Server](https://github.com/XeroAPI/xero-mcp-server) - Official Xero MCP Server
- [Xero API Documentation](https://developer.xero.com/documentation)
- [Xero Python SDK](https://github.com/XeroAPI/xero-python)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/) - MCP specification

