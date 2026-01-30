from dotenv import load_dotenv
import os
from twilio.rest import Client

load_dotenv()

print("SID:", os.getenv("TWILIO_ACCOUNT_SID"))
print("TOKEN:", os.getenv("TWILIO_AUTH_TOKEN"))
print("FROM:", os.getenv("TWILIO_FROM_NUMBER"))
print("TO:", os.getenv("TEST_TO_NUMBER"))

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_number = os.getenv("TWILIO_FROM_NUMBER")
to_number = os.getenv("TEST_TO_NUMBER")

client = Client(account_sid, auth_token)

message = client.messages.create(
    body="Test SMS from Twilio",
    from_=from_number,
    to=to_number
)

print("Message SID:", message.sid)
