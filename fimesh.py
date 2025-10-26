import os
import zlib
import base64
import hashlib
import time
import threading
from collections import defaultdict
from configparser import ConfigParser

# Directory structure
FIMESH_IN_DIR = 'fimesh/in/'
FIMESH_IN_TEMP_DIR = 'fimesh/in/temp/'
FIMESH_OUT_DIR = 'fimesh/out/'
FIMESH_OUT_SENT_DIR = 'fimesh/out/sent/'
FIMESH_HASH_DIR = 'fimesh/hash/'

# Packet format: fmsh:<session_id>:<type>:<chunk_num_hex>:<payload>
# MAN extended: fmsh:<session_id>:MAN:<man_num_hex>:<is_last_flag>:<payload>

class UploadState:
    def __init__(self, session_id, file_path, file_size, device_id):
        self.session_id = session_id
        self.file_path = file_path
        self.file_size = file_size
        self.device_id = device_id
        self.chunks = []  # List of (chunk_num, chunk_data)
        self.sent_chunks = set()
        self.acked_chunks = set()
        self.window_size = 2
        self.next_chunk_to_send = 0
        self.last_ack_time = time.time()
        self.start_time = time.time()  # Track total transfer time
        self.base_timeout = 180  # 3 minutes initial timeout for mesh networks
        self.current_timeout = 180
        self.backoff_factor = 2  # Exponential backoff multiplier
        self.max_retries = 5  # Reduced retries with longer intervals
        self.total_timeout = 1800  # 30 minutes total transfer timeout
        self.max_window_size = 10  # from config
        self.manifests = []  # For large files, chain of manifests
        self.retry_count = 0
        self.pause_until = 0
        self.failed = False
        self.pong_received = False

class DownloadState:
    def __init__(self, session_id, file_name, file_size, device_id):
        self.session_id = session_id
        self.file_name = file_name
        self.file_size = file_size
        self.device_id = device_id
        self.received_chunks = {}  # chunk_num -> chunk_data
        self.expected_chunks = set()
        self.window_size = 2
        self.next_expected_chunk = 0
        self.last_packet_time = time.time()
        self.start_time = time.time()  # Track total transfer time
        self.timeout = 300  # 5 minutes timeout for downloads in mesh networks
        self.total_timeout = 1800  # 30 minutes total transfer timeout
        self.max_window_size = 10  # from config
        self.manifests = []  # Received manifests

# Global dictionaries
active_uploads = {}  # session_id -> UploadState
active_downloads = {}  # session_id -> DownloadState

def initialize_fimesh():
    # Ensure directories exist
    os.makedirs(FIMESH_IN_DIR, exist_ok=True)
    os.makedirs(FIMESH_IN_TEMP_DIR, exist_ok=True)
    os.makedirs(FIMESH_OUT_DIR, exist_ok=True)
    os.makedirs(FIMESH_OUT_SENT_DIR, exist_ok=True)
    os.makedirs(FIMESH_HASH_DIR, exist_ok=True)

    # Load config
    config = ConfigParser()
    config.read('config.ini')
    if 'fimesh' in config:
        global FIMESH_MAX_WINDOW_SIZE
        FIMESH_MAX_WINDOW_SIZE = config.getint('fimesh', 'max_window_size', fallback=10)

def handle_fimesh_packet(packet_str, from_node_id, deviceID):
    try:
        parts = packet_str.split(':')
        if len(parts) < 4 or parts[0] != 'fmsh':
            return  # Invalid packet

        session_id = parts[1]
        packet_type = parts[2]

        if packet_type == 'MAN':
            # Manifest packet: fmsh:<session_id>:MAN:<man_num_hex>:<is_last_flag>:<payload>
            if len(parts) < 5:
                return
            man_num_hex = parts[3]
            is_last_flag = parts[4]
            payload = ':'.join(parts[5:])
            handle_manifest_packet(session_id, man_num_hex, is_last_flag, payload, from_node_id, deviceID)
        else:
            # Data packet: fmsh:<session_id>:<type>:<chunk_num_hex>:<payload>
            chunk_num_hex = parts[3]
            payload = ':'.join(parts[4:])
            handle_data_packet(session_id, packet_type, chunk_num_hex, payload, from_node_id, deviceID)
    except Exception as e:
        print(f"Error handling FiMesh packet: {e}")

def handle_manifest_packet(session_id, man_num_hex, is_last_flag, payload, from_node_id, deviceID):
    try:
        man_num = int(man_num_hex, 16)
        decoded_payload = base64.b64decode(payload)
        decompressed = zlib.decompress(decoded_payload)
        manifest_data = decompressed.decode('utf-8')

        if session_id not in active_downloads:
            # New download
            lines = manifest_data.split('\n')
            if len(lines) >= 2:
                file_name = lines[0]
                file_size = int(lines[1])
                active_downloads[session_id] = DownloadState(session_id, file_name, file_size, deviceID)

                # Create transfer record in database
                from webui.db_handler import create_fimesh_transfer
                try:
                    create_fimesh_transfer(session_id, file_name, file_size, 0, 'download', from_node_id, str(deviceID))
                except Exception as e:
                    print(f"Error creating download transfer record: {e}")

        if session_id in active_downloads:
            download = active_downloads[session_id]
            download.manifests.append((man_num, manifest_data))

            if is_last_flag == '1':
                # All manifests received, process
                process_manifests(download)
    except Exception as e:
        print(f"Error handling manifest packet: {e}")

def handle_data_packet(session_id, packet_type, chunk_num_hex, payload, from_node_id, deviceID):
    try:
        chunk_num = int(chunk_num_hex, 16)

        if packet_type == 'DAT':
            # Data chunk
            if session_id in active_downloads:
                download = active_downloads[session_id]
                decoded_payload = base64.b64decode(payload)
                decompressed = zlib.decompress(decoded_payload)
                download.received_chunks[chunk_num] = decompressed
                download.last_packet_time = time.time()
                # Send ACK immediately when MAN packet is received
                send_ack_packet(session_id, chunk_num, deviceID, from_node_id)
        elif packet_type == 'ACK':
            # Acknowledgement
            if session_id in active_uploads:
                upload = active_uploads[session_id]
                upload.acked_chunks.add(chunk_num)
                upload.last_ack_time = time.time()
                # AIMD: Additive increase
                upload.window_size = min(upload.window_size + 1, upload.max_window_size)
                # Update progress in database
                from webui.db_handler import update_fimesh_transfer_status
                try:
                    progress = len(upload.acked_chunks) / len(upload.chunks) * 100 if upload.chunks else 0
                    update_fimesh_transfer_status(session_id, progress=int(progress))
                except Exception as e:
                    print(f"Error updating transfer progress: {e}")
        elif packet_type == 'PING':
            # Node discovery request - respond with pong
            send_pong_packet(session_id, from_node_id)
        elif packet_type == 'PONG':
            # Node discovery response
            if session_id in active_uploads:
                upload = active_uploads[session_id]
                upload.pong_received = True
                print(f"Node {upload.device_id} is online, starting file transfer")
    except Exception as e:
        print(f"Error handling data packet: {e}")

def process_manifests(download):
    # Combine manifests and parse chunk list
    full_manifest = ''
    for _, data in sorted(download.manifests):
        full_manifest += data

    lines = full_manifest.split('\n')
    file_name = lines[0]
    file_size = int(lines[1])
    chunk_hashes = {}
    for line in lines[2:]:
        if line:
            parts = line.split(':')
            chunk_num = int(parts[0], 16)
            chunk_hash = parts[1]
            chunk_hashes[chunk_num] = chunk_hash
            download.expected_chunks.add(chunk_num)

    download.chunk_hashes = chunk_hashes

def send_ack_packet(session_id, chunk_num, deviceID, target_node_id):
    # Send ACK packet as plain text message through normal message system
    packet = f"fmsh:{session_id}:ACK:{chunk_num:04x}:ACK"
    from mesh_bot import send_message
    send_message(packet, 0, target_node_id, deviceID)  # Send to specific target node

def check_for_outgoing_files():
    for file_name in os.listdir(FIMESH_OUT_DIR):
        file_path = os.path.join(FIMESH_OUT_DIR, file_name)
        if os.path.isfile(file_path):
            # Parse filename for node ID: filename___nodeid.ext
            if '___' in file_name:
                parts = file_name.rsplit('___', 1)
                if len(parts) == 2:
                    base_name = parts[0]
                    node_id = parts[1].split('.')[0]  # Remove extension if present
                    # Skip files marked as failed
                    if node_id == 'failed':
                        continue
                    session_id = generate_session_id()
                    start_upload(file_path, session_id, node_id)
            # If no node specified, skip
    return []

def start_upload(file_path, session_id, device_id):
    with open(file_path, 'rb') as f:
        file_data = f.read()

    file_size = len(file_data)
    compressed = zlib.compress(file_data)
    chunks = [compressed[i:i+140] for i in range(0, len(compressed), 140)]  # Chunk size

    # Convert hex node ID to numeric
    device_id = int(device_id, 16)
    upload = UploadState(session_id, file_path, file_size, device_id)
    upload.chunks = list(enumerate(chunks))
    active_uploads[session_id] = upload

    # Create transfer record in database
    from webui.db_handler import create_fimesh_transfer
    try:
        file_name = os.path.basename(file_path)
        create_fimesh_transfer(session_id, file_name, file_size, len(chunks), 'upload', 'web', device_id)
    except Exception as e:
        print(f"Error creating transfer record: {e}")

    # Node discovery: Send ping before starting transfer
    send_ping_packet(session_id, device_id)

def send_ping_packet(session_id, target_node_id):
    # Send ping packet to check if node is online
    packet = f"fmsh:{session_id}:PING::PING"
    from mesh_bot import send_message
    send_message(packet, 0, target_node_id, 1)  # Send to target node on device 1

def send_pong_packet(session_id, target_node_id):
    # Send pong response
    packet = f"fmsh:{session_id}:PONG::PONG"
    from mesh_bot import send_message
    send_message(packet, 0, target_node_id, 1)  # Send to target node on device 1

def send_manifests(upload):
    from mesh_bot import send_message
    file_name = os.path.basename(upload.file_path)
    manifest_data = f"{file_name}\n{upload.file_size}\n"
    for chunk_num, chunk in upload.chunks:
        chunk_hash = hashlib.md5(chunk).hexdigest()
        manifest_data += f"{chunk_num:04x}:{chunk_hash}\n"

    compressed = zlib.compress(manifest_data.encode('utf-8'))
    encoded = base64.b64encode(compressed).decode('utf-8')

    # Split into manifest packets if large
    man_packets = [encoded[i:i+140] for i in range(0, len(encoded), 140)]
    for i, packet in enumerate(man_packets):
        is_last = '1' if i == len(man_packets) - 1 else '0'
        # Send MAN packet as plain text message to target node
        man_packet = f"fmsh:{upload.session_id}:MAN:{i:04x}:{is_last}:{packet}"
        send_message(man_packet, 0, upload.device_id, 1)  # Send to target node on device 1

def periodic_fimesh_task():
    current_time = time.time()

    # Handle uploads: send chunks, handle timeouts and retries
    for session_id, upload in list(active_uploads.items()):
        if upload.failed:
            continue  # Skip failed uploads
        if current_time < upload.pause_until:
            continue  # Paused

        # Check if pong received for node discovery
        if not upload.pong_received:
            # Wait for pong before starting transfer
            if current_time - upload.last_ack_time > 60:  # 1 minute timeout for pong in mesh networks
                print(f"Node {upload.device_id} did not respond to ping, aborting transfer")
                fail_upload(upload)
                del active_uploads[session_id]
                continue
            else:
                continue  # Wait for pong

        # Start sending manifests after pong received
        if not hasattr(upload, 'manifests_sent'):
            send_manifests(upload)
            upload.manifests_sent = True
            continue

        # Check total transfer timeout
        if current_time - upload.start_time > upload.total_timeout:
            print(f"Upload {session_id} timed out after {upload.total_timeout} seconds")
            fail_upload(upload)
            del active_uploads[session_id]
            continue

        if current_time - upload.last_ack_time > upload.current_timeout:
            upload.retry_count += 1
            if upload.retry_count <= upload.max_retries:
                # Exponential backoff: increase timeout
                upload.current_timeout = min(upload.current_timeout * upload.backoff_factor, 600)  # Max 10 minutes
                print(f"Retry {upload.retry_count} for upload {session_id}, new timeout: {upload.current_timeout}s")
                # Retransmit
                retransmit_chunks(upload)
                upload.window_size = max(1, upload.window_size // 2)  # AIMD: Multiplicative decrease
                upload.last_ack_time = current_time  # Reset timer for new timeout
            else:
                print(f"Upload {session_id} failed after {upload.max_retries} retries")
                fail_upload(upload)
                del active_uploads[session_id]
                continue
        else:
            # Send next chunks within window
            send_next_chunks(upload)

    # Handle downloads: check for completion, timeouts
    for session_id, download in list(active_downloads.items()):
        # Check total transfer timeout
        if current_time - download.start_time > download.total_timeout:
            print(f"Download {session_id} timed out after {download.total_timeout} seconds")
            del active_downloads[session_id]
            continue

        if current_time - download.last_packet_time > download.timeout:
            # Timeout, abort download
            print(f"Download {session_id} timed out waiting for packets")
            del active_downloads[session_id]
        elif len(download.received_chunks) == len(download.expected_chunks):
            # All chunks received, assemble file
            assemble_file(download)
            del active_downloads[session_id]

    return []

def retransmit_chunks(upload):
    # Retransmit unacked chunks
    for chunk_num in range(upload.next_chunk_to_send - upload.window_size, upload.next_chunk_to_send):
        if chunk_num not in upload.acked_chunks and chunk_num < len(upload.chunks):
            send_chunk(upload, chunk_num)

def send_next_chunks(upload):
    while upload.next_chunk_to_send < len(upload.chunks) and (upload.next_chunk_to_send - len(upload.acked_chunks)) < upload.window_size:
        send_chunk(upload, upload.next_chunk_to_send)
        upload.next_chunk_to_send += 1

def send_chunk(upload, chunk_num):
    from mesh_bot import send_message
    if chunk_num < len(upload.chunks):
        chunk_data = upload.chunks[chunk_num][1]
        encoded = base64.b64encode(chunk_data).decode('utf-8')
        # Send DAT packet as plain text message to target node
        packet = f"fmsh:{upload.session_id}:DAT:{chunk_num:04x}:{encoded}"
        send_message(packet, 0, upload.device_id, 1)  # Send to target node on device 1

def assemble_file(download):
    # Sort chunks and verify hashes
    sorted_chunks = sorted(download.received_chunks.items())
    file_data = b''
    for chunk_num, chunk in sorted_chunks:
        if chunk_num in download.chunk_hashes:
            expected_hash = download.chunk_hashes[chunk_num]
            actual_hash = hashlib.md5(chunk).hexdigest()
            if actual_hash != expected_hash:
                print(f"Hash mismatch for chunk {chunk_num}")
                return
        file_data += chunk

    # Decompress
    decompressed = zlib.decompress(file_data)

    # Save to temp, then move to in/
    temp_path = os.path.join(FIMESH_IN_TEMP_DIR, download.file_name)
    with open(temp_path, 'wb') as f:
        f.write(decompressed)

    final_path = os.path.join(FIMESH_IN_DIR, download.file_name)
    os.rename(temp_path, final_path)

    # Update transfer status to completed
    from webui.db_handler import update_fimesh_transfer_status
    try:
        update_fimesh_transfer_status(download.session_id, 'completed')
    except Exception as e:
        print(f"Error updating transfer status to completed: {e}")

def fail_upload(upload):
    # Rename file to ___failed
    file_name = os.path.basename(upload.file_path)
    failed_name = file_name + '___failed'
    failed_path = os.path.join(FIMESH_OUT_DIR, failed_name)
    os.rename(upload.file_path, failed_path)
    upload.failed = True

    # Update transfer status to failed
    from webui.db_handler import update_fimesh_transfer_status
    try:
        update_fimesh_transfer_status(upload.session_id, 'failed')
    except Exception as e:
        print(f"Error updating transfer status to failed: {e}")

def generate_session_id():
    return hashlib.md5(str(time.time()).encode()).hexdigest()[:8]