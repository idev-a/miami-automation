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
import argparse
import threading
import multiprocessing.pool as mpool

from logger import logger
upload_lock = threading.Lock()

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
	users = []
	zoom_users = []
	size_limit = 1024
	page_size = 300

	def __init__(self):
		self.session = requests.Session()
		self.session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=100000, max_retries=2))
		self.generate_jwt_token()
		# self.read_all_users()

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

	def find_drive_folder_id(self, cur_topic):
		folder_id = None
		for folder_link, topic in zip(self.ccs['Google Drive: Recordings'], self.ccs['Zoom Topic']):
			if topic == cur_topic:
				folder_id = os.path.basename(folder_link)
				break

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
					res = self.session.delete(f"{self.base_url}/meetings/{meeting['id']}/recordings?action=trash", headers=self.get_headers())
					if res.status_code == 204:
						logger.info(f'*** clear meeting ID: {meeting["start_time"]}, Topic: {meeting["topic"]}')
						total_cleared += 1
				except Exception as E:
					logger.warning(str(E))

		logger.info(f'--- Successfully cleared recordings {total_cleared}')			

	def delete_downloaded_recording(self, api):
		try:
			self.session.post(f"{self.base_url}api?action=trash", headers=self.get_headers())
		except Exception as E:
			logger.warning(str(E))

	def validate_size_of_meeting(self, meeting, size=1024):
		total_size = 0
		try:
			for recording in meeting['recording_files']:
				total_size += recording.get('file_size', 0)

			return total_size >= size*1024
		except Exception as E:
			logger.warning(str(E))

	def is_processing_meeting(self, meeting):
		is_processing = False
		try:
			for recording in meeting['recording_files']:
				if recording.get('status', '') == 'processing':
					is_processing = True

			return is_processing
		except Exception as E:
			logger.warning(str(E))

	def validate_recordings_for_upload(self, meeting):
		return self.validate_size_of_meeting(meeting, 1024*10) and not self.is_processing_meeting(meeting) and meeting['topic'].startswith('Q4')

	def download_recordings(self):
		logger.info('---- Download from zoom cloud recordings and upload them to Google Drive')
		# pool = mpool.ThreadPool(20)
		# threads = []
		for meeting in self.meetings:
			if self.validate_recordings_for_upload(meeting):
				# thread = pool.apply_async(self._upload_recording, args=(meeting,))
				# threads.append(thread)
				self._upload_recording(meeting)

		# for thread in threads:
		# 	thread.get()

	def _upload_recording(self, meeting):
		topic = meeting['topic']
		for recording in meeting['recording_files']:
			if recording.get('file_size', 0) < 1024 or True:
				vid = self.session.get(f"{recording['download_url']}?access_token={self.token.decode()}", stream=True)
				try:
					if vid.status_code == 200 and recording.get('recording_type') and recording.get('status', '') != 'processing':
						recording_type = ' '.join([d.capitalize() for d in recording['recording_type'].split('_')])
						file_type = recording["file_type"]
						filename = f'{topic} {recording_type}'
						parent_id = self.find_drive_folder_id(topic)
						if parent_id:
							course_number = topic.split('-')[1]
							start_date_time = datetime.strptime(recording['recording_start'], '%Y-%m-%dT%H:%M:%SZ').strftime('%b %d %Y')

							folder_name = f"{course_number} {start_date_time}"
							folder_id = self.drive.check_folder(folder_name, parent_id)
							# download file
							# with open(filename, "wb") as f:
							# 	total_size = int(vid.headers.get('content-length'))
							# 	for chunk in progress.bar(vid.iter_content(chunk_size=1024),
							# 							  expected_size=total_size/1024 + 1):
							# 		if chunk:
							# 			f.write(chunk)
							# 			f.flush()

							logger.info(f"*** before uploading in meeting {meeting['id']}, topic {topic} created folder {folder_name} id: {folder_id} file {filename}")
							self.drive.upload_file(filename, file_type, vid, folder_id)
							# self.delete_downloaded_recording(f'/meetings/{meeting["id"]}/recordings/{recording["id"]}')
				except Exception as E:
					logger.warning(str(E))


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

	zoom.size_limit = parser.parse_args().size * 1024
	zoom.clean_tiny_recordings()