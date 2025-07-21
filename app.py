from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
import os
import requests
from dotenv import load_dotenv

load_dotenv()  # Load .env if running locally

# Slack setup
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

# Jira setup
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")              # Your Atlassian email
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")      # Jira API token
JIRA_PROJECT_KEY = "ENGLOG"                            # Your Jira project key
JIRA_BASE_URL = "https://yourdomain.atlassian.net"     # Replace with your Jira Cloud base URL

@app.command("/logoffqueuework")
def handle_log_command(ack, body, client):
    ack()

    user_id = body["user_id"]

    # Open modal for user input
    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "log_modal",
            "title": {"type": "plain_text", "text": "Log Off-Queue Work"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "category",
                    "label": {"type": "plain_text", "text": "Work Category"},
                    "element": {
                        "type": "static_select",
                        "action_id": "input",
                        "placeholder": {"type": "plain_text", "text": "Select category"},
                        "options": [
                            {"text": {"type": "plain_text", "text": "Documentation"}, "value": "Documentation"},
                            {"text": {"type": "plain_text", "text": "Interviewing"}, "value": "Interviewing"},
                            {"text": {"type": "plain_text", "text": "Learning"}, "value": "Learning"},
                            {"text": {"type": "plain_text", "text": "Misc"}, "value": "Misc"},
                        ],
                    },
                },
                {
                    "type": "input",
                    "block_id": "duration",
                    "label": {"type": "plain_text", "text": "Duration (e.g. 1h, 30m)"},
                    "element": {"type": "plain_text_input", "action_id": "input"},
                },
                {
                    "type": "input",
                    "block_id": "description",
                    "label": {"type": "plain_text", "text": "Work Description"},
                    "element": {"type": "plain_text_input", "action_id": "input", "multiline": True},
                },
            ],
        }
    )

@app.view("log_modal")
def handle_modal_submission(ack, body, view, client):
    ack()

    user_id = body["user"]["id"]
    user_info = client.users_info(user=user_id)
    user_email = user_info["user"]["profile"]["email"]

    category = view["state"]["values"]["category"]["input"]["selected_option"]["value"]
    duration = view["state"]["values"]["duration"]["input"]["value"]
    description = view["state"]["values"]["description"]["input"]["value"]

    summary = f"{category} - {duration} by {user_email}"
    issue_description = f"*Engineer:* {user_email}\n*Category:* {category}\n*Duration:* {duration}\n*Description:* {description}"

    # Create Jira ticket
    jira_url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    headers = {
        "Content-Type": "application/json"
    }
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": issue_description,
            "issuetype": {"name": "Task"}
        }
    }

    response = requests.post(jira_url, json=payload, headers=headers, auth=auth)

    if response.status_code == 201:
        issue_key = response.json().get("key")
        client.chat_postMessage(channel=user_id, text=f"✅ Off-queue work logged successfully and Jira ticket `{issue_key}` created.")
    else:
        client.chat_postMessage(channel=user_id, text="❌ Failed to create Jira ticket. Please try again later.")

# Flask route for Slack
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

# Health check
@flask_app.route("/", methods=["GET"])
def home():
    return "Slack + Jira app is running!"

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
