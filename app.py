import os
import logging
from flask import Flask, request, make_response, jsonify
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
import requests
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Slack credentials from environment
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_USER_EMAIL = os.environ.get("JIRA_USER_EMAIL")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY")  # e.g., "ENGLOG"
JIRA_DOMAIN = os.environ.get("JIRA_DOMAIN")  # e.g., "your-domain.atlassian.net"

slack_client = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(signing_secret=SLACK_SIGNING_SECRET)

# Util: generate issue summary per user + category
def get_issue_summary(user_email, category):
    date_prefix = datetime.now().strftime("%B %Y")
    return f"[{category}] {user_email} - {date_prefix}"

# Util: search or create Jira issue
def get_or_create_jira_issue(user_email, category):
    summary = get_issue_summary(user_email, category)

    # 1. Search for existing issue
    jql = f'project = {JIRA_PROJECT_KEY} AND summary ~ "{summary}" AND reporter = "{user_email}"'
    search_url = f"https://{JIRA_DOMAIN}/rest/api/3/search"
    headers = {
        "Authorization": f"Basic {os.environ.get('JIRA_AUTH_HEADER')}",  # pre-base64'd email:token
        "Content-Type": "application/json",
    }
    params = {"jql": jql}
    response = requests.get(search_url, headers=headers, params=params)
    logging.debug(f"Jira search response: {response.text}")

    issues = response.json().get("issues", [])
    if issues:
        return issues[0]["key"]

    # 2. If not found, create new
    create_url = f"https://{JIRA_DOMAIN}/rest/api/3/issue"
    issue_data = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "issuetype": {"name": "Task"},
            "reporter": {"emailAddress": user_email},
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"text": f"Issue for {category} - {user_email}", "type": "text"}]
                }]
            }
        }
    }
    response = requests.post(create_url, headers=headers, json=issue_data)
    logging.debug(f"Jira create response: {response.text}")
    return response.json().get("key")

# Util: add comment to Jira
def add_jira_comment(issue_key, comment):
    url = f"https://{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/comment"
    headers = {
        "Authorization": f"Basic {os.environ.get('JIRA_AUTH_HEADER')}",
        "Content-Type": "application/json",
    }
    data = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{
                "type": "paragraph",
                "content": [{"text": comment, "type": "text"}]
            }]
        }
    }
    response = requests.post(url, headers=headers, json=data)
    logging.debug(f"Jira comment response: {response.text}")

@app.route("/", methods=["GET"])
def index():
    return "Slack Off-Queue Logger is Running!", 200

@app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.get_json(force=True)

    if request.content_type != "application/json":
        return make_response("Unsupported Media Type", 415)

    payload = request.get_json()
    logging.debug("Incoming Slack request")
    logging.debug(f"Payload: {payload}")

    # Handle Slack challenge (for URL verification)
    if payload.get("type") == "url_verification":
        return jsonify({"challenge": payload.get("challenge")})

    if payload.get("type") == "event_callback":
        event = payload.get("event", {})
        logging.debug(f"Slack Event: {event}")
        return make_response("Event received", 200)

    return make_response("OK", 200)

@app.route("/slack/submit", methods=["POST"])
def handle_modal_submission():
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid signature", 403)

    if request.content_type != "application/json":
        return make_response("Unsupported Media Type", 415)

    payload = request.get_json()
    logging.debug(f"Modal payload: {payload}")

    view = payload.get("view", {})
    state_values = view.get("state", {}).get("values", {})
    user = payload.get("user", {})
    user_email = user.get("email") or user.get("username") or "unknown@example.com"

    description = ""
    category = ""
    duration = ""

    for block in state_values.values():
        for action_id, action in block.items():
            if action_id == "description_input":
                description = action.get("value", "")
            elif action_id == "category_select":
                category = action.get("selected_option", {}).get("value", "")
            elif action_id == "duration_input":
                duration = action.get("value", "")

    comment = f"*{datetime.now().strftime('%Y-%m-%d %H:%M')}*\nCategory: {category}\nDuration: {duration}\nDetails: {description}"
    issue_key = get_or_create_jira_issue(user_email, category)
    add_jira_comment(issue_key, comment)

    # Placeholder: Log to Google Sheets if needed
    logging.debug(f"Would log to Sheets: {user_email}, {category}, {duration}, {description}")

    return make_response("", 200)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
