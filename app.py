import os
import json
import datetime
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_USER_EMAIL = os.getenv("JIRA_USER_EMAIL")
GOOGLE_SHEET_WEBHOOK_URL = os.getenv("GOOGLE_SHEET_WEBHOOK_URL")

flask_app = Flask(__name__)
slack_client = WebClient(token=SLACK_BOT_TOKEN)
verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

@flask_app.route("/", methods=["GET"])
def health():
    return "Off-queue Work Logger is running.", 200

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    if not verifier.is_valid_request(request.get_data(), request.headers):
        return "Invalid request", 403

    payload = request.form
    if payload.get("command") == "/logoffqueuework":
        trigger_id = payload.get("trigger_id")
        user_id = payload.get("user_id")
        open_modal(trigger_id, user_id)
        return "", 200

    return "No handler for this command", 404

def open_modal(trigger_id, user_id):
    try:
        slack_client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "offqueue_modal",
                "title": {"type": "plain_text", "text": "Log Off-Queue Work"},
                "submit": {"type": "plain_text", "text": "Submit"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "private_metadata": user_id,
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "category",
                        "element": {
                            "type": "static_select",
                            "action_id": "selected_category",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Select a category",
                            },
                            "options": [
                                {"text": {"type": "plain_text", "text": "Interviewing"}, "value": "Interviewing"},
                                {"text": {"type": "plain_text", "text": "Documentation"}, "value": "Documentation"},
                                {"text": {"type": "plain_text", "text": "Tech Debt"}, "value": "Tech Debt"},
                                {"text": {"type": "plain_text", "text": "Learning"}, "value": "Learning"},
                                {"text": {"type": "plain_text", "text": "Other"}, "value": "Other"},
                            ],
                        },
                        "label": {"type": "plain_text", "text": "Category"},
                    },
                    {
                        "type": "input",
                        "block_id": "description",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "input_description",
                            "multiline": True,
                        },
                        "label": {"type": "plain_text", "text": "Description"},
                    },
                    {
                        "type": "input",
                        "block_id": "duration",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "input_duration",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Duration in minutes (e.g., 45)",
                            },
                        },
                        "label": {"type": "plain_text", "text": "Duration (in minutes)"},
                    },
                ],
            },
        )
    except SlackApiError as e:
        print(f"Error opening modal: {e}")

@flask_app.route("/slack/interactions", methods=["POST"])
def handle_interactions():
    if not verifier.is_valid_request(request.get_data(), request.headers):
        return "Invalid request", 403

    payload = json.loads(request.form["payload"])
    if payload["type"] == "view_submission":
        user_id = payload["user"]["id"]
        view = payload["view"]
        state = view["state"]["values"]
        category = state["category"]["selected_category"]["selected_option"]["value"]
        description = state["description"]["input_description"]["value"]
        duration = state["duration"]["input_duration"]["value"]

        log_to_google_sheet(user_id, category, description, duration)
        add_comment_to_jira(user_id, category, description, duration)

        return jsonify({"response_action": "clear"})

    return "", 200

def log_to_google_sheet(user_id, category, description, duration):
    payload = {
        "user_id": user_id,
        "category": category,
        "description": description,
        "duration": duration,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    try:
        res = requests.post(GOOGLE_SHEET_WEBHOOK_URL, json=payload)
        res.raise_for_status()
    except Exception as e:
        print(f"Failed to log to Google Sheet: {e}")

def add_comment_to_jira(user_id, category, description, duration):
    summary = f"Off-queue Work - {category}"
    comment = f"*User:* <@{user_id}>\n*Category:* {category}\n*Duration:* {duration} minutes\n*Description:* {description}\n*Timestamp:* {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"

    jql = f'project = {JIRA_PROJECT_KEY} AND summary ~ "{summary}" AND assignee = {user_id} AND statusCategory != Done ORDER BY created DESC'
    search_url = f"{JIRA_BASE_URL}/rest/api/2/search"
    auth = (JIRA_USER_EMAIL, JIRA_API_TOKEN)

    try:
        response = requests.get(search_url, headers={"Content-Type": "application/json"}, params={"jql": jql}, auth=auth)
        issues = response.json().get("issues", [])
        if issues:
            issue_key = issues[0]["key"]
            comment_url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/comment"
            requests.post(comment_url, json={"body": comment}, auth=auth)
        else:
            print("No matching JIRA issue found to comment on.")
    except Exception as e:
        print(f"Failed to update Jira: {e}")

# ✅ Ensure the server starts properly on Render (or any host)
if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
