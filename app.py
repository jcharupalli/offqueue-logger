import os
import logging
from flask import Flask, request, make_response, jsonify
from slack_sdk.web import WebClient
from slack_sdk.signature import SignatureVerifier
import requests
import datetime

# Init
app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Slack Setup
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
client = WebClient(token=SLACK_BOT_TOKEN)
verifier = SignatureVerifier(signing_secret=SLACK_SIGNING_SECRET)

# Jira Setup
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_PROJECT_KEY = os.environ["JIRA_PROJECT_KEY"]

def get_jira_issue_key(user_id, category):
    issue_summary = f"[{user_id}] Off-Queue Log - {category}"
    search_url = f"{JIRA_BASE_URL}/rest/api/3/search"
    headers = {"Content-Type": "application/json"}
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    jql = f'project="{JIRA_PROJECT_KEY}" AND summary ~ "{issue_summary}" ORDER BY created DESC'

    resp = requests.get(search_url, headers=headers, params={"jql": jql}, auth=auth)
    data = resp.json()
    logger.debug(f"Jira Search Response: {data}")
    if data.get("issues"):
        return data["issues"][0]["key"]
    return None

def add_comment_to_jira(issue_key, comment):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    headers = {"Content-Type": "application/json"}
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    data = {"body": comment}
    response = requests.post(url, json=data, headers=headers, auth=auth)
    logger.debug(f"Jira Comment Response: {response.status_code} {response.text}")
    return response.status_code == 201

@app.route("/", methods=["GET"])
def home():
    return "Slack OffQueue Logger is running!"

@app.route("/slack/command", methods=["POST"])
def command():
    if not verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid request", 403)

    trigger_id = request.form["trigger_id"]
    user_id = request.form["user_id"]

    modal = {
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
                    "action_id": "category_input",
                    "options": [
                        {"text": {"type": "plain_text", "text": "Interviewing"}, "value": "Interviewing"},
                        {"text": {"type": "plain_text", "text": "Documentation"}, "value": "Documentation"},
                        {"text": {"type": "plain_text", "text": "Meetings"}, "value": "Meetings"},
                        {"text": {"type": "plain_text", "text": "Other"}, "value": "Other"},
                    ]
                }
            },
            {
                "type": "input",
                "block_id": "desc_block",
                "label": {"type": "plain_text", "text": "Work Description"},
                "element": {"type": "plain_text_input", "action_id": "desc_input", "multiline": True}
            },
            {
                "type": "input",
                "block_id": "duration_block",
                "label": {"type": "plain_text", "text": "Time Spent (in minutes)"},
                "element": {"type": "plain_text_input", "action_id": "duration_input"}
            }
        ]
    }

    client.views_open(trigger_id=trigger_id, view=modal)
    return make_response("", 200)

@app.route("/slack/interactions", methods=["POST"])
def interactions():
    if not verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid request", 403)

    payload = request.form["payload"]
    data = json.loads(payload)
    logger.debug(f"Interaction Payload: {data}")

    if data["type"] == "view_submission":
        user_id = data["user"]["id"]
        values = data["view"]["state"]["values"]
        category = values["category_block"]["category_input"]["selected_option"]["value"]
        desc = values["desc_block"]["desc_input"]["value"]
        duration = values["duration_block"]["duration_input"]["value"]

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        comment = f"*Date:* {timestamp}\n*User:* <@{user_id}>\n*Category:* {category}\n*Description:* {desc}\n*Duration:* {duration} min"

        issue_key = get_jira_issue_key(user_id, category)
        if issue_key:
            success = add_comment_to_jira(issue_key, comment)
            if not success:
                logger.error("Failed to post comment to Jira.")
        else:
            logger.warning("No Jira issue found for user/category.")

        return make_response("", 200)

    return make_response("", 200)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
