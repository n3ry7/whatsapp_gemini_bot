from flask import Flask, jsonify, request, Response
import os
import requests
from dotenv import load_dotenv
import google.generativeai as genai
import json # Import json for better error handling/logging if needed

load_dotenv()
app = Flask(__name__)

# --- Environment Variables ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHAT_TOKEN = os.getenv("WHAT_TOKEN")         # WhatsApp Cloud API Permanent Token
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")     # Your webhook verification token
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID") # Your Bot's phone number ID
# PHONE_NUMBER = os.getenv("PHONE_NUMBER") # You don't strictly need your bot's number here now

# --- Gemini Setup ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-lite')

def ai_response(ask):
    """Generates a response using the Gemini API."""
    try:
        response = model.generate_content(
            ask,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7)
        )
        # Add basic safety check
        if response.parts:
             return response.text
        else:
            # Handle cases where Gemini might return no content (e.g., safety filters)
            print("Gemini Warning: No content generated, possibly due to safety settings.")
            return "Sorry, I couldn't process that request due to safety constraints."
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return "Sorry, I encountered an error trying to generate a response."


def send_whatsapp_message(recipient_number, message_body):
    """Sends a WhatsApp message using the Graph API."""
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages" # Use variable
    headers = {
        "Authorization": f"Bearer {WHAT_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient_number, # Send to the user who messaged
        "type": "text",
        "text": {"body": message_body}
    }
    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        print(f"Message sent to {recipient_number}. Response: {response.text}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp message: {e}")
        print(f"Response body: {response.text if 'response' in locals() else 'No response object'}")
        return False

@app.route('/', methods=["GET"])
def check_webhook():
    """Handles webhook verification challenge."""
    # No need to check request.method == 'GET' again, Flask handles it
    mode = request.args.get('hub.mode')
    verify_token_received = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    print(f"GET Request received: mode={mode}, token={verify_token_received}, challenge={challenge}") # Debugging

    if mode and verify_token_received:
        if mode == 'subscribe' and verify_token_received == VERIFY_TOKEN:
            print("Webhook verification successful.")
            return Response(challenge, status=200)
        else:
            print(f"Webhook verification failed. Mode: {mode}, Token Match: {verify_token_received == VERIFY_TOKEN}")
            return Response("Verification token mismatch", status=403)
    else:
        print("Webhook verification failed. Missing mode or token.")
        return Response("Missing parameters", status=400) # Bad request


@app.route('/', methods=["POST"])
def handle_message():
    """Handles incoming WhatsApp messages."""
    body = request.get_json()
    print("POST Request received body:")
    # Using json.dumps for pretty printing the dict
    print(json.dumps(body, indent=2))

    try:
        # Basic validation of payload structure
        if (body.get("object") == "whatsapp_business_account" and
                body.get("entry") and isinstance(body["entry"], list) and
                len(body["entry"]) > 0 and body["entry"][0].get("changes") and
                isinstance(body["entry"][0]["changes"], list) and
                len(body["entry"][0]["changes"]) > 0 and
                body["entry"][0]["changes"][0].get("value") and
                body["entry"][0]["changes"][0]["value"].get("messages") and
                isinstance(body["entry"][0]["changes"][0]["value"]["messages"], list) and
                len(body["entry"][0]["changes"][0]["value"]["messages"]) > 0):

            message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]

            # Check if it's a text message
            if message_info.get("type") == "text":
                sender_number = message_info["from"]
                user_question = message_info["text"]["body"]

                print(f"Received text message from {sender_number}: '{user_question}'")

                # Generate AI response
                bot_response = ai_response(user_question)
                print(f"Gemini response: '{bot_response}'")

                # Send response back to the user
                send_whatsapp_message(sender_number, bot_response)

            else:
                # Handle non-text messages if needed (optional)
                print(f"Received non-text message type: {message_info.get('type')}")
                # You might want to send a default reply like:
                # send_whatsapp_message(message_info["from"], "Sorry, I can only process text messages right now.")

        else:
            # Handle other types of notifications if necessary (e.g., status updates)
            print("Received notification is not a user message.")

    except Exception as e:
        print(f"Error processing incoming message: {e}")
        # Still return 200 OK to Meta, otherwise they might retry the webhook
        # Log the actual error on your server side (Heroku logs)

    # IMPORTANT: Always return 200 OK to acknowledge receipt of the webhook
    # even if you didn't process the message or encountered an error.
    return Response(status=200)


if __name__ == '__main__':
    # Make sure port is an integer
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False) # Turn debug=False for production
