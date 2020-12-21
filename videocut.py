#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2020/12/14 16:52
# @Author  : shadow
# @Site    : 
# @File    : videocut.py
# @Descript: PyCharm

import cv2
import os
import sys
import time
from threading import Thread
from queue import Queue
import numpy as np
from configparser import ConfigParser


class MyConfigParser(ConfigParser):
    def __init__(self, defaults=None):
        ConfigParser.__init__(self, defaults=defaults)

    def optionxform(self, optionstr):
        return optionstr


class BufferQueue(Queue):
    """Slight modification of the standard Queue that discards the oldest item
    when adding an item and the queue is full.
    """
    def put(self, item, *args, **kwargs):
        # The base implementation, for reference:
        # https://github.com/python/cpython/blob/2.7/Lib/Queue.py#L107
        # https://github.com/python/cpython/blob/3.8/Lib/queue.py#L121
        with self.mutex:
            if 0 < self.maxsize == self._qsize():
                self._get()
            self._put(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()


class DisplayThread(Thread):
    """
    Thread that displays the current images
    It is its own thread so that all display can be done
    in one thread to overcome imshow limitations and
    """
    def __init__(self, queue, cut):
        Thread.__init__(self)
        self.queue = queue
        self.image = None
        self.cut = cut

    def run(self):
        cv2.namedWindow("display", cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("display", self.cut.on_mouse)
        cv2.createTrackbar("Progress", "display", 0, 100, lambda x: self.cut.pos_set(x))
        cv2.createTrackbar("Play fast", "display", 8, 10, lambda x: self.cut.fast_set(x))
        while True:
            if self.queue.qsize() > 0:
                self.image = self.queue.get()
                cv2.imshow("display", self.image)
            else:
                # print("DisplayThread run ...")
                time.sleep(0.05)
            cv2.waitKey(1)
            # k = cv2.waitKey(1) & 0xFF
            # if k in [27, ord('q')]:
            #     break


class VideoCut:
    def __init__(self):
        self.Video = False  # 播放开关
        self.Cut = False    # 剪切开关
        self.Move = False   # 是否运行调整播放位置
        self.SAVE = False   # 保存图片
        self.RUN = False    # 是否运行，退出视频
        self.wait = 0.001
        self.queue_display = BufferQueue(maxsize=1)
        self.display_thread = DisplayThread(self.queue_display, self)
        self.display_thread.setDaemon(True)
        self.display_thread.start()

    def pos_set(self, pos):
        if not self.Video and not self.Move:  # 暂停时拖动进度条获取一帧图像
            self.cut_pos = round(self.total_frame*pos/100)
            self.caputre.set(cv2.CAP_PROP_POS_FRAMES, self.cut_pos)
            log.write(f'[Set] video progress to {pos}%({round(self.total_frame*pos/100)})', Level.INFO)
            self.Move = True

    def fast_set(self, pos):
        self.wait = 1/self.fps/10*(10-pos)
        log.write(f'[Set] video play speed level {pos}', Level.INFO)

    def pause(self):
        while True:
            if self.Video or self.Move:
                break
            time.sleep(0.1)

    def run(self):
        time.sleep(1)   # 等待显示线程加载
        while True:
            if self.SAVE:
                self.save_image()
                self.SAVE = False
            if cv2.getWindowProperty('display', cv2.WND_PROP_AUTOSIZE) < 0:
                print('VideoCut close ...')
                log.write('[CLOSE] VideoCut close ...', Level.INFO)
                self.RUN = False
                self.Move = True
                break
            time.sleep(0.01)

    def cut(self, video_info: dict):
        if not os.path.exists(video_info['in']):
            print("警告:", '没有该文件或该文件有错误')
            log.write(f'没有{video_info["in"]}或该文件有错误', Level.ERROR)
            return
        self.caputre = cv2.VideoCapture(video_info["in"])
        if not self.caputre.isOpened():
            print("警告:", '视频打开错误！')
            log.write(f'视频{video_info["in"]}打开错误', Level.ERROR)
            return

        start = video_info["start"]
        # 获取读入视频的参数
        self.fps = round(self.caputre.get(cv2.CAP_PROP_FPS))
        self.size = int(self.caputre.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.caputre.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frame = int(self.caputre.get(cv2.CAP_PROP_FRAME_COUNT))
        print(self.fps, self.size)
        log.write(f'Video:{video_info["in"]} fps:{self.fps}, size:{self.size}, total:{self.total_frame} start:{start}%',
                  Level.INFO)
        video_writer = cv2.VideoWriter(video_info["out"], cv2.VideoWriter_fourcc(*'mp4v'), self.fps, self.size)
        self.cut_pos = int(self.fps*start)
        self.pos_set(start)
        self.caputre.set(cv2.CAP_PROP_POS_FRAMES, self.cut_pos)
        Thread(target=self.run, daemon=True).start()
        self.RUN = True
        while True:
            ret, frame = self.caputre.read()
            if ret:
                self.cut_pos += 1
                self.paly(frame, round(self.cut_pos*100/self.total_frame))
                if not self.Video:
                    self.Move = False
                    log.write(f'[VIDEO] Pause at {self.cut_pos}({self.cut_pos/self.total_frame:.3f})', Level.INFO)
                    self.pause()

                if not self.RUN:
                    break

                if self.Cut:
                    video_writer.write(frame)
                time.sleep(self.wait)
            else:
                print("视频结束")
                log.write(f'[VIDEO] {video_info["in"]} play over!', Level.INFO)
                break

        cv2.destroyAllWindows()
        video_writer.release()

    def on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and self.size[0] < x:
            size = round(self.size[1]/7)
            if size <= y < 2*size:
                self.Video = not self.Video
                if self.Video:
                    log.write(f'[VIDEO] Start play at {self.cut_pos}({self.cut_pos/self.total_frame:.3f})', Level.INFO)
            elif 3*size <= y < 4*size:
                if self.Video:
                    self.Cut = not self.Cut
                    if self.Cut:
                        log.write(f'[CUT] Start at {self.cut_pos}({self.cut_pos/self.total_frame:.3f})', Level.INFO)
                    else:
                        log.write(f'[CUT] Stop at {self.cut_pos}({self.cut_pos/self.total_frame:.3f})', Level.INFO)
            elif 5*size <= y < 6*size:
                self.SAVE = True

    def paly(self, image, pos):
        height, width = image.shape[:2]
        display = np.zeros((height, width + round(min(height, width)/7), 3), dtype=np.uint8)
        display[0:height, 0:width, :] = image
        display[0:height, width:, :].fill(255)
        self.buttons(display)
        cv2.setTrackbarPos("Progress", "display", pos)
        self.queue_display.put(display)
        self.image = image

    def button(self, dst, label, enable):
        dst.fill(255)
        size = int(dst.shape[0]), int(dst.shape[1])
        if enable:
            color = (0, 200, 0)
        else:
            color = (0, 0, 200)
        cv2.circle(dst, (size[0]//2, size[1]//2), min(size)//2, color, -1)
        # cv2.rectangle(dst, (5, 0), size, color, -1)
        self.put_text(dst, label, size, (0, 255, 255))

    def buttons(self, display):
        x, y = self.size[0], round(self.size[1]/7)
        msg = "Drag the progress bar when video pause"
        cv2.putText(display, msg, (10, round(x/40)), cv2.FONT_HERSHEY_SIMPLEX, x/1000, (255, 0, 255), round(x/800))
        self.button(display[y:2*y, x:x+y], "Video "+("PAUSE" if self.Video else "START"), self.Video)
        self.button(display[3*y:4*y, x:x+y], "CUT "+("PAUSE" if self.Cut else "START"), self.Cut)
        self.button(display[5*y:6*y, x:x+y], "SAVE IMAGE", self.SAVE)

    def save_image(self):
        i = 0
        while os.access("image-%d.png" % i, os.R_OK):
            i += 1
        cv2.imwrite("image-%d.png" % i, self.image)
        print("Saved image: image-%d.png" % i)
        log.write(f"[IMAGE] Saved image: image-{i}.png", Level.INFO)

    @classmethod
    def put_text(cls, img, text, size, color=(0, 0, 0)):
        msgs = text.split()
        num = len(msgs)
        for n in range(num):
            for i in range(12, 2, -1):
                j = 2 if i > 4 else 1
                w, h = cv2.getTextSize(msgs[n], cv2.FONT_HERSHEY_SIMPLEX, i/10, j)[0]
                # print(i, j, w, h, size)
                if w+10 <= size[0] and h < size[1]/(num+2):
                    cv2.putText(img, msgs[n], ((size[0]-w)//2, (1+n)*2*h), cv2.FONT_HERSHEY_SIMPLEX, i/10, color, j)
                    # print(i, j, w, h, size, msgs[n])
                    break


class Level:
    DEBUG = 'DEBUG'
    ERROR = 'ERROR'
    INFO = 'INFO'
    WARN = 'WARN'


class Logcat:
    def __init__(self):
        self.name = 'logcat.txt'

    def write(self, msg, level=Level.INFO):
        msg = f'[{time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())}] [{level}] {msg} \n'
        with open(self.name, "a+", encoding='utf-8') as df:
            df.write(msg)

    def clear(self):
        with open(self.name, "w+", encoding='utf-8') as df:
            df.write(f'Clear at {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())} \n')


def param_get(file):
    conf = MyConfigParser()
    if conf.read(file, encoding="utf-8-sig"):  # 此处是utf-8-sig，而不是utf-8
        conf_dict = {s: {v: conf.get(s, v) for v in conf.options(s)} for s in conf.sections()}
    else:
        print("no config file")
        log.write("no config file", Level.ERROR)
        return
    # print(conf_dict)
    # logcat set
    if conf_dict.get('log'):
        if conf_dict['log'].get('name'):
            name = conf_dict['log'].get('name')
            if '{date}' in name:
                name = name.replace('{date}', time.strftime("%Y-%m-%d", time.localtime()))
            elif '{time}' in name:
                name = name.replace('{time}', time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime()))

            name = name.rsplit('.', 1)
            name = name[0].strip() + ('.log' if len(name) < 2 else '.'+name[1])
            log.name = name

        if conf_dict['log'].get('clear'):
            if os.path.exists(log.name):
                log.clear()

    if not conf_dict.get('video'):
        log.write("no config about [video]", Level.ERROR)
    if not conf_dict['video'].get('in'):
        log.write("no config about video of in", Level.ERROR)
    if not conf_dict['video'].get('out'):
        log.write("no config about video of out", Level.ERROR)

    start = float(conf_dict['video']['start']) if conf_dict['video'].get('start') else 0
    return {'in': conf_dict['video']['in'], 'out': conf_dict['video']['out'], 'start': start}


def main():
    # 获取ini配置文件
    video_info = param_get("config.ini")
    cut = VideoCut()
    cut.cut(video_info)
    sys.exit()  # 结束线程


if __name__ == '__main__':
    log = Logcat()
    main()
