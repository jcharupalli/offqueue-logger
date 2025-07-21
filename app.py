import os
import json
import logging
from flask import Flask, request, make_response
from slack_sdk.web import WebClient
from slack_sdk.signature import SignatureVerifier
import requests

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Load environment variables
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]

slack_client = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)


@app.route("/slack/events", methods=["POST"])
def slack_events():
    logging.debug("Incoming Slack request")

    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        logging.warning("Invalid Slack signature")
        return make_response("Invalid signature", 403)

    payload = request.form
    if "payload" in payload:
        data = json.loads(payload["payload"])
        logging.debug(f"Slack payload type: {data.get('type')}")

        if data["type"] == "view_submission":
            user = data["user"]["username"]
            values = data["view"]["state"]["values"]
            category = values["category_block"]["category_action"]["selected_option"]["value"]
            time_spent = values["time_block"]["time_action"]["value"]
            description = values["desc_block"]["desc_action"]["value"]

            logging.info(f"View submitted by {user}: {category}, {time_spent}, {description}")

            # Construct Jira issue key
            issue_key = f"ENGLOG-{get_issue_number_for_user_and_category(user, category)}"

            comment = f"*Off-Queue Log:*\n• *User:* {user}\n• *Category:* {category}\n• *Time Spent:* {time_spent}\n• *Description:* {description}"

            # Post to Jira
            post_comment_to_jira(issue_key, comment)

            return make_response("", 200)  # Must respond quickly!

    elif payload.get("command") == "/logoffqueuework":
        trigger_id = payload["trigger_id"]

        modal = {
            "type": "modal",
            "title": {"type": "plain_text", "text": "Log Off-Queue Work"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "callback_id": "offqueue_modal",
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
                            {"text": {"type": "plain_text", "text": "Training"}, "value": "Training"},
                        ],
                    },
                },
                {
                    "type": "input",
                    "block_id": "time_block",
                    "label": {"type": "plain_text", "text": "Time Spent (e.g. 1h 30m)"},
                    "element": {"type": "plain_text_input", "action_id": "time_action"},
                },
                {
                    "type": "input",
                    "block_id": "desc_block",
                    "label": {"type": "plain_text", "text": "Description"},
                    "element": {"type": "plain_text_input", "action_id": "desc_action"},
                },
            ],
        }

        slack_client.views_open(trigger_id=trigger_id, view=modal)
        logging.debug("Modal opened successfully")
        return make_response("", 200)

    logging.warning("Unhandled Slack event type")
    return make_response("", 200)


def get_issue_number_for_user_and_category(user, category):
    # Placeholder: you can hardcode mapping for now
    if user == "jyothi" and category == "Interviewing":
        return 1  # e.g., ENGLOG-1
    elif user == "jyothi" and category == "Documentation":
        return 2
    return 3  # fallback


def post_comment_to_jira(issue_key, comment):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Content-Type": "application/json"}
    data = {"body": comment}

    try:
        response = requests.post(url, headers=headers, auth=auth, json=data)
        response.raise_for_status()
        logging.info(f"Comment added to {issue_key}")
    except Exception as e:
        logging.error(f"Failed to post comment to Jira: {str(e)}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    logging.info(f"Starting server on port {port}")
    app.run(host="0.0.0.0", port=port)
