# Written by aiortc team and rewriting by Aviv to this project
# mainpage on aioquic: https://github.com/aiortc/aioquic

import argparse
import asyncio
import importlib
import logging
import time
from collections import deque
from email.utils import formatdate
from typing import Callable, Deque, Dict, List, Optional, Union, cast
import threading
import sys

import wsproto
import wsproto.events
from quic_logger import QuicDirectoryLogger

import aioquic
from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.h0.connection import H0_ALPN, H0Connection
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DataReceived, H3Event, HeadersReceived
from aioquic.h3.exceptions import NoAvailablePushIDError
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import DatagramFrameReceived, ProtocolNegotiated, QuicEvent
from aioquic.tls import SessionTicket
from pprint import pprint
from asgiref.sync import async_to_sync



connectionListener = None

try:
    import uvloop
except ImportError:
    uvloop = None

AsgiApplication = Callable
HttpConnection = Union[H0Connection, H3Connection]

SERVER_NAME = "aioquic/" + aioquic.__version__

i = 0

class HttpRequestHandler:
    #see myServe function
    requestListener = None
    
    def __init__(
        self,
        *,
        authority: bytes,
        connection: HttpConnection,
        protocol: QuicConnectionProtocol,
        scope: Dict,
        stream_ended: bool,
        stream_id: int,
        transmit: Callable[[], None],
    ) -> None:
        self.authority = authority
        self.connection = connection
        self.protocol = protocol
        self.queue: asyncio.Queue[Dict] = asyncio.Queue()
        self.queueData: list = []
        self.queueHeader: list = []
        self.scope = scope
        self.stream_id = stream_id
        self.transmit = transmit

        if stream_ended:
            self.queue.put_nowait({"type": "http.request"})

    

    def http_event_received(self, event: H3Event,id) -> None:               
        #print(str(type(event)) + " in http_event_received. stream_ended: " + str(event.stream_ended) )
       
        
        if isinstance(event, DataReceived): 
            #print("data is "+ str(event.data))        
            self.queueData.append(event.data)
            
        elif isinstance(event, HeadersReceived):
            #print("Header is "+ str(event.headers))
            self.queueHeader.append(event.headers)
                
        if(event.stream_ended):              

            #feature work not support segmentation theory but  segmentation work
            requestsHeader = self.queueHeader[0]
            requestsData = self.queueData[0]
                 
           
            self.http_event_response(requestsHeader,requestsData,id)  

            
            """t = threading.Thread(target=self.http_event_response, args=(requestsHeader,requestsData,id))
            t.start()
            t.join()""" #try to fix this https://github.com/aiortc/aioquic/issues/240


    def http_event_response(self,requestsHeader,requestsData,id):     
        print("stream_id: ",self.stream_id) 
        responseHeader , responseData = HttpRequestHandler.requestListener(requestsHeader,requestsData,id)                

        if responseHeader != None:                    
            self.connection.send_headers(stream_id=self.stream_id,headers=responseHeader)
            self.connection.send_data(stream_id=self.stream_id,data=responseData,end_stream=True) 
              

                

""" @async_to_sync
    async def http_event_response(self,requestsHeader,requestsData,id):        
        print("stream_id: ",self.stream_id)         

        responseHeader , responseData = await HttpRequestHandler.requestListener(requestsHeader,requestsData,id)   

        if responseHeader != None:                    
            self.connection.send_headers(stream_id=self.stream_id,headers=responseHeader)
            self.connection.send_data(stream_id=self.stream_id,data=responseData,end_stream=True)     """




class WebSocketHandler:
    def __init__(
        self,
        *,
        connection: HttpConnection,
        scope: Dict,
        stream_id: int,
        transmit: Callable[[], None],
    ) -> None:
        self.closed = False
        self.connection = connection
        self.http_event_queue: Deque[DataReceived] = deque()
        self.queue: asyncio.Queue[Dict] = asyncio.Queue()
        self.scope = scope
        self.stream_id = stream_id
        self.transmit = transmit
        self.websocket: Optional[wsproto.Connection] = None

    def http_event_received(self, event: H3Event) -> None:     
        if isinstance(event, DataReceived) and not self.closed:
            if self.websocket is not None:
                self.websocket.receive_data(event.data)

                for ws_event in self.websocket.events():
                    self.websocket_event_received(ws_event)
            else:
                # delay event processing until we get `websocket.accept`
                # from the ASGI application
                self.http_event_queue.append(event)

    def websocket_event_received(self, event: wsproto.events.Event) -> None:
        if isinstance(event, wsproto.events.TextMessage):
            self.queue.put_nowait({"type": "websocket.receive", "text": event.data})
        elif isinstance(event, wsproto.events.Message):
            self.queue.put_nowait({"type": "websocket.receive", "bytes": event.data})
        elif isinstance(event, wsproto.events.CloseConnection):
            self.queue.put_nowait({"type": "websocket.disconnect", "code": event.code})

    async def run_asgi(self, app: AsgiApplication) -> None:
        self.queue.put_nowait({"type": "websocket.connect"})

        try:
            await application(self.scope, self.receive, self.send)
        finally:
            if not self.closed:
                await self.send({"type": "websocket.close", "code": 1000})

    async def receive(self) -> Dict:
        return await self.queue.get()

    async def send(self, message: Dict) -> None:
        data = b""
        end_stream = False
        if message["type"] == "websocket.accept":
            subprotocol = message.get("subprotocol")

            self.websocket = wsproto.Connection(wsproto.ConnectionType.SERVER)

            headers = [
                (b":status", b"200"),
                (b"server", SERVER_NAME.encode()),
                (b"date", formatdate(time.time(), usegmt=True).encode()),
            ]
            if subprotocol is not None:
                headers.append((b"sec-websocket-protocol", subprotocol.encode()))
            self.connection.send_headers(stream_id=self.stream_id, headers=headers)

            # consume backlog
            while self.http_event_queue:
                self.http_event_received(self.http_event_queue.popleft())

        elif message["type"] == "websocket.close":
            if self.websocket is not None:
                data = self.websocket.send(
                    wsproto.events.CloseConnection(code=message["code"])
                )
            else:
                self.connection.send_headers(
                    stream_id=self.stream_id, headers=[(b":status", b"403")]
                )
            end_stream = True
        elif message["type"] == "websocket.send":
            if message.get("text") is not None:
                data = self.websocket.send(
                    wsproto.events.TextMessage(data=message["text"])
                )
            elif message.get("bytes") is not None:
                data = self.websocket.send(
                    wsproto.events.Message(data=message["bytes"])
                )

        if data:
            self.connection.send_data(
                stream_id=self.stream_id, data=data, end_stream=end_stream
            )
        if end_stream:
            self.closed = True
        self.transmit()


Handler = Union[HttpRequestHandler, WebSocketHandler]


class HttpServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._handlers: Dict[int, Handler] = {}
        self._http: Optional[HttpConnection] = None

    def connection_lost(self,exc):#not work
        print("close")
        super().connection_lost(exc)

    def connection_made(self,transport):#connection indication
        print("connect")
        #move to proxy_server.py this indication and some unique ID for this connect
        #use python object is it unique ID
        connectionListener(id(self))
        super().connection_made(transport)

    def http_event_received(self, event: H3Event) -> None:              
        if isinstance(event, HeadersReceived) and event.stream_id not in self._handlers:
            authority = None
            headers = []
            http_version = "0.9" if isinstance(self._http, H0Connection) else "3"
            raw_path = b""
            method = ""
            protocol = None
            for header, value in event.headers:
                if header == b":authority":
                    authority = value
                    headers.append((b"host", value))
                elif header == b":method":
                    method = value.decode()
                elif header == b":path":
                    raw_path = value
                elif header == b":protocol":
                    protocol = value.decode()
                elif header and not header.startswith(b":"):
                    headers.append((header, value))

            if b"?" in raw_path:
                path_bytes, query_string = raw_path.split(b"?", maxsplit=1)
            else:
                path_bytes, query_string = raw_path, b""
            path = path_bytes.decode()
            self._quic._logger.info("HTTP request %s %s", method, path)

            # feature work: add a public API to retrieve peer address
            client_addr = self._http._quic._network_paths[0].addr
            client = (client_addr[0], client_addr[1])

            handler: Handler
            scope: Dict
            if method == "CONNECT" and protocol == "websocket":
                subprotocols: List[str] = []
                for header, value in event.headers:
                    if header == b"sec-websocket-protocol":
                        subprotocols = [x.strip() for x in value.decode().split(",")]
                scope = {
                    "client": client,
                    "headers": headers,
                    "http_version": http_version,
                    "method": method,
                    "path": path,
                    "query_string": query_string,
                    "raw_path": raw_path,
                    "root_path": "",
                    "scheme": "wss",
                    "subprotocols": subprotocols,
                    "type": "websocket",
                }
                handler = WebSocketHandler(
                    connection=self._http,
                    scope=scope,
                    stream_id=event.stream_id,
                    transmit=self.transmit,
                )
            else:
                extensions: Dict[str, Dict] = {}
                if isinstance(self._http, H3Connection):
                    extensions["http.response.push"] = {}
                scope = {
                    "client": client,
                    "extensions": extensions,
                    "headers": headers,
                    "http_version": http_version,
                    "method": method,
                    "path": path,
                    "query_string": query_string,
                    "raw_path": raw_path,
                    "root_path": "",
                    "scheme": "https",
                    "type": "http",
                }
                handler = HttpRequestHandler(
                    authority=authority,
                    connection=self._http,
                    protocol=self,
                    scope=scope,
                    stream_ended=event.stream_ended,
                    stream_id=event.stream_id,
                    transmit=self.transmit,
                )                
                handler.http_event_received(event,id(self))# fix bug event_received not callback 
            self._handlers[event.stream_id] = handler
            #asyncio.ensure_future(handler.run_asgi(application))
        elif (
            isinstance(event, (DataReceived, HeadersReceived))
            and event.stream_id in self._handlers
        ):
            handler = self._handlers[event.stream_id]
            handler.http_event_received(event,id(self))
        
        #print(str(type(event)) + " for id " + str(event.stream_id) + " is end "+str(event.stream_ended) )
        

    def quic_event_received(self, event: QuicEvent) -> None: 
        
        
        if isinstance(event, ProtocolNegotiated):
            if event.alpn_protocol in H3_ALPN:
                self._http = H3Connection(self._quic,enable_webtransport=True)
            elif event.alpn_protocol in H0_ALPN:
                self._http = H0Connection(self._quic)
        elif isinstance(event, DatagramFrameReceived):
            if event.data == b"quack":
                self._quic.send_datagram_frame(b"quack-ack")

        # ??pass event to the HTTP layer
        if self._http is not None:
            for http_event in self._http.handle_event(event):
                self.http_event_received(http_event)    

          


        

    def close():
        print("close")
        super().close()

class SessionTicketStore:
    """
    Simple in-memory store for session tickets.
    """

    def __init__(self) -> None:
        self.tickets: Dict[bytes, SessionTicket] = {}

    def add(self, ticket: SessionTicket) -> None:       
        self.tickets[ticket.ticket] = ticket

    def pop(self, label: bytes) -> Optional[SessionTicket]:
        return self.tickets.pop(label, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QUIC server")
    parser.add_argument(
        "app",
        type=str,
        nargs="?",
        default="demo:app",
        help="the ASGI application as <module>:<attribute>",
    )
    parser.add_argument(
        "-c",
        "--certificate",
        type=str,
        required=True,
        help="load the TLS certificate from the specified file",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="::",
        help="listen on the specified address (defaults to ::)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4433,
        help="listen on the specified port (defaults to 4433)",
    )
    parser.add_argument(
        "-k",
        "--private-key",
        type=str,
        help="load the TLS private key from the specified file",
    )
    parser.add_argument(
        "-l",
        "--secrets-log",
        type=str,
        help="log secrets to a file, for use with Wireshark",
    )
    parser.add_argument(
        "-q",
        "--quic-log",
        type=str,
        help="log QUIC events to QLOG files in the specified directory",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="send a retry for new connections",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="increase logging verbosity"
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    # import ASGI application
    module_str, attr_str = args.app.split(":", maxsplit=1)
    module = importlib.import_module(module_str)
    application = getattr(module, attr_str)

    # create QUIC logger
    if args.quic_log:
        quic_logger = QuicDirectoryLogger(args.quic_log)
    else:
        quic_logger = None

    # open SSL log file
    if args.secrets_log:
        secrets_log_file = open(args.secrets_log, "a")
    else:
        secrets_log_file = None

    configuration = QuicConfiguration(
        alpn_protocols=H3_ALPN + H0_ALPN + ["siduck"],
        is_client=False,
        max_datagram_frame_size=65536,
        quic_logger=quic_logger,
        secrets_log_file=secrets_log_file,
    )

    # load SSL certificate and key
    configuration.load_cert_chain(args.certificate, args.private_key)

    ticket_store = SessionTicketStore()

    if uvloop is not None:
        uvloop.install()
    
    print(configuration)
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        serve(
            '::',
            4433,
            configuration=configuration,
            create_protocol=HttpServerProtocol,
            session_ticket_fetcher=ticket_store.pop,
            session_ticket_handler=ticket_store.add,
            retry=False
        )
    )
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass


# Written by Aviv this function call from proxy_server.py. 
#see in this file the requestListener function for more informatin abut listener.
def myServe(requestListener,conListener):
    HttpRequestHandler.requestListener=requestListener  
    global connectionListener
    connectionListener = conListener



    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    
    quic_logger = QuicDirectoryLogger("quicLoggerPServer")

    configuration = QuicConfiguration(
        alpn_protocols=H3_ALPN + H0_ALPN + ["siduck"],
        is_client=False,
        max_datagram_frame_size=65536,        
        secrets_log_file=open("sslkeylogPServer.log", "a"),
    )#quic_logger=quic_logger,

    # load SSL certificate and key
    configuration.load_cert_chain("ssl_cert.pem", "ssl_key.pem")
    
    ticket_store = SessionTicketStore()
    
    if uvloop is not None:
        uvloop.install()
        
    
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        serve(
            '::',
            4433,
            configuration=configuration,
            create_protocol=HttpServerProtocol,
            session_ticket_fetcher=ticket_store.pop,
            session_ticket_handler=ticket_store.add,            
            retry=False,            
        )
        
    )
    
    
    
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    
