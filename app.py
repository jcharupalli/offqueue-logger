import os
import json
from flask import Flask, request, make_response
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
import requests

app = Flask(__name__)

# Slack tokens
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")

# Jira configuration
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")  # e.g., you@example.com
JIRA_PROJECT_KEY = "ENGLOG"
JIRA_URL = "https://offqueuework.atlassian.net"

# Slack setup
client = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

@app.route("/slack/events", methods=["POST"])
def slack_events():
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid request signature", 403)

    payload = request.form
    if "payload" in payload:
        data = json.loads(payload["payload"])
        if data["type"] == "view_submission":
            user = data["user"]["username"]
            state_values = data["view"]["state"]["values"]
            category = state_values["category_block"]["category_action"]["selected_option"]["value"]
            duration = state_values["duration_block"]["duration_action"]["value"]
            description = state_values["description_block"]["description_action"]["value"]

            summary = f"[{category}] Off-Queue Work by {user}"
            jira_description = f"*Category:* {category}\n*Duration:* {duration} minutes\n*Description:* {description}\n*Slack User:* {user}"

            issue_key = create_jira_issue(summary, jira_description)

            # Slack confirmation
            client.chat_postMessage(
                channel=data["user"]["id"],
                text=f"✅ Your off-queue work log has been recorded.\nJira ticket: *{issue_key}*"
            )

            return make_response("", 200)

    elif payload.get("command") == "/logoffqueuework":
        trigger_id = payload.get("trigger_id")
        open_modal(trigger_id)
        return make_response("", 200)

    return make_response("", 404)

def open_modal(trigger_id):
    modal_view = {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Log Off-Queue Work"},
        "callback_id": "offqueue_modal",
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "category_block",
                "label": {"type": "plain_text", "text": "Category"},
                "element": {
                    "type": "static_select",
                    "action_id": "category_action",
                    "options": [
                        {"text": {"type": "plain_text", "text": "Interviewing"}, "value": "Interviewing"},
                        {"text": {"type": "plain_text", "text": "Documentation"}, "value": "Documentation"},
                        {"text": {"type": "plain_text", "text": "Meetings"}, "value": "Meetings"},
                        {"text": {"type": "plain_text", "text": "Other"}, "value": "Other"}
                    ]
                }
            },
            {
                "type": "input",
                "block_id": "duration_block",
                "label": {"type": "plain_text", "text": "Duration (in minutes)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "duration_action"
                }
            },
            {
                "type": "input",
                "block_id": "description_block",
                "label": {"type": "plain_text", "text": "Description"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "description_action",
                    "multiline": True
                }
            }
        ]
    }

    client.views_open(trigger_id=trigger_id, view=modal_view)

def create_jira_issue(summary, description):
    url = f"{JIRA_URL}/rest/api/3/issue"
    headers = {
        "Content-Type": "application/json"
    }
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "text": description,
                                "type": "text"
                            }
                        ]
                    }
                ]
            },
            "issuetype": {"name": "Task"}
        }
    }

    response = requests.post(url, json=payload, headers=headers, auth=auth)
    if response.status_code == 201:
        return response.json()["key"]
    else:
        print("Jira Issue Creation Failed:", response.text)
        return "Jira creation failed"

if __name__ == "__main__":
    app.run(port=3000)
