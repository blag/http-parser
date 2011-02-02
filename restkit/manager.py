# -*- coding: utf-8 -
#
# This file is part of restkit released under the MIT license. 
# See the NOTICE for more information.

from __future__ import with_statement

from collections import Counter, deque
import signal
import threading
import time

from .sock import close

class Manager(object):

    def __init__(self, max_conn=10, timeout=300):
        self.max_conn = max_conn
        self.timeout = timeout

        self.sockets = dict()
        self.active_sockets = dict()
        self._lock = threading.Lock()
        self.connections_count = Counter()

        if timeout and timeout is not None:
            self.start()

    def murder_connections(self, signum, frame):
        self._lock.acquire()
        try:
            active_sockets = self.active_sockets.copy()
            for fno, (sock, t0) in active_sockets.items():
                diff = time.time() - t0
                if diff <= self.timeout:
                    continue
                close(sock)
                del self.active_sockets[fno]
        finally:
            self._lock.release()
       
    def start(self):
        signal.signal(signal.SIGALRM, self.murder_connections)
        signal.alarm(self.timeout)

    def all_connections_count(self, n=None):
        """ return all counts per address registered. if n is specified,
        it will return the n most commons """
        return self.connections_count.most_common(n)

    def connection_count(self, addr, ssl):
        """ get connections count for an address """
        return self.connections_count[(addr, ssl)]

    def find_socket(self, addr, ssl=False):
        """ find a socket from a its address in the pool and return if
        there is one available, else, return None """

        self._lock.acquire()
        try:
            key = (addr, ssl)
            try:
                socks = self.sockets[key]
                while True:
                    sock = socks.pop()
                    if sock.fileno() in self.active_sockets:
                        del self.active_sockets[sock.fileno()]
                        break
                self.sockets[key] = socks
                self.connections_count[key] -= 1 
                return sock
            except (IndexError, KeyError,):
                return None
        finally:
            self._lock.release()

    def store_socket(self, sock, addr, ssl=False):
        """ store a socket in the pool to reuse it across threads """
        self._lock.acquire()
        try:
            key = (addr, ssl)
            try:
                socks = self.sockets[key]
            except KeyError:
                socks = deque()

            if len(socks) < self.max_conn:
                # add connection to the pool
                socks.appendleft(sock)
                self.sockets[key] = socks
                self.connections_count[key] += 1
                self.active_sockets[sock.fileno()] = (sock, time.time())
            else:
                # close connection if we have enough connections in the
                # pool.
                close(sock)
        finally:
            self._lock.release()
                
