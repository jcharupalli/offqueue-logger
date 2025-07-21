import os
import logging
from flask import Flask, request, make_response
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.models.views import View
from slack_sdk.errors import SlackApiError
import requests

# Logging setup
logging.basicConfig(level=logging.DEBUG)

# Flask app
flask_app = Flask(__name__)

# Load environment variables
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]

# Slack setup
client = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

# Static mapping for now (can be automated later)
USER_ISSUE_MAPPING = {
    "jcharupalli": "ENGLOG-3",
    # Add other user mappings here
}

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    logging.debug("Incoming Slack request")
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid signature", 403)

    payload = request.json
    logging.debug(f"Slack payload type: {payload.get('type')}")

    if payload.get("type") == "url_verification":
        return make_response(payload.get("challenge"), 200)

    if payload.get("type") == "event_callback":
        event = payload["event"]
        if event.get("type") == "app_mention" or event.get("type") == "message":
            return make_response("", 200)

    if payload.get("type") == "view_submission":
        user = payload["user"]["username"]
        values = payload["view"]["state"]["values"]
        logging.info(f"View submitted by {user}: {values}")

        try:
            category = next(iter(values["category_block"].values()))["selected_option"]["value"]
            duration = next(iter(values["duration_block"].values()))["value"]
            description = next(iter(values["description_block"].values()))["value"]

            comment = f"*Off-Queue Log*\n• Category: {category}\n• Duration: {duration}\n• Description: {description}"
            issue_key = USER_ISSUE_MAPPING.get(user)

            if not issue_key:
                logging.error(f"No Jira issue mapped for user: {user}")
                return make_response("", 200)

            jira_response = requests.post(
                f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment",
                auth=(JIRA_EMAIL, JIRA_API_TOKEN),
                headers={"Content-Type": "application/json"},
                json={"body": comment},
            )

            logging.debug(f"Jira response: {jira_response.status_code} {jira_response.text}")

            if jira_response.status_code != 201:
                logging.error(f"Failed to post comment to Jira: {jira_response.status_code}")
        except Exception as e:
            logging.error(f"Error handling view_submission: {e}")

        return make_response("", 200)

    return make_response("", 200)

@flask_app.route("/slack/command", methods=["POST"])
def slack_command():
    logging.debug("Slack command invoked")

    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid signature", 403)

    trigger_id = request.form["trigger_id"]

    modal_view = {
        "type": "modal",
        "callback_id": "offqueue_log_modal",
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
                    "placeholder": {"type": "plain_text", "text": "Select a category"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Interviewing"}, "value": "Interviewing"},
                        {"text": {"type": "plain_text", "text": "Documentation"}, "value": "Documentation"},
                        {"text": {"type": "plain_text", "text": "Learning"}, "value": "Learning"},
                        {"text": {"type": "plain_text", "text": "Meetings"}, "value": "Meetings"},
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "duration_block",
                "label": {"type": "plain_text", "text": "Duration (e.g., 30m, 1h)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "duration_action",
                    "placeholder": {"type": "plain_text", "text": "e.g., 30m or 1h"},
                },
            },
            {
                "type": "input",
                "block_id": "description_block",
                "label": {"type": "plain_text", "text": "Description"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "description_action",
                    "multiline": True,
                },
            },
        ],
    }

    try:
        response = client.views_open(trigger_id=trigger_id, view=modal_view)
        logging.debug("Modal opened successfully")
    except SlackApiError as e:
        logging.error(f"Error opening modal: {e.response['error']}")

    return make_response("", 200)

# Optional root route
@flask_app.route("/", methods=["GET"])
def home():
    return "Off-Queue Logger is running."

# Main method to run the app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)
