import socket

SOCKET_PORT = 65432

def send_message(message, host='localhost', port=SOCKET_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        s.sendall((message + '\n').encode('utf-8'))

if __name__ == '__main__':
    while True:
        message = input('Enter your message: ')
        if message.lower() in ('exit', 'quit'):
            break
        send_message(message)
