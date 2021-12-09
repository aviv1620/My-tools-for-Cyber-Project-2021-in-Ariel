This tool replay HTTP queries between two machines. This tool transform the data over socket and give the system to manage tho TCP paketes. 
# logic 
Read  the  logic  of  the experiment  in  the  readme  in  the  main  repository.
The remote control channel  gives basic communication between the software that replay in client side(machineC) to software that replay in server sise(machineD) to say with response to send and when.
The transform from machineC to machineD of remote control channel need be directed.
The transform from machineC to machineD of replay can move over the proxy.
Have  Issues  in  my  system  in  case  that  the  order  of  queries  is  not  pairs  of  requests  and  responses.  Have  solution  for  this  in  the  private  repository, you  can contact  me  for  more  information.


# install
Download the folder, and install Python3, Java JDK,Java JRE, and tshark.  
In java add the file `gson-2.8.7.jar` to `JAVA_LOCATION\Java\jdk1.8.0_291\jre\lib\ext` and to `JAVA_LOCATION\Java\jre1.8.0_291\lib\ext`.  
Test on Java 1.8, Python3.8 and tshark(wireshark) 3.2.3

# run 
First you need extract the pcap/pcapng files to dump_http. 
second you need run the server. 
third you need run the client.
## extract dump_http and compile
run `python3 pcap_to_dump.py -f PCAP_FILE_PATH` from any machine support python3.
run `javac -cp gson-2.8.7.jar Server.java Client.java`. from any machine support java compiler. 
## run the server
run `java Server rc_port replay_port dump_http_path` 
when:
* rc_port is port for remote control channel.
* replay_port is port for HTTP replay
* dump_http_path - is path for dump_http
## run the Client. 
run `java Client rc_address rc_port debug replay_address replay_port dump_http_path`.
when:
*  rc_address - is IP address for remote control channel.
*  rc_port - is port for remote control channel.
*  debug - is true if we want press enter any query.
*  replay_address - is IP address for replay server.
*  replay_port - is port for remote replay server.
*  dump_http_path - is path for dump_http.