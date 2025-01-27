import os, sys
import time
from datetime import datetime, timedelta
from rsudp.raspberryshake import ConsumerThread
import rsudp.raspberryshake as rs
from rsudp import printM, printW, printE, helpers
import rsudp
import requests
import traceback
import shutil
import hashlib

#import telegram as tg

class LINEApi(rs.ConsumerThread):
	def __init__(self, token1, user1, token2, user2, image_dir_path, image_url_path, q=False, send_images=False):
		"""
		Initializing the LINE API message posting thread.

		"""
		super().__init__()
		self.sender = 'LINEApi'
		self.alive = True
		self.send_images = send_images
		self.token1 = token1
		self.user1 = user1
		self.token2 = token2
		self.user2 = user2
		self.image_dir_path = image_dir_path
		self.image_url_path = image_url_path
		self.fmt = '%Y-%m-%d %H:%M:%S.%f'
		self.region = ' - region: %s' % rs.region.title() if rs.region else ''
		self.message0 = '(Raspberry Shake station %s.%s%s) Event detected at' % (rs.net, rs.stn, self.region)
		self.livelink = 'live feed https://raspberryshake.net/stationview/#?net=%s&sta=%s' % (rs.net, rs.stn)
		self.message1 = '地震発生 %s.%s' % (rs.net, rs.stn)

		if q:
			self.queue = q
		else:
			printE('no queue passed to consumer! Thread will exit now!', self.sender)
			sys.stdout.flush()
			self.alive = False
			sys.exit()

		printM('Starting.', self.sender)

	def line_api_send_image(self, filename, msg, token, user):
		line_image_enable = False

		try:
			file_ext = os.path.splitext(filename)[1]

			line_filename = hashlib.sha256(filename.encode()).hexdigest() + file_ext
			dst_file_full_path = self.image_dir_path.rstrip('/') + '/' + line_filename
			image_url = self.image_url_path.rstrip('/') + '/' + line_filename

			shutil.copyfile(filename, dst_file_full_path)

			line_image_enable = True
		except:
			pass

		line_url = 'https://api.line.me/v2/bot/message/push'

		line_headers = {
            "Content_Type": "application/json",
            "Authorization": "Bearer " + token
        }
	
		if line_image_enable:
			data = {
				"to": user,
				"messages":[
					{
						"type": "text",
						"text": msg
					},
					{
						"type": "image",
						"originalContentUrl": image_url,
						"previewImageUrl": image_url
					}
				]
			}
		else:
			data = {
				"to": user,
				"messages":[
					{
						"type": "text",
						"text": msg
					}
				]
			}
		
		line_response = requests.post(line_url,
                                      headers=line_headers,json=data).text
		printM('Post response: %s' % (line_response),self.sender)
	
		return line_response

	def line_api_send_message(self, msg, token, user):
		line_url = 'https://api.line.me/v2/bot/message/push'

		line_headers = {
            "Content_Type": "application/json",
            "Authorization": "Bearer " + token
        }
	
		data = {
			"to": user,
			"messages":[
				{
					"type": "text",
					"text": msg
				}
			]
		}
		
		line_response = requests.post(line_url,
                                      headers=line_headers,json=data).text
		printM('Post response: %s' % (line_response),self.sender)
	
		return line_response

	def getq(self):
		d = self.queue.get()
		self.queue.task_done()

		if 'TERM' in str(d):
			self.alive = False
			printM('Exiting.', self.sender)
			sys.exit()
		else:
			return d


	def _when_alarm(self, d):
		'''
		Send a LINE API in an alert scenario.

		:param bytes d: queue message
		'''
		event_time = helpers.fsec(helpers.get_msg_time(d))
		self.last_event_str = '%s' % ((event_time+(3600*9)).strftime(self.fmt)[:22])
		message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/' % (self.message1, self.last_event_str)
		if self.token != '':
			try:
				printM('Sending alert...', sender=self.sender)
				self.line_api_send_message(message, self.token1, self.user1)
				printM('Sent LINE API: %s' % (message), sender=self.sender)

			except Exception as e:
				printE('Could not send alert - %s' % (e))
				try:
					printE('Waiting 5 seconds and trying to send again...', sender=self.sender, spaces=True)
					time.sleep(5)
					self.line_api_send_message(message, self.token1, self.user1)
					printM('Sent LINE API: %s' % (message), sender=self.sender)
				except Exception as e:
					printE('Could not send alert - %s' % (e))

	def _when_img(self, d):
		'''
		Send a LINE API image in when you get an ``IMGPATH`` message.

		:param bytes d: queue message
		'''
		if self.send_images:
			imgpath = helpers.get_msg_path(d).split('|')[0]
			printM('imgpath:%s' %(imgpath),sender=self.sender)
			response = None
			if os.path.exists(imgpath):
				msg = d.decode('utf-8').split('|')
				already_sent = False
				# token2
				if self.token2 != '' and self.user2 != '':
					if not (('震度０' in msg[1]) or ('震度１' in msg[1]) or ('震度２' in msg[1])):
						message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/\n' % (self.message1, self.last_event_str)
						try:
							printM('Uploading image to LINE API %s' % (imgpath), self.sender)
							self.line_api_send_image(imgpath, message+msg[1], self.token2, self.user2)
							printM('Sent image', sender=self.sender)
							already_sent = True
						except Exception as e:
							printE('Could not send image - %s' % (e))
							try:
								printM('Waiting 5 seconds and trying to send again...', sender=self.sender)
								time.sleep(5.1)
								printM('Uploading image to LINE API (2nd try) %s' % (imgpath), self.sender)
								self.line_api_send_image(imgpath, message+msg[1], self.token2, self.user2)
								printM('Sent image', sender=self.sender)
								already_sent = True

							except Exception as e:
								printE('Could not send image - %s' % (e))
								response = None
					else:
						printM('Do not send LINE API for token 2, becuase Shindo is less than 3.')

				if self.token1 != '' and self.user1 != '' and not already_sent:
					try:
						printM('Uploading image to LINE API %s' % (imgpath), self.sender)
						self.line_api_send_image(imgpath, msg[1], self.token1, self.user1)
						printM('Sent image', sender=self.sender)
					except Exception as e:
						printE('Could not send image - %s' % (e))
						try:
							printM('Waiting 5 seconds and trying to send again...', sender=self.sender)
							time.sleep(5.1)
							printM('Uploading image to LINE API (2nd try) %s' % (imgpath), self.sender)
							self.line_api_send_image(imgpath, msg[1], self.token1, self.user1)
							printM('Sent image', sender=self.sender)

						except Exception as e:
							printE('Could not send image - %s' % (e))
							response = None
			else:
				printM('Could not find image: %s' % (imgpath), sender=self.sender)


	def run(self):
		"""
		Reads data from the queue and sends a message if it sees an IMGPATH message
		"""
		while True:
			d = self.getq()

			if 'ALARM' in str(d):
				self._when_alarm(d)

			if 'IMGPATH' in str(d):
				self._when_img(d)
