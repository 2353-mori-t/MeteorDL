# by Milan Kalina
# based on Tensorflow API 2 Object Detection code

import os
from os import path
import cv2
from google.colab.patches import cv2_imshow
from matplotlib import pyplot as plt
#import matplotlib
import time
import argparse
import numpy as	np
#import cupy as cp
from datetime import datetime
from threading import Thread, Semaphore, Lock
from detector import DetectorTF2
#import dvg_ringbuffer as rb
from PIL import Image
#import cumpy
#import subprocess as sp
import cupy as cp
import cupyx.scipy.ndimage
import configparser
import statistics as st


class VideoStreamWidget(object):
	def __init__(self, src=0):
			# Create a VideoCapture object
			self.capture = cv2.VideoCapture(src)
			# Start the thread to read frames from the video stream
			self.thread = Thread(target=self.update_rb_gpu, args=())
			self.thread.daemon = True
			self.thread.start()

	def buffer_fill(self):
		if self.capture.isOpened():
			print('Filling buffer...')
			while (self.status) and (len(self.t) < self.total):
				(self.status, self.frame) = self.capture.read()
				self.np_buffer[self.k] = self.frame
				self.t.append((self.k, time.time()))
				self.j += 1
				self.k += 1

	def update_rb_gpu(self):
			# Read the next frame from the stream in a different thread
			# and maintains buffer - list of consequtive frames
			self.total = fps * b_size		# buffer size
			self.k = 0									# global frame counter
			self.j = 0									# maxpixel counter
			self.t = []								  # frame/time tracking
			self.time0 = time.time()
			self.cp_buffer = None
			mutex = Lock()
			self.station = args.station
			(self.status, self.frame) = self.capture.read()
			self.frame_width = self.frame.shape[1]
			self.frame_height = self.frame.shape[0]
			#self.np_buffer = rb.RingBuffer(self.total, dtype=(np.uint8,(self.frame_height, self.frame_width, 3)), allow_overwrite=False)
			self.np_buffer = np.zeros((self.total, self.frame_height, self.frame_width, 3), dtype='uint8')
			self.buffer_fill()

			# push the buffer to GPU
			print('Moving the ring buffer to GPU...')
			self.cp_buffer = cp.array(self.np_buffer)
			# convert tracking buffer to numpy array
			self.t = np.asarray(self.t, dtype=('int,float'))
			while True:
				if self.capture.isOpened():
					(self.status, self.frame) = self.capture.read()
					if (self.status):
						cv2.rectangle(self.frame, (0, (self.frame_height-10)), (210, self.frame_height), (0,0,0), -1)
						cv2.putText(self.frame, self.station + ' ' + datetime.utcfromtimestamp(time.time()).strftime('%d/%m/%Y %H:%M:%S.%f')[:-4] + ' ' + str(self.k), (0,self.frame_height-3), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255,255,255), 1, cv2.LINE_AA)
								#cv2.putText(self.frame, datetime.utcfromtimestamp(self.t).strftime('%d/%m/%Y %H:%M:%S.%f')[:-4], (0,self.frame_height-3), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255,255,255), 1, cv2.LINE_AA)

						# an attempt to block the array saving until roll is completed
						mutex.acquire()
						# roll the buffer one possition left
						self.cp_buffer = cp.roll(self.cp_buffer,-1,axis=0)
						# append new frame to the right
						self.cp_buffer[self.total-1] = cp.array(self.frame)
						mutex.release()
						# roll the tracking buffer left
						self.t = np.roll(self.t, -1, axis=0)
						# append new frame to tracking buffer to the right
						self.t[self.total-1] = ((self.k, time.time()))
						self.k += 1
						self.j += 1
					else:
						print("\n" + 'Connection lost... trying to restore...' + datetime.utcfromtimestamp(time.time()).strftime('%H:%M:%S'))
						self.con_restore()
						print('Connection restored...' + datetime.utcfromtimestamp(time.time()).strftime('%H:%M:%S'))
				else:
					print('Capture closed...')


	def check_ping(self):
		hostname = config[station]['ip']
		response = os.system("ping -c 1 " + hostname)
		# and then check the response...
		if response == 0:
			pingstatus = True
		else:
			pingstatus = False
		return pingstatus


	def con_restore(self):
		self.capture.release()
		while not self.check_ping():
			time.sleep(10)
		self.capture = cv2.VideoCapture(source)


	def saveArray(self, ar):
		# saves array ar, t = tupple(k, time)
		# time = first frame time
		ar = cp.asnumpy(ar)
		a = 0
		while a < ar.shape[0]:
			#ar[a] = detector.DisplayDetections(ar[a], self.det_boxes)
			#cv2.rectangle(ar[a], (0, (self.frame_height-10)), (300, self.frame_height), (0,0,0), -1)
			#cv2.putText(ar[a], datetime.utcfromtimestamp(t[1]+a*0.04).strftime('%d/%m/%Y %H:%M:%S.%f')[:-4], (0,self.frame_height-3), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255,255,255), 1, cv2.LINE_AA)
			self.out.write(ar[a])
			a += 1


	def DetectFromStream(self, detector, save_output=False, output_dir='output/'):

		self.mp = fps			# maxpixel size in frames
		self.mp1 = sec_pre * fps			
		self.mp2 = self.mp1 + self.mp	# maxpixel position within the buffer
		time1 = 0
		time2 = 1
		t0 = t1 = t2 = t3 = t4 = 0
		self.last_frame = 0
		self.last_frame_recorded = 0
		mean = 0
		# limit for detection trigger
		perc30 = 0
		mean_limit = 140
		bg_max = 0.9
		thr = 0.9
		bg=[1,1,1,1,1,1,1,1,1]
		# number of sec to be added for capture

		mask = False
		self.station = args.station
        # apply the mask if there is any
		maskFile = 'mask-' + args.station + '.bmp'
		if path.exists(maskFile):
			print ('Loading mask...')
			maskImage = Image.open(maskFile).convert('L')
			maskImage = np.array(maskImage, dtype='uint8')
			random_mask = np.random.rand(720,1280,1) * 255
			mask = True
		else:
			print ('No mask file found')

		while True:
			# if new 1s chunk in the buffer is ready for detection
			if (self.j >= self.mp) and (self.cp_buffer.shape[0] >= self.total):
				# new maxpixel frame to be tested for detection
				self.j = 0
				#print ("detecting at fps={:2.1f}".format(self.mp/(time.time()-time1)) + ' | t=' + str(int(self.t[-1][0])) + ' | ' + str(self.frame_width) + 'x' + str(self.frame_height) + ' | buffer=' + str(self.cp_buffer.shape) + ' | maxpixel=' + str(self.mp) + ' | threshold=' + str(round(detector.Threshold * 10)/10) + ' | t1=' + "{:1.3f}".format(t1-t0) + ' | t2=' + "{:1.3f}".format(t2-t1) + ' | t3=' + "{:1.3f}".format(t3-t2)+ ' | t4=' + "{:1.3f}".format(t4-t3) + ' | perc30=' + "{:.0f}".format(perc30) + '  ', end='\r', flush=True)
				print ("detecting at fps={:2.1f}".format(self.mp/(time.time()-time1)) + ' | t=' + str(int(self.t[-1][0])) + ' | ' + str(self.frame_width) + 'x' + str(self.frame_height) + ' | buffer=' + str(self.cp_buffer.shape) + ' | maxpixel=' + str(self.mp) + ' | threshold=' + str(round((bg_max + margin) * 100)/100) + ' | t1=' + "{:1.3f}".format(t1-t0) + ' | t2=' + "{:1.3f}".format(t2-t1) + ' | t3=' + "{:1.3f}".format(t3-t2)+ ' | t4=' + "{:1.3f}".format(t4-t3) + ' | perc30=' + "{:.0f}".format(perc30) + '  ', end='\r', flush=True)

				time1 = t0 = time.time()
				# timestamp for file name, 1st frame of maxpixel image
				t_frame1 = self.t[self.mp1][1]
					
				# take 1s from middle of buffer to create maxpixel for detection
				buffer_small = self.cp_buffer[self.mp1:self.mp2,:,:,:]

				t1 = time.time()
				# calculate the maxpixel image
				img = cupyx.scipy.ndimage.maximum_filter1d (buffer_small, axis=0, size=buffer_small.shape[0])
				img = img[buffer_small.shape[0]-2]
				
				# move the array to CPU
				img = img.get()

				t2 = time.time()
				mean = np.copy(cv2.cvtColor(img,cv2.COLOR_BGR2GRAY))
				perc30 = np.percentile(mean, 30)
				#mean = np.mean(img[100:self.frame_height-100,100:self.frame_width-100])

				if mask:
					# apply trick from RMS
					img[maskImage < 3] = random_mask[maskImage < 3]
				t3 = time.time()
				self.det_boxes = detector.DetectFromImage(img)
				#self.det_boxes = self.det_boxes[:][5] > 0.1
				img_clean = img
				print('det_boxes', img.shape, self.det_boxes)
				if self.det_boxes[0][5] > 0.1:
					img = detector.DisplayDetections(img, self.det_boxes[:1])

				t4 = time.time()
				img_small = cv2.resize(img, (928, 522), interpolation = cv2.INTER_AREA)
				# cv2.imshow('Meteor detection',	img_small)
				cv2.imwrite('Meteordetection.jpg', img_small)
				# key = cv2.waitKeyEx(1) # TODO: Fix
				key = 27 
				# trigger the saving if signal above the mean noise and sky background below the daytime brightness 
				if (self.det_boxes and perc30 < mean_limit):
					#print (self.det_boxes)	
					if self.det_boxes[0][5] > (bg_max + margin):
						if save_output:
							# prepare file and folder for saving
							subfolder = 'output/' + args.station + '_' + time.strftime("%Y%m%d", time.gmtime())
							if not os.path.exists(subfolder):
								os.mkdir(subfolder)
							output_path = os.path.join(subfolder, station +  '_' + datetime.utcfromtimestamp(t_frame1).strftime("%Y%m%d_%H%M%S_%f") + '_' + "{:0.0f}".format(100*self.det_boxes[0][5]) + '.mp4')
							output_path_mp = os.path.join(subfolder, station +  '_mp_' + datetime.utcfromtimestamp(t_frame1).strftime("%Y%m%d_%H%M%S_%f") + '.jpg')
							output_path_mp_clean = os.path.join(subfolder, station +  '_mp-clean_' + datetime.utcfromtimestamp(t_frame1).strftime("%Y%m%d_%H%M%S_%f") + '.jpg')
							self.out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), 25, (img.shape[1], img.shape[0]))
							# save the maxpixel as jpg
							cv2.imwrite(output_path_mp, img)
							cv2.imwrite(output_path_mp_clean, img_clean)
							
							# copy the buffer to CPU
							buffer = self.cp_buffer.get()
							# note the last frame
							self.last_frame = self.t[-1][0]
							print ("\n" + 'Starting recording...', time.strftime("%H:%M:%S", time.gmtime()), output_path, self.det_boxes[0], 'frame: ' + str(self.last_frame - buffer.shape[0]) + '-' + str(self.last_frame))
							# save full buffer
							self.saveArray(buffer)
							self.last_frame_recorded = self.last_frame
						
						  # save another <post> seconds of frames
							for s in range(sec_post):
								# wait until 1s data available
								while self.t[-1][0] < (self.last_frame + 2*self.mp):
									...
								if self.t[-1][0] == (self.last_frame + 2*self.mp):
									self.last_frame = self.t[-1][0]
									# copy 1s to CPU
									buffer = self.cp_buffer[-2*self.mp:].get()
									self.saveArray(buffer)
									print ('Recording going on...', buffer.shape, 'frame: ' + str(self.last_frame_recorded) + '-' + str(self.last_frame))
									self.last_frame_recorded = self.last_frame
							print ('Stopping recording...')
							self.out.release()
				
				# update mean and max noise
				bg = bg[-9:]
				bg.append(self.det_boxes[0][5])
				bg_max = max(bg[:9])
				#detector.Threshold = st.mean(bg)
				
				
				# update the screen
				#img = cv2.resize(img, (928, 522), interpolation = cv2.INTER_AREA)
				#cv2.imshow('Meteor detection',	img)
				#key = cv2.waitKeyEx(1)
				if key == 27:
					#self.out.release()
					break
				elif key == 113:
					detector.Threshold += 0.1
				elif key == 97:
					detector.Threshold -= 0.1
				#img = np.zeros((self.frame.shape[0], self.frame.shape[1], self.frame.shape[2]), 'uint8')
				time2 = time.time()

		self.capture.release()


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Object Detection from Images or Video')
	parser.add_argument('--model_path', help='Path to frozen detection model', default='trt_fp16_dir/saved_model')
	parser.add_argument('--path_to_labelmap', help='Path to labelmap (.pbtxt) file', default='labelmap.pbtxt')
	parser.add_argument('--class_ids', help='id of classes to detect, expects string with ids delimited by ","', type=str, default=None) # example input "1,3" to detect person and car
	parser.add_argument('--threshold', help='Detection Threshold', type=float, default=0.7)
	parser.add_argument('--output_directory', help='Path to output images and video', default='output/')
	parser.add_argument('--save_output', help='Flag for save images and video with detections visualized', default=True, action='store_true')  # default is false
	parser.add_argument('--station', help='mask file name', default='default')
	parser.add_argument('source', help='mp4 file or url')
	args = parser.parse_args()

	# threshold margin
	margin = 0.3	
	station = args.station
	config = configparser.ConfigParser()
	config.read('config.ini')
	if station not in config:
		station = 'default'
	fps = int(config[station]['fps'])
	# source = 'rtsp://' + config[station]['ip'] + ':' + config[station]['rtsp']
	source = args.source
	print(source)
	sec_post = int(config['general']['post_seconds'])
	sec_pre = int(config['general']['pre_seconds'])
	b_size = int(config['general']['buffer_size'])

	id_list = None
	if args.class_ids is not None:
		id_list = [int(item) for item in args.class_ids.split(',')]

	if args.save_output:
		if not os.path.exists(args.output_directory):
			os.makedirs(args.output_directory)
	# instance of the class DetectorTF2
	detector = DetectorTF2(args.model_path, args.path_to_labelmap, class_id=id_list, threshold=args.threshold)
	video_stream_widget = VideoStreamWidget(source)
	while (video_stream_widget.cp_buffer is None):
		...
	video_stream_widget.DetectFromStream(detector, save_output=args.save_output, output_dir=args.output_directory)

	print("Done ...")
	# cv2.destroyAllWindows()
