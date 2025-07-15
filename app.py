import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

load_dotenv()

app = App(
    token=os.getenv("SLACK_BOT_TOKEN"),
    signing_secret=os.getenv("SLACK_SIGNING_SECRET")
)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@app.command("/logoffqueuework")
def handle_command(ack, body, client):
    ack()
    trigger_id = body["trigger_id"]
    client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "callback_id": "log_modal",
            "title": {"type": "plain_text", "text": "Log Off-Queue Work"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "duration_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "duration_input",
                        "placeholder": {"type": "plain_text", "text": "e.g. 1h or 30m"}
                    },
                    "label": {"type": "plain_text", "text": "Time Spent"}
                },
                {
                    "type": "input",
                    "block_id": "category_block",
                    "element": {
                        "type": "static_select",
                        "action_id": "category_input",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Interviewing"}, "value": "Interviewing"},
                            {"text": {"type": "plain_text", "text": "Documentation"}, "value": "Documentation"},
                            {"text": {"type": "plain_text", "text": "Mentoring"}, "value": "Mentoring"},
                            {"text": {"type": "plain_text", "text": "Tech Debt"}, "value": "Tech Debt"}
                        ]
                    },
                    "label": {"type": "plain_text", "text": "Category"}
                },
                {
                    "type": "input",
                    "block_id": "notes_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "notes_input",
                        "placeholder": {"type": "plain_text", "text": "e.g. Interview panel or doc update"}
                    },
                    "label": {"type": "plain_text", "text": "Description"}
                }
            ]
        }
    )

@flask_app.route("/slack/commands", methods=["POST"])
def slack_commands():
    return handler.handle(request)

@flask_app.route("/slack/interactions", methods=["POST"])
def slack_interactions():
    return handler.handle(request)

if __name__ == "__main__":
    flask_app.run(port=3000)

