# Written by Aviv

import subprocess
import os
import shutil
import json
import argparse

path_dump_http = "dump_http"

def main():
    #files
    if os.path.exists(path_dump_http+'.json'):
        os.remove(path_dump_http+'.json')

    if os.path.exists(path_dump_http):
        shutil.rmtree(path_dump_http,ignore_errors=True)
        
    if not os.path.exists(path_dump_http):        
        os.makedirs(path_dump_http) 

    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--pcapfile", type=str, help="set pcap file when you dump to java progrem")   
    args = parser.parse_args()
    file_name = args.pcapfile
    if file_name is None:
        raise Exception('Invalid input for --pcapfile')

    #parse   
    tshark_cmd = "tshark -2 -r "+file_name+" -Y http -T fields -e frame.number -e tcp.stream -e http.request -e http.prev_request_in -e http.next_request_in -e http.response_in -e tcp.segment.count -e tcp.payload -e tcp.reassembled.data"
    #[0]    frame.number            is frame ID
    #[1]    tcp.stream              is stream ID
    #[2]    http.request            is '' or 1.'' meen the http is response. 1 meen the http is requests.
    #[3]    http.prev_request_in    is '' or numbr. '' meen this response *or this the first requests*
    #[4]    http.next_request_in    is '' or numbe. '' meen this lest request. number is frame when have more request.
    #[5]    http.response_in        is '' or numbe. '' meen have response. *if next_request_in and response_in is '' is lest.
    #[6]    tcp.segment.count       is '' or number.'' meen the data not need reassembled. number nees reassembled.
    #[7]    tcp.payload             tcp.payload
    #[8]    tcp.reassembled.data    tcp.reassembled.data

    input_text = subprocess.run(tshark_cmd, stdout=subprocess.PIPE, shell=True)

    queries = []

    if input_text.returncode != 0:
        raise Exception("tshark not work. run 'tshark -version' in terminal or cmd")

    for s in input_text.stdout.split(b'\n'):
        s = s.decode("utf-8") 
        s = s.split("\t")

        query = {}

        #fix end line
        if len(s) == 1:
            break

        query["streamID"] = int(s[1])
        query["isRequest"] = s[2] == '1'
        query["isFirst"] = s[3] == '' and query["isRequest"]
        query["isLest"] = s[4] == '' and s[5] == ''
        query["data"] = file_payload(s,s[0])        

        print(query)
        queries.append(query)

    with open(path_dump_http+'.json', 'w') as outfile:
        json.dump(queries, outfile)
        
    print("write to "+path_dump_http+'.json')

#parse the payload. wirte to file and return the file name
def file_payload(s,name):
    data = parse_payload(s)
    file_name = path_dump_http+'/'+name.zfill(2)+".bin"
    f = open(file_name, "wb")
    f.write(data)
    f.close()
    return file_name

def parse_payload(s):
    if s[6] == "":#take s[7] payload
        return bytes.fromhex(s[7])
    else:#take s[8] reassembled
        return bytes.fromhex(s[8])




if __name__ == "__main__":
    main()








