# Written by aiortc team and rewriting by Aviv to this project
# mainpage on aioquic: https://github.com/aiortc/aioquic

import argparse

import asyncio

import logging

import os

import pickle

import ssl

import time

from collections import deque

from typing import BinaryIO, Callable, Deque, Dict, List, Optional, Union, cast

from urllib.parse import urlparse

import threading

import wsproto

import wsproto.events

import queue

from quic_logger import QuicDirectoryLogger



import aioquic

from aioquic.asyncio.client import connect

from aioquic.asyncio.protocol import QuicConnectionProtocol

from aioquic.h0.connection import H0_ALPN, H0Connection

from aioquic.h3.connection import H3_ALPN, H3Connection

from aioquic.h3.events import (

    DataReceived,

    H3Event,

    HeadersReceived,

    PushPromiseReceived,

)

from aioquic.quic.configuration import QuicConfiguration

from aioquic.quic.events import QuicEvent

from aioquic.tls import CipherSuite, SessionTicket



try:

    import uvloop

except ImportError:

    uvloop = None



logger = logging.getLogger("client")



HttpConnection = Union[H0Connection, H3Connection]



USER_AGENT = "aioquic/" + aioquic.__version__





class URL:

    def __init__(self, url: str) -> None:

        parsed = urlparse(url)



        self.authority = parsed.netloc

        self.full_path = parsed.path

        if parsed.query:

            self.full_path += "?" + parsed.query

        self.scheme = parsed.scheme





class HttpRequest:

    def __init__(

        self, method: str, url: URL, content: bytes = b"", headers: Dict = {}

    ) -> None:

        self.content = content

        self.headers = headers

        self.method = method

        self.url = url





class WebSocket:

    def __init__(

        self, http: HttpConnection, stream_id: int, transmit: Callable[[], None]

    ) -> None:

        self.http = http

        self.queue: asyncio.Queue[str] = asyncio.Queue()

        self.stream_id = stream_id

        self.subprotocol: Optional[str] = None

        self.transmit = transmit

        self.websocket = wsproto.Connection(wsproto.ConnectionType.CLIENT)



    async def close(self, code=1000, reason="") -> None:

        """

        Perform the closing handshake.

        """

        data = self.websocket.send(

            wsproto.events.CloseConnection(code=code, reason=reason)

        )

        self.http.send_data(stream_id=self.stream_id, data=data, end_stream=True)

        self.transmit()



    async def recv(self) -> str:

        """

        Receive the next message.

        """

        return await self.queue.get()



    async def send(self, message: str) -> None:

        """

        Send a message.

        """

        assert isinstance(message, str)



        data = self.websocket.send(wsproto.events.TextMessage(data=message))

        self.http.send_data(stream_id=self.stream_id, data=data, end_stream=False)

        self.transmit()



    def http_event_received(self, event: H3Event) -> None:

        if isinstance(event, HeadersReceived):

            for header, value in event.headers:

                if header == b"sec-websocket-protocol":

                    self.subprotocol = value.decode()

        elif isinstance(event, DataReceived):

            self.websocket.receive_data(event.data)



        for ws_event in self.websocket.events():

            self.websocket_event_received(ws_event)



    def websocket_event_received(self, event: wsproto.events.Event) -> None:

        if isinstance(event, wsproto.events.TextMessage):

            self.queue.put_nowait(event.data)





class HttpClient(QuicConnectionProtocol):

    def __init__(self, *args, **kwargs) -> None:

        super().__init__(*args, **kwargs)



        self.pushes: Dict[int, Deque[H3Event]] = {}

        self._http: Optional[HttpConnection] = None

        self._request_events: Dict[int, Deque[H3Event]] = {}

        self._request_waiter: Dict[int, asyncio.Future[Deque[H3Event]]] = {}

        self._websockets: Dict[int, WebSocket] = {}



        if self._quic.configuration.alpn_protocols[0].startswith("hq-"):

            self._http = H0Connection(self._quic)

        else:

            self._http = H3Connection(self._quic)



    async def get(self, url: str, headers: Dict = {}) -> Deque[H3Event]:

        """

        Perform a GET request.

        """

        return await self._request(

            HttpRequest(method="GET", url=URL(url), headers=headers)

        )

    async def head(self, url: str, headers: Dict = {}) -> Deque[H3Event]:

        """

        Perform a head request.

        """

        return await self._request(

            HttpRequest(method="HEAD", url=URL(url), headers=headers)

        )



    async def post(self, url: str, data: bytes, headers: Dict = {}) -> Deque[H3Event]:

        """

        Perform a POST request.

        """

        return await self._request(

            HttpRequest(method="POST", url=URL(url), content=data, headers=headers)

        )



    async def websocket(self, url: str, subprotocols: List[str] = []) -> WebSocket:

        """

        Open a WebSocket.

        """

        request = HttpRequest(method="CONNECT", url=URL(url))

        stream_id = self._quic.get_next_available_stream_id()

        websocket = WebSocket(

            http=self._http, stream_id=stream_id, transmit=self.transmit

        )



        self._websockets[stream_id] = websocket



        headers = [

            (b":method", b"CONNECT"),

            (b":scheme", b"https"),

            (b":authority", request.url.authority.encode()),

            (b":path", request.url.full_path.encode()),

            (b":protocol", b"websocket"),

            (b"user-agent", USER_AGENT.encode()),

            (b"sec-websocket-version", b"13"),

        ]

        if subprotocols:

            headers.append(

                (b"sec-websocket-protocol", ", ".join(subprotocols).encode())

            )

        self._http.send_headers(stream_id=stream_id, headers=headers)



        self.transmit()



        return websocket



    def http_event_received(self, event: H3Event) -> None:

        if isinstance(event, (HeadersReceived, DataReceived)):

            stream_id = event.stream_id

            if stream_id in self._request_events:

                # http

                self._request_events[event.stream_id].append(event)

                if event.stream_ended:

                    request_waiter = self._request_waiter.pop(stream_id)

                    request_waiter.set_result(self._request_events.pop(stream_id))



            elif stream_id in self._websockets:

                # websocket

                websocket = self._websockets[stream_id]

                websocket.http_event_received(event)



            elif event.push_id in self.pushes:

                # push

                self.pushes[event.push_id].append(event)



        elif isinstance(event, PushPromiseReceived):

            self.pushes[event.push_id] = deque()

            self.pushes[event.push_id].append(event)



    def quic_event_received(self, event: QuicEvent) -> None:

        #  pass event to the HTTP layer

        if self._http is not None:

            for http_event in self._http.handle_event(event):

                self.http_event_received(http_event)



    async def _request(self, request: HttpRequest) -> Deque[H3Event]:

        stream_id = self._quic.get_next_available_stream_id()

        self._http.send_headers(

            stream_id=stream_id,

            headers=[

                (b":method", request.method.encode()),

                (b":scheme", request.url.scheme.encode()),

                (b":authority", request.url.authority.encode()),

                (b":path", request.url.full_path.encode()),

                (b"user-agent", USER_AGENT.encode()),

            ]

            + [(k.encode(), v.encode()) for (k, v) in request.headers.items()],

        )

        self._http.send_data(stream_id=stream_id, data=request.content, end_stream=True)



        waiter = self._loop.create_future()

        self._request_events[stream_id] = deque()

        self._request_waiter[stream_id] = waiter

        self.transmit()



        return await asyncio.shield(waiter)





async def perform_http_request(

    response,

    client: HttpClient,

    url: str,

    data: bytes,
    
    headre: dict,

    include: bool,

    output_dir: Optional[str],
    
    path: str,

    method: str,

) -> None:     
    # perform request
    start = time.time()

    if data is not None:

        http_events = await client.post(

            path,

            data=data,

            headers=headre,

        )

        method = "POST"

    else:
        if method == "HEAD":
            http_events = await client.head(path,headers=headre)
        else:
            http_events = await client.get(path,headers=headre)
            method = "GET"

    elapsed = time.time() - start  



    # callback response
    dataR = []
    for http_event in http_events:
        if isinstance(http_event, HeadersReceived):    
            responseHeaders = http_event.headers
        elif isinstance(http_event, DataReceived):
            dataR.append(http_event.data)
       
       
    if len(dataR) == 0:
        response.response(None,responseHeaders)
    else:
        dataR = b''.join(dataR)
        response.response(dataR,responseHeaders)
   





def process_http_pushes(

    client: HttpClient,

    include: bool,

    output_dir: Optional[str],

) -> None:

    for _, http_events in client.pushes.items():

        method = ""

        octets = 0

        path = ""

        for http_event in http_events:

            if isinstance(http_event, DataReceived):

                octets += len(http_event.data)

            elif isinstance(http_event, PushPromiseReceived):

                for header, value in http_event.headers:

                    if header == b":method":

                        method = value.decode()

                    elif header == b":path":

                        path = value.decode()

        logger.info("Push received for %s %s : %s bytes", method, path, octets)



        # output response

        if output_dir is not None:

            output_path = os.path.join(

                output_dir, os.path.basename(path) or "index.html"

            )

            with open(output_path, "wb") as output_file:

                write_response(

                    http_events=http_events, include=include, output_file=output_file

                )





def write_response(

    http_events: Deque[H3Event], output_file: BinaryIO, include: bool

) -> None:

    for http_event in http_events:

        if isinstance(http_event, HeadersReceived) and include:

            headers = b""

            for k, v in http_event.headers:

                headers += k + b": " + v + b"\r\n"

            if headers:

                output_file.write(headers + b"\r\n")

        elif isinstance(http_event, DataReceived):

            output_file.write(http_event.data)





def save_session_ticket(ticket: SessionTicket) -> None:

    """

    Callback which is invoked by the TLS engine when a new session ticket

    is received.

    """

    logger.info("New session ticket received")





async def run(

    configuration: QuicConfiguration,

    host: int,
    
    port: str,

    include: bool,

    output_dir: Optional[str],

    local_port: int,

    zero_rtt: bool,

    queue_requests: queue.Queue,

) -> None:
    # Connect to a QUIC server at the given host and port.
    # https://aioquic.readthedocs.io/en/latest/asyncio.html#client
    # https://docs.python.org/3/reference/compound_stmts.html#async-with
    async with connect(

        host,

        port,

        configuration=configuration,

        create_protocol=HttpClient,

        session_ticket_handler=save_session_ticket,

        local_port=local_port,

        wait_connected=not zero_rtt,

    ) as client:
        # https://docs.python.org/3/library/typing.html#typing.cast
        # This returns the value unchanged. To the type checker this signals that the return value has the designated type, but at runtime we intentionally don’t check anything (we want this to be as fast as possible).
        client = cast(HttpClient, client)    
        
        isStilConnect = True

        while isStilConnect:

            isStilConnect ,data ,headre ,response,path,method = await queue_get_without_blocking_io(queue_requests)

            if isStilConnect:
                asyncio.create_task(perform_http_request(
                    response=response,
                    client=client,
                    url=host,
                    data=data,
                    headre=headre,
                    include=include,
                    output_dir=output_dir,
                    path=path,
                    method=method,
                ))
                    
    configuration.secrets_log_file.close()


 # Written by Aviv     
hostStr = "localhost"
hostPort = 4433
time_sleep = 0.015

#wait until have conncetion from proxy_client.py and open conncetion to proxy
async def h3(queue_connection: queue.Queue):
    while True:
        queue_requests = await queue_get_without_blocking_io(queue_connection)   
       
        asyncio.create_task(addConnection(queue_requests))

#get item from queue not asyncio.queue without blocking the io.
async def queue_get_without_blocking_io(queue: queue.Queue):
    while True:
        if not queue.empty():
            return queue.get()
        else:
            await asyncio.sleep(time_sleep)




async def addConnection(queue_requests: queue.Queue):   
    # my Quic Configuration
    quic_logger = QuicDirectoryLogger("quicLoggerPClient")
    defaults = QuicConfiguration(
        is_client=True,
        alpn_protocols=H3_ALPN)#,quic_logger=quic_logger
    defaults.load_verify_locations("pycacert.pem")
    defaults.secrets_log_file = open("sslkeylogPClient.log", "a")

    
    # call to async def run...
   
      
    await run(
        configuration=defaults,
        host=hostStr,
        port=hostPort,
        include=True,
        output_dir=None,
        local_port=0,
        zero_rtt=False,
        queue_requests=queue_requests
    )

    
#hare take care of the queues
def H1_connect(queue_connection : queue.Queue):    
    queue_requests = queue.Queue()
    queue_connection.put(queue_requests)
    return queue_requests

def H1_close(queue_requests: queue.Queue):    
    queue_requests.put((False,None,None,None,None,None))


def H1_request(data: bytes,headre: dict,response,path: str,queue_requests: queue.Queue,method: str):
    queue_requests.put((True,data,headre,response,path,method))




   
    

    
