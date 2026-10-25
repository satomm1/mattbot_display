import json
import socket

SOCKET_PORT = 65432

def send_message(text, speak=False, host='localhost', port=SOCKET_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        s.sendall((json.dumps({'text': text, 'speak': speak}) + '\n').encode('utf-8'))

if __name__ == '__main__':
    # Prefix a message with "!" to have it spoken aloud.
    while True:
        message = input('Enter your message: ')
        if message.lower() in ('exit', 'quit'):
            break
        speak = message.startswith('!')
        send_message(message[1:] if speak else message, speak=speak)
