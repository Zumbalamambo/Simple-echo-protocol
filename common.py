import asyncio
import logging
import random
import struct


class Handler(asyncio.Protocol):
    """
    Defines common methods for echo clients and servers
    """
    def __init__(self):
        super().__init__()
        # The counter is used to identify each message. If an incoming request has a known ID, it is processed as a response
        self.counter = random.SystemRandom().randint(0, 2 ** 32 - 1)
        # The box stores all sent messages IDs
        self.box = set()
        # defines command length
        self.cmd_len = 10
        # defines header length
        self.header_len = self.cmd_len + 8 # 4 bytes of counter and 4 bytes of message size
        # defines header format
        self.header_format = '!2I{}s'.format(self.cmd_len)


    def push(self, message):
        """
        Sends a message to peer

        :param message: message to send
        """
        self.transport.write(message)


    def next_counter(self):
        """
        Increases the message ID counter
        """
        self.counter += 1
        return self.counter


    def msg_build(self, command, counter, data):
        """
        Builds a message with header + payload

        :param command: command to send
        :param counter: message id
        :param data: data to send
        :return: built message
        """
        cmd_len = len(command)
        if cmd_len > self.cmd_len:
            raise Exception("Length of command '{}' exceeds limit ({}/{})".format(command, cmd_len, self.cmd_len))

        # adds - to command until it reaches cmd length
        command = '{} {}'.format(command, '-'*(self.cmd_len - cmd_len - 1))

        return struct.pack(self.header_format, len(data), counter, command.encode()) + data.encode()


    def msg_parse(self, message):
        """
        Parses an incoming message

        :param message: received message
        :return: command, counter and payload
        """
        if message:
            msg_size, msg_counter, command = struct.unpack(self.header_format, message[:self.header_len])
            payload = message[self.header_len:self.header_len+msg_size]
            return command.decode().split(' ')[0], msg_size+self.header_len, msg_counter, payload.decode()
        else:
            return None


    def get_messages(self, buffer):
        parsed = self.msg_parse(buffer)

        while parsed:
            command, size, counter, payload = parsed
            buffer = buffer[size:]
            yield command, counter, payload
            parsed = self.msg_parse(buffer)


    def send_request(self, command, data):
        """
        Sends a request to peer

        :param command: command to send
        :param data: data to send
        :return: whether sending was successful or not
        """
        msg_counter = self.next_counter()
        self.box.add(msg_counter)
        self.push(self.msg_build(command, msg_counter, data))


    def data_received(self, message):
        """
        Handles received data from other peer.

        :param message: data received
        """
        for command, counter, payload in self.get_messages(message):

            if counter in self.box:
                self.process_response(command, payload)
            else:
                self.dispatch(command, counter, payload)


    def dispatch(self, command, counter, payload):
        """
        Processes a received message and sends a response

        :param command: command received
        :param counter: message id
        :param payload: data received
        """
        try:
            command, payload = self.process_request(command, payload)
        except Exception as e:
            logging.error("Error processing request: {}".format(e))
            command, payload = 'err', str(e)

        self.push(self.msg_build(command, counter, payload))


    def process_request(self, command, data):
        """
        Defines commands for both master and clients.

        :param command: Received command from other peer.
        :param data: Received data from other peer.
        :return: message to send.
        """
        if command == 'echo':
            return self.echo(data)
        else:
            return self.process_unknown_cmd(command)


    def process_response(self, command, payload):
        """
        Defines response commands for both master and client

        :param command: response command received
        :param payload: data received
        :return:
        """
        if command == 'ok':
            logging.info("Sucessful response: {}".format(payload))
        elif command == 'err':
            self.process_error_from_peer(payload)
        else:
            logging.error("Unkown response command received: '{}'".format(command))


    def echo(self, data):
        """
        Defines command "echo"

        :param data: message to echo
        :return: message to send
        """
        return 'ok ', data


    def process_unknown_cmd(self, command):
        """
        Defines message when an unknown command is received

        :param command: command received from peer
        :return: message to send
        """
        return 'err', "unknown command '{}'".format(command)


    def process_error_from_peer(self, data):
        """
        Handles errors in requests

        :param data: error message from peer
        :return: Nothing
        """
        logging.error("Peer reported an error: {}".format(data))
        return None
