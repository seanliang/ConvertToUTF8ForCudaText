from cudatext import *
from .chardet.universaldetector import UniversalDetector
import codecs
import cudatext_cmd
import os
import shutil
import time
import hashlib

SKIP_ENCODINGS = ('ASCII', 'UTF-8', 'UTF-16LE', 'UTF-16BE')
SUPERSETS = {
	'GB2312': 'GBK',
	'GBK': 'GB18030',
	'BIG5': 'CP950', # CP950 is common in Taiwan
	'CP950': 'BIG5-HKSCS', # HK official Big5 variant
	'EUC-KR': 'CP949' # CP949 is a superset of euc-kr!
}
CODE_PAGES = {
	'GB2312': 'cp936',
	'GBK': 'cp936',
	'BIG5': 'cp950',
	'EUC-KR': 'cp949'
}

TMP_DIR = os.path.join(app_path(APP_DIR_DATA), 'c2u_tmp')
if not os.path.exists(TMP_DIR):
	os.mkdir(TMP_DIR)

def get_temp_name(name):
	if not name:
		return None
	name = name.encode('UTF-8')
	return hashlib.md5(name).hexdigest()

def detect(view, file_name, cnt):
	if not file_name or not os.path.exists(file_name) or os.path.getsize(file_name) == 0:
		return
	msg_status('Detecting encoding, please wait...')
	detector = UniversalDetector()
	fp = open(file_name, 'rb')
	for line in fp:
		# cut MS-Windows CR code
		line = line.replace(b'\r',b'')
		detector.feed(line)
		cnt -= 1
		if detector.done or cnt == 0:
			break
	fp.close()
	detector.close()
	encoding = detector.result['encoding']
	if encoding:
		encoding = encoding.upper()
	confidence = detector.result['confidence']
	check_encoding(view, encoding, confidence)

def check_encoding(view, encoding, confidence):
	view_encoding = view.get_prop(PROP_ENC)
	result = 'Detected {0} vs {1} with {2:.0%} confidence'.format(encoding, view_encoding, confidence) if encoding else 'Encoding can not be detected'
	msg_status(result)
	print(result)
	not_detected = not encoding or confidence < 0.95 or encoding == view_encoding
	# CudaText can't detect the encoding
	if view_encoding in ('ANSI', '?'):
		if not_detected:
			return
	else:
		return
	init_encoding_vars(view, encoding)

def get_menu(encoding):
	cp = CODE_PAGES.get(encoding, encoding.lower())
	menu = 'cmd_Encoding_' + cp + '_Reload'
	return getattr(cudatext_cmd, menu, None)

def init_encoding_vars(view, encoding, run_convert=True, stamp=None, detect_on_fail=False):
	if not encoding:
		return
	if encoding in SKIP_ENCODINGS:
		return
	menu = get_menu(encoding)
	if menu:
		# use reload menu item
		view.cmd(menu)
		return
	if run_convert:
		if stamp == None:
			stamp = '{0}'.format(time.time())
		convert_to_utf8(view, encoding, stamp, detect_on_fail)

def convert_to_utf8(view, encoding=None, stamp=None, detect_on_fail=False):
		if not encoding:
			return
		file_name = view.get_filename()
		if not (file_name and os.path.exists(file_name)):
			return
		# try fast decode
		fp = None
		try:
			fp = codecs.open(file_name, 'rb', encoding, errors='strict')
			contents = fp.read()
		except LookupError as e:
			try:
				# reload codecs
				import _multibytecodec, imp, encodings
				imp.reload(encodings)
				imp.reload(codecs)
				codecs.getencoder(encoding)
				msg_status("Please reopen this file")
			except (ImportError, LookupError) as e:
				need_codecs = (type(e) == ImportError)
				msg_box("Codecs for {0} is not supproted".format(encoding), MB_OK)
			return
		except UnicodeDecodeError as e:
			if detect_on_fail:
				detect(view, file_name, 100)
				return
			superset = SUPERSETS.get(encoding)
			if superset:
				print('Try encoding {0} instead of {1}.'.format(superset, encoding))
				init_encoding_vars(view, superset, True, stamp)
				return
			fp.close()
			fp = codecs.open(file_name, 'rb', encoding, errors='ignore')
			contents = fp.read()
		finally:
			if fp:
				fp.close()
		contents = contents.replace('\r\n', '\n').replace('\r', '\n')
		view.set_text_all(contents)
		view.set_prop(PROP_ENC, encoding)
		msg_status('{0} -> UTF8'.format(encoding))

def convert_from_utf8(file_name, encoding):
	if encoding in SKIP_ENCODINGS or get_menu(encoding):
		return
	msg = "Converting {0} back to {1}".format(file_name, encoding)
	msg_status(msg)
	print(msg)
	try:
		fp = open(file_name, 'rb')
		contents = codecs.EncodedFile(fp, encoding, 'UTF-8').read()
	except (LookupError, UnicodeEncodeError) as e:
		msg_box('Can not convert file encoding of {0} to {1}, it was saved as UTF-8 instead:\n\n{2}'.format
			(os.path.basename(file_name), encoding, e), MB_OK)
		return
	finally:
		if fp:
			fp.close()
	# write content to temporary file
	tmp_name = os.path.join(TMP_DIR, get_temp_name(file_name))
	fp = open(tmp_name, 'wb')
	fp.write(contents)
	fp.close()
	# os.rename has "Invalid cross-device link" issue
	os.chmod(tmp_name, os.stat(file_name)[0])
	shutil.move(tmp_name, file_name)
	msg_status('UTF8 -> {0}'.format(encoding))

class Command:
	def on_open(self, ed_self):
		detect(ed_self, ed_self.get_filename(), 100)
	def on_save(self, ed_self):
		convert_from_utf8(ed_self.get_filename(), ed_self.get_prop(PROP_ENC))
