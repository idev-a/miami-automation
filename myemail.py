import smtplib, ssl

smtp_server = "smtp.gmail.com"
port = 587  # For starttls
password = 'Imobile1'
sender_email = "ideveloper003@gmail.com"
receiver_email = "ideveloper003@gmail.com"
reply_email = "help@miamiadschool.com"
message = """\
Subject: Hi there

This message is sent from Python."""

class Email:

	def __init__(self):
		context = ssl.create_default_context()

		# Try to log in to server and send email
		try:
		    self.server = smtplib.SMTP(smtp_server,port)
		    self.server.ehlo() # Can be omitted
		    self.server.starttls(context=context) # Secure the connection
		    self.server.ehlo() # Can be omitted
		    self.server.login(sender_email, password)
		    # TODO: Send email here
		except Exception as e:
		    # Print any error messages to stdout
		    print(e)
		finally:
		    self.server.quit() 

	def send_email(self):
		self.server.sendmail(reply_email, receiver_email, message)