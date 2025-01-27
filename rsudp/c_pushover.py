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

class Pushover(rs.ConsumerThread):
	def __init__(self, user, token, q=False, send_images=False):
		"""
		Initializing the Pushover message posting thread.

		"""
		super().__init__()
		self.sender = 'Pushover'
		self.alive = True
		self.send_images = send_images
		self.user = user
		self.token = token
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

	def pushover_send_image(self, filename, msg, priority):
		url = "https://api.pushover.net/1/messages.json"
		data = {
			"token": self.token,
			"user": self.user,
			"message": msg,
			"priority": priority
		}
		res = ''
		with open(filename, 'rb') as f:
			res = requests.post(url, data=data, files={'attachment': f}).text
			printM('Post response: %s' % (res),self.sender)
		return res

	def pushover_send_message(self, msg):
		url = "https://api.pushover.net/1/messages.json"
		data = {
			"token": self.token,
			"user": self.user,
			"message": msg
		}
		res = ''
		res = requests.post(url, data = data).text
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
		Send a Pushover in an alert scenario.

		:param bytes d: queue message
		'''
		event_time = helpers.fsec(helpers.get_msg_time(d))
		self.last_event_str = '%s' % ((event_time+(3600*9)).strftime(self.fmt)[:22])
		message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/' % (self.message1, self.last_event_str)

		try:
			printM('Sending alert...', sender=self.sender)
			self.pushover_send_message(message)
			printM('Sent Pushover: %s' % (message), sender=self.sender)

		except Exception as e:
			printE('Could not send alert - %s' % (e))
			try:
				printE('Waiting 5 seconds and trying to send again...', sender=self.sender, spaces=True)
				time.sleep(5)
				self.pushover_send_message(message)
				printM('Sent Pushover: %s' % (message), sender=self.sender)
			except Exception as e:
				printE('Could not send alert - %s' % (e))

	def _when_img(self, d):
		'''
		Send a Pushover image in when you get an ``IMGPATH`` message.

		:param bytes d: queue message
		'''
		if self.send_images:
			imgpath = helpers.get_msg_path(d).split('|')[0]
			printM('imgpath:%s' %(imgpath),sender=self.sender)
			if os.path.exists(imgpath):
				msg = d.decode('utf-8').split('|')

				priority = 0
				if not (('震度０' in msg[1]) or ('震度１' in msg[1]) or ('震度２' in msg[1])):
					priority=1

				message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/\n' % (self.message1, self.last_event_str)
				try:
					printM('Uploading image to Pushover %s' % (imgpath), self.sender)
					self.pushover_send_image(imgpath,message+msg[1],priority)
					printM('Sent image', sender=self.sender)
					already_sent = True
				except Exception as e:
					printE('Could not send image - %s' % (e))
					try:
						printM('Waiting 5 seconds and trying to send again...', sender=self.sender)
						time.sleep(5.1)
						printM('Uploading image to Pushover (2nd try) %s' % (imgpath), self.sender)
						self.pushover_send_image(imgpath,message+msg[1],priority)
						printM('Sent image', sender=self.sender)

					except Exception as e:
						printE('Could not send image - %s' % (e))
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
