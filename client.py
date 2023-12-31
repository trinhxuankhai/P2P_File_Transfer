import socket
import os
import threading
import ast
import time
from tqdm import tqdm

HEADER = 64 # number of bytes of the message length
PORT = 5050
PORT_P2P = 0 # random port
PORT_LISTEN_SERVER = 0 # random port
FORMAT = 'utf-8'
# SERVER = "172.0.0.129"
# SERVER_P2P = "172.0.0.123"
SERVER = socket.gethostbyname(socket.gethostname())
SERVER_P2P = socket.gethostbyname(socket.gethostname())
ADDR = (SERVER, PORT) 
ADDR_P2P = (SERVER_P2P, PORT_P2P)
ADDR_LISTEN_SERVER = (SERVER_P2P, PORT_LISTEN_SERVER)
BUFFER_SIZE = 4096 # send 4096 bytes each time step

class Client:
    def __init__(self):
        # create a socket to connect to the server
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
        self.client.connect(ADDR)

        # create a socket to connect to listen from the server
        self.listen_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_server_socket.bind(ADDR_LISTEN_SERVER)

        # create a socket to listen other clients
        self.p2p_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.p2p_server_socket.bind(ADDR_P2P)

        self.hostname = ""

    def start(self):
        # start the thread to listen other clients
        thread_response_handler = threading.Thread(target=self.handleP2PConnection)
        thread_response_handler.start()

        # start listen to the server
        thread_listen_server = threading.Thread(target=self.handleListenServer)
        thread_listen_server.start()

        # REGISTER THE HOST NAME #
        hostname = input("Enter your hostname : ")
        self.sendMessage(self.client, hostname)
        response = self.receiveMessage(self.client)
        print(response)
        while response.startswith("The hostname already exist !"):
            hostname = input("Enter another name: ")
            self.sendMessage(self.client, hostname)
            response = self.receiveMessage(self.client)
            print(response)
        
        self.hostname = hostname
        # SEND THE PORT HOST P2P
        port_p2p = self.p2p_server_socket.getsockname()[1]
        self.sendMessage(self.client, str(port_p2p))

        # SEND THE PORT LISTEN SERVER
        port_listen_server = self.listen_server_socket.getsockname()[1]
        self.sendMessage(self.client, str(port_listen_server))

        while True:
            try:
                command = input("> ")
                if command == "disconnect":
                    self.commandHandler(command)
                    break
                self.commandHandler(command)

            except KeyboardInterrupt:
                print("Client closed.")
                break
        
        print("Client closed.")

    def sendMessage(self, conn, msg):
        message = msg.encode(FORMAT) # encode the message
        msg_length = len(message) # get the message length
        send_length = str(msg_length).encode(FORMAT) # encode the message length
        padded_send_length = send_length + b' ' * (HEADER - len(send_length)) # pad the message length
        conn.send(padded_send_length) # send the message length
        conn.send(message) # send the message

    def receiveMessage(self, conn):
        message = ""
        msg_length = conn.recv(HEADER).decode(FORMAT)
        if msg_length:
            msg_length = int(msg_length) 
            message = conn.recv(msg_length).decode(FORMAT)
        return message

    def publishFile(self, type, filename, newFilename):
        ## HANDLE THE FILE NOT FOUND CASE ##
        listFile = os.listdir()
        if filename not in listFile:
            print("File not found !")
            return

        ## SEND THE TYPE OF COMMAND AND THE FILE NAME ##
        self.sendMessage(self.client, type)
        self.sendMessage(self.client, filename)
        self.sendMessage(self.client, newFilename)   

    def fetchFile(self, type, filename):
        ## SEND THE FILE NAME ##
        self.sendMessage(self.client, type)  
        self.sendMessage(self.client, filename)
        self.sendMessage(self.client, self.hostname)

        response = self.receiveMessage(self.client)
        print(response)
        ## FILE NOT FOUND CASE
        if response.startswith("File not found !"):
            return
        if response.startswith("No other hostname has that file !"):
            return

        ## RECEIVE THE LIST OF USERS HAVE THAT FILE ##
        listUser = self.receiveMessage(self.client)
        
        ## CHOOSE THE LIST OF USERS ##
        print("Choose one user to download the file: ")
        listUser = listUser.split("-")
        for i in range(len(listUser)):
            print(f"{i+1}. {listUser[i]}")
        choice = int(input("Enter your choice: "))
        while choice>len(listUser):
            print("Please choose a number in range !")
            choice = int(input("Re-enter your choice: "))

        hostname = ast.literal_eval(listUser[choice-1])[0]
        filename = ast.literal_eval(listUser[choice-1])[1]
        ## SEND THE HOSTNAME BACK TO SERVER ##  
        self.sendMessage(self.client, hostname)

        ip = self.receiveMessage(self.client)
        port_p2p = self.receiveMessage(self.client)

        ## ESTABLISH THE P2P CONNECTION ##
        p2p_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        p2p_socket.connect((ip, int(port_p2p)))  
        
        ## SEND THE FILE NAME TO THE PEER ##
        self.sendMessage(p2p_socket, filename)

        ## RECEIVE THE FILE SIZE ##
        file_size = int(self.receiveMessage(p2p_socket))
        received_size = 0
        ## RECEIVE THE FILE ##
        flag = False
        with open(filename, "wb") as f:
            with tqdm( total=file_size, unit='B', unit_scale=True, desc='Receiving', ascii=True, colour='green') as pbar:
                bytes_read = p2p_socket.recv(BUFFER_SIZE)
                while bytes_read:
                    flag = True
                    received_size += len(bytes_read)
                    pbar.update(len(bytes_read))
                    f.write(bytes_read)
                    bytes_read = p2p_socket.recv(BUFFER_SIZE)
        
        if flag:
            print("File received !")
            self.sendMessage(self.client, "success")
        else:
            print("File failed to receive !")
            self.sendMessage(self.client, "fail")

    def commandHandler(self, command):
        command = command.split()
        try:
            if command[0] == "publish":
                self.publishFile(command[0], command[1], command[2])
            elif command[0] == "fetch":
                self.fetchFile(command[0], command[1])
            elif command[0] == "disconnect":
                self.sendMessage(self.client, command[0])
                self.client.close()
                self.listen_server_socket.close()
                self.p2p_server_socket.close()
            else:
                print("Invalid command !")
        except IndexError:
            print("Invalid command !")

    def handlePeer(self, conn, addr):
        # print(f"[NEW CONNECTION] {addr} connected.")
        filename = self.receiveMessage(conn)
        # print(filename)
        start_time = time.time()
        file_size = os.path.getsize(filename)
        self.sendMessage(conn, str(file_size))
        sent_size = 0
        with open(filename, "rb") as f: 
            with tqdm( total=file_size, unit='B', unit_scale=True, desc='Sending', ascii=True, colour='red') as pbar:
                bytes_read = f.read(BUFFER_SIZE)
                while bytes_read:
                    # read the bytes from the file
                    conn.sendall(bytes_read)
                    sent_size += len(bytes_read)
                    pbar.update(len(bytes_read))
                    bytes_read = f.read(BUFFER_SIZE)
                    
                # print("File sent !")
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Time to send file: {elapsed_time:.2f} seconds \n> ", end="")
        conn.close()

    def handleP2PConnection(self):
        self.p2p_server_socket.listen()
        # print(f"[LISTENING] P2P is listening on port {self.p2p_server_socket.getsockname()[1]} \n")
        while True:
            try:
                conn, addr = self.p2p_server_socket.accept()
            except:
                exit()
            # print("Connect p2p successfully !")
            thread = threading.Thread(target=self.handlePeer, args=(conn, addr))
            thread.start()

    def handleServer(self, conn, addr):
        msg = self.receiveMessage(conn)
        if msg == "ping":
            self.sendMessage(conn, "pong")
            conn.close()
        # if msg == "discover":
        #     listFile = os.listdir()
        #     self.sendMessage(conn, str(listFile))
        #     conn.close()

    def handleListenServer(self):
        self.listen_server_socket.listen()
        while True:
            try:
                conn, addr = self.listen_server_socket.accept()
            except:
                exit()
            # print("Connect listen server successfully ! \n")
            thread = threading.Thread(target=self.handleServer, args=(conn, addr))
            thread.start()


if __name__ == "__main__":
    client = Client()
    client.start()
