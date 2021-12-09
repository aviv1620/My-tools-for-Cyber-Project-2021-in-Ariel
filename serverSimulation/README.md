
ServerSimulation is a simple server that runs simple HTTP 1.1 web application.  
Is sleep 3 seconds before the response to simulate case that have multi requests before the response.  
Have option to lose the response on purpose.  
Test on python 3.8

# install and run
Install python3' download the folder.  
In simple_server. py change the `host` to IP addresses in machine D.  
Run `python3 simple_server.py`  

# test regular HTTP 1.1
open the browser in machine C and enter http://IP_ADDRESSES:8000 when IP_ADDRESSES is the **IP of machine D**

# test HTTP 3 upgrade
open the browser in machine C and enter http://IP_ADDRESSES:8000 when IP_ADDRESSES is the **IP of machine A**
