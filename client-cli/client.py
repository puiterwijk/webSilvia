# Copyright (c) 2014, Patrick Uiterwijk <puiterwijk@gmail.com>
# All rights reserved.
#
# This file is part of webSilvia.
#
# webSilvia is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# webSilvia is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with webSilvia.  If not, see <http://www.gnu.org/licenses/>.

# Please configure the path to the silvia_proxy binary
PROXY_PATH = '/usr/bin/silvia_proxy'


# No changes need hereunder
from socketIO_client import SocketIO, BaseNamespace
from getpass import getpass
import sys

try:
    import subprocess32 as subprocess
except ImportError:
    import subprocess

import logging
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


class IrmaNamespace(BaseNamespace):
    def initialize(self):
        global connectionID
        self.connectionID = connectionID

    def on_connected(self, *args):
        irma_namespace.emit('login', {'supportedVersions': ['proxy-1'],
                                      'connID': self.connectionID})

    def on_loggedin(self, *args):
        self.proxy = subprocess.Popen(PROXY_PATH,
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
        self.proxy.poll()
        if self.proxy.returncode is not None:
            print 'proxy error!'
            print 'stdout: %s' % self.proxy.stdout.read()
            print 'stderr: %s' % self.proxy.stderr.read()
            sys.exit(1)

        status = self.proxy.stdout.readline().replace('\n', '')
        if status == '' or not status.startswith('control wait-for-card'):
            print 'Error! Not waiting for card?'
            print 'Status: %s' % status
            sys.exit(1)

        print 'Waiting for card connection...'

        status = self.proxy.stdout.readline().replace('\n', '')
        if status == 'control connected':
            print 'Card connected! Notifying server and starting protocol.'
            irma_namespace.emit('card_connected', {})
            socketIO.wait(seconds=1)
        else:
            print 'Error, unknown response: %s' % status
            sys.exit(1)

    def perform_request(self, request):
        self.proxy.stdin.write('request %s\n' % request)
        return self.proxy.stdout.readline().replace('\n', '')

    def on_card_request(self, *args):
        request = args[0]['data']
        response = self.perform_request(request).split(' ')
        if response[0] == 'response':
            irma_namespace.emit('card_response', {'data': response[1]})
            socketIO.wait(seconds=1)

    def on_card_authenticate(self, *args):
        # We need to get a PIN

        pindone = None
        while pindone is None:
            PIN = getpass("PIN code: ")
            APDU = '0020000008' + PIN.encode('hex')
            while len(APDU) < 26:
                APDU += '00'

            response = self.perform_request(APDU).split(' ')

            if response[1] == '9000':
                pindone = True
            elif response[1] == '63C0':
                pindone = False
                print 'Error: Card blocked'
            else:
                print 'Error: PIN incorrect (%u tries remaining). Try again!' % int(response[1][3])

        if not pindone:
            # abort
            raise Exception('PIN error')

        irma_namespace.emit('pin_ok', {})
        socketIO.wait(seconds=1)

    def on_finished(self, *args):
        irma_namespace.disconnect()


# Get Connection string
connURL = ''
while (connURL == ''
        or '#' not in connURL
        or not (connURL.startswith('http://') or
                connURL.startswith('https://'))):
    sys.stdout.write('Please enter the connection URL: ')
    connURL = sys.stdin.readline().replace('\n', '').strip()

split= connURL.split('#')
url = split[0]
connectionID = split[1]

with SocketIO(url) as socketIO:
    irma_namespace = socketIO.define(IrmaNamespace, '/irma')

    socketIO.wait(seconds=1)
