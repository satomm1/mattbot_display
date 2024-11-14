#!/usr/bin/python3

import tkinter as tk
import socket
import threading
import time
import os
import pyttsx3
import pygame
from pathlib import Path
from helvetica import helvetica_widths

DEFAULT_MESSAGE = "Hello! I am a mobile robot.\nSay \"Hey Robot\" to talk to me."
CHARACTER_WIDTH = 16

class MessageDisplayApp:
    def __init__(self, root):

        self.engine = pyttsx3.init()

        self.home_dir = Path.home()
        # Construct the path to the audio files
        self.audio_dir = self.home_dir / 'Desktop' / 'audio'

        os.environ['SDL_AUDIODRIVER'] = 'alsa'
        os.environ['AUDIODEV'] = 'plughw:1,3'
        pygame.mixer.init()
        

        # Set properties (optional)
        self.engine.setProperty('rate', 175)    # Speed of speech
        self.engine.setProperty('volume', 1.0)  # Volume (0.0 to 1.0)

        self.root = root
        self.root.title("Message Display")

        # Set the application to full screen
        self.root.attributes("-fullscreen", True)

        # Set the background color of the root window to black
        self.root.configure(bg='black')

        # Binding Escape key to exit fullscreen
        self.root.bind("<Escape>", self.exit_fullscreen)

        # Configure the grid layout        
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)

        # Configure grid weights for the button row
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=2)
        self.root.grid_columnconfigure(2, weight=2)
        self.root.grid_columnconfigure(3, weight=1)


        # Add Yes, No, Clear, and Exit buttons
        self.clear_button = tk.Button(root, text="Clear", command=self.clear_text, bg='white', fg='black', font=("Helvetica", 16))
        self.clear_button.grid(row=0, column=0, padx=20, pady=10)

        self.yes_button = tk.Button(root, text="Yes", command=self.yes_action, bg='white', fg='black', font=("Helvetica", 16))
        self.yes_button.grid(row=0, column=1, padx=20, pady=10)

        self.no_button = tk.Button(root, text="No", command=self.no_action, bg='white', fg='black', font=("Helvetica", 16))
        self.no_button.grid(row=0, column=2, padx=20, pady=10)        

        self.exit_button = tk.Button(root, text="Exit", command=self.exit_application, bg='white', fg='black', font=("Helvetica", 16))
        self.exit_button.grid(row=0, column=3, padx=20, pady=10)
        
        self.clear_button.focus_set()
        
        # The sticky parameter makes the widget fill the cell
        self.text_widget = tk.Text(root, bg='black', fg='white', insertbackground='white', font=("Helvetica", 48))
        self.text_widget.grid(row=1, column=0, columnspan=4, sticky='nsew', padx=10, pady=10)    

        # Set up a socket server in a separate thread
        self.socket_thread = threading.Thread(target=self.socket_server)
        self.socket_thread.daemon = True
        self.socket_thread.start()

        # Lock for synchronizing message display
        self.display_lock = threading.Lock()
        
        self.display_default_message()      

    def get_word_length(self, word):
        # Calculate the length of a word in characters
        length = 0
        for letter in word:
            if letter in helvetica_widths:
                length += helvetica_widths[letter]
            else:
                length += 0.5
        return length

    def display_message(self, message):
        print(message)
        

        def add_letter_by_letter():
            # Save the speech as an audio file
            # self.engine.save_to_file(message, "~/Desktop/output.mp3")
            # self.engine.runAndWait()
            # time.sleep(1)

            with self.display_lock:

                if message == DEFAULT_MESSAGE:
                    pygame.mixer.music.load(self.audio_dir / 'default.mp3')  # Replace with your audio file
                    pygame.mixer.music.play()
                elif message != "Listening..." and message != "No speech detected.":
                    pygame.mixer.music.load(self.audio_dir / 'response.mp3')  # Replace with your audio file
                    pygame.mixer.music.play()

                words = message.split()
                # max_chars_per_line = 28  # Adjust this value as needed
                max_chars_per_line = CHARACTER_WIDTH
                current_line_length = 0
                for word in words:
                    word_length = self.get_word_length(word)
                    if current_line_length + word_length > max_chars_per_line:
                        self.text_widget.insert(tk.END, "\n")
                        current_line_length = 0
                    current_line_length += word_length + 0.5  # Add 0.5 for the space
                    for letter in word:
                        self.text_widget.insert(tk.END, letter)
                        self.text_widget.see(tk.END)  # Scroll to the end
                        self.text_widget.update_idletasks()  # Update the text widget
                        time.sleep(0.075)  # Delay between each letter
                    self.text_widget.insert(tk.END, " ")  # Add a space after each word
                self.text_widget.insert(tk.END, "\n\n\n")
        # Clear the text box before displaying the new message
        # self.clear_text()
        
        threading.Thread(target=add_letter_by_letter).start()

    def clear_text(self):
        self.text_widget.delete(1.0, tk.END)
        self.display_default_message()

    def yes_action(self):
        # Action for Yes button
        # self.display_message("Yes button clicked")
        pass

    def no_action(self):
        # Action for No button
        # self.display_message("No button clicked")
        pass

    def socket_server(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('0.0.0.0', 65432))
        s.listen()
        while True:
            conn, addr = s.accept()
            threading.Thread(target=self.handle_client, args=(conn,)).start()

    def handle_client(self, conn):
        with conn:
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                message = data.decode('utf-8')
                self.root.after(0, self.display_message, message)

    def exit_fullscreen(self, event=None):
        self.root.attributes("-fullscreen", False)

    def exit_application(self):
        self.root.quit()

    def display_default_message(self):
        self.display_message(DEFAULT_MESSAGE)
        
if __name__ == "__main__":
    root = tk.Tk()
    app = MessageDisplayApp(root)
    root.mainloop()