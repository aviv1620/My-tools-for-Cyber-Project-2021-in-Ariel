




import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.lang.reflect.Type;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.List;
import java.util.Scanner;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;

public class Client {

	public static void main(String[] args) throws Exception {
		/*run 'java Client rc_address rc_port debug replay_address replay_port dump_http_path
		//when:
		 *  rc_address - is IP address for remote control channel.
		 *  rc_port - is port for remote control channel.
		 *  debug - is true if we want press enter any query.
		 *  replay_address - is IP address for replay server.
		 *  replay_port - is port for remote replay server.
		 *  dump_http_path - is path for dump_http
		 * */

		if(args.length != 6)
			throw new Exception("not enough arguments or too much");

		//dump_http files path
		String dump_http_path = args[5];

		//debug mode
		boolean debug = Boolean.parseBoolean(args[2]); 
		Scanner scanner = null;
		if(debug) {
			scanner = new Scanner(System.in);
			System.out.println("enter to send query");
		}

		// remote control channel		
		String rc_address = args[0];
		int rc_port = Integer.parseInt( args[1] );
		Socket remoteSocket = new Socket( rc_address, rc_port );		

		// replay channel
		String replay_address = args[3];
		int replay_port = Integer.parseInt( args[4] );
		HashMap< Integer, Socket> replayConnections = new HashMap<Integer, Socket>();
		//replayConnections hold all the connections and map streamID to connections.


		//Iterate on querys to replay
		Gson gson = new Gson();
		Type listType = new TypeToken<List<Query>>() {}.getType();
		List<Query> querys = gson.fromJson(new FileReader(dump_http_path + "/" + "dump_http.json"), listType);

		for (int i = 0; i < querys.size(); i++) {
			if(debug) {
				scanner.nextLine();
			}
			Query query = querys.get(i);

			String first = query.isFirst ? "first" : "";
			String queryType = query.isRequest ? "request" : "response";
			String lest = query.isLest ? "lest" : "";
			System.out.println("query "+i+" from "+querys.size() + " " + first + " " + queryType + " " + lest);

			//open/close and send the first/lest query is one monotonic action
			
			
			
			//open new socket
			if(query.isFirst) {				
				//*) ask server to open new connection for query.streamID
				askServer(remoteSocket,"open connection "+query.streamID);
				//*) ask server to listen to my request
				Path path = Paths.get(dump_http_path + '/' + query.data);
				byte[] data = Files.readAllBytes(path);
				askServer(remoteSocket,"listen request "+query.streamID+" "+data.length);		

				//*) open connection in my side to query.streamID				
				Socket socket = new Socket( replay_address, replay_port );
				replayConnections.put(query.streamID, socket);
				
				//*) send my request				
				socket.getOutputStream().write(data);
				
			}else if(!query.isLest)

				//send
				if(query.isRequest) {//send Request		
					//*) ask server to listen to my request
					Path path = Paths.get(dump_http_path + '/' + query.data);
					byte[] data = Files.readAllBytes(path);
					askServer(remoteSocket,"listen request "+query.streamID+" "+data.length);			
					//*) send my request
					Socket socket = replayConnections.get(query.streamID);				
					socket.getOutputStream().write(data);	
						
	
				}else {				
					//*) ask server to send response
					int size = askServer(remoteSocket,"send response "+query.streamID+" "+query.data);
					if(size < 0)
						throw new Exception("bed response");
					//*) listen to my responses
					Socket socket = replayConnections.get(query.streamID);
					readResponses(socket,size);
				}

			//close
			else{//query.isLest			
												
				byte[] data = null;
				int size = -1;
				
				
				//*) ask server to close connection for query.streamID
				askServer(remoteSocket,"close connection "+query.streamID);
				
				//lest query
				if(query.isRequest) {
					//*) ask server to listen to my request			
					Path path = Paths.get(dump_http_path + '/' + query.data);
					data = Files.readAllBytes(path);
					askServer(remoteSocket,"listen request "+query.streamID+" "+data.length);						
				}else {
					//*) ask server to send response
					size = askServer(remoteSocket,"send response "+query.streamID+" "+query.data);
					if(size < 0)
						throw new Exception("bed response");
				}															
				
				
				//send the query
				if(query.isRequest) {
					//*) send my request
					Socket socket = replayConnections.get(query.streamID);				
					socket.getOutputStream().write(data);	
				}else {
					//*) listen to my responses
					Socket socket = replayConnections.get(query.streamID);
					readResponses(socket,size);
				}
								
				
				//*) close connection in my side to query.streamID
				Socket socket = replayConnections.get(query.streamID);
				//socket.getInputStream().close();
				//socket.getOutputStream().close();				
				socket.close();
			}

		}


		//finish close server
		askServer(remoteSocket,"finish");



		// Close remote control channel
		//remoteSocket.getOutputStream().close();
		//remoteSocket.getInputStream().close();
		remoteSocket.close();

		System.out.println("goodbye");


	}

	//read requests from connection and ignore the contents
	private static void readResponses(Socket socket,int size) throws IOException {			
		InputStream in = socket.getInputStream();
		
		int count = 0;		
		while(count < size) {
			in.read();
			count++;
			if(count % 1000000 == 0)
				System.out.print("*");
		}
		if(count >= 1000000)
			System.out.print("|\n");
			
	}




	/*askServer some command.
	 * return number id have response or -1 if not have.
	 * throw exception if the command invalid
	 */
	private static int askServer(Socket remoteSocket,String command) throws Exception {
		command = command + "\n";
		
		PrintStream out = new PrintStream( remoteSocket.getOutputStream() );
		BufferedReader in = new BufferedReader( new InputStreamReader( remoteSocket.getInputStream() ) );
		
		out.write(command.getBytes());
		String feedback = in.readLine();
		if(feedback.equals("ok"))
			return -1;
		else if(feedback.startsWith("response")) {
			int size = Integer.parseInt(feedback.split(" ")[1]);
			return size;
		}else
			throw new Exception("server not do the command. server say "+feedback);        

	}

	public static class Query{
		public int streamID;
		public boolean isRequest;
		public boolean isFirst;
		public boolean isLest;
		public String data;


	}

}
