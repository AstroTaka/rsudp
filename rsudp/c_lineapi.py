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
import numpy as np

from PIL import Image, ImageDraw, ImageFont
import requests
import io

import textwrap
import unicodedata
from itertools import groupby

#import telegram as tg

#copy from docutils
east_asian_widths = {'W': 2,   # Wide
                     'F': 2,   # Full-width (wide)
                     'Na': 1,  # Narrow
                     'H': 1,   # Half-width (narrow)
                     'N': 1,   # Neutral (not East Asian, treated as narrow)
                     'A': 1}   # Ambiguous (s/b wide in East Asian context,
                               # narrow otherwise, but that doesn't work)

#copy from docutils
def column_width(text):
    """Return the column width of text.

    Correct ``len(text)`` for wide East Asian and combining Unicode chars.
    """
    if isinstance(text, str) and sys.version_info < (3,0):
        return len(text)
    combining_correction = sum([-1 for c in text
                                if unicodedata.combining(c)])
    try:
        width = sum([east_asian_widths[unicodedata.east_asian_width(c)]
                     for c in text])
    except AttributeError:  # east_asian_width() New in version 2.4.
        width = len(text)
    return width + combining_correction


class TextWrapper(textwrap.TextWrapper):
    """Custom subclass that uses a different word splitter."""

    def _wrap_chunks(self, chunks):
        """_wrap_chunks(chunks : [string]) -> [string]

        Original _wrap_chunks use len() to calculate width.
        This method respect to wide/fullwidth characters for width adjustment.
        """
        lines = []
        if self.width <= 0:
            raise ValueError("invalid width %r (must be > 0)" % self.width)

        chunks.reverse()

        while chunks:
            cur_line = []
            cur_len = 0

            if lines:
                indent = self.subsequent_indent
            else:
                indent = self.initial_indent

            width = self.width - column_width(indent)

            if self.drop_whitespace and chunks[-1].strip() == '' and lines:
                del chunks[-1]

            while chunks:
                l = column_width(chunks[-1])

                if cur_len + l <= width:
                    cur_line.append(chunks.pop())
                    cur_len += l

                else:
                    break

            if chunks and column_width(chunks[-1]) > width:
                self._handle_long_word(chunks, cur_line, cur_len, width)

            if self.drop_whitespace and cur_line and cur_line[-1].strip() == '':
                del cur_line[-1]

            if cur_line:
                lines.append(indent + ''.join(cur_line))

        return lines

    def _break_word(self, word, space_left):
        """_break_word(word : string, space_left : int) -> (string, string)

        Break line by unicode width instead of len(word).
        """
        total = 0
        for i,c in enumerate(word):
            total += column_width(c)
            if total > space_left:
                return word[:i-1], word[i-1:]
        return word, ''

    def _split(self, text):
        """_split(text : string) -> [string]

        Override original method that only split by 'wordsep_re'.
        This '_split' split wide-characters into chunk by one character.
        """
        split = lambda t: textwrap.TextWrapper._split(self, t)
        chunks = []
        for chunk in split(text):
            for w, g in groupby(chunk, column_width):
                if w == 1:
                    chunks.extend(split(''.join(g)))
                else:
                    chunks.extend(list(g))
        return chunks

    def _handle_long_word(self, reversed_chunks, cur_line, cur_len, width):
        """_handle_long_word(chunks : [string],
                             cur_line : [string],
                             cur_len : int, width : int)

        Override original method for using self._break_word() instead of slice.
        """
        space_left = max(width - cur_len, 1)
        if self.break_long_words:
            l, r = self._break_word(reversed_chunks[-1], space_left)
            cur_line.append(l)
            reversed_chunks[-1] = r

        elif not cur_line:
            cur_line.append(reversed_chunks.pop())

MAXWIDTH = 70

def fw_wrap(text, width=MAXWIDTH, **kwargs):
    w = TextWrapper(width=width, **kwargs)
    return w.wrap(text)

class LINEApi(rs.ConsumerThread):
	def __init__(self, token1, user1, token2, user2, image_dir_path, location_name, image_url_path, q=False, send_images=False):
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
		self.location_name = location_name
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

	def line_api_send_image(self, filename, msg, token, user, access_kyoshin, kyoshin_time):
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
	
		if access_kyoshin:
			kyoshin_url = ''
			while True:
				try:
					map_url = 'http://www.kmoni.bosai.go.jp/data/map_img/CommonImg/base_map_w.gif'
					map_img = Image.open(io.BytesIO(requests.get(map_url).content)).convert("RGBA")
				except:
					break
				kyoshin_time_tmp = kyoshin_time
				find_image = False
				for count in range(3):
					try:
						jma_url = 'http://www.kmoni.bosai.go.jp/data/map_img/RealTimeImg/jma_s/'+kyoshin_time_tmp[0:8]+'/'+kyoshin_time_tmp+'.jma_s.gif'
						ima_img = Image.open(io.BytesIO(requests.get(jma_url).content)).convert("RGBA")
						map_img.paste(ima_img,(0,0), ima_img)
						ima_img.close()
						find_image = True
						break
					except:
						pass
					kyoshin_time_tmp = (datetime.strptime(kyoshin_time_tmp, '%Y%m%d%H%M%S')-timedelta(seconds=1)).strftime('%Y%m%d%H%M%S')
				if not find_image:
					break

				find_image = False
				for count in range(3):
					try:
						eew_url = 'http://www.kmoni.bosai.go.jp/data/map_img/PSWaveImg/eew/'+kyoshin_time_tmp[0:8]+'/'+kyoshin_time_tmp+'.eew.gif'
						eew_img = Image.open(io.BytesIO(requests.get(eew_url).content)).convert("RGBA")
						map_img.paste(eew_img,(0,0), eew_img)
						eew_img.close()
						find_image = True
						break
					except:
						pass
					kyoshin_time_tmp = (datetime.strptime(kyoshin_time_tmp, '%Y%m%d%H%M%S')-timedelta(seconds=1)).strftime('%Y%m%d%H%M%S')
				if not find_image:
					break

				try:
					level_url = 'http://www.kmoni.bosai.go.jp/data/map_img/ScaleImg/nied_jma_s_w_scale.gif'
					level_img = Image.open(io.BytesIO(requests.get(level_url).content)).convert("RGBA")
					map_img.paste(level_img,(map_img.width-level_img.width+10,map_img.height-level_img.height-3), level_img)
					level_img.close()
				except:
					map_img.close()
					break

				kyoshin_filename = hashlib.sha256((kyoshin_time+'.jma_s').encode()).hexdigest() + '.png'
				dst_file_full_path = self.image_dir_path.rstrip('/') + '/' + kyoshin_filename
				kyoshin_url = self.image_url_path.rstrip('/') + '/' + kyoshin_filename

				msg1=''
				for line in msg.splitlines():
					msg1 = msg1 + '\n'.join(fw_wrap(line,45,replace_whitespace=False))+'\n'
				line = msg1.count('\n')
				width, height = map_img.size
				map_img_new = Image.new(map_img.mode, (width, height+8+18*line), (254,253,253))
				map_img_new.paste(map_img,(0,0))
				map_img.close()

				font = ImageFont.truetype('KosugiMaru-Regular.ttf', 14)
				draw = ImageDraw.Draw(map_img_new)
				draw.text((4,height+8),msg1,'black',font=font)

				map_img_new.save(dst_file_full_path)
				map_img_new.close()
				break

			if kyoshin_url == '':
				kyoshin_url = 'https://smi.lmoniexp.bosai.go.jp/data/map_img/RealTimeImg/jma_s/'+kyoshin_time[0:8]+'/'+kyoshin_time+'.jma_s.gif'
			
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
						},
						{
							"type": "image",
							"originalContentUrl": kyoshin_url,
							"previewImageUrl": kyoshin_url
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
						},
						{
							"type": "image",
							"originalContentUrl": kyoshin_url,
							"previewImageUrl": kyoshin_url
						}
					]
				}
		else:
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

	def line_api_send_message(self, msg, token, user, access_kyoshin, enable_send_shindo_image, kyoshin_time):
		line_url = 'https://api.line.me/v2/bot/message/push'

		line_headers = {
            "Content_Type": "application/json",
            "Authorization": "Bearer " + token
        }
	
		if access_kyoshin:
			kyoshin_url = ''
			if enable_send_shindo_image:
				while True:
					try:
						map_url = 'http://www.kmoni.bosai.go.jp/data/map_img/CommonImg/base_map_w.gif'
						map_img = Image.open(io.BytesIO(requests.get(map_url).content)).convert("RGBA")
					except:
						break
					kyoshin_time_tmp = kyoshin_time
					find_image = False
					for count in range(3):
						try:
							jma_url = 'http://www.kmoni.bosai.go.jp/data/map_img/RealTimeImg/jma_s/'+kyoshin_time_tmp[0:8]+'/'+kyoshin_time_tmp+'.jma_s.gif'
							ima_img = Image.open(io.BytesIO(requests.get(jma_url).content)).convert("RGBA")
							map_img.paste(ima_img,(0,0), ima_img)
							ima_img.close()
							find_image = True
							break
						except:
							pass
						kyoshin_time_tmp = (datetime.strptime(kyoshin_time_tmp, '%Y%m%d%H%M%S')-timedelta(seconds=1)).strftime('%Y%m%d%H%M%S')
					if not find_image:
						break

					find_image = False
					for count in range(3):
						try:
							eew_url = 'http://www.kmoni.bosai.go.jp/data/map_img/PSWaveImg/eew/'+kyoshin_time_tmp[0:8]+'/'+kyoshin_time_tmp+'.eew.gif'
							eew_img = Image.open(io.BytesIO(requests.get(eew_url).content)).convert("RGBA")
							map_img.paste(eew_img,(0,0), eew_img)
							eew_img.close()
							find_image = True
							break
						except:
							pass
						kyoshin_time_tmp = (datetime.strptime(kyoshin_time_tmp, '%Y%m%d%H%M%S')-timedelta(seconds=1)).strftime('%Y%m%d%H%M%S')
					if not find_image:
						break

					try:
						level_url = 'http://www.kmoni.bosai.go.jp/data/map_img/ScaleImg/nied_jma_s_w_scale.gif'
						level_img = Image.open(io.BytesIO(requests.get(level_url).content)).convert("RGBA")
						map_img.paste(level_img,(map_img.width-level_img.width+10,map_img.height-level_img.height-3), level_img)
						level_img.close()
					except:
						map_img.close()
						break

					kyoshin_filename = hashlib.sha256((kyoshin_time+'.jma_s').encode()).hexdigest() + '.png'
					dst_file_full_path = self.image_dir_path.rstrip('/') + '/' + kyoshin_filename
					kyoshin_url = self.image_url_path.rstrip('/') + '/' + kyoshin_filename

					msg1=''
					for line in msg.splitlines():
						msg1 = msg1 + '\n'.join(fw_wrap(line,45,replace_whitespace=False))+'\n'
					line = msg1.count('\n')
					width, height = map_img.size
					map_img_new = Image.new(map_img.mode, (width, height+8+18*line), (254,253,253))
					map_img_new.paste(map_img,(0,0))
					map_img.close()

					font = ImageFont.truetype('KosugiMaru-Regular.ttf', 14)
					draw = ImageDraw.Draw(map_img_new)
					draw.text((4,height+8),msg1,'black',font=font)

					map_img_new.save(dst_file_full_path)
					map_img_new.close()
					break

			if kyoshin_url == '':
				kyoshin_url = 'https://smi.lmoniexp.bosai.go.jp/data/map_img/RealTimeImg/jma_s/'+kyoshin_time[0:8]+'/'+kyoshin_time+'.jma_s.gif'

			data = {
				"to": user,
				"messages":[
					{
						"type": "text",
						"text": msg
					},
					{
						"type": "image",
						"originalContentUrl": kyoshin_url,
						"previewImageUrl": kyoshin_url
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
		url1 = 'http://www.kmoni.bosai.go.jp/webservice/hypo/eew/'
		url2 = 'https://weather-kyoshin.west.edge.storage-yahoo.jp/RealTimeData/'
		now = datetime.now()
		kyoshin_time0 = (now).strftime('%Y%m%d%H%M%S')
		kyoshin_time1 = (now-timedelta(seconds=1)).strftime('%Y%m%d%H%M%S')
		kyoshin_time2 = (now-timedelta(seconds=2)).strftime('%Y%m%d%H%M%S')
		header= {"content-type": "application/json"}
		intensity = 0.0
		find_kyoshin = True
		access_kyoshin = False
		kyoshin_time = ''
		data_source = ''

		try:
			try:
				kyoshin_time = kyoshin_time2
				res = requests.get(url1+kyoshin_time2+'.json',headers=header,timeout=1).json()
				data_source = 'NIED' # 防災科研
			except:
				printE('%s' % (traceback.format_exc()), self.sender)
				# --- Yahoo!のURL階層（日付フォルダ）に合わせて取得 ---
				res = requests.get(url2+kyoshin_time2[0:8]+'/'+kyoshin_time2+'.json',headers=header,timeout=1).json()
				data_source = 'Yahoo!' # Yahoo!

			if res['result']['message'] != "":
				try:
					kyoshin_time = kyoshin_time1
					res = requests.get(url1+kyoshin_time1+'.json',headers=header,timeout=1).json()
					data_source = 'NIED'
				except:
					printE('%s' % (traceback.format_exc()), self.sender)
					res = requests.get(url2+kyoshin_time1[0:8]+'/'+kyoshin_time1+'.json',headers=header,timeout=1).json()
					data_source = 'Yahoo!'

			if res['result']['message'] != "":
				try:
					kyoshin_time = kyoshin_time0
					res = requests.get(url1+kyoshin_time0+'.json',headers=header,timeout=1).json()
					data_source = 'NIED'
				except:
					printE('%s' % (traceback.format_exc()), self.sender)
					res = requests.get(url2+kyoshin_time0[0:8]+'/'+kyoshin_time0+'.json',headers=header,timeout=1).json()
					data_source = 'Yahoo!'

			access_kyoshin = True

			if 'hypoInfo' in res and res['hypoInfo'] is not None:
				yahoo_eew = res['hypoInfo']
				res = {
					"result": {"status": "success", "message": ""},
					"region_name": yahoo_eew.get('regionName', ''),
					"magunitude": yahoo_eew.get('magnitude', '0.0'),
					"depth": yahoo_eew.get('depth', '0km'),
					"calcintensity": yahoo_eew.get('calcIntensity', '0'),
					"report_num": yahoo_eew.get('reportNum', '1'),
					"is_final": yahoo_eew.get('isFinal', False),
					"latitude": yahoo_eew.get('latitude', '0.0'),
					"longitude": yahoo_eew.get('longitude', '0.0')
				}
				if 'items' in yahoo_eew and len(yahoo_eew['items']) > 0:
					res['alertflg'] = '警報' if yahoo_eew['items'][0].get('isAlert', False) else '予報'

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

			if data_source != '':
				msg = msg + ' (' + data_source + ')'

			if res['result']['message'] != "":
				msg = '地震発生の確認ができませんでした。\n(' + kyoshin_time + ')'
				find_kyoshin = False

		except:
			printE('%s' % (traceback.format_exc()), self.sender)
			msg='地震情報にアクセス出来ませんでした。'
			find_kyoshin = False
		
		return msg, intensity, find_kyoshin, access_kyoshin, kyoshin_time

	def _when_alarm(self, d):
		'''
		Send a LINE API in an alert scenario.

		:param bytes d: queue message
		'''
		event_time = helpers.fsec(helpers.get_msg_time(d))
		self.last_event_str = '%s' % ((event_time+(3600*9)).strftime(self.fmt)[:22])

		for count in range(2):
			kyoshin_msg, intensity, find_kyoshin, access_kyoshin, kyoshin_time = self.get_kyoshin_msg()
			if count==0:
				message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/\n%s' % (self.message1, self.last_event_str, kyoshin_msg)
				enable_send_shindo_image = False
			else:
				enable_send_shindo_image = True
				if find_kyoshin or not access_kyoshin:
					message = kyoshin_msg
				else:
					message = '地震は発生していないと思われます。'
			
			if self.token1 != '':
				try:
					printM('Sending alert...', sender=self.sender)
					self.line_api_send_message(message, self.token1, self.user1, access_kyoshin, enable_send_shindo_image, kyoshin_time)
					printM('Sent LINE API: %s' % (message), sender=self.sender)

				except Exception as e:
					printE('Could not send alert - %s' % (e), sender=self.sender)
					try:
						printE('Waiting 5 seconds and trying to send again...', sender=self.sender, spaces=True)
						time.sleep(5)
						self.line_api_send_message(message, self.token1, self.user1, access_kyoshin, enable_send_shindo_image, kyoshin_time)
						printM('Sent LINE API: %s' % (message), sender=self.sender)
					except Exception as e:
						printE('Could not send alert - %s' % (e), sender=self.sender)

			message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/\n%s' % (self.message1, self.last_event_str, kyoshin_msg)

			if intensity >= 3.5 and self.token2 != '':
				try:
					printM('Sending alert...', sender=self.sender)
					self.line_api_send_message(message, self.token2, self.user2, access_kyoshin, enable_send_shindo_image, kyoshin_time)
					printM('Sent LINE API: %s' % (message), sender=self.sender)

				except Exception as e:
					printE('Could not send alert - %s' % (e), sender=self.sender)
					try:
						printE('Waiting 5 seconds and trying to send again...', sender=self.sender, spaces=True)
						time.sleep(5)
						self.line_api_send_message(message, self.token2, self.user2, access_kyoshin, enable_send_shindo_image, kyoshin_time)
						printM('Sent LINE API: %s' % (message), sender=self.sender)
					except Exception as e:
						printE('Could not send alert - %s' % (e), sender=self.sender)
			
			if find_kyoshin:
				break
			
			if count==0:
				printE('Cannot find Kyoshin data and Waiting 3 seconds and trying to send again...', sender=self.sender, spaces=True)
				time.sleep(3)


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
				kyoshin_msg, intensity, find_kyoshin, access_kyoshin, kyoshin_time = self.get_kyoshin_msg()

				msg = d.decode('utf-8').split('|')
				already_sent = False
				# token2
				if self.token2 != '' and self.user2 != '':
					if not (('震度０' in msg[1]) or ('震度１' in msg[1]) or ('震度２' in msg[1])):
						message = '%s\n%s JST\nhttp://www.kmoni.bosai.go.jp/\n%s\n' % (self.message1, self.last_event_str, kyoshin_msg)
						try:
							printM('Uploading image to LINE API %s' % (imgpath), self.sender)
							self.line_api_send_image(imgpath, message+self.location_name+'の実際の震度：'+msg[1], self.token2, self.user2, access_kyoshin, kyoshin_time)
							printM('Sent image', sender=self.sender)
							already_sent = True
						except Exception as e:
							printE('Could not send image - %s' % (e), sender=self.sender)
							try:
								printM('Waiting 5 seconds and trying to send again...', sender=self.sender)
								time.sleep(5.1)
								printM('Uploading image to LINE API (2nd try) %s' % (imgpath), self.sender)
								self.line_api_send_image(imgpath, message+self.location_name+'の実際の震度：'+msg[1], self.token2, self.user2, access_kyoshin, kyoshin_time)
								printM('Sent image', sender=self.sender)
								already_sent = True

							except Exception as e:
								printE('Could not send image - %s' % (e), sender=self.sender)
								response = None
					else:
						printM('Do not send LINE API for token 2, becuase Shindo is less than 3.', sender=self.sender)

				if self.token1 != '' and self.user1 != '':
					if not (('震度０' in msg[1]) or ('震度１' in msg[1]) or ('震度２' in msg[1])) or "_10" in imgpath or intensity >= 2.5:
						try:
							printM('Uploading image to LINE API %s' % (imgpath), self.sender)
							self.line_api_send_image(imgpath, kyoshin_msg+'\n'+self.location_name+'の実際の震度：'+msg[1], self.token1, self.user1, access_kyoshin, kyoshin_time)
							printM('Sent image', sender=self.sender)
						except Exception as e:
							printE('Could not send image - %s' % (e), sender=self.sender)
							try:
								printM('Waiting 5 seconds and trying to send again...', sender=self.sender)
								time.sleep(5.1)
								printM('Uploading image to LINE API (2nd try) %s' % (imgpath), self.sender)
								self.line_api_send_image(imgpath, kyoshin_msg+'\n'+self.location_name+'の実際の震度：'+msg[1], self.token1, self.user1, access_kyoshin, kyoshin_time)
								printM('Sent image', sender=self.sender)

							except Exception as e:
								printE('Could not send image - %s' % (e), sender=self.sender)
								response = None
					else:
						printM('Do not send LINE API for token 1, 2nd time, becuase Shindo is less than 3.', sender=self.sender)
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
