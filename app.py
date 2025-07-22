import os
import json
import logging
from flask import Flask, request, make_response
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.models.views import View
from slack_sdk.models.blocks import InputBlock, PlainTextInputElement, SectionBlock, StaticSelectElement, Option
import requests
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Environment variables
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
JIRA_PROJECT_KEY = os.environ["JIRA_PROJECT_KEY"]

slack_client = WebClient(token=SLACK_BOT_TOKEN)

# Category options
CATEGORY_OPTIONS = [
    Option(text="Interviewing", value="Interviewing"),
    Option(text="Documentation", value="Documentation"),
    Option(text="Tech Debt Cleanup", value="Tech Debt Cleanup"),
    Option(text="Meetings", value="Meetings"),
    Option(text="Other", value="Other"),
]

@app.route("/slack/events", methods=["POST"])
def slack_events():
    if request.headers.get("X-Slack-Retry-Num"):
        return make_response("No retries please", 200)

    payload = request.form

    if "payload" in payload:
        data = json.loads(payload["payload"])
        if data["type"] == "view_submission":
            handle_view_submission(data)
            return make_response("", 200)

    if payload.get("command") == "/logoffqueuework":
        trigger_id = payload.get("trigger_id")
        user_id = payload.get("user_id")
        open_log_modal(trigger_id, user_id)
        return make_response("", 200)

    return make_response("Unknown request", 404)

def open_log_modal(trigger_id, user_id):
    try:
        view = View(
            type="modal",
            callback_id="offqueue_log_modal",
            title={"type": "plain_text", "text": "Log Off-Queue Work"},
            submit={"type": "plain_text", "text": "Submit"},
            close={"type": "plain_text", "text": "Cancel"},
            blocks=[
                InputBlock(
                    block_id="category_input",
                    label={"type": "plain_text", "text": "Category"},
                    element=StaticSelectElement(
                        action_id="category",
                        options=CATEGORY_OPTIONS
                    )
                ),
                InputBlock(
                    block_id="duration_input",
                    label={"type": "plain_text", "text": "Duration (minutes)"},
                    element=PlainTextInputElement(action_id="duration")
                ),
                InputBlock(
                    block_id="description_input",
                    label={"type": "plain_text", "text": "Description"},
                    element=PlainTextInputElement(action_id="description", multiline=True)
                )
            ]
        )
        slack_client.views_open(trigger_id=trigger_id, view=view)
    except SlackApiError as e:
        logging.error(f"Slack API error: {e.response['error']}")

def handle_view_submission(view_payload):
    user = view_payload["user"]["id"]
    values = view_payload["view"]["state"]["values"]
    category = values["category_input"]["category"]["selected_option"]["value"]
    duration = values["duration_input"]["duration"]["value"]
    description = values["description_input"]["description"]["value"]

    username_resp = slack_client.users_info(user=user)
    real_name = username_resp["user"]["real_name"]
    slack_email = username_resp["user"]["profile"]["email"]

    summary = f"[Off-Queue] {category} log by {real_name} on {datetime.now().strftime('%Y-%m-%d')}"

    # Create Jira issue and notify user
    issue_key = create_jira_issue(slack_email, summary, category, duration, description)
    if issue_key:
        try:
            slack_client.chat_postMessage(
                channel=user,
                text=f":white_check_mark: Your off-queue work has been logged successfully.\nJira Ticket: *<{JIRA_BASE_URL}/browse/{issue_key}|{issue_key}>*"
            )
        except SlackApiError as e:
            logging.error(f"Failed to send confirmation message: {e.response['error']}")

def create_jira_issue(slack_email, summary, category, duration, description):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    adf_description = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": f"Category: {category}"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": f"Duration: {duration} minutes"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": f"Description: {description}"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": f"Logged by: {slack_email}"}]}
        ]
    }

    payload = json.dumps({
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": adf_description,
            "issuetype": {"name": "Task"}
        }
    })

    response = requests.post(url, headers=headers, data=payload, auth=auth)
    if response.status_code in [200, 201]:
        issue_key = response.json().get("key")
        logging.info(f"Created Jira issue: {issue_key}")
        return issue_key
    else:
        logging.error(f"Failed to create Jira issue: {response.status_code}, {response.text}")
        return None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
