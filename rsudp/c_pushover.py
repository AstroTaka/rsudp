import os, sys
import time
from datetime import datetime, timedelta
from rsudp.raspberryshake import ConsumerThread
import rsudp.raspberryshake as rs
from rsudp import printM, printW, printE, helpers
import rsudp
import requests
import traceback
import numpy as np

#import telegram as tg

class Pushover(rs.ConsumerThread):
	def __init__(self, user, token, location_name, send_over_shindo3=False, q=False, send_images=False):
		"""
		Initializing the Pushover message posting thread.

		"""
		super().__init__()
		self.sender = 'Pushover'
		self.alive = True
		self.send_images = send_images
		self.user = user
		self.token = token
		self.location_name = location_name
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

	def pushover_send_image(self, filename, msg, priority=0):
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

	def pushover_send_message(self, msg, priority=0):
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
				"priority": priority,
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

	def calc_distance(self, lat1, lng1, lat2, lng2):
		R = 6371. # 地球の平均半径

		# 度数法からラジアンに変換
		lat1 = np.deg2rad(lat1)
		lng1 = np.deg2rad(lng1)
		lat2 = np.deg2rad(lat2)
		lng2 = np.deg2rad(lng2)

		d = R * np.arccos(
			np.cos(lat1) * np.cos(lat2) * np.cos(lng1 - lng2)
			+ np.sin(lat1) * np.sin(lat2)
		) 

		return d
	
	def getShindoName(self, I: float, lang: str = 'jp') -> str:
		"""
		@brief Convert instrumental shindo scale to a string
		@param I JMA instrumental shindo scale
		@param lang Language ('jp' or 'en')
		"""
		if I < 0.5:
			if lang == 'jp':
				return '０'
			else:
				return '0'
		elif 0.5 <= I < 1.5:
			if lang == 'jp':
				return '１'
			else:
				return '1'
		elif 1.5 <= I < 2.5:
			if lang == 'jp':
				return '２'
			else:
				return '2'
		elif 2.5 <= I < 3.5:
			if lang == 'jp':
				return '３'
			else:
				return '3'
		elif 3.5 <= I < 4.5:
			if lang == 'jp':
				return '４'
			else:
				return '4'
		elif 4.5 <= I < 5.0:
			if lang == 'jp':
				return '５弱'
			else:
				return '5-'
		elif 5.0 <= I < 5.5:
			if lang == 'jp':
				return '５強'
			else:
				return '5+'
		elif 5.5 <= I < 6.0:
			if lang == 'jp':
				return '６弱'
			else:
				return '6-'
		elif 6.0 <= I < 6.5:
			if lang == 'jp':
				return '６強'
			else:
				return '6+'
		elif I >= 6.5:
			if lang == 'jp':
				return '７'
			else:
				return '7'

	def get_kyoshin_msg(self):
		url = 'http://www.kmoni.bosai.go.jp/webservice/hypo/eew/'
		now = datetime.now()
		kyoshin_time0 = (now).strftime('%Y%m%d%H%M%S')
		kyoshin_time1 = (now-timedelta(seconds=1)).strftime('%Y%m%d%H%M%S')
		kyoshin_time2 = (now-timedelta(seconds=2)).strftime('%Y%m%d%H%M%S')
		header= {"content-type": "application/json"}
		intensity = 0.0
		find_kyoshin = True
		try:
			kyoshin_time = kyoshin_time2
			res = requests.get(url+kyoshin_time2+'.json',headers=header).json()

			if res['result']['message'] != "":
				kyoshin_time = kyoshin_time1
				res = requests.get(url+kyoshin_time1+'.json',headers=header).json()

			if res['result']['message'] != "":
				kyoshin_time = kyoshin_time0
				res = requests.get(url+kyoshin_time0+'.json',headers=header).json()

			alertflg=''
			if 'alertflg' in res:
				alertflg = '/'+res['alertflg']
				if '予報' in alertflg:
					alertflg=''

			report_num='第'+res['report_num']+'報'
			if res['is_final']:
				report_num=report_num+'(最終)'

			msg = ('震源地:'+res['region_name']+'/M'+res['magunitude']+'/深さ'+
				res['depth']+'/最大予測震度'+res['calcintensity']+'/'+
				report_num+alertflg)

			try:
				latitude = float(res['latitude'])
				longitude = float(res['longitude'])
				mag = float(res['magunitude']) - 0.171
				depth = float("".join(filter(lambda c: not str.isalpha(c), res['depth'])))
			except:
				latitude = 0.0
				longitude = 0.0
				mag = 0.0
				depth = 0.0

			if latitude != 0 and longitude !=0:
				epicenterDistance  = self.calc_distance(latitude, longitude, rs.inv[0][-1].latitude, rs.inv[0][-1].longitude)
				long = 10 ** (0.5 * mag - 1.85) / 2
				hypocenterDistance = (depth ** 2 + epicenterDistance ** 2) ** 0.5 - long
				x = max([hypocenterDistance, 3])
				gpv600 = 10 ** (0.58 * mag + 0.0038 * depth - 1.29 - np.log10(x + 0.0028 * (10 ** (0.5 * mag))) - 0.002 * x)
				pgv400 = gpv600 * 1.31
				intensity = 2.68 + 1.72 * np.log10(pgv400)
				shindo = self.getShindoName(intensity)
				msg = msg + '\n' + self.location_name + 'の最大予測震度：' + shindo + '(' + "{:.1f}".format(intensity) +')'

			if res['result']['message'] != "":
				msg = '地震発生の確認ができませんでした。\n(' + kyoshin_time + ')'
				find_kyoshin = False

		except:
			printE('%s' % (traceback.format_exc()), self.sender)
			msg='地震発生の確認ができませんでした。'
			find_kyoshin = False
		
		return msg, intensity, find_kyoshin

	def _when_alarm(self, d):
		'''
		Send a Pushover in an alert scenario.

		:param bytes d: queue message
		'''

		event_time = helpers.fsec(helpers.get_msg_time(d))
		self.last_event_str = '%s' % ((event_time+(3600*9)).strftime(self.fmt)[:22])

		for count in range(2):
			kyoshin_msg, intensity, find_kyoshin = self.get_kyoshin_msg()
			if count==0:
				message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/\n%s' % (self.message1, self.last_event_str, kyoshin_msg)
			else:
				if find_kyoshin:
					message = kyoshin_msg
				else:
					message = '地震は発生していないと思われます。'

			if self.send_over_shindo3 and intensity <= 3.5:
				printM('Do not send Pushover, becuase Shindo is less than 3.', sender=self.sender)
				return

			priority = 0
			if intensity >= 2.5:
				priority=1
				if intensity >= 4.5:
					priority=2

			try:
				printM('Sending alert...', sender=self.sender)
				self.pushover_send_message(message, priority)
				printM('Sent Pushover: %s' % (message), sender=self.sender)

			except Exception as e:
				printE('Could not send alert - %s' % (e), sender=self.sender)
				try:
					printE('Waiting 5 seconds and trying to send again...', sender=self.sender, spaces=True)
					time.sleep(5)
					self.pushover_send_message(message, priority)
					printM('Sent Pushover: %s' % (message), sender=self.sender)
				except Exception as e:
					printE('Could not send alert - %s' % (e), sender=self.sender)
			
			if find_kyoshin:
				break

			if count==0:
				printE('Cannot find Kyoshin data and Waiting 3 seconds and trying to send again...', sender=self.sender, spaces=True)
				time.sleep(3)

	def _when_img(self, d):
		'''
		Send a Pushover image in when you get an ``IMGPATH`` message.

		:param bytes d: queue message
		'''
		if self.send_images:
			kyoshin_msg, intensity, find_kyoshin = self.get_kyoshin_msg()

			imgpath = helpers.get_msg_path(d).split('|')[0]
			printM('imgpath:%s' %(imgpath),sender=self.sender)
			if os.path.exists(imgpath):
				msg = d.decode('utf-8').split('|')

				priority = 0
				if not (('震度０' in msg[1]) or ('震度１' in msg[1]) or ('震度２' in msg[1])) or intensity >= 2.5:
					priority=1
					if not (('震度３' in msg[1]) or ('震度４' in msg[1])) or intensity >= 4.5:
						priority=2

				if self.send_over_shindo3 and priority == 0:
					printM('Do not send Pushover, becuase Shindo is less than 3.', sender=self.sender)
					return

				message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/\n%s\n' % (self.message1, self.last_event_str, kyoshin_msg)
				try:
					printM('Uploading image to Pushover %s' % (imgpath), self.sender)
					self.pushover_send_image(imgpath,message+self.location_name+'の実際の震度：'+msg[1],priority)
					printM('Sent image', sender=self.sender)
					already_sent = True
				except Exception as e:
					printE('Could not send image - %s' % (e), sender=self.sender)
					try:
						printM('Waiting 5 seconds and trying to send again...', sender=self.sender)
						time.sleep(5.1)
						printM('Uploading image to Pushover (2nd try) %s' % (imgpath), self.sender)
						self.pushover_send_image(imgpath,message+self.location_name+'の実際の震度：'+msg[1],priority)
						printM('Sent image', sender=self.sender)

					except Exception as e:
						printE('Could not send image - %s' % (e), sender=self.sender)
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
