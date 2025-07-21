import os
import json
import logging
from flask import Flask, request, make_response
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

JIRA_BASE_URL = "https://your-domain.atlassian.net"
JIRA_PROJECT_KEY = "ENGLOG"
JIRA_EMAIL = "your-email@example.com"
JIRA_API_TOKEN = "your-api-token"

# Set this to category-wise issues manually created, keyed by category
JIRA_ISSUES = {
    "Interviewing": "ENGLOG-101",
    "Documentation": "ENGLOG-102",
    "Dev Tooling": "ENGLOG-103",
    "Other": "ENGLOG-104"
}

@app.route("/slack/events", methods=["POST"])
def slack_events():
    payload = json.loads(request.form.get("payload"))
    logging.debug(f"Slack event received: {json.dumps(payload)}")

    if payload["type"] == "view_submission" and payload["view"]["callback_id"] == "log_modal":
        state_values = payload["view"]["state"]["values"]

        # Extract modal input values
        category = state_values["category"]["category_input"]["selected_option"]["value"]
        time_spent = state_values["time"]["time_input"]["value"]
        description = state_values["description"]["description_input"]["value"]
        slack_user = payload["user"]["username"]

        logging.debug(f"Category: {category}, Time: {time_spent}, Description: {description}, User: {slack_user}")

        # Get corresponding Jira issue
        jira_issue_key = JIRA_ISSUES.get(category)
        if not jira_issue_key:
            logging.error(f"No Jira issue configured for category '{category}'")
            return make_response("", 200)

        # Prepare Jira comment
        comment = f"*Off-Queue Log*\n*User*: {slack_user}\n*Category*: {category}\n*Time*: {time_spent} mins\n*Description*: {description}"

        # Make API call to Jira to add comment
        response = requests.post(
            f"{JIRA_BASE_URL}/rest/api/3/issue/{jira_issue_key}/comment",
            headers={
                "Content-Type": "application/json"
            },
            auth=(JIRA_EMAIL, JIRA_API_TOKEN),
            json={"body": comment}
        )

        logging.info(f"Jira response status: {response.status_code}, body: {response.text}")

        if response.status_code != 201:
            logging.error("Failed to post comment to Jira")

        return make_response("", 200)

    return make_response("", 200)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
