import os
from flask import Flask, request, make_response
from slack_sdk import WebClient
from slack_sdk.models.blocks import InputBlock, PlainTextInputElement, SectionBlock
from slack_sdk.models.views import View
from slack_sdk.models.blocks.block_elements import StaticSelectElement
from slack_sdk.models.blocks.basic_components import Option
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])

@app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.form

    if "command" in data and data["command"] == "/logoffqueuework":
        trigger_id = data["trigger_id"]

        modal_view = View(
            type="modal",
            title={"type": "plain_text", "text": "Log Off-Queue Work"},
            callback_id="log_offqueue_modal",
            submit={"type": "plain_text", "text": "Submit"},
            close={"type": "plain_text", "text": "Cancel"},
            blocks=[
                InputBlock(
                    block_id="category_block",
                    label="Category",
                    element=StaticSelectElement(
                        action_id="category_action",
                        placeholder="Select a category",
                        options=[
                            Option(text="Documentation", value="Documentation"),
                            Option(text="Interviewing", value="Interviewing"),
                            Option(text="Mentoring", value="Mentoring"),
                            Option(text="Meetings", value="Meetings"),
                            Option(text="Other", value="Other")
                        ]
                    )
                ),
                InputBlock(
                    block_id="time_block",
                    label="Time Spent (e.g., 30m, 1h)",
                    element=PlainTextInputElement(action_id="time_action")
                ),
                InputBlock(
                    block_id="description_block",
                    label="What did you do?",
                    element=PlainTextInputElement(action_id="description_action")
                )
            ]
        )

        client.views_open(trigger_id=trigger_id, view=modal_view)
        return make_response("", 200)

    elif "payload" in data:
        payload = request.form["payload"]
        payload_data = eval(payload)  # Slack sends stringified dict; use json.loads in prod

        if payload_data["type"] == "view_submission" and payload_data["view"]["callback_id"] == "log_offqueue_modal":
            user_id = payload_data["user"]["id"]
            username = payload_data["user"]["username"]

            values = payload_data["view"]["state"]["values"]
            category = values["category_block"]["category_action"]["selected_option"]["value"]
            time_spent = values["time_block"]["time_action"]["value"]
            description = values["description_block"]["description_action"]["value"]

            message = f"*Logged off-queue work:*\n• *Category:* {category}\n• *Time Spent:* {time_spent}\n• *Description:* {description}"

            # ✅ Send confirmation to user
            client.chat_postMessage(
                channel=user_id,
                text=message
            )

            # ✅ Create Jira Issue
            create_jira_issue(category, time_spent, description, username)

            return make_response("", 200)

    return make_response("", 404)

def create_jira_issue(category, time_spent, description, username):
    jira_url = os.environ["JIRA_BASE_URL"] + "/rest/api/3/issue"
    auth = (os.environ["JIRA_USER_EMAIL"], os.environ["JIRA_API_TOKEN"])
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    summary = f"{username} - {category} - {time_spent}"
    jira_description = f"*Category:* {category}\n*Time Spent:* {time_spent}\n*Description:* {description}"

    payload = {
        "fields": {
            "project": {
                "key": os.environ["JIRA_PROJECT_KEY"]
            },
            "summary": summary,
            "description": jira_description,
            "issuetype": {
                "name": "Task"
            }
        }
    }

    response = requests.post(jira_url, json=payload, auth=auth, headers=headers)
    print("Jira response:", response.status_code, response.text)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
