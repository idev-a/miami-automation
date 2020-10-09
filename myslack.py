import os
from slack import WebClient
import pdb

from logger import logger

SLACK_CHANNEL_LINK_COLUMN = 'Slack Channel URL'
SLACK_CHANNEL_ID_COLUMN = 'Slack Channel ID'

class Slack:
	SLACK_API_TOKEN = 'xoxp-1013175414562-1241019797840-1396826073638-f28367384c6c7143dc34418f50c1991f'
	channels = []
	members = []

	def __init__(self):
		self.slack_client = WebClient(token=self.SLACK_API_TOKEN)

	def look_channel_from_name(self, name):
		_channel = None
		for channel in self.channels:
			if channel['name'] == name:
				_channel = channel
				break

		return _channel

	def ids_from_emails(self, emails):
		ids = []
		for email in emails:
			for member in self.members:
				if member['profile'].get('email', '') == email:
					ids.append(member['id'])

		return ','.join(ids)


	def setup(self, spread):
		self.ccs = spread.ccs # Campuscafe Course Schedule sheet
		self.sr = spread.sr # Student Roster sheet

		self.read_all_users()
		
		self.read_all_channels()

		# self.archive_channels_start_with_q3()

		self.archive_channels('q4')

		# self.create_new_channels()

		# self.invite_users()

		# self.post_and_pin_message()

		return self.ccs

	def read_all_users(self):
		try:
			cursor = None
			while True:
				res = self.slack_client.users_list(cursor=cursor)
				self.members += res["members"]
				cursor = res['response_metadata']['next_cursor']
				if not cursor:
					break
		except Exception as e:
			print(e)

	def read_all_channels(self):
		try:
			cursor = None
			while True:
				res = self.slack_client.conversations_list(cursor=cursor)
				self.channels += res["channels"]
				cursor = res['response_metadata']['next_cursor']
				if not cursor:
					break
		except Exception as e:
			print(e)

	def archive_channels(self, prefix):
		logger.info(f'--- Archive channels starts with {prefix}')
		# Find all Slack channels that start with prefix
		# Archive all Slack channels that match that criterion
		for channel in self.channels:
			if channel['name'].startswith(prefix):
				if not channel['is_archived']:
					res = self.slack_client.pins_list(channel=channel['id'])
					for item in res['items']:
						try:
							self.slack_client.pins_remove(channel=channel['id'], timestamp=item['message']['ts'])
						except Exception as E:
							logger.warning(f'====== {channel["id"]}')

	def archive_channels_start_with_q3(self):
		self.archive_channels('q3')

	def update_sheet(self, channel, index):
		self.ccs.at[index, SLACK_CHANNEL_LINK_COLUMN] = f"https://app.slack.com/client/T010D55C6GJ/{channel['id']}"
		self.ccs.at[index, SLACK_CHANNEL_ID_COLUMN] = channel['id']

	def create_new_channels(self):
		logger.info('--- Create New Channels and update Campuscafe Course Schedule sheet with channel link')
		index = 0
		for sc in self.ccs['Slack Channel Name']:
			try:
				channel = self.look_channel_from_name(sc)
				if not channel:
					res = self.slack_client.conversations_create(name=sc)
					if res['ok']:
						self.channels.append(res['channel'])
						channel = res['channel']
				elif channel['is_archived']:
					self.slack_client.conversations_unarchive(channel=channel['id'])

				self.update_sheet(channel, index)
				index += 1
				# break
			except Exception as E:
				logger.warning(str(E))

	def invite_users(self):
		'''
			read users from student roster and invite them to new channels
		'''
		logger.info('--- Invite users from student roster to new channels')
		for sc, scl, unique_id in zip(self.ccs['Slack Channel Name'], self.ccs[SLACK_CHANNEL_ID_COLUMN], self.ccs['Unique ID']):
			users = []
			for course, addr in zip(self.sr['COURSE'], self.sr['ADDRESS']):
				if unique_id in course:
					users.append(addr)

			if not scl:
				scl = self.look_channel_from_name(sc)['id']
			try:
				users_ids = self.ids_from_emails(users)
				if users_ids:
					res = self.slack_client.conversations_invite(channel=scl, users=users_ids)
					if not res['ok']:
						logger.warning(res['error'])
			except Exception as E:
				logger.warning(str(E))

			# break		

	def post_and_pin_message(self):
		'''
			Post message to channel and pin it
		'''		
		for channel_id, zoom_link, student_link, recordings_link  in zip(
			self.ccs[SLACK_CHANNEL_ID_COLUMN],
			self.ccs['Zoom Meeting Link'],
			self.ccs['Google Drive: Student Work'],
			self.ccs['Google Drive: Recordings']
		):
			try:
				text = f"The Zoom Link is: {zoom_link} \n \
				The Student Work link is: {student_link} \n \
				The Recordings link is: {recordings_link}"
				res = self.slack_client.chat_postMessage(channel=channel_id, text=text)
				if res['ok']:
					res = self.slack_client.pins_add(channel=channel_id, timestamp=res['ts'])
					if not res['ok']:
						logger.warning(res['error'])
				else:
					logger.warning(res['error'])

			except Exception as E:
				logger.warning(str(E))
			
			# break

if __name__ == '__main__':
	slack = Slack()

	slack.init_slack()
	slack.manage_slack_channels()