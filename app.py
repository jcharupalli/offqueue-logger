import os
import json
from flask import Flask, request, make_response
from slack_sdk.web import WebClient
from slack_sdk.signature import SignatureVerifier
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]

client = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)


@app.route("/slack/events", methods=["POST"])
def slack_events():
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return make_response("Invalid request signature", 403)

    if "payload" in request.form:
        # This is a view_submission payload
        payload = json.loads(request.form["payload"])
        if payload["type"] == "view_submission":
            user = payload["user"]["id"]
            values = payload["view"]["state"]["values"]
            category = values["category_block"]["category_action"]["selected_option"]["value"]
            duration = values["duration_block"]["duration_action"]["value"]
            description = values["description_block"]["description_action"]["value"]

            # Send a confirmation message to the user
            client.chat_postMessage(
                channel=user,
                text=f"✅ Logged your off-queue work:\n• *Category:* {category}\n• *Duration:* {duration} mins\n• *Description:* {description}"
            )
            return make_response("", 200)

    if request.form.get("command") == "/logoffqueuework":
        trigger_id = request.form["trigger_id"]

        # Open a modal
        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "log_offqueue_work",
                "title": {"type": "plain_text", "text": "Log Off-Queue Work"},
                "submit": {"type": "plain_text", "text": "Submit"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "category_block",
                        "label": {"type": "plain_text", "text": "Category"},
                        "element": {
                            "type": "static_select",
                            "action_id": "category_action",
                            "placeholder": {"type": "plain_text", "text": "Select a category"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "Documentation"}, "value": "Documentation"},
                                {"text": {"type": "plain_text", "text": "Interviewing"}, "value": "Interviewing"},
                                {"text": {"type": "plain_text", "text": "Mentoring"}, "value": "Mentoring"},
                                {"text": {"type": "plain_text", "text": "Training"}, "value": "Training"},
                                {"text": {"type": "plain_text", "text": "Other"}, "value": "Other"}
                            ]
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "duration_block",
                        "label": {"type": "plain_text", "text": "Duration (minutes)"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "duration_action"
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "description_block",
                        "label": {"type": "plain_text", "text": "Short Description"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "description_action",
                            "multiline": True
                        }
                    }
                ]
            }
        )
        return make_response("", 200)

    return make_response("No action taken", 200)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
