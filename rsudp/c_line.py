import os, sys
import time
from datetime import datetime, timedelta
from rsudp.raspberryshake import ConsumerThread
import rsudp.raspberryshake as rs
from rsudp import printM, printW, printE, helpers
import rsudp
import requests
import traceback

#import telegram as tg

class LINE(rs.ConsumerThread):
	def __init__(self, token, q=False, send_images=False):
		"""
		Initializing the LINE message posting thread.

		"""
		super().__init__()
		self.sender = 'LINE'
		self.alive = True
		self.send_images = send_images
		self.token = token
		self.fmt = '%Y-%m-%d %H:%M:%S.%f'
		self.region = ' - region: %s' % rs.region.title() if rs.region else ''
		self.message0 = '(Raspberry Shake station %s.%s%s) Event detected at' % (rs.net, rs.stn, self.region)
		self.livelink = 'live feed https://raspberryshake.net/stationview/#?net=%s&sta=%s' % (rs.net, rs.stn)

		if q:
			self.queue = q
		else:
			printE('no queue passed to consumer! Thread will exit now!', self.sender)
			sys.stdout.flush()
			self.alive = False
			sys.exit()

		printM('Starting.', self.sender)

	def line_send_image(self, filename, msg):
		url = "https://notify-api.line.me/api/notify"
		headers = {"Authorization" : "Bearer "+ self.token}
		payload = {"message" :  msg }
		res = ''
		with open(filename, 'rb') as f:
			res = requests.post(url ,headers = headers ,params=payload, files={'imageFile': f}).text
			printM('Post response: %s' % (res),self.sender)
		return res

	def line_send_message(self, message):
		url = "https://notify-api.line.me/api/notify"
		headers = {"Authorization" : "Bearer "+ self.token}
		payload = {"message" :  message}
		res = ''
		res = requests.post(url ,headers = headers ,params=payload,).text
		printM('Post response: %s' % (res),self.sender)
		return res

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
		Send a LINE in an alert scenario.

		:param bytes d: queue message
		'''
		event_time = helpers.fsec(helpers.get_msg_time(d))
		self.last_event_str = '%s' % ((event_time+(3600*9)).strftime(self.fmt)[:22])
		message = '%s %s JST - %s\nhttp://www.kmoni.bosai.go.jp/' % (self.message0, self.last_event_str, self.livelink)
		response = None
		try:
			printM('Sending alert...', sender=self.sender)
			self.line_send_message(message)
			printM('Sent LINE: %s' % (message), sender=self.sender)

		except Exception as e:
			printE('Could not send alert - %s' % (e))
			try:
				printE('Waiting 5 seconds and trying to send again...', sender=self.sender, spaces=True)
				time.sleep(5)
				self.line_send_message(message)
				printM('Sent LINE: %s' % (message), sender=self.sender)
			except Exception as e:
				printE('Could not send alert - %s' % (e))
				response = None

	def _when_img(self, d):
		'''
		Send a LINE image in when you get an ``IMGPATH`` message.

		:param bytes d: queue message
		'''
		if self.send_images:
			imgpath = helpers.get_msg_path(d).split('|')[0]
			printM('imgpath:%s' %(imgpath),sender=self.sender)
			response = None
			if os.path.exists(imgpath):
				try:
					printM('Uploading image to LINE %s' % (imgpath), self.sender)
					self.line_send_image(imgpath,d.decode('utf-8').split('|')[1])
					printM('Sent image', sender=self.sender)
				except Exception as e:
					printE('Could not send image - %s' % (e))
					try:
						printM('Waiting 5 seconds and trying to send again...', sender=self.sender)
						time.sleep(5.1)
						printM('Uploading image to LINE (2nd try) %s' % (imgpath), self.sender)
						self.line_send_image(imgpath,d.decode('utf-8').split('|')[1])
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
