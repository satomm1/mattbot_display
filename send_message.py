import socket

def send_message(message):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(('localhost', 65432))
        s.sendall(message.encode('utf-8'))

if __name__ == "__main__":
    while True:
        message = input("Enter your message: ")
        if message.lower() in ['exit', 'quit']:
            break
        send_message(message)