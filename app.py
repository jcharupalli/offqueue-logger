import os
import logging
import requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# ENV VARIABLES — replace these or use actual environment variables
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "your-slack-bot-token")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://your-domain.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "your-email@example.com")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "your-jira-api-token")
JIRA_PROJECT_KEY = "ENGLOG"  # Fixed as per your requirement

CATEGORY_ISSUE_MAP = {
    "Interviewing": "Interviewing",
    "Documentation": "Documentation",
    "Dev Tooling": "Dev Tooling",
    "Other": "Other"
}

@app.route("/slack/interactions", methods=["POST"])
def handle_slack_interactions():
    payload = request.form.get("payload")
    if not payload:
        return jsonify({"error": "Missing payload"}), 400

    data = request.get_json(force=True, silent=True)
    if data is None:
        import json
        data = json.loads(payload)

    logging.debug("Slack modal submission received")
    logging.debug(data)

    try:
        user_id = data['user']['id']
        user_name = data['user']['username']
        values = data['view']['state']['values']

        category = values['category']['category_input']['selected_option']['value']
        time_spent = values['time']['time_input']['value']
        description = values['description']['description_input']['value']

        jira_issue_key = get_or_create_jira_issue(user_name, category)
        post_comment_to_issue(jira_issue_key, user_name, category, time_spent, description)

        return jsonify({"response_action": "clear"}), 200

    except Exception as e:
        logging.exception("Error handling modal submission")
        return jsonify({"response_action": "errors", "errors": {"": str(e)}}), 500


def get_or_create_jira_issue(user_name, category):
    today = datetime.now()
    summary = f"{category} Logs - {user_name} - {today.strftime('%B %Y')}"

    headers = {
        "Authorization": f"Basic {get_jira_auth()}",
        "Content-Type": "application/json"
    }

    jql = f'project = {JIRA_PROJECT_KEY} AND summary ~ "{summary}" AND status != Done'
    search_url = f"{JIRA_BASE_URL}/rest/api/3/search"
    res = requests.get(search_url, headers=headers, params={"jql": jql})
    res.raise_for_status()
    issues = res.json().get("issues", [])

    if issues:
        return issues[0]["key"]

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": f"Auto-created issue for {user_name} - {category}",
            "issuetype": {"name": "Task"},
        }
    }

    res = requests.post(f"{JIRA_BASE_URL}/rest/api/3/issue", headers=headers, json=payload)
    res.raise_for_status()
    return res.json()["key"]


def post_comment_to_issue(issue_key, user_name, category, time_spent, description):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    headers = {
        "Authorization": f"Basic {get_jira_auth()}",
        "Content-Type": "application/json"
    }

    comment = f"*User:* {user_name}\n*Category:* {category}\n*Time Spent:* {time_spent} mins\n*Description:* {description}\n*Logged on:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    payload = {"body": comment}
    res = requests.post(url, headers=headers, json=payload)
    res.raise_for_status()
    logging.info(f"Comment added to {issue_key}")


def get_jira_auth():
    import base64
    token = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
    return base64.b64encode(token.encode()).decode()


@app.route("/", methods=["GET"])
def index():
    return "Slack Off-Queue Logger is running!", 200


if __name__ == "__main__":
    app.run(port=3000, debug=True)
