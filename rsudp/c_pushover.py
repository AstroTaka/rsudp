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
	def __init__(self, user, token, send_over_shindo3=False, q=False, send_images=False):
		"""
		Initializing the Pushover message posting thread.

		"""
		super().__init__()
		self.sender = 'Pushover'
		self.alive = True
		self.send_images = send_images
		self.user = user
		self.token = token
		self.send_over_shindo3 = send_over_shindo3
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

		if priority==2:
			data = {
				"token": self.token,
				"user": self.user,
				"message": msg,
				"priority": priority,
				"retry": 30,
				"expire": 1800,
				"sound": "siren"
			}
		else:
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

	def get_kyoshin_msg(self):
		url = 'http://www.kmoni.bosai.go.jp/webservice/hypo/eew/'
		kyoshin_time = (datetime.now()-timedelta(seconds=2)).strftime('%Y%m%d%H%M%S')
		header= {"content-type": "application/json"}
		try:
			res = requests.get(url+kyoshin_time+'.json',headers=header).json()

			alertflg=''
			if 'alertflg' in res:
				alertflg = '/'+res['alertflg']
				if '予報' in alertflg:
					alertflg=''

			report_num=''
			if res['is_final']:
				report_num='最終報'
			else:
				report_num='第'+res['report_num']+'報'

			msg = ('震源地:'+res['region_name']+'/M'+res['magunitude']+'/深さ'+
				res['depth']+'/最大予測震度'+res['calcintensity']+'/'+
				report_num+alertflg)

			if res['result']['message'] != "":
				msg = '地震の発生が確認できませんでした。'
				
		except:
			msg=''
		
		return msg

	def _when_alarm(self, d):
		'''
		Send a Pushover in an alert scenario.

		:param bytes d: queue message
		'''

		event_time = helpers.fsec(helpers.get_msg_time(d))
		self.last_event_str = '%s' % ((event_time+(3600*9)).strftime(self.fmt)[:22])
		kyoshin_msg = self.get_kyoshin_msg()
		message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/\n%s' % (self.message1, self.last_event_str, kyoshin_msg)

		if self.send_over_shindo3:
			printM('Do not send Pushover, becuase Shindo is less than 3.', sender=self.sender)
			return

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
			kyoshin_msg = self.get_kyoshin_msg()

			imgpath = helpers.get_msg_path(d).split('|')[0]
			printM('imgpath:%s' %(imgpath),sender=self.sender)
			if os.path.exists(imgpath):
				msg = d.decode('utf-8').split('|')

				priority = 0
				if not (('震度０' in msg[1]) or ('震度１' in msg[1]) or ('震度２' in msg[1])):
					priority=1
					if not (('震度３' in msg[1]) or ('震度４' in msg[1])):
						priority=2

				if self.send_over_shindo3 and priority == 0:
					printM('Do not send Pushover, becuase Shindo is less than 3.', sender=self.sender)
					return

				message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/\n%s\n' % (self.message1, self.last_event_str, kyoshin_msg)
				try:
					printM('Uploading image to Pushover %s' % (imgpath), self.sender)
					self.pushover_send_image(imgpath,message+'地震計の震度：'+msg[1],priority)
					printM('Sent image', sender=self.sender)
					already_sent = True
				except Exception as e:
					printE('Could not send image - %s' % (e))
					try:
						printM('Waiting 5 seconds and trying to send again...', sender=self.sender)
						time.sleep(5.1)
						printM('Uploading image to Pushover (2nd try) %s' % (imgpath), self.sender)
						self.pushover_send_image(imgpath,message+'地震計の震度：'+msg[1],priority)
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
