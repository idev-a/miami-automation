from apiclient import errors
from httplib2 import Http
from email.mime.text import MIMEText
import base64
from googleapiclient.discovery import build
from google.oauth2 import service_account
import pdb
import os

EMAIL_FROM = "it@miamiadschool.com"
EMAIL_TO = "it@miamiadschool.com"
EMAIL_SUBJECT = "Report: Error while uploading recordings"
EMAIL_CONTENT = 'Hello, this is a test\nLyfepedia\nhttps://lyfepedia.com'

class Email:

	def __init__(self):
		SCOPES = ['https://www.googleapis.com/auth/gmail.send']
		BASE_PATH = os.path.abspath(os.curdir)
		# BASE_PATH = '/root/miami-scripts'
		SERVICE_ACCOUNT_FILE = f'{BASE_PATH}/creds/google_secret.json'

		credentials = service_account.Credentials.from_service_account_file(
			SERVICE_ACCOUNT_FILE,
			scopes=SCOPES,
			subject=EMAIL_FROM)
		# delegated_credentials = credentials.with_subject(EMAIL_FROM)
		self.service = build('gmail', 'v1', credentials=credentials, cache_discovery=False)

	def send_message(self, msg):
		message = self.create_message(EMAIL_FROM, EMAIL_TO, EMAIL_SUBJECT, msg)
		sent = self._send_message('me', message)

	def create_message(self, sender, to, subject, message_text):
		"""Create a message for an email.
		Args:
		sender: Email address of the sender.
		to: Email address of the receiver.
		subject: The subject of the email message.
		message_text: The text of the email message.
		Returns:
		An object containing a base64url encoded email object.
		"""
		message = MIMEText(message_text)
		message['to'] = to
		message['cc'] = "ideveloper003@gmail.com"
		message['from'] = sender
		message['subject'] = subject
		return {'raw': base64.urlsafe_b64encode(message.as_string().encode('utf-8')).decode("ascii")}

	def _send_message(self, user_id, message):
		"""Send an email message.
		Args:
		service: Authorized Gmail API service instance.
		user_id: User's email address. The special value "me"
		can be used to indicate the authenticated user.
		message: Message to be sent.
		Returns:
		Sent Message.
		"""
		try:
			message = self.service.users().messages().send(userId=user_id, body=message).execute()
			print('Message Id: %s' % message['id'])
			return message
		except errors.HttpError as error:
			print('An error occurred: %s' % error)

if __name__ == '__main__':
	myemail = Email()
	myemail.send_message('test1')