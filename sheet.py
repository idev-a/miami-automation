from google.oauth2 import service_account
from googleapiclient.discovery import build
from gspread_pandas import Spread, Client

from logger import logger

import pdb

SPREADSHEETS_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_NAME = 'https://docs.google.com/spreadsheets/d/1ainUnfZAD7ISHzTVjS8-IuCy3lm991wBRdRzI26N3Cg'
GSUITE_USER_EMAIL = 'it@miamiadschool.com'

CCS_SHEET = 'Campuscafe Course Schedule'
ZOOM_USERS = 'Zoom Users'
CALENDAR_SCHEDULE = 'Calendar Schedule'
STUDENT_ROSTER = 'Student Roster'

class Sheet:

	def __init__(self):
		self.spread = Spread(SPREADSHEET_NAME)
		self.ccs= self.spread.sheet_to_df(sheet=CCS_SHEET, index=0)
		self.zu = self.spread.sheet_to_df(sheet=ZOOM_USERS, index=0)
		# self.cs = self.spread.sheet_to_df(sheet=CALENDAR_SCHEDULE)
		self.sr = self.spread.sheet_to_df(sheet=STUDENT_ROSTER, index=0)
		
		# set index in ccs sheet with Unique ID column to get updated.
		# self.ccs = self.ccs.set_index(self.ccs['Unique ID'])

		# set index in sr sheet with ID_NUMBER
		# self.sr = self.sr.set_index(self.sr['COURSE', 'ADDRESS'])

	def update_calendar_schedule(self):
		for cn, cs, desc, loc, teacher, index in zip(
			self.ccs['Course Number'],
			self.ccs['Course Section'],
			self.ccs['Description'],
			self.ccs['Site'],
			self.ccs['Instructor 1'],
			self.ccs['Unique ID']
		):
			class_name = f"Q4-{cn}-{cs}-{desc}"
			location = loc[4:]
			quarter = '2020.Q4'
			slack_channel_name = f"Q4"
			host = '' # from zoom users sheet
			notes = ''

	def update_sheet_from_df(self, df, sheet_name):
		logger.info(f'--- Update {sheet_name} Sheet from df')
		self.spread.df_to_sheet(df, index=False, sheet=sheet_name)

	def update_ccs_sheet_from_df(self, df):
		self.update_sheet_from_df(df, CCS_SHEET)

	# deprecated
	def init_sheet_with_service_key(self):
		self.credentials = service_account.Credentials.from_service_account_file(
			'./creds/google_secret.json',
			scopes=SPREADSHEETS_SCOPES,
			subject=GSUITE_USER_EMAIL)

		self.sheet_service = build('sheets', 'v4', credentials=self.credentials, cache_discovery=False)
		self.sheet = self.sheet_service.spreadsheets()

	# deprecated
	def read_sheets(self, range):
		result = self.sheet.values().get(
			spreadsheetId=SPREADSHEET_ID,
			range=range).execute()
		values = result.get('values', [])


if __name__ == '__main__':
	sheet = Sheet()

	# sheet.init_sheet()
	# sheet.read_sheets()

	sheet.read_sheet_by_pd()
