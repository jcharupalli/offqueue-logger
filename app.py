import os
import json
import logging
from flask import Flask, request, jsonify, make_response
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.models.views import View
import requests

# Setup
app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Slack Setup
SLACK_BOT_TOKEN = os.environ['SLACK_BOT_TOKEN']
SLACK_SIGNING_SECRET = os.environ['SLACK_SIGNING_SECRET']
slack_client = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

# Jira Setup
JIRA_BASE_URL = os.environ['JIRA_BASE_URL']
JIRA_EMAIL = os.environ['JIRA_EMAIL']
JIRA_API_TOKEN = os.environ['JIRA_API_TOKEN']
JIRA_PROJECT_KEY = os.environ['JIRA_PROJECT_KEY']
jira_auth = (JIRA_EMAIL, JIRA_API_TOKEN)

# Memory cache for category+user ticket mapping (could be replaced with DB later)
jira_issues_cache = {}

@app.route("/", methods=["GET"])
def home():
    return "Off-Queue Logger is running!"

@app.route("/slack/events", methods=["POST"])
def slack_events():
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid signature", 403)

    payload = request.form or json.loads(request.data)
    logging.debug(f"Slack event received: {payload}")

    if "command" in payload and payload["command"] == "/logoffqueuework":
        trigger_id = payload["trigger_id"]
        user_id = payload["user_id"]
        open_modal(trigger_id, user_id)
        return make_response("", 200)

    if payload.get("type") == "view_submission":
        return handle_modal_submission(payload)

    return make_response("", 200)

def open_modal(trigger_id, user_id):
    modal = {
        "type": "modal",
        "callback_id": "log_modal",
        "title": {"type": "plain_text", "text": "Log Off-Queue Work"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "blocks": [
            {
                "type": "input",
                "block_id": "category",
                "label": {"type": "plain_text", "text": "Category"},
                "element": {
                    "type": "static_select",
                    "action_id": "category_input",
                    "options": [
                        {"text": {"type": "plain_text", "text": "Interviewing"}, "value": "Interviewing"},
                        {"text": {"type": "plain_text", "text": "Documentation"}, "value": "Documentation"},
                        {"text": {"type": "plain_text", "text": "Dev Tooling"}, "value": "Dev Tooling"},
                        {"text": {"type": "plain_text", "text": "Other"}, "value": "Other"},
                    ]
                }
            },
            {
                "type": "input",
                "block_id": "time",
                "label": {"type": "plain_text", "text": "Time Spent (in mins)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "time_input"
                }
            },
            {
                "type": "input",
                "block_id": "description",
                "label": {"type": "plain_text", "text": "Description"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "description_input",
                    "multiline": True
                }
            }
        ]
    }

    slack_client.views_open(trigger_id=trigger_id, view=modal)

def handle_modal_submission(payload):
    user = payload["user"]["id"]
    state_values = payload["view"]["state"]["values"]

    category = state_values["category"]["category_input"]["selected_option"]["value"]
    time_spent = state_values["time"]["time_input"]["value"]
    description = state_values["description"]["description_input"]["value"]

    logging.info(f"Modal submitted by {user}: {category}, {time_spent} mins, {description}")

    try:
        issue_key = get_or_create_jira_issue(user, category)
        logging.info(f"Jira issue key: {issue_key}")
        comment = f"*Time:* {time_spent} mins\n*Description:* {description}"
        post_comment_to_jira(issue_key, comment)
    except Exception as e:
        logging.error(f"Jira submission failed: {str(e)}")

    return make_response("", 200)

def get_or_create_jira_issue(user_id, category):
    key = f"{user_id}-{category}"
    if key in jira_issues_cache:
        return jira_issues_cache[key]

    slack_user_info = slack_client.users_info(user=user_id)
    real_name = slack_user_info["user"]["real_name"]
    summary = f"{category} logs for {real_name}"

    # Check if issue exists
    search_url = f"{JIRA_BASE_URL}/rest/api/3/search"
    jql = f'project="{JIRA_PROJECT_KEY}" AND summary ~ "{summary}"'
    logging.debug(f"Searching Jira for issue: {jql}")

    search_response = requests.get(
        search_url,
        headers={"Accept": "application/json"},
        auth=jira_auth,
        params={"jql": jql}
    )

    search_response.raise_for_status()
    data = search_response.json()

    if data.get("issues"):
        issue_key = data["issues"][0]["key"]
        jira_issues_cache[key] = issue_key
        logging.info(f"Found existing Jira issue: {issue_key}")
        return issue_key

    # Create issue if not found
    create_url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": f"Auto-created issue for {category} logs by {real_name}",
            "issuetype": {"name": "Task"}
        }
    }

    logging.debug(f"Creating Jira issue with payload: {json.dumps(payload)}")

    create_response = requests.post(create_url, json=payload, auth=jira_auth)
    create_response.raise_for_status()
    issue_key = create_response.json()["key"]
    jira_issues_cache[key] = issue_key
    logging.info(f"Created new Jira issue: {issue_key}")
    return issue_key

def post_comment_to_jira(issue_key, comment):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    payload = {"body": comment}
    headers = {"Content-Type": "application/json"}

    logging.debug(f"Posting comment to {issue_key}: {comment}")

    response = requests.post(url, headers=headers, json=payload, auth=jira_auth)
    try:
        response.raise_for_status()
        logging.info(f"Posted comment to Jira issue: {issue_key}")
    except requests.HTTPError as e:
        logging.error(f"Failed to post comment to Jira: {e.response.status_code} - {e.response.text}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
