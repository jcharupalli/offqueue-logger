import os
import json
import requests
from flask import Flask, request, make_response
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.web.classes.blocks import InputBlock, PlainTextInputElement
from slack_sdk.web.classes.views import View
from slack_sdk.web.classes.elements import PlainTextInput
from slack_sdk.web.classes.objects import PlainText
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")  # e.g., https://yourdomain.atlassian.net
JIRA_PROJECT_KEY = "ENGLOG"

app = Flask(__name__)
client = WebClient(token=SLACK_BOT_TOKEN)
verifier = SignatureVerifier(signing_secret=SLACK_SIGNING_SECRET)

@app.route("/slack/events", methods=["POST"])
def slack_events():
    if not verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("invalid request", 403)

    payload = request.form
    if "command" in payload and payload["command"] == "/logoffqueuework":
        trigger_id = payload.get("trigger_id")
        user_id = payload.get("user_id")

        modal_view = {
            "type": "modal",
            "callback_id": "log_offqueue_work_modal",
            "title": {"type": "plain_text", "text": "Log Off-Queue Work"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "category_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "category_input"
                    },
                    "label": {"type": "plain_text", "text": "Category"}
                },
                {
                    "type": "input",
                    "block_id": "duration_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "duration_input"
                    },
                    "label": {"type": "plain_text", "text": "Duration (in minutes)"}
                },
                {
                    "type": "input",
                    "block_id": "description_block",
                    "element": {
                        "type": "plain_text_input",
                        "multiline": True,
                        "action_id": "description_input"
                    },
                    "label": {"type": "plain_text", "text": "Description"}
                }
            ]
        }

        client.views_open(trigger_id=trigger_id, view=modal_view)
        return make_response("", 200)

    if "payload" in payload:
        data = json.loads(payload["payload"])
        if data["type"] == "view_submission" and data["view"]["callback_id"] == "log_offqueue_work_modal":
            user = data["user"]["id"]
            values = data["view"]["state"]["values"]
            category = values["category_block"]["category_input"]["value"]
            duration = values["duration_block"]["duration_input"]["value"]
            description = values["description_block"]["description_input"]["value"]

            # Create Jira issue
            jira_url = f"{JIRA_BASE_URL}/rest/api/3/issue"
            headers = {
                "Content-Type": "application/json"
            }
            auth = (JIRA_EMAIL, JIRA_API_TOKEN)
            issue_data = {
                "fields": {
                    "project": {"key": JIRA_PROJECT_KEY},
                    "summary": f"{category} work log by Slack user {user}",
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": f"Duration: {duration} minutes\nDescription: {description}"}
                                ]
                            }
                        ]
                    },
                    "issuetype": {"name": "Task"}
                }
            }

            response = requests.post(jira_url, headers=headers, auth=auth, json=issue_data)
            if response.status_code == 201:
                issue_key = response.json()["key"]
                confirmation_msg = f"✅ Your off-queue work has been logged. Jira ticket: {issue_key}"
            else:
                confirmation_msg = f"❌ Failed to create Jira issue. Status: {response.status_code}"

            client.chat_postMessage(channel=user, text=confirmation_msg)
            return make_response("", 200)

    return make_response("no action", 200)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
