import json
import os, re, sys
import pdb
import requests
import time
import http.client
import random
import string
from clint.textui import progress
from datetime import datetime, timedelta
import jwt
from uuid import uuid1
import argparse
from urllib.parse import urlencode
from dotenv import load_dotenv
from sqlalchemy import create_engine, Table, Column, Text, BLOB, \
					Integer, Text, String, MetaData, DateTime, JSON, select, Boolean
from sqlalchemy.ext.declarative import declarative_base

from logger import logger
from myemail import Email

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Zoom():
	userId = 'zoom@miamiadschool.com'
	api_key = '_pfgSLXiR76j3AnzOqa0Pg'
	api_secret = 'fumzkWiH5Xnpfs0iLAU31Uy1XiKshsHswGRQ'
	client_secret = 'pQPjWmBm32jDKTiDwCQ2I6I7Qhvc9JqM'
	client_id = 'IGEu77pbRaCXfjPYTM088A'
	base_url = 'https://api.zoom.us/v2/'

	redirect_uri = 'http://localhost:5000/api/mine/zoom_callback'
	# redirect_uri = 'https://secure-dashboard.revampcybersecurity.com//api/mine/zoom_callback'

	downloaded_recordings = []
	recording_data_to_insert = []
	meeting_data_to_insert = []
	failed_meetings = []
	users = []
	zoom_users = []
	size_limit = 1024
	page_size = 300

	def __init__(self):
		self.emailSender = Email()
		self.session = requests.Session()
		self.session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=10000000, max_retries=3))
		self.generate_jwt_token()
		self._setup_db()
		# self.read_all_users()

	def _setup_db(self):
		Base = declarative_base()
		metadata = MetaData()
		engine = create_engine(os.environ.get('DATABASE_URL'))
		self.connection = engine.connect()
		metadata.bind = engine
		metadata.clear()

		self.upload_history = Table(
			'recording_upload_history', 
			metadata,
			Column('id', Integer, primary_key=True),
			Column('topic', String(512)),
			Column('meeting_id', String(512)),
			Column('meeting_uuid', String(512)),
			# Column('meeting_link', String(512)),
			Column('start_time', String(512)),
			Column('file_name', String(512)),
			# Column('file_type', String(128)),
			Column('recording_link', String(512)),
			Column('folder_link', String(512)),
			Column('status', Boolean),
			Column('run_at', String(256)),
		)

		self.upload_status = Table(
			'meeting_upload_status', 
			metadata,
			Column('id', Integer, primary_key=True),
			Column('topic', String(512)),
			Column('meeting_id', String(512)),
			Column('meeting_uuid', String(512)),
			# Column('meeting_link', String(512)),
			Column('start_time', String(512)),
			Column('folder_link', String(512)),
			Column('cnt_files', Integer),
			Column('status', Boolean),
			Column('is_deleted', Boolean),
			Column('run_at', String(256)),
		)
		metadata.create_all()

	def generate_jwt_token(self):
		'''
			Generate jwt token from api_key
			@input 
				api_key
			@output
				jwt token

		'''
		expire = int(datetime.timestamp(datetime.now() + timedelta(days=2))) * 1000
		payload = {
			"iss": self.api_key,
			"exp": expire
		}
		headers = {
			"alg": "HS256",
			"typ": "JWT"
		}
		self.token = jwt.encode(payload, self.api_secret, headers=headers)

	def format_time(self, _time):
		return datetime.strptime(_time, '%H:%M%p')

	def get_random_pwd(self, length=10):
		letters = string.ascii_lowercase + ''.join([str(x) for x in range(0, 9)]) + string.ascii_uppercase + '@-_*'
		return_str = []
		for i in range(length):
			return_str.append(random.choice(letters))
		return ''.join(return_str)

	def select_time(self, mon, tue, wed, thu, fri, sat):
		selected = ''
		dow = 0
		for idx, day in enumerate([mon, tue, wed, thu, fri, sat]):
			if day:
				selected = day.strip()
				dow = idx + 2

		start_time = self.format_time(selected.split('-')[0].strip())
		end_time = self.format_time(selected.split('-')[1].strip())

		c = (end_time - start_time)
		duration = c.total_seconds() / 60 # duration in mins

		return start_time.strftime('%H:%M:%S'), end_time.strftime('%H:%M:%S'), duration, dow

	def setup(self, gspread, drive=None):
		logger.info('--- Setup Zoom')
		self.ccs = gspread.ccs
		self.zu = gspread.zu
		if drive:
			self.drive = drive

		self.list_all_recordings()

		self.download_recordings()

		# self.read_all_zoom_users()

		# self.read_zoom_info_create_meetings()

		return self.ccs

	def read_all_users(self):
		logger.info('--- read all zoom users')
		next_page_token = ''
		while True:
			res = self.session.get(f'{self.base_url}users?page_size={self.page_size}&next_page_token={next_page_token}', headers=self.get_headers())
			if res.status_code == 200:
				self.zoom_users += res.json()['users']
			
			if not next_page_token:
				break

	def read_all_zoom_users(self):
		for email, pwd, fn in zip(self.zu['Email'], self.zu['Zoom Passwords'], self.zu['Full Name']):
			if pwd:
				self.users.append({
					'email': email,
					'pwd': pwd,
					'fullname': fn
				})

	def lookup_cred(self, instructor):
		account = {}
		for user in self.users:
			if user['fullname'].strip() == instructor.strip():
				account = user
				break

		return account

	def update_sheet(self, meeting, index):
		meeting = meeting.json()
		self.ccs.at[index, 'Zoom Meeting Link'] = meeting['join_url']
		self.ccs.at[index, 'Zoom Meeting ID'] = meeting['id']

	def read_zoom_info_create_meetings(self):
		# Calendar Schedule sheet
		index = 0
		for sd, ed, mon, tue, wed, thu, fri, sat, sir, cn, cs, desc in zip(
			self.ccs['Start Date'],
			self.ccs['End Date'],
			self.ccs['Monday'],
			self.ccs['Tuesday'],
			self.ccs['Wednesday'],
			self.ccs['Thursday'],
			self.ccs['Friday'],
			self.ccs['Saturday'],
			self.ccs['Instructor 1'],
			self.ccs['Course Number'],
			self.ccs['Course Section'],
			self.ccs['Description']
		):
			try:
				sd = datetime.strptime(sd, '%m/%d/%Y').strftime('%Y-%m-%d')
				ed = datetime.strptime(ed, '%m/%d/%Y').strftime('%Y-%m-%d')
				star_time, end_time, duration, dow = self.select_time(mon, tue, wed, thu, fri, sat)
				start_date_time = f"{sd}T{star_time}Z"
				end_date_time = f"{ed}T{end_time}Z"
				account = self.lookup_cred(sir)

				class_name = f"Q4-{cn}-{cs}-{desc}"

				if account:
					meeting = self.create_recurring_zoom_meetings(account, start_date_time, end_date_time, duration, dow, class_name)
					# if meeting.status_code == 201:
					# 	self.update_sheet(meeting, index)
				else:
					logger.warning(f'******* no matching zoom users for instuctor {sir} ********')

				# break
			except Exception as E:
				logger.warning(str(E))

			index += 1
			break

	def _topic(self, topic):
		return ' '.join(topic.lower().strip().split('-'))

	def find_drive_folder_id(self, cur_topic):
		folder_id = None
		for folder_link, topic in zip(self.ccs['Google Drive: Recordings'], self.ccs['Zoom Topic']):
			if self._topic(topic) in self._topic(cur_topic):
				folder_id = os.path.basename(folder_link)
				break

		if folder_id and '?' in folder_id:
			folder_id = folder_id.split('?')[0]

		return folder_id

	def get_headers(self):
		return {
			'authorization': f"Bearer {self.token.decode()}",
			'content-type': "application/json"
		}

	def list_all_recordings(self):
		logger.info('--- list all recordings')
		self.meetings = []
		delta = 30
		to_date = datetime.now()
		from_date = datetime.now() - timedelta(days=delta)
		while True:
			sub_meetings = self._list_recordings(from_date, to_date)
			if len(sub_meetings) == 0:
				break
			else:
				self.meetings += sub_meetings
				to_date = datetime.now() - timedelta(days=delta)
				delta += 30
				from_date = datetime.now() - timedelta(days=delta)

		print(len(self.meetings))

	def _list_recordings(self, from_date, to_date):
		sub_meetings = []
		next_page_token = ''
		while True:
			res = self.session.get(f"{self.base_url}/accounts/me/recordings?mc=true&page_size={self.page_size}&from={from_date.strftime('%Y-%m-%d')}&to={to_date.strftime('%Y-%m-%d')}&next_page_token={next_page_token}", headers=self.get_headers())
			if res.status_code == 200:
				sub_meetings += res.json()['meetings']

			next_page_token = res.json()['next_page_token']
			
			if not res.json()['next_page_token']:
				break

		return sub_meetings

	def double_urlencode(self, text):
		"""double URL-encode a given 'text'.  Do not return the 'variablename=' portion."""

		text = self.single_urlencode(text)
		text = self.single_urlencode(text)

		return text

	def single_urlencode(self, text):
		"""single URL-encode a given 'text'.  Do not return the 'variablename=' portion."""

		blah = urlencode({'blahblahblah':text})

		#we know the length of the 'blahblahblah=' is equal to 13.  This lets us avoid any messy string matches
		blah = blah[13:]

		return blah

	def clean_tiny_recordings(self):
		self.list_all_recordings()

		self.clear_recordings()

	def clear_recordings(self):
		'''
			Clear recording whose size is under input limit size. normally kb file
			@caution: should not delete processing recodings as they appear 0 in size
		'''
		logger.info('--- clean tiny recordings')
		total_cleared = 0
		for meeting in self.meetings:
			# if meeting['topic'] == 'Q4-POP540-1A-Portfolio Development':
			# 	print('h===========', meeting['id'])
			if not self.validate_size_of_meeting(meeting, self.size_limit) and not self.is_processing_meeting(meeting):
				try:
					res = self.session.delete(f"{self.base_url}/meetings/{self.double_urlencode(meeting['uuid'])}/recordings?action=trash", headers=self.get_headers())
					if res.status_code == 204:
						logger.info(f'*** clear meeting ID: {meeting["start_time"]}, Topic: {meeting["topic"]}')
						total_cleared += 1
				except Exception as E:
					logger.warning(str(E))

		logger.info(f'--- Successfully cleared recordings {total_cleared}')		

	def update_upload_history(self, meeting, file_name, file_type, folder_id, file_id, status=True):
		_file_name = None
		if file_name and file_type:
			_file_name = f'{file_name}.{file_type}'
		start_time = datetime.strptime(meeting['start_time'], '%Y-%m-%dT%H:%M:%SZ').strftime('%b %d %Y, %H:%M:%S')
		recording_link = f'https://drive.google.com/file/d/{file_id}/view?usp=sharing'
		folder_link = f'https://drive.google.com/drive/folders/{folder_id}'
		self.recording_data_to_insert.append({
			'topic': meeting['topic'],
			'meeting_id': meeting['id'],
			'start_time': start_time,
			'file_name': _file_name,
			'file_id': file_id,
			'recording_link': recording_link,
			'folder_link': folder_link,
			'status': status,
			'run_at': datetime.now().strftime('%m/%d/%Y %H:%M:%S')
		})

	def get_meeting_status(self, meeting):
		cnt = 0
		for recording in meeting['recording_files']:
			if recording.get('status') == 'completed':
				cnt += 1
		status = False
		if len(self.recording_data_to_insert) == cnt:
			status = True
		else:
			status = False

		return status

	def update_db(self, meeting):
		if self.recording_data_to_insert:
			try:
				self.connection.execute(self.upload_history.insert(), self.recording_data_to_insert)
				is_deleted = self.delete_uploaded_meeting(meeting)
				self.update_upload_status(meeting, is_deleted)
			except Exception as E:
				logger.warning(str(E))

	def build_report_to_admin(self, meeting):
		status = self.get_meeting_status(meeting)
		folder_link = None
		start_time = None
		for recording in self.recording_data_to_insert:
			folder_link = recording['folder_link']
			start_time = recording['start_time']
		if self.recording_data_to_insert and not status:
			logger.info(f'--- report error to admin {meeting["uuid"]}')
			# should notify admin about it.
			msg = f'Failed to download meeting recordings for topic {meeting["topic"]} on {start_time} \n Here is the cloud link https://zoom.us/recording/management/detail?meeting_id={self.double_urlencode(meeting["uuid"])}'
			if folder_link and folder_link.endswith('None'):
				# topic was changed, so cannot find out corresponding drive link in the sheet
				msg += '\n It seems like that the topic was changed by host for some reason. Please have a look at the description for it in sheet and then correct it accordingly.'

			self.emailSender.send_message(msg)

			self.drive.clear_old_recordings(meeting, self.recording_data_to_insert)

	def delete_uploaded_meeting(self, meeting):
		logger.info(f'--- delete meeting after uploading {meeting["uuid"]}')
		status = self.get_meeting_status(meeting)

		# should not delete meeting where any of recordings was not properly uploaded.
		# focus on status
		is_deleted = False
		if status:
			try:
				res = self.session.delete(f"{self.base_url}/meetings/{self.double_urlencode(meeting['uuid'])}/recordings?action=trash", headers=self.get_headers())
				if res.status_code == 204:
					is_deleted = True
			except Exception as E:
				logger.warning(str(E))

		return is_deleted

	def update_upload_status(self, meeting, is_deleted):
		logger.info(f'--- update the meeting_upload_status table {meeting["uuid"]}')
		cnt_files = 0
		topic = meeting['topic']
		start_time = None
		run_at = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
		folder_link = None
		meeting_id = meeting['id']
		meeting_uuid = meeting['uuid']
		for recording in self.recording_data_to_insert:
			folder_link = recording['folder_link']
			start_time = recording['start_time']
			if recording['status']:
				cnt_files += 1

		status = self.get_meeting_status(meeting)
		try:
			# check if this meeting has already inserted or should update
			res = self.connection.execute(f"SELECT id FROM meeting_upload_status WHERE meeting_uuid='{meeting_uuid}'")
			items = [dict(r) for r in res]
			self.meeting_data_to_insert = []
			if len(items):
				update_statement = self.upload_status.update().\
					where(self.upload_status.c.meeting_uuid == meeting_uuid).\
					values({
						'topic': topic,
						'is_deleted': is_deleted,
						'cnt_files': cnt_files,
						'folder_link': folder_link,
						'status': status,
						'run_at': run_at,
					})
				self.connection.execute(update_statement)
			else:
				self.meeting_data_to_insert.append({
					'topic': topic,
					'meeting_id': meeting_id,
					'meeting_uuid': meeting_uuid,
					'start_time': start_time,
					'cnt_files': cnt_files,
					'folder_link': folder_link,
					'status': status,
					'is_deleted': is_deleted,
					'run_at': run_at
				})
				self.connection.execute(self.upload_status.insert(), self.meeting_data_to_insert)
		except Exception as E:
			logger(str(E))

	def delete_recordings_after_download(self, api):
		try:
			self.session.post(f"{self.base_url}api?action=trash", headers=self.get_headers())
		except Exception as E:
			logger.warning(str(E))

	def validate_size_of_meeting(self, meeting, size=1024):
		total_size = 0
		try:
			for recording in meeting['recording_files']:
				total_size += recording.get('file_size', 0)

			return total_size >= size*1024*1024 # and total_size < 200*1024*1024
		except Exception as E:
			logger.warning(str(E))

	def is_processing_meeting(self, meeting):
		is_processing = False
		try:
			for recording in meeting['recording_files']:
				if recording.get('recording_type') != None and recording.get('status', '') != 'completed':
					is_processing = True

			return is_processing
		except Exception as E:
			logger.warning(str(E))

	def validate_recordings_for_upload(self, meeting):
		# 
		return self.validate_size_of_meeting(meeting, 10) and not self.is_processing_meeting(meeting) and meeting['topic'].lower().startswith('q4')

	def download_to_tempfile(self, temp_filename, vid):
		with open(temp_filename, "wb") as f:
			total_size = int(vid.headers.get('content-length'))
			for chunk in progress.bar(vid.iter_content(chunk_size=1024),
									  expected_size=total_size/1024 + 1):
				if chunk:
					f.write(chunk)
					f.flush()

	def _upload_recording(self, meeting):
		topic = meeting['topic']
		start_date_time = datetime.strptime(meeting['start_time'], '%Y-%m-%dT%H:%M:%SZ').strftime('%b %d %Y')
		file_name = None
		file_type = None
		folder_id = None
		file_id = None
		status = True
		parent_id = None

		for recording in meeting['recording_files']:
			if recording.get('recording_type') != None and recording.get('status', '') != 'processing':
				vid = self.session.get(f"{recording['download_url']}?access_token={self.token.decode()}", stream=True)
				if vid.status_code == 200:
					try:
						recording_type = ' '.join([d.capitalize() for d in recording['recording_type'].split('_')])
						file_type = recording["file_type"]
						file_name = f'{topic} {recording_type}'
						parent_id = self.find_drive_folder_id(topic)
						if parent_id:
							course_number = topic.split('-')[1]

							folder_name = f"{course_number} {start_date_time}"
							folder_id = self.drive.check_folder(folder_name, parent_id)
							# download file with progress
							temporary_file_name = f'/tmp/miami_{uuid1()}'
							logger.info(f'=== download file temp')

							self.download_to_tempfile(temporary_file_name, vid)

							logger.info(f"*** before uploading in meeting {meeting['id']}, topic {topic} created folder {folder_name} id: {folder_id} file {file_name}")
							file_id = self.drive.upload_file(temporary_file_name, file_name, file_type, vid, folder_id)
							if not file_id:
								status = False
							# self.delete_recordings_after_download(f'/meetings/{meeting["id"]}/recordings/{recording["id"]}')
						else:
							msg = f'**** cannot findout parent_id in sheet for topic {topic}'
							logger.warning(msg)
							self.emailSender.send_message(msg)
					except Exception as E:
						status = False
						logger.warning(str(E))

					if folder_id:
						self.update_upload_history(meeting, file_name, file_type, folder_id, file_id, status)
					else:
						# for some reason topic was changed so cannot find out drive link
						# notify admin it@miamiadschool.com about it
						pass

		if folder_id and not parent_id:
			msg = f'cannot findout topic in the sheet for {meeting["topic"]}.'
			self.emailSender.send_message(msg)

	def download_recordings(self):
		logger.info('---- Download from zoom cloud recordings and upload them to Google Drive')
		for meeting in self.meetings:
			if self.validate_recordings_for_upload(meeting):
				self.recording_data_to_insert = []
				self._upload_recording(meeting)
				self.build_report_to_admin(meeting)
				self.update_db(meeting)

	def create_recurring_zoom_meetings(self, account, start_date_time, end_date_time, duration, dow, class_name):
		'''
			Create a recurring zoom meeting for the given user
			- join_before_host must be set to true.
			- duration can be calculated based on start_date_time and end_date_time
			@params:
				start_date, start_time, end_date, end_time
				host_email, password
			@input:
				topic: class name
				host_email: email address of the meeting host
				start_time: meeting start date time in UTC/GMT. e.g: 2020-10-03T00:00:00Z
				password: meeting password
				duration: meeting duration (integer)
				timezone: America/New_York
				settings:
					join_before_host: allow participants to join the meeting before the host starts 
						the meeting
				recurrence:
					type: 2 - weekly
					weekly_days: 2
						1: Sunday ~ 7: Monday

		'''
		meeting = None
		try:
			
			json_data = {
				'topic': class_name,
				'type': 8,
				'host_email': account['email'],
				'start_time': start_date_time,
				'password': self.get_random_pwd(),
				'duration': duration,
				'timezone': 'America/New_York',
				'schedule_for':account['email'],
				'settings': {
					'waiting_room': False,
					'join_before_host': True,
					'use_pmi': False
				},
				'recurrence': {
					'type': 2,
					'weekly_days': dow,
					'end_date_time': end_date_time
				}
			}

			meeting = self.session.post(f"{self.base_url}users/{account['email']}/meetings", json=json_data, headers=self.get_headers())
		except Exception as E:
			logger.warning(str(E))

		return meeting

if __name__ == '__main__':
	zoom = Zoom()

	parser = argparse.ArgumentParser()
	parser.add_argument('-s', '--size', type=int, required=True, help="size of trash file in MB to delete")

	zoom.size_limit = parser.parse_args().size
	zoom.clean_tiny_recordings()