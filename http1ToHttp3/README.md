
http1ToHttp3 is the proxy servers that run on machine A and B in the article, and convert HTTP1.1 to HTTP3.  
proxy_client.py run on machine A and proxy_server.py run on machine B.  

# install
Install aioquic by [aioquic github README.](https://github.com/aiortc/aioquic)  
Run `python3 impot_test.py` to see if you need install more something and if show install it.  
If `python3 impot_test.py` run without errors apparently all the installation done.  
Test on python3.10

# run
in `proxy_client.py`  
change `proxyServerAddr` to ip addresses in machine A.  
change `proxyClientHost` to ip addresses in machine C.  
change `proxyClientPort` to the port you want listen from machine C.  
run `python3 proxy_client.py` in machine A.

in `proxy_server.py`  
change address_server to ip addresses and port that machine D listing.
run `python3 proxy_server` in machine B.

# test
to test if it work follow the README in serverSimulation
