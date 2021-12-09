# Written by Aviv

import http3_proxy_server
import requests
import sys
import asyncio
import threading
import time
import queue
from asgiref.sync import async_to_sync

address_server = 'http://10.0.2.9:8000'
#address_server = 'http://10.0.2.11:8000'
#address_server = 'http://10.0.2.11:9999'

time_sleep = 0.1
time_sleep_queue = 0.015
#time_out = 4
time_out = 60


def connectionListener(connectionId):
    pass


def requestListener(requestsHeader,requestsData,connectionId):   
  


    """
    requestListener is take header and data from aioquic,
    send it to server in HTTP1.1, get response and return it to aioquic.

    requestsHeader is the requests header from aioquic.
    requestsData is the requests data from aioquic.

    return responseHeader , responseData  from HTTP 1.1
    responseData is None if not have data
    responseHeader is None if have timeout error
    """
    time.sleep(time_sleep)
    print("::::requestListener::::")    
    try:       
        requestsHeaderDict = listTupToDict(requestsHeader)   
        method = requestsHeaderDict[':method']
        del requestsHeaderDict[':method']
        path = requestsHeaderDict[':path']
        del requestsHeaderDict[':path']                     
        
        print(method,path)
        #print("requests header (first 3): "+str(list(requestsHeaderDict.items())[:3]))

        #request feom server without blocking io
        queue_response = queue.Queue()

        """t = threading.Thread(target=requestServer, args=(method,address_server,path,requestsHeaderDict,time_out,requestsData,queue_response))
        t.start()        
        
        return await queue_get_without_blocking_io(queue_response)"""#try fix this https://github.com/aiortc/aioquic/issues/240

        return requestServer(method,address_server,path,requestsHeaderDict,time_out,requestsData,queue_response)


       
    except requests.exceptions.ReadTimeout:
        print("read time out")
        return(None,None)


#run on different on thread not blocking_io #OLD not use
def requestServer(method,address_server,path,requestsHeaderDict,time_out,requestsData,queue_response):
    if method == 'GET':            
        req = requests.request('GET', address_server+path , headers=requestsHeaderDict ,allow_redirects=False,timeout=time_out)
    elif method == 'HEAD':
        req = requests.request('HEAD', address_server+path , headers=requestsHeaderDict ,allow_redirects=False,timeout=time_out)
    else:
        #print("requests data (first 10 bytes) "+":".join("{:02x}".format(c) for c in requestsData[:10]) + "("+str(sys.getsizeof(requestsData))+")")
        req = requests.request('POST', address_server+path , headers=requestsHeaderDict  , data=requestsData, allow_redirects=False,timeout=time_out)
                                
    responseHeader = req.headers
    responseData = req.content

    #chak if server send massege to proxy. aviv_proxy_info: no matched
    proxy_info = responseHeader.get('aviv_proxy_info')        
    if proxy_info != None:
        print("proxy_info:      ",proxy_info)
    if proxy_info == 'no matched':
        print("no matched")
        return(None,None) #in new aioquic version the client blocking
        
    """print("response header (first 3): "+str(list(responseHeader.items())[:3]))
    if responseData != None:
        print("response data (first 10 bytes) "+":".join("{:02x}".format(c) for c in responseData[:10])+ "("+str(sys.getsizeof(responseData))+")")  """  
    responseHeaderList = dictTolistTup(responseHeader) 
    responseHeaderList.insert(0, (b':status', str(req.status_code).encode()))   
                
    return (responseHeaderList, responseData)
    #queue_response.put((responseHeaderList, responseData))     return await queue_get_without_blocking_io(queue_response)"""


#get item from queue not asyncio.queue without blocking the io.
async def queue_get_without_blocking_io(queue: queue.Queue):
    while True:
        if not queue.empty():
            return queue.get()
        else:
            await asyncio.sleep(time_sleep_queue)



# convert dict to list of tuple.
# for exmaple {'a':'a','b':'b'} convert to [('a','a'),('b','b')]
def dictTolistTup(d):
    lt = []
    for k in d:
        lt.append( (k.encode().lower(),d[k].encode()) )
    return lt

# convert list of tuple to dict.
# for exmaple [('a','a'),('b','b')] convert to {'a':'a','b':'b'}
def listTupToDict(lt):
    d = {}
    for a, b in lt:  
        if b != b'':
            key = a.decode("utf-8") 
            value = b.decode("utf-8")           
            d[key] =  value
    return d
    
http3_proxy_server.myServe(requestListener,connectionListener)