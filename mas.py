import pdb

from sheet import Sheet
from drive import GDrive
from myslack import Slack
from zoom import Zoom
from myemail import Email

from logger import logger

# Constants
SPREADSHEET_NAME = 'https://docs.google.com/spreadsheets/d/1ainUnfZAD7ISHzTVjS8-IuCy3lm991wBRdRzI26N3Cg'
GSUITE_USER_EMAIL = 'it@miamiadschool.com'

class Mas:
	mysheet = {}

	def __init__(self):
		# SpreadSheet
		logger.info('--- Initialize Spreadsheet')
		self.mysheet = Sheet()

		# Google Drive
		logger.info('--- Initialize Google Drive')
		self.mydrive = GDrive()

		# Slack
		# logger.info('--- Initialize Slack')
		# self.slack = Slack()

		# Zoom
		logger.info('--- Initialize Zoom')
		self.zoom = Zoom()

		# Email
		# logger.info('--- Initialize Email')
		# self.email = Email()

	'''
		Google Spreadsheet
	'''
	def update_ccs_sheet(self):
		self.mysheet.update_ccs_sheet_from_df(self.updated_ccs)

	'''
		Google Drive
	'''
	def drive_setup(self):
		logger.info('--- Setup Google Drive')
		self.mydrive.setup(self.mysheet)
		self.updated_ccs = self.mydrive.generate_links_and_share_permission()

		self.update_ccs_sheet()

	'''
		Slack
	'''
	def slack_setup(self):
		self.updated_ccs = self.slack.setup(self.mysheet)
		self.update_ccs_sheet()

	'''
		Zoom
	'''
	def zoom_setup(self):
		self.updated_ccs = self.zoom.setup(self.mysheet, self.mydrive)
		# self.update_ccs_sheet()

	'''
		Email
	'''
	def email_setup(self):
		self.email.send_email()

	def run(self):
		# self.drive_setup()

		self.zoom_setup()

		# self.slack_setup()

		# self.email_setup()

if __name__ == '__main__':
	mas = Mas()

	mas.run()