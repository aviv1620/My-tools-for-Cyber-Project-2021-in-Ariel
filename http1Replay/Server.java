



import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;

public class Server {

	public static void main(String[] args) throws Exception {
		/*run 'java Server rc_port replay_port dump_http_path'
		 * when:
		 * rc_port is port for remote control channel.
		 * replay_port is port for HTTP replay
		 * dump_http_path - is path for dump_http
		 */
		
		
		
		
		if(args.length != 3)
			throw new Exception("not enough arguments or too much");
		
		//dump_http files path
		String dump_http_path = args[2];
		
		// remote control channel
		int rc_port = Integer.parseInt( args[0] );
		ServerSocket rcServerSocket = new ServerSocket(rc_port);
		Socket remoteSocket = rcServerSocket.accept();
		PrintStream remoteOut = new PrintStream( remoteSocket.getOutputStream() );
        BufferedReader remoteIn = new BufferedReader( new InputStreamReader( remoteSocket.getInputStream() ) );
		
		// replay channel
		int replay_port = Integer.parseInt( args[1] );
		ServerSocket replayServerSocket = new ServerSocket(replay_port);
		HashMap< Integer, Socket> replayConnections = new HashMap<Integer, Socket>();
		//replayConnections hold all the connections and map streamID to connections.
		

		//listing to command		
		boolean finish = false;
		while(!finish) {
			String command = remoteIn.readLine();			
			if(command.equals("finish")) { //command finish
				finish = true;
				remoteOut.write("ok\n".getBytes());
				
			}else if(command.startsWith("open connection")){
				
				//listen first request and open connection is one monotonic action
				//feedback on open connection
				int streamID = parseThirdWord(command);//parse streamID
				remoteOut.write("ok\n".getBytes());	
				
				//feedback on listen first request
				command = remoteIn.readLine();				
				int size = Integer.parseInt( command.split(" ")[3] );
				remoteOut.write("ok\n".getBytes());
				
				//open connection
				Socket socket = replayServerSocket.accept();			
				replayConnections.put(streamID, socket);	
						
				//listen first request
				readRequests(socket,size);
				
			}else if(command.startsWith("listen request")){
				int streamID = parseThirdWord(command);//parse streamID
				int size = Integer.parseInt( command.split(" ")[3] );
				remoteOut.write("ok\n".getBytes());
				Socket socket = replayConnections.get(streamID);
				readRequests(socket,size);
				
			}else if(command.startsWith("send response")){
				int streamID = parseThirdWord(command);//parse streamID
				String fileName = command.split(" ")[3];//parse file name
				
				Path path = Paths.get(dump_http_path + '/' + fileName);
			    byte[] data = Files.readAllBytes(path);
			    	
			    String feedback = "response "+data.length+"\n";
			    remoteOut.write(feedback.getBytes());
				
				
			    Socket socket = replayConnections.get(streamID);
			    socket.getOutputStream().write(data);
				
				
			}else if(command.startsWith("close connection")){
				int streamID = parseThirdWord(command);//parse streamID				
				remoteOut.write("ok\n".getBytes());											

				
				//lest query and close is one monotonic action
				command = remoteIn.readLine();													
				if(command.startsWith("listen request")){
					int size = Integer.parseInt( command.split(" ")[3] );
					remoteOut.write("ok\n".getBytes());
					Socket socket = replayConnections.get(streamID);
					readRequests(socket,size);
					
				}else if(command.startsWith("send response")){					
					String fileName = command.split(" ")[3];//parse file name
					
					Path path = Paths.get(dump_http_path + '/' + fileName);
				    byte[] data = Files.readAllBytes(path);
				    	
				    String feedback = "response "+data.length+"\n";
				    remoteOut.write(feedback.getBytes());
					
					
				    Socket socket = replayConnections.get(streamID);
				    socket.getOutputStream().write(data);										
				}
				
				
				Socket socket = replayConnections.get(streamID);
				//socket.getOutputStream().close();
				//socket.getInputStream().close();
				socket.close();				
				
			}else { //unidentified			
				remoteOut.write("unidentified\n".getBytes());
				finish = true;
			}

		}
		
		
		
		//remoteOut.close();
		//remoteIn.close();
		remoteSocket.close();
				
		replayServerSocket.close();		
		rcServerSocket.close();

	}

	//read requests from connection and ignore the contents
	private static void readRequests(Socket socket,int size) throws IOException {
		
		InputStream in = socket.getInputStream();
		
		int count = 0;		
		while(count < size) {
			in.read();
			count++;			
		}
	}
	
	//Mostly used to parse streamID
	private static int parseThirdWord(String s){
		return Integer.parseInt( s.split(" ")[2] );
	}
	
	


}
