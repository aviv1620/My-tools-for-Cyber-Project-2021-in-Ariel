# Written by Aviv
#test on python 3.10

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import http3_proxy_client
import cgi
import sys
import asyncio
import queue
import threading
import time

#server ip and port
proxyServerAddr = "10.0.2.12"
proxyServerPort = 4433

#this machine ip and port
proxyClientHost = '192.168.56.102'
proxyClientPort = 8000

queue_connection = None

#listen to HTTP 1.1 from client.
class CustomHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'        


    def handle(self):
        print("connect")
        self._queue_requests = http3_proxy_client.H1_connect(queue_connection)
        super().handle()
        print("close")
        http3_proxy_client.H1_close(self._queue_requests)
        
        
    def do_HEAD(self): 
        print("do head call")
        # request to proxy. response callback
        headers_dict = self.HTTPMessage_to_dict(self.headers)
        #print("requests header (first 3): "+str(list(headers_dict.items())[:3]))          
        http3_proxy_client.H1_request(None,headers_dict,self,self.path,self._queue_requests,"HEAD")   
    
    def do_GET(self):  
        print("do_GET call")        
        # request to proxy. response callback
        headers_dict = self.HTTPMessage_to_dict(self.headers)
        #print("requests header (first 3): "+str(list(headers_dict.items())[:3]))          
        http3_proxy_client.H1_request(None,headers_dict,self,self.path,self._queue_requests,"GET")   
       
        

    def do_POST(self):    
        print("do_POST call")
        #string the data  
        length = int(self.headers.get('content-length'))
        data = self.rfile.read(length)  
        
     
        
        # request to proxy. response callback
        headers_dict = self.HTTPMessage_to_dict(self.headers)
        #print("requests header (first 3): "+str(list(headers_dict.items())[:3]))
        #print("requests data (first 10 bytes) "+":".join("{:02x}".format(c) for c in data[:10]) + "("+str(sys.getsizeof(data))+")")
        http3_proxy_client.H1_request(data,headers_dict,self,self.path,self._queue_requests,"POST") 
        
        
    def HTTPMessage_to_dict(self,httpMessage):
        ans = {}
        for key in httpMessage.keys():            
            ans[key.lower()] = httpMessage.get(key)
        return ans  

    #call from http3_proxy_client when have response from second proxy.
    def response(self,data,header):
        #header = [(b':status', b'200'), (b'server', b'BaseHTTP/0.6 Python/3.8.10, BaseHTTP/0.6 Python/3.8.10'), (b'date', b'Thu, 08 Jul 2021 14:32:44 GMT, Thu, 08 Jul 2021 14:32:44 GMT'), (b'content-type', b'text/html'), (b'content-length', b'14')]#FIXME


        #print("response header (first 3): "+str(header[:3]))
        if data != None:
            print("response data (first 10 bytes) "+":".join("{:02x}".format(c) for c in data[:10])+ "("+str(sys.getsizeof(data))+")")
        #print("header:",header)
        # send header
        for h in header:             
            k,v = h            
            if(k == b':status'):
                status = int(v.decode("utf-8"))
                self.send_response(status)
            elif(k != b'transfer-encoding' and k != b'content-length'): 
                self.send_header(k.decode("utf-8"), v.decode("utf-8"))

        if data != None:
            self.send_header("Content-Length", len(data))
      
        self.end_headers()
        
        #send data        
        self.wfile.write(data)
                   
                   
def start_server(host = proxyClientHost, port = proxyClientPort):
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, CustomHandler)
    threading.Thread(target=serve_forever, args=(httpd,)).start()

def serve_forever(httpd):#call from threading to not block IO
    httpd.serve_forever() #block IO

async def main():
    #sharing connection between two systems.
    global queue_connection
    queue_connection = queue.Queue()
    c1 = h1()
    c2 = http3_proxy_client.h3(queue_connection)
    await asyncio.gather(c1,c2)   

async def h1():
    http3_proxy_client.hostStr = proxyServerAddr
    http3_proxy_client.hostPort = proxyServerPort
    start_server()

if __name__== "__main__":
    asyncio.run(main())
