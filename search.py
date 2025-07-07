import os
import webbrowser
import platform
import subprocess
import tempfile
import requests
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from mutagen import File as MutagenFile
from dotenv import load_dotenv

import pygame  # for audio playback

import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = 'https://spotify.com'

print(f"Using CLIENT ID '{SPOTIFY_CLIENT_ID}'")

SCOPE = "playlist-modify-public"

BLACKLIST_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif"]


def reveal_in_explorer(file_path):
	"""
	Open the system's file explorer/finder at the location of file_path.
	On Windows, it will select the file in Explorer;
	on macOS, it will reveal in Finder;
	on Linux, it opens the folder (won't highlight the exact file on many distros).
	"""
	if not os.path.exists(file_path):
		messagebox.showerror("Error", f"File does not exist:\n{file_path}")
		return

	system_name = platform.system()
	try:
		if system_name == "Windows":
			# Opens Windows Explorer and selects the file
			subprocess.Popen(f'explorer /select,"{os.path.abspath(file_path)}"')
		elif system_name == "Darwin":  # macOS
			subprocess.Popen(["open", "-R", file_path])
		else:
			# Linux / others: just open the folder
			folder = os.path.dirname(file_path)
			subprocess.Popen(["xdg-open", folder])
	except Exception as e:
		messagebox.showerror("Error", f"Unable to open in file explorer:\n{e}")


class SpotifyPlaylistApp:
	def __init__(self, root):
		self.root = root
		self.root.title("Spotify Playlist Creator")

		pygame.mixer.init()

		self.main_frame = tk.Frame(self.root)
		self.main_frame.pack(fill="both", expand=True)

		# Initialize Spotify client
		try:
			self.sp = spotipy.Spotify(
				auth_manager=SpotifyOAuth(
					client_id=SPOTIFY_CLIENT_ID,
					client_secret=SPOTIFY_CLIENT_SECRET,
					redirect_uri=SPOTIFY_REDIRECT_URI,
					scope=SCOPE
				)
			)
		except SpotifyOauthError as e:
			messagebox.showerror("Spotify Auth Error", f"Could not authenticate with Spotify:\n{e}")
			self.sp = None

		self.selected_directory = None
		self.playlist_id = None
		self.playlist_name = None
		self.audio_files = []
		self.skipped_songs = []
		self.current_index = 0
		self.current_filepath = None
		self.local_title = None
		self.local_artist = None
		self.local_duration_str = None

		# Temporary file path for Spotify previews
		self.preview_temp_path = None

		self.blacklisted_extensions = BLACKLIST_EXTENSIONS

		# Draw the initial UI (select directory)
		self.draw_initial_ui()

	def draw_initial_ui(self):
		"""Draw the initial UI with a button to select a directory."""
		# Clear any existing widgets
		for widget in self.main_frame.winfo_children():
			widget.destroy()

		welcome_label = tk.Label(self.main_frame, text="Welcome to the Spotify Playlist Creator!")
		welcome_label.pack(pady=10)

		select_dir_button = tk.Button(
			self.main_frame,
			text="Select Directory",
			command=self.select_directory
		)
		select_dir_button.pack(pady=5)

	def create_playlist(self):
		if self.playlist_name and self.sp:
			# Create playlist in Spotify
			user_id = self.sp.current_user()["id"]
			new_playlist = self.sp.user_playlist_create(user=user_id, name=self.playlist_name, public=True)
			self.playlist_id = new_playlist["id"]

	def select_directory(self):
		"""Prompt user to select a directory and then ask for the playlist name."""
		directory = filedialog.askdirectory(title="Select a directory containing your music files")
		if directory:
			self.selected_directory = directory
			self.playlist_name = simpledialog.askstring("Playlist Name", "Enter the name for the new Spotify Playlist:")
			# Gather non-blacklisted files
			self.audio_files = self.get_audio_files(directory)
			self.audio_files.sort(key=lambda x: os.path.basename(x).lower())
			
			# Start with the first file
			self.current_index = 0
			self.show_file_prompt()

	def get_audio_files(self, directory):
		"""Get all non-blacklisted files from the directory (recursively)."""
		all_files = []
		for root, dirs, files in os.walk(directory):
			for filename in files:
				_, ext = os.path.splitext(filename)
				if ext.lower() not in self.blacklisted_extensions:
					all_files.append(os.path.join(root, filename))
		return all_files

	def show_file_prompt(self):
		"""Show the UI for the current file, allowing user to see local metadata,
		edit the search query, see immediate search results, add track by URL, and skip."""
		# If we've processed all files, show a 'finished' message
		if self.current_index >= len(self.audio_files):
			messagebox.showinfo("Done", f"All files processed.\nSkipped songs:\n{self.skipped_songs}")
			# Optionally redraw the initial UI
			self.draw_initial_ui()
			return

		# Clear the main_frame
		for widget in self.main_frame.winfo_children():
			widget.destroy()

		# Current file
		self.current_filepath = self.audio_files[self.current_index]
		filename = os.path.basename(self.current_filepath)

		# Read metadata
		title, artist, duration_str = self.get_file_metadata(self.current_filepath)
		self.local_title = title
		self.local_artist = artist
		self.local_duration_str = duration_str

		# Determine prefill text for search
		if title and artist:
			prefill_text = f"{title} {artist}"
		elif title and not artist:
			prefill_text = title
		elif not title and artist:
			prefill_text = artist
		else:
			base, _ = os.path.splitext(filename)
			prefill_text = base

		# -- UI Elements --
		# 1) Filename label
		file_label = tk.Label(self.main_frame, text=f"File: {filename}", fg="blue")
		file_label.pack(pady=5)

		# 2) "Show in Explorer" button
		explorer_button = tk.Button(
			self.main_frame,
			text="Show in Explorer",
			command=lambda path=self.current_filepath: reveal_in_explorer(path)
		)
		explorer_button.pack(pady=2)

		# 3) Local file metadata
		meta_label_text = (
			f"Local Title: {title or 'Unknown'}\n"
			f"Local Artist: {artist or 'Unknown'}\n"
			f"Local Duration: {duration_str or 'Unknown'}"
		)
		meta_label = tk.Label(self.main_frame, text=meta_label_text)
		meta_label.pack(pady=5)

		# 4) Local playback controls
		playback_frame = tk.Frame(self.main_frame)
		playback_frame.pack(pady=5)

		play_button = tk.Button(playback_frame, text="Play local file", command=self.play_local_audio)
		play_button.pack(side="left", padx=5)

		stop_button = tk.Button(playback_frame, text="Stop local playback", command=self.stop_local_audio)
		stop_button.pack(side="left", padx=5)

		# 5) Search query label & entry
		prompt_label = tk.Label(self.main_frame, text="Edit search query if needed:")
		prompt_label.pack(pady=(10, 0))

		self.query_var = tk.StringVar(value=prefill_text)
		query_entry = tk.Entry(self.main_frame, textvariable=self.query_var, width=50)
		query_entry.pack(pady=5)
		
		# 6) Search button
		search_button = tk.Button(self.main_frame, text="Search", command=self.search_spotify)
		search_button.pack()

		# 7) Frame for results
		self.results_frame = tk.Frame(self.main_frame)
		self.results_frame.pack(pady=5)

		# 8) Buttons row
		buttons_frame = tk.Frame(self.main_frame)
		buttons_frame.pack()
		
		# 9) "Spotify Track URL" label & entry
		url_label = tk.Label(buttons_frame, text="Or enter a Spotify Track URL:")
		url_label.pack()
		self.url_var = tk.StringVar()
		url_entry = tk.Entry(buttons_frame, textvariable=self.url_var, width=50)
		url_entry.pack(pady=5)
		
		# 10) Add by url button
		add_by_url_button = tk.Button(
			buttons_frame, 
			text="Add by URL", 
			command=self.add_track_by_url
		)
		add_by_url_button.pack(padx=5)

		# 11) Skip button
		skip_button = tk.Button(
			buttons_frame,
			text="Skip",
			command=self.skip_file
		)
		skip_button.pack(padx=5)

		# We automatically run the search
		self.search_spotify()

	def add_track_by_url(self):
		"""
		If the user enters a Spotify track URL (or URI), we attempt to fetch that
		track via Spotipy. If valid, add it to the playlist; otherwise, show an error.
		"""
		track_url = self.url_var.get().strip()
		if not track_url:
			messagebox.showerror("No URL", "Please enter a Spotify track URL or URI.")
			return

		if self.playlist_id is None:
			self.create_playlist()
		try:
			# sp.track() can accept a full URL or URI, e.g.:
			# 'https://open.spotify.com/track/123...' or 'spotify:track:123...'
			track_info = self.sp.track(track_url)  
			if track_info and track_info["type"] == "track":
				track_uri = track_info["uri"]
				self.sp.playlist_add_items(self.playlist_id, [track_uri])
				messagebox.showinfo("Success", f"Added track by URL:\n{track_info['name']}")
				self.go_to_next_file()
			else:
				messagebox.showerror("Invalid Track", "The provided URL does not correspond to a valid Spotify track.")
		except Exception as e:
			messagebox.showerror("Invalid URL", f"Error trying to fetch track:\n{e}")

	def search_spotify(self):
		"""Perform the search on Spotify (immediately on show_file_prompt) and display up to 5 hits with radio buttons."""
		# Clear previous search results (and stop any ongoing preview)
		for widget in self.results_frame.winfo_children():
			widget.destroy()
		self.stop_preview_audio()

		query = self.query_var.get().strip()
		if not query:
			return

		results = self.sp.search(q=query, limit=5, type='track')
		tracks = results.get('tracks', {}).get('items', [])

		if not tracks:
			tk.Label(self.results_frame, text="No results found.", fg="red").pack()
			return

		# Radio variable
		self.track_var = tk.StringVar()
		self.track_var.set(tracks[0]['uri'])  # select the top track by default

		# Display each track with radio button
		for i, track in enumerate(tracks):
			track_uri = track['uri']
			track_name = track['name']
			artists = ", ".join(artist['name'] for artist in track['artists'])
			album_name = track['album']['name']
			duration_ms = track['duration_ms']
			duration_s = duration_ms // 1000
			duration_str = f"{duration_s // 60}:{duration_s % 60:02d}"
			preview_url = track.get('preview_url', None)

			# Frame for each track row
			row_frame = tk.Frame(self.results_frame)
			row_frame.pack(anchor='w', pady=2, fill='x')

			# Radio button text
			text_line = f"{track_name} - {artists}\nAlbum: {album_name} | Duration: {duration_str}"
			rb = tk.Radiobutton(
				row_frame,
				text=text_line,
				variable=self.track_var,
				value=track_uri,
				justify="left",
				anchor="w"
			)
			rb.pack(side="left", padx=5)

			# Visit button
			visit_button = tk.Button(
				row_frame,
				text="Visit",
				command=lambda url=track['external_urls']['spotify']: webbrowser.open(url)
			)
			visit_button.pack(side="left", padx=5)

			if preview_url:
				# Preview playback buttons
				preview_play_button = tk.Button(
					row_frame,
					text="Play Preview",
					command=lambda url=preview_url: self.play_spotify_preview(url)
				)
				preview_play_button.pack(side="left", padx=5)

				preview_stop_button = tk.Button(
					row_frame,
					text="Stop",
					command=self.stop_preview_audio
				)
				preview_stop_button.pack(side="left", padx=5)

		# Add button (below the list)
		add_button = tk.Button(self.results_frame, text="Add to Playlist", command=self.add_to_playlist)
		add_button.pack(pady=5)

	def play_spotify_preview(self, url):
		"""Download and play the Spotify preview (if available) via pygame."""
		self.stop_preview_audio()  # Stop any currently-playing preview first
		if not url:
			messagebox.showinfo("Preview Unavailable", "No preview available for this track.")
			return
		try:
			# Download the preview MP3 to a temporary file
			response = requests.get(url, timeout=10)
			response.raise_for_status()
			with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
				tmp.write(response.content)
				tmp.flush()
				self.preview_temp_path = tmp.name

			# Load in pygame and play
			pygame.mixer.music.load(self.preview_temp_path)
			pygame.mixer.music.play()
		except Exception as e:
			messagebox.showerror("Error", f"Unable to play preview:\n{e}")

	def stop_preview_audio(self):
		"""Stop any Spotify preview currently playing and remove the temp file."""
		pygame.mixer.music.stop()
		if self.preview_temp_path and os.path.exists(self.preview_temp_path):
			try:
				os.remove(self.preview_temp_path)
			except Exception as e:
				print("Failed to remove temp preview file:", e)
		self.preview_temp_path = None

	def add_to_playlist(self):
		"""Add the selected track to the Spotify playlist."""
		if self.playlist_id is None:
			self.create_playlist()
		selected_track_uri = self.track_var.get()
		if selected_track_uri:
			self.sp.playlist_add_items(self.playlist_id, [selected_track_uri])
		self.go_to_next_file()

	def skip_file(self):
		"""Skip the current file (do not add anything to the playlist)."""
		filename = os.path.basename(self.audio_files[self.current_index])
		self.skipped_songs.append(filename)
		self.go_to_next_file()

	def go_to_next_file(self):
		"""Move on to the next file, or finish if we're at the end."""
		self.stop_local_audio()   # Stop local file playback
		self.stop_preview_audio() # Stop any Spotify preview
		self.current_index += 1
		self.show_file_prompt()

	def play_local_audio(self):
		"""Play the local audio file using pygame.mixer."""
		self.stop_local_audio()  # Stop if something else is playing
		if self.current_filepath and os.path.exists(self.current_filepath):
			try:
				pygame.mixer.music.load(self.current_filepath)
				pygame.mixer.music.play()
			except Exception as e:
				messagebox.showerror("Playback Error", f"Unable to play file:\n{e}")

	def stop_local_audio(self):
		"""Stop local audio playback."""
		pygame.mixer.music.stop()

	def get_file_metadata(self, filepath):
		"""
		Extracts the title, artist, and duration from the local file using mutagen.
		Returns (title, artist, duration_str).
		"""
		title = None
		artist = None
		duration_str = None

		try:
			meta = MutagenFile(filepath)
			if meta:
				# Title & artist (commonly in ID3 tags for MP3: 'TIT2', 'TPE1')
				if hasattr(meta, "tags") and meta.tags:
					if "TIT2" in meta.tags:
						title = str(meta.tags["TIT2"])
					if "TPE1" in meta.tags:
						artist = str(meta.tags["TPE1"])

				# Duration (if meta.info is available)
				if hasattr(meta, "info") and meta.info:
					length_seconds = int(meta.info.length)
					duration_str = f"{length_seconds // 60}:{length_seconds % 60:02d}"
		except Exception as e:
			print(f"Error reading metadata from {filepath}: {e}")

		return title, artist, duration_str


def main():
	root = tk.Tk()
	app = SpotifyPlaylistApp(root)
	root.mainloop()

	# When the app closes, ensure pygame mixer is quit
	pygame.mixer.quit()


if __name__ == "__main__":
	main()
