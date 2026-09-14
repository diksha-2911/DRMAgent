# DRMAgent

**DRMAgent** is an autonomous donor relationship management system that connects Gmail conversations with structured donor intelligence and an agent-driven decision workflow.

The project is designed around a simple principle:

> **Use LLMs for interpretation and planning, while keeping sensitive approval decisions and application control deterministic in code.**

---

## What it does

DRMAgent can:

* Authenticate an NGO user through the application login flow
* Connect to Gmail through Google OAuth 2.0 with PKCE
* Load donor records from a CSV file
* Discover Gmail conversations associated with each donor
* Normalize email content and build chronological conversation summaries
* Extract a structured `DonorProfile` using Strands agents
* Classify the appropriate donor action
* Generate an executable `ActionPlan`
* Apply deterministic human-approval rules for sensitive actions
* Generate donor email drafts
* Send emails through Gmail when human approval is not required
* Monitor Gmail for new incoming donor messages

The supported DRM actions are:

1. **Human Review**
2. **Thank You**
3. **Follow-Up**
4. **Outreach**
5. **Wait**

---

## Architecture

```text
                         ┌─────────────────────┐
                         │      NGO User       │
                         └──────────┬──────────┘
                                    │
                              FastAPI Login
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Google OAuth 2.0  │
                         │       + PKCE        │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Gmail Service    │
                         │                     │
                         │ Search / Parse /    │
                         │ Reply / Send        │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │    Gmail Watcher    │
                         │   Polling Worker    │
                         └──────────┬──────────┘
                                    │
                           Incoming donor email
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Donor Resolver /    │
                         │   Orchestrator      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Conversation History│
                         │   + Normalization   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Strands Profile     │
                         │ Pipeline            │
                         │                     │
                         │ Consolidate →       │
                         │ Extract Profile     │
                         └──────────┬──────────┘
                                    │
                              DonorProfile
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ DRM Decision Layer  │
                         │                     │
                         │ Classify → Plan     │
                         └──────────┬──────────┘
                                    │
                              ActionPlan
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Deterministic Human │
                         │ Approval Policy     │
                         └──────────┬──────────┘
                              ┌─────┴─────┐
                              │           │
                       Approval needed   Safe
                              │           │
                              ▼           ▼
                       Human Review   Execution Agent
                                              │
                                         Email Draft
                                              │
                                              ▼
                                         Gmail Send
```

### Design principle

The profile pipeline converts Gmail-specific communication into structured donor information.

The DRM decision layer then operates on those structured contracts rather than directly depending on Gmail implementation details.

LLMs are responsible for:

* Understanding conversations
* Extracting donor information
* Classifying donor intent
* Creating action plans
* Generating email drafts

Application code remains responsible for:

* Authentication
* Gmail access
* Deterministic approval rules
* Session handling
* Email execution
* Workflow orchestration

---

# Directory Structure

```text
DRMAgent/
│
├── drmagent/
│   ├── __init__.py
│   ├── agent.py
│   ├── config.py
│   ├── main.py
│   ├── models.py
│   ├── orchestrator.py
│   │
│   ├── gmail/
│   │   ├── auth.py
│   │   └── service.py
│   │
│   ├── profile/
│   │   ├── agents.py
│   │   └── service.py
│   │
│   ├── drm/
│   │   ├── agent.py
│   │   ├── approval.py
│   │   ├── execution_agent.py
│   │   └── tools.py
│   │
│   └── worker/
│       └── gmail_watcher.py
│
├── donors.csv
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

# Technology Stack

* **Python**
* **FastAPI** — REST API and Swagger/OpenAPI interface
* **Uvicorn** — ASGI server
* **Google Gmail API** — Gmail access and email sending
* **Google OAuth 2.0 + PKCE** — authentication and authorization
* **Strands Agents** — agent orchestration and structured outputs
* **Groq** — LLM inference through its OpenAI-compatible API
* **Pydantic** — structured data validation
* **BeautifulSoup** — HTML email parsing
* **CSV** — donor data input

---

# Prerequisites

Before running DRMAgent, make sure you have:

* Python 3.10+ installed
* A Google Cloud project
* Gmail API enabled in Google Cloud
* A Google OAuth 2.0 client
* A Groq API key
* Access to a Gmail account that can be authorized by the application

---

# Installation

## 1. Clone the repository

```bash
git clone https://github.com/diksha-2911/DRMAgent.git
cd DRMAgent
```

---

## 2. Create a virtual environment

### Windows

Using the Python launcher:

```powershell
py -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\Activate.ps1
```

If `py` is unavailable:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## 3. Install dependencies

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install project dependencies:

```bash
pip install -r requirements.txt
```

---

# Environment Configuration

Create a `.env` file in the root directory.

```env
# --------------------------------------------------
# Application Authentication
# --------------------------------------------------

NGO_USERNAME=ngo_admin
NGO_PASSWORD=replace-with-a-strong-password


# --------------------------------------------------
# Google OAuth
# --------------------------------------------------

GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback


# --------------------------------------------------
# Groq
# --------------------------------------------------

GROQ_API_KEY=your-groq-api-key

GROQ_BASE_URL=https://api.groq.com/openai/v1


# --------------------------------------------------
# Gmail Watcher
# --------------------------------------------------

GMAIL_POLL_INTERVAL_SECONDS=30


# --------------------------------------------------
# LLM Models
# --------------------------------------------------

CONSOLIDATION_MODEL=openai/gpt-oss-20b

EXTRACTION_MODEL=openai/gpt-oss-120b

CLASSIFICATION_MODEL=openai/gpt-oss-20b

PLANNING_MODEL=openai/gpt-oss-120b

EXECUTION_MODEL=openai/gpt-oss-120b


# --------------------------------------------------
# Processing Limits
# --------------------------------------------------

MAX_THREADS_PER_DONOR=20

MAX_MESSAGES_PER_THREAD=30

MAX_CONVERSATION_CHARS=50000


# --------------------------------------------------
# Human Approval
# --------------------------------------------------

DONATION_APPROVAL_THRESHOLD=100000
```

The application loads these values through `drmagent/config.py`.

**Never commit `.env` to Git.**

---

# Google Gmail OAuth Setup

DRMAgent uses Google OAuth to access the Gmail account.

## Step 1 — Create a Google Cloud project

Open Google Cloud Console and either create a new project or select an existing project.

## Step 2 — Enable Gmail API

Navigate to:

```text
Google Cloud Console
→ APIs & Services
→ Library
→ Gmail API
→ Enable
```

## Step 3 — Configure OAuth consent screen

Configure the OAuth consent screen for the application.

Add the required Gmail scopes used by the application.

## Step 4 — Create OAuth credentials

Create an OAuth 2.0 Client ID.

For local development, configure the redirect URI as:

```text
http://localhost:8000/auth/google/callback
```

## Step 5 — Add credentials to `.env`

```env
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret

GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

The application generates the authorization URL and uses PKCE during the authorization-code exchange.

---

# Donor CSV

Donor records are loaded from a CSV file.

The minimum required columns are:

```csv
donor_id,email,name
D001,donor@example.com,Example Donor
D002,another@example.com,Another Donor
```

### Required fields

| Field      | Required | Description             |
| ---------- | -------- | ----------------------- |
| `donor_id` | Yes      | Unique donor identifier |
| `email`    | Yes      | Donor email address     |
| `name`     | Yes       | Donor's display name    |

The donor email is used to associate Gmail conversations with the donor record.

---

# Running the Application

Start the FastAPI server:

```bash
uvicorn drmagent.main:app --reload
```

The application will be available at:

```text
http://localhost:8000
```

Swagger API documentation:

```text
http://localhost:8000/docs
```

---

# Development Commands

Create environment:

```bash
python -m venv .venv
```

Activate on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Activate on macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn drmagent.main:app --reload
```

Open Swagger:

```text
http://localhost:8000/docs
```

---

# License

This project is licensed under the **MIT License**.

See [`LICENSE`](LICENSE) for the complete license text.

---

# Disclaimer

DRMAgent is an engineering prototype for donor relationship automation.

Automated interpretation, decision-making and email sending can have real-world consequences. Before using the system with real donor information or enabling autonomous communication in production, thoroughly review and harden authentication, authorization, data storage, approval workflows, audit logging, idempotency, privacy controls and email-sending safeguards.
