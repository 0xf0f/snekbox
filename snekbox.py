import json
import multiprocessing
import subprocess
import threading
import time
import os
import sys

from logs import log
from rmq import Rmq


class Snekbox(object):
    def __init__(self,
                 nsjail_binary='nsjail',
                 python_binary=os.path.dirname(sys.executable)+os.sep+'python3.6'):

        self.nsjail_binary = nsjail_binary
        self.python_binary = python_binary
        self.nsjail_workaround()

    env = {
        'PATH': '/snekbox/.venv/bin:/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'LANG': 'en_US.UTF-8',
        'PYTHON_VERSION': '3.6.5',
        'PYTHON_PIP_VERSION': '10.0.1',
        'PYTHONDONTWRITEBYTECODE': '1',
    }

    def nsjail_workaround(self):
        dirs = ['/sys/fs/cgroup/pids/NSJAIL', '/sys/fs/cgroup/memory/NSJAIL']
        for d in dirs:
            if not os.path.exists(d):
                os.makedirs(d)

    def python3(self, cmd):
        args = [self.nsjail_binary, '-Mo',
                '--rlimit_as', '700',
                '--chroot', '/',
                '-E', 'LANG=en_US.UTF-8',
                '-R/usr', '-R/lib', '-R/lib64',
                '--user', 'nobody',
                '--group', 'nogroup',
                '--time_limit', '2',
                '--disable_proc',
                '--iface_no_lo',
                '--cgroup_pids_max=1',
                '--cgroup_mem_max=52428800'
                '--quiet', '--',
                self.python_binary, '-ISq', '-c', cmd]

        proc = subprocess.Popen(args,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=self.env,
                                universal_newlines=True)

        stdout, stderr = proc.communicate()
        if proc.returncode == 0:
            output = stdout
        elif proc.returncode == 1:
            try:
                output = stderr.split('\n')[-2]
            except IndexError:
                output = ''
        elif proc.returncode == 109:
            output = 'timed out or memory limit exceeded'
        else:
            log.debug(stderr)
            output = 'unknown error'

        return output

    def execute(self, body):
        msg = body.decode('utf-8')
        log.info(f'incoming: {msg}')
        result = ''
        snek_msg = json.loads(msg)
        snekid = snek_msg['snekid']
        snekcode = snek_msg['message'].strip()

        result = self.python3(snekcode)

        log.info(f'outgoing: {result}')

        rmq.publish(result,
                    queue=snekid,
                    routingkey=snekid,
                    exchange=snekid)
        exit(0)

    def message_handler(self, ch, method, properties, body, thread_ws=None):
        p = multiprocessing.Process(target=self.execute, args=(body,))
        p.daemon = True
        p.start()

        ch.basic_ack(delivery_tag=method.delivery_tag)


if __name__ == '__main__':
    try:
        rmq = Rmq()
        snkbx = Snekbox()
        rmq.consume(callback=snkbx.message_handler)
    except KeyboardInterrupt:
        print('Exited')
        exit(0)
