import os
import json
import logging
from flask import Flask, request, make_response
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.models.views import View
from slack_sdk.models.blocks import InputBlock, PlainTextInputElement, StaticSelectElement, Option
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
    Option(text="Interview", value="Interview"),
    Option(text="Product/Process Documentation", value="Product/Process Documentation"),
    Option(text="Case Reviews", value="Case Reviews"),
    Option(text="Meetings", value="Meetings"),
    Option(text="Growth Plan 1/1 discusssions", value="Growth Plan 1/1 discusssions"),
    Option(text="Training", value="Training"),
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

    # summary = f"[Off-Queue] {category} log by {real_name} on {datetime.now().strftime('%Y-%m-%d')}"
    summary = description[:250]  # Truncate to fit Jira's summary limit


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

    # Convert duration into "Xh Ym" format for estimated time field (customfield_10086)
    try:
        minutes = int(duration)
        hours = minutes // 60
        remaining_minutes = minutes % 60
        estimate_str = ""
        if hours > 0:
            estimate_str += f"{hours}h "
        if remaining_minutes > 0 or hours == 0:
            estimate_str += f"{remaining_minutes}m"
        estimate_str = estimate_str.strip()
    except ValueError:
        estimate_str = "0m"

    # Get Jira accountId from email
    user_lookup_url = f"{JIRA_BASE_URL}/rest/api/3/user/search?query={slack_email}"
    user_response = requests.get(user_lookup_url, headers=headers, auth=auth)
    if user_response.status_code != 200 or not user_response.json():
        logging.error(f"Failed to fetch Jira user for email {slack_email}: {user_response.text}")
        return None
    account_id = user_response.json()[0]["accountId"]

    # ADF formatted description
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
            "issuetype": {"name": "Task"},
            "assignee": {"accountId": account_id},
            "customfield_10087": {"value": category},  # Task Category dropdown
            "customfield_10086": estimate_str  # Estimated Time (text format like "1h 15m")
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
