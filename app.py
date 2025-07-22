import os
import json
from flask import Flask, request, make_response
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
import requests
from datetime import datetime

app = Flask(__name__)

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_PROJECT_KEY = os.environ["JIRA_PROJECT_KEY"]

client = WebClient(token=SLACK_BOT_TOKEN)
verifier = SignatureVerifier(SLACK_SIGNING_SECRET)


@app.route("/slack/events", methods=["POST"])
def slack_events():
    if not verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid signature", 403)

    payload = request.form
    if "command" in payload and payload["command"] == "/logoffqueuework":
        trigger_id = payload["trigger_id"]

        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "offqueue_modal",
                "title": {"type": "plain_text", "text": "Log Off-Queue Work"},
                "submit": {"type": "plain_text", "text": "Submit"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "category_block",
                        "label": {"type": "plain_text", "text": "Category"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "category_input"
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "description_block",
                        "label": {"type": "plain_text", "text": "Description"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "description_input",
                            "multiline": True
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "duration_block",
                        "label": {"type": "plain_text", "text": "Duration (in minutes)"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "duration_input"
                        }
                    }
                ]
            }
        )
        return make_response("", 200)

    if "payload" in payload:
        data = json.loads(payload["payload"])
        if data["type"] == "view_submission" and data["view"]["callback_id"] == "offqueue_modal":
            user = data["user"]["username"]
            values = data["view"]["state"]["values"]
            category = values["category_block"]["category_input"]["value"]
            description = values["description_block"]["description_input"]["value"]
            duration = values["duration_block"]["duration_input"]["value"]

            # --- Create Jira issue ---
            jira_summary = f"[Off-Queue] {category} by {user}"
            jira_description = f"*User:* {user}\n*Category:* {category}\n*Description:* {description}\n*Duration:* {duration} minutes\n*Logged on:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            jira_response = requests.post(
                f"{JIRA_BASE_URL}/rest/api/3/issue",
                auth=(JIRA_EMAIL, JIRA_API_TOKEN),
                headers={"Content-Type": "application/json"},
                json={
                    "fields": {
                        "project": {"key": JIRA_PROJECT_KEY},
                        "summary": jira_summary,
                        "description": jira_description,
                        "issuetype": {"name": "Task"}
                    }
                }
            )

            if jira_response.status_code == 201:
                issue_key = jira_response.json().get("key")
                confirmation_text = f"✅ Logged your off-queue work in Jira as issue *{issue_key}*."
            else:
                confirmation_text = f"⚠️ Failed to create Jira issue. Please check integration. ({jira_response.status_code})"

            client.chat_postMessage(
                channel=data["user"]["id"],
                text=confirmation_text
            )

            return make_response("", 200)

    return make_response("No action taken", 200)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
