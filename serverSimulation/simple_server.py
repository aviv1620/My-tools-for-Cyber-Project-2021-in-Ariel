# Written by Aviv
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import cgi
import time

host = '10.0.2.9'
lose_response = False# lose_response 


class CustomHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'           
    

    
    
    def do_GET(self):                  
        print(self.path)               
        
        time.sleep(3)


        if self.path == '/':
            self.response_file("index.html","text/html")
        elif self.path == '/pic_trulli.jpg':           
            if lose_response == False: # lose response on purpose
                self.response_file("pic_trulli.jpg","image/jpg")
        elif self.path == '/styles.css':           
                self.response_file("styles.css","test/css")
        elif self.path == '/myScript.js':
            self.response_file("myScript.js","application/javascript")
        elif self.path == '/favicon.ico':
            self.response_file("favicon.ico","image/x-icon")
        elif self.path == '/Fronalpstock_big.jpg':
            self.response_file("Fronalpstock_big.jpg","image/jpg")
        else:
            print("bed request")
            self.send_response(404)
            self.end_headers()
        
        
       
                 

    def do_POST(self):
        print("do_POST call")
        
        #send response
        response = 'hello world'.encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", len(response))
        self.end_headers()
        self.wfile.write(response)
        
    def response_file(self, path : str, type_file: str):
        with open(path, "rb") as f:
            response = f.read()                                
        
            self.send_response(200)
            self.send_header("Content-Type",type_file )
            self.send_header("Content-Length", len(response))
            self.end_headers()
            self.wfile.write(response)             
    
        
                   
def start_server(host = host, port = 8000):
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, CustomHandler)
    httpd.serve_forever()
    


def main():
    start_server()

if __name__== "__main__":
    main()
