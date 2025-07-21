import os
import json
import logging
from flask import Flask, request, make_response
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
import requests
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Environment variables
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")  # e.g., https://your-domain.atlassian.net
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY")

app = Flask(__name__)
client = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

@app.route("/", methods=["GET"])
def index():
    return "Slack Jira Logger is running!", 200

@app.route("/slack/events", methods=["POST"])
def slack_events():
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid signature", 403)

    payload = request.form
    if payload.get("command") == "/logoffqueuework":
        trigger_id = payload.get("trigger_id")
        user_id = payload.get("user_id")
        open_modal(trigger_id, user_id)
        return make_response("", 200)

    return make_response("No action taken", 200)

def open_modal(trigger_id, user_id):
    try:
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
                        "block_id": "category",
                        "element": {
                            "type": "static_select",
                            "action_id": "category_select",
                            "placeholder": {"type": "plain_text", "text": "Select a category"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "Documentation"}, "value": "Documentation"},
                                {"text": {"type": "plain_text", "text": "Interviewing"}, "value": "Interviewing"},
                                {"text": {"type": "plain_text", "text": "Learning"}, "value": "Learning"},
                                {"text": {"type": "plain_text", "text": "Other"}, "value": "Other"}
                            ]
                        },
                        "label": {"type": "plain_text", "text": "Category"},
                    },
                    {
                        "type": "input",
                        "block_id": "duration",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "duration_input",
                            "placeholder": {"type": "plain_text", "text": "e.g., 1h, 30m"}
                        },
                        "label": {"type": "plain_text", "text": "Duration"},
                    },
                    {
                        "type": "input",
                        "block_id": "description",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "description_input",
                            "multiline": True
                        },
                        "label": {"type": "plain_text", "text": "Description"},
                    }
                ]
            }
        )
    except Exception as e:
        logging.error(f"Failed to open modal: {e}")

@app.route("/slack/interactions", methods=["POST"])
def slack_interactions():
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid signature", 403)

    payload = json.loads(request.form["payload"])
    if payload["type"] == "view_submission" and payload["view"]["callback_id"] == "offqueue_modal":
        user_id = payload["user"]["id"]
        values = payload["view"]["state"]["values"]
        category = values["category"]["category_select"]["selected_option"]["value"]
        duration = values["duration"]["duration_input"]["value"]
        description = values["description"]["description_input"]["value"]

        user_info = client.users_info(user=user_id)
        display_name = user_info["user"]["real_name"]
        email = user_info["user"]["profile"]["email"]

        jira_comment = f"*User:* {display_name}\n*Category:* {category}\n*Duration:* {duration}\n*Description:* {description}\n*Timestamp:* {datetime.now().isoformat()}"

        try:
            issue_key = get_or_create_jira_issue(email, category)
            if issue_key:
                post_jira_comment(issue_key, jira_comment)
            else:
                logging.error("Jira issue creation failed.")
        except Exception as e:
            logging.exception(f"Error handling Jira ticket: {e}")

        return make_response("", 200)

    return make_response("", 200)

def get_or_create_jira_issue(user_email, category):
    summary = f"Off-Queue Work Log: {category} - {user_email}"
    search_url = f"{JIRA_BASE_URL}/rest/api/3/search"
    headers = {
        "Authorization": f"Basic {get_jira_auth_token()}",
        "Content-Type": "application/json"
    }
    jql = f'project = "{JIRA_PROJECT_KEY}" AND summary ~ "{summary}" AND reporter = "{user_email}"'

    logging.debug(f"Searching for Jira issue with JQL: {jql}")
    response = requests.get(search_url, headers=headers, params={"jql": jql})
    logging.debug(f"Search response: {response.status_code} - {response.text}")

    if response.status_code == 200:
        issues = response.json().get("issues", [])
        if issues:
            return issues[0]["key"]

    # Create issue if not found
    create_url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": f"Off-queue work log issue for {user_email} in category {category}.",
            "issuetype": {"name": "Task"},
            "reporter": {"emailAddress": user_email}
        }
    }

    logging.debug(f"Creating Jira issue with payload: {json.dumps(payload)}")
    create_response = requests.post(create_url, headers=headers, json=payload)
    logging.debug(f"Issue creation response: {create_response.status_code} - {create_response.text}")

    if create_response.status_code == 201:
        return create_response.json()["key"]
    return None

def post_jira_comment(issue_key, comment):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    headers = {
        "Authorization": f"Basic {get_jira_auth_token()}",
        "Content-Type": "application/json"
    }
    data = {"body": comment}
    logging.debug(f"Posting comment to {issue_key}: {comment}")
    response = requests.post(url, headers=headers, json=data)
    logging.debug(f"Comment response: {response.status_code} - {response.text}")

def get_jira_auth_token():
    import base64
    token = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
    return base64.b64encode(token.encode()).decode()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
