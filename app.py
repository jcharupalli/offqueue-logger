import os
import json
import logging
from flask import Flask, request, make_response
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError
import requests

# Setup
app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Environment Variables (make sure to set them in Render)
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]               # e.g. https://yourdomain.atlassian.net
JIRA_EMAIL = os.environ["JIRA_EMAIL"]                     # e.g. your-email@domain.com
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]             # Jira API token
JIRA_PROJECT_KEY = os.environ["JIRA_PROJECT_KEY"]         # e.g. ENGLOG

client = WebClient(token=SLACK_BOT_TOKEN)
verifier = SignatureVerifier(signing_secret=SLACK_SIGNING_SECRET)

# Route for Slack Events
@app.route("/slack/events", methods=["POST"])
def slack_events():
    if not verifier.is_valid_request(request.get_data(), request.headers):
        logger.warning("Invalid Slack signature")
        return make_response("Invalid request", 403)

    payload = request.form
    if "payload" in payload:
        data = json.loads(payload["payload"])
        logger.debug(f"Slack payload type: {data.get('type')}")

        # Modal submission
        if data["type"] == "view_submission":
            user = data["user"]["username"]
            values = data["view"]["state"]["values"]
            category = values["category_block"]["category_action"]["selected_option"]["value"]
            duration = values["duration_block"]["duration_action"]["value"]
            description = values["desc_block"]["desc_action"]["value"]
            log_entry = f"*{category}* | {duration} | {description}"

            logger.info(f"View submitted by {user}: {log_entry}")
            post_comment_to_jira(user, category, log_entry)
            return make_response("", 200)

    # Slash command
    if payload.get("command") == "/logoffqueuework":
        trigger_id = payload.get("trigger_id")
        open_modal(trigger_id)
        return make_response("", 200)

    return make_response("", 200)

# Function to open Slack modal
def open_modal(trigger_id):
    try:
        response = client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "offqueue_modal",
                "title": {"type": "plain_text", "text": "Log Off-Queue Work"},
                "submit": {"type": "plain_text", "text": "Submit"},
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
                                {"text": {"type": "plain_text", "text": "Incident Analysis"}, "value": "Incident Analysis"},
                                {"text": {"type": "plain_text", "text": "Other"}, "value": "Other"}
                            ]
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "duration_block",
                        "label": {"type": "plain_text", "text": "Duration (e.g., 1h, 30m)"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "duration_action"
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "desc_block",
                        "label": {"type": "plain_text", "text": "Description"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "desc_action",
                            "multiline": True
                        }
                    }
                ]
            }
        )
        logger.debug("Modal opened successfully")
    except SlackApiError as e:
        logger.error(f"Error opening modal: {e.response['error']}")

# Function to post comment to Jira
def post_comment_to_jira(username, category, message):
    issue_key = f"{JIRA_PROJECT_KEY}-{get_jira_issue_number(username, category)}"
    comment_url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Content-Type": "application/json"}
    data = {"body": message}

    try:
        response = requests.post(comment_url, auth=auth, headers=headers, json=data)
        response.raise_for_status()
        logger.info(f"Logged to Jira: {issue_key}")
    except requests.RequestException as e:
        logger.error(f"Failed to post comment to Jira: {e}")

# Temporary static issue mapping (automate later)
def get_jira_issue_number(username, category):
    mapping = {
        "jcharupalli": {
            "Interviewing": 3,
            "Documentation": 4,
            "Incident Analysis": 5,
            "Other": 6
        }
    }
    return mapping.get(username, {}).get(category, 1)

# Root route
@app.route("/", methods=["GET"])
def health_check():
    return "Off-Queue Work Logger is running", 200

# Main function
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
