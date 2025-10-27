import os
import zlib
import base64
import hashlib
import time
import json
from collections import defaultdict
from configparser import ConfigParser
import sys
from modules.log import logger

# Directory structure
FIMESH_IN_DIR = 'fimesh/in/'
FIMESH_IN_TEMP_DIR = 'fimesh/in/temp/'
FIMESH_OUT_DIR = 'fimesh/out/'
FIMESH_OUT_SENT_DIR = 'fimesh/out/sent/'
FIMESH_HASH_DIR = 'fimesh/hash/'

class UploadState:
    def __init__(self, session_id, file_path, file_size, device_id):
        self.session_id = session_id
        self.file_path = file_path
        self.file_size = file_size
        self.device_id = device_id
        self.chunks = []
        self.sent_chunks = set()
        self.acked_chunks = set()
        self.window_size = 2
        self.next_chunk_to_send = 0
        self.last_ack_time = time.time()
        self.start_time = time.time()
        self.base_timeout = 180
        self.current_timeout = 180
        self.backoff_factor = 2
        self.max_retries = 5
        self.total_timeout = 1800
        self.max_window_size = 10
        self.manifests = []
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
        self.received_chunks = {}
        self.expected_chunks = set()
        self.window_size = 2
        self.next_expected_chunk = 0
        self.last_packet_time = time.time()
        self.start_time = time.time()
        self.timeout = 300
        self.total_timeout = 1800
        self.max_window_size = 10
        self.manifests = []

class FiMesh:
    def __init__(self, send_message_callback):
        self.send_message = send_message_callback
        self.active_uploads = {}
        self.active_downloads = {}
        self.initialize_fimesh()

    def initialize_fimesh(self):
        os.makedirs(FIMESH_IN_DIR, exist_ok=True)
        os.makedirs(FIMESH_IN_TEMP_DIR, exist_ok=True)
        os.makedirs(FIMESH_OUT_DIR, exist_ok=True)
        os.makedirs(FIMESH_OUT_SENT_DIR, exist_ok=True)
        os.makedirs(FIMESH_HASH_DIR, exist_ok=True)

        config = ConfigParser()
        config.read('config.ini')
        if 'fimesh' in config:
            self.FIMESH_MAX_WINDOW_SIZE = config.getint('fimesh', 'max_window_size', fallback=10)

    def handle_fimesh_packet(self, packet_str, from_node_id, deviceID):
        try:
            parts = packet_str.split(':')
            if len(parts) < 4 or parts[0] != 'fmsh':
                return

            session_id = parts[1]
            packet_type = parts[2]

            if packet_type == 'MAN':
                if len(parts) < 5:
                    return
                man_num_hex = parts[3]
                is_last_flag = parts[4]
                payload = ':'.join(parts[5:])
                self.handle_manifest_packet(session_id, man_num_hex, is_last_flag, payload, from_node_id, deviceID)
            else:
                chunk_num_hex = parts[3]
                payload = ':'.join(parts[4:])
                self.handle_data_packet(session_id, packet_type, chunk_num_hex, payload, from_node_id, deviceID)
        except Exception as e:
            logger.error(f"Error handling FiMesh packet: {e}")

    def handle_manifest_packet(self, session_id, man_num_hex, is_last_flag, payload, from_node_id, deviceID):
        try:
            if not man_num_hex or not man_num_hex.strip():
                logger.error(f"Error: invalid man_num_hex '{man_num_hex}' in manifest packet")
                return

            if not payload or not payload.strip():
                logger.error(f"Error: empty payload in MAN packet")
                return

            man_num = int(man_num_hex, 16)
            decoded_payload = base64.b64decode(payload)
            decompressed = zlib.decompress(decoded_payload)
            manifest_data = decompressed.decode('utf-8')

            if session_id not in self.active_downloads:
                manifest = json.loads(manifest_data)
                file_name = manifest['name']
                file_size = manifest['size']
                self.active_downloads[session_id] = DownloadState(session_id, file_name, file_size, deviceID)

                from webui.db_handler import create_fimesh_transfer, update_fimesh_transfer_status
                try:
                    create_fimesh_transfer(session_id, file_name, file_size, 0, 'download', from_node_id, str(deviceID))
                    update_fimesh_transfer_status(session_id, 'receiving_manifest')
                except Exception as e:
                    logger.error(f"Error creating download transfer record: {e}")

            if session_id in self.active_downloads:
                download = self.active_downloads[session_id]
                download.manifests.append((man_num, manifest_data))

                if is_last_flag == '1':
                    self.process_manifests(download)
        except Exception as e:
            logger.error(f"Error handling manifest packet: {e}")

    def handle_data_packet(self, session_id, packet_type, chunk_num_hex, payload, from_node_id, deviceID):
        try:
            if packet_type == 'DAT':
                if not chunk_num_hex or not chunk_num_hex.strip():
                    logger.error(f"Error: invalid chunk_num_hex '{chunk_num_hex}' in DAT packet")
                    return
                chunk_num = int(chunk_num_hex, 16)

                if not payload or not payload.strip():
                    logger.error(f"Error: empty payload in DAT packet")
                    return

                if session_id in self.active_downloads:
                    download = self.active_downloads[session_id]
                    decoded_payload = base64.b64decode(payload)
                    decompressed = zlib.decompress(decoded_payload)
                    download.received_chunks[chunk_num] = decompressed
                    download.last_packet_time = time.time()
                    time.sleep(0.1)
                    self.send_ack_packet(session_id, chunk_num, deviceID, from_node_id)
            elif packet_type == 'ACK':
                if not chunk_num_hex or not chunk_num_hex.strip():
                    logger.error(f"Error: invalid chunk_num_hex '{chunk_num_hex}' in ACK packet")
                    return
                chunk_num = int(chunk_num_hex, 16)

                if session_id in self.active_uploads:
                    upload = self.active_uploads[session_id]
                    upload.acked_chunks.add(chunk_num)
                    upload.last_ack_time = time.time()
                    upload.window_size = min(upload.window_size + 1, upload.max_window_size)
                    from webui.db_handler import update_fimesh_transfer_status
                    try:
                        progress = len(upload.acked_chunks) / len(upload.chunks) * 100 if upload.chunks else 0
                        update_fimesh_transfer_status(session_id, 'transferring', progress=int(progress))
                    except Exception as e:
                        logger.error(f"Error updating transfer progress: {e}")
            elif packet_type == 'PING':
                self.send_pong_packet(session_id, from_node_id)
            elif packet_type == 'PONG':
                if session_id in self.active_uploads:
                    upload = self.active_uploads[session_id]
                    upload.pong_received = True
                    logger.info(f"Node {upload.device_id} is online, starting file transfer")
        except Exception as e:
            logger.error(f"Error handling data packet: {e}")

    def process_manifests(self, download):
        full_manifest_str = ''
        for _, data in sorted(download.manifests):
            full_manifest_str += data

        manifest = json.loads(full_manifest_str)
        download.chunk_hashes = {int(k): v for k, v in manifest['chunks'].items()}
        download.expected_chunks = set(download.chunk_hashes.keys())

    def send_ack_packet(self, session_id, chunk_num, deviceID, target_node_id):
        packet = f"fmsh:{session_id}:ACK:{chunk_num:04x}:ACK"
        self.send_message(packet, 0, target_node_id, deviceID)

    def check_for_outgoing_files(self):
        for file_name in os.listdir(FIMESH_OUT_DIR):
            file_path = os.path.join(FIMESH_OUT_DIR, file_name)
            if os.path.isfile(file_path):
                if '___' in file_name:
                    parts = file_name.rsplit('___', 1)
                    if len(parts) == 2:
                        base_name = parts[0]
                        node_id = parts[1].split('.')[0]
                        if node_id == 'failed':
                            continue
                        session_id = self.generate_session_id()
                        self.start_upload(file_path, session_id, node_id)
        return []

    def start_upload(self, file_path, session_id, device_id):
        with open(file_path, 'rb') as f:
            file_data = f.read()

        file_size = len(file_data)
        compressed = zlib.compress(file_data)
        chunks = [compressed[i:i+140] for i in range(0, len(compressed), 140)]

        device_id = int(device_id, 16)
        upload = UploadState(session_id, file_path, file_size, device_id)
        upload.chunks = list(enumerate(chunks))
        self.active_uploads[session_id] = upload

        from webui.db_handler import create_fimesh_transfer, update_fimesh_transfer_status
        try:
            file_name = os.path.basename(file_path)
            create_fimesh_transfer(session_id, file_name, file_size, len(chunks), 'upload', 'web', device_id)
            update_fimesh_transfer_status(session_id, 'connecting')
        except Exception as e:
            logger.error(f"Error creating transfer record: {e}")

        self.send_ping_packet(session_id, device_id)

    def send_ping_packet(self, session_id, target_node_id):
        packet = f"fmsh:{session_id}:PING:0000:PING"
        self.send_message(packet, 0, target_node_id, 1)

    def send_pong_packet(self, session_id, target_node_id):
        packet = f"fmsh:{session_id}:PONG:0000:PONG"
        self.send_message(packet, 0, target_node_id, 1)

    def send_manifests(self, upload):
        file_name = os.path.basename(upload.file_path)

        chunk_hashes = {}
        for chunk_num, chunk in upload.chunks:
            chunk_hashes[chunk_num] = hashlib.md5(chunk).hexdigest()

        manifest = {
            'name': file_name,
            'size': upload.file_size,
            'chunks': chunk_hashes
        }
        manifest_data = json.dumps(manifest)

        compressed = zlib.compress(manifest_data.encode('utf-8'))
        encoded = base64.b64encode(compressed).decode('utf-8')

        man_packets = [encoded[i:i+140] for i in range(0, len(encoded), 140)]
        for i, packet in enumerate(man_packets):
            is_last = '1' if i == len(man_packets) - 1 else '0'
            man_packet = f"fmsh:{upload.session_id}:MAN:{i:04x}:{is_last}:{packet}"
            self.send_message(man_packet, 0, upload.device_id, 1)

    def periodic_fimesh_task(self):
        current_time = time.time()

        for session_id, upload in list(self.active_uploads.items()):
            if upload.failed:
                continue
            if current_time < upload.pause_until:
                continue

            if not upload.pong_received:
                if current_time - upload.last_ack_time > 60:
                    logger.warning(f"Node {upload.device_id} did not respond to ping, aborting transfer")
                    self.fail_upload(upload)
                    del self.active_uploads[session_id]
                    continue
                else:
                    continue

            if not hasattr(upload, 'manifests_sent'):
                from webui.db_handler import update_fimesh_transfer_status
                try:
                    update_fimesh_transfer_status(session_id, 'sending_manifest')
                except Exception as e:
                    logger.error(f"Error updating upload status to sending_manifest: {e}")
                self.send_manifests(upload)
                upload.manifests_sent = True
                continue

            if current_time - upload.start_time > upload.total_timeout:
                logger.warning(f"Upload {session_id} timed out after {upload.total_timeout} seconds")
                self.fail_upload(upload)
                del self.active_uploads[session_id]
                continue

            if current_time - upload.last_ack_time > upload.current_timeout:
                upload.retry_count += 1
                if upload.retry_count <= upload.max_retries:
                    from webui.db_handler import update_fimesh_transfer_status
                    try:
                        update_fimesh_transfer_status(session_id, 'retrying')
                    except Exception as e:
                        logger.error(f"Error updating upload status to retrying: {e}")
                    upload.current_timeout = min(upload.current_timeout * upload.backoff_factor, 600)
                    logger.info(f"Retry {upload.retry_count} for upload {session_id}, new timeout: {upload.current_timeout}s")
                    self.retransmit_chunks(upload)
                    upload.window_size = max(1, upload.window_size // 2)
                    upload.last_ack_time = current_time
                else:
                    logger.warning(f"Upload {session_id} failed after {upload.max_retries} retries")
                    self.fail_upload(upload)
                    del self.active_uploads[session_id]
                    continue
            else:
                self.send_next_chunks(upload)

        for session_id, download in list(self.active_downloads.items()):
            if current_time - download.start_time > download.total_timeout:
                logger.warning(f"Download {session_id} timed out after {download.total_timeout} seconds")
                del self.active_downloads[session_id]
                continue

            if current_time - download.last_packet_time > download.timeout:
                missing_chunks = download.expected_chunks - set(download.received_chunks.keys())
                if missing_chunks:
                    self.request_missing_chunks(session_id, missing_chunks, download.device_id)
                else:
                    logger.warning(f"Download {session_id} timed out waiting for packets")
                    del self.active_downloads[session_id]
            elif len(download.received_chunks) == len(download.expected_chunks) and download.expected_chunks:
                self.assemble_file(download)
                del self.active_downloads[session_id]

    def request_missing_chunks(self, session_id, missing_chunks, target_node_id):
        chunk_list = ",".join([f"{c:04x}" for c in missing_chunks])
        packet = f"fmsh:{session_id}:REQ:{chunk_list}"
        self.send_message(packet, 0, target_node_id, 1)


    def retransmit_chunks(self, upload):
        for chunk_num in range(upload.next_chunk_to_send - upload.window_size, upload.next_chunk_to_send):
            if chunk_num not in upload.acked_chunks and chunk_num < len(upload.chunks):
                self.send_chunk(upload, chunk_num)

    def send_next_chunks(self, upload):
        while upload.next_chunk_to_send < len(upload.chunks) and (upload.next_chunk_to_send - len(upload.acked_chunks)) < upload.window_size:
            self.send_chunk(upload, upload.next_chunk_to_send)
            upload.next_chunk_to_send += 1
            time.sleep(0.1)

    def send_chunk(self, upload, chunk_num):
        if chunk_num < len(upload.chunks):
            chunk_data = upload.chunks[chunk_num][1]
            encoded = base64.b64encode(chunk_data).decode('utf-8')
            packet = f"fmsh:{upload.session_id}:DAT:{chunk_num:04x}:{encoded}"
            self.send_message(packet, 0, upload.device_id, 1)

    def assemble_file(self, download):
        file_data = b''
        for chunk_num in sorted(download.received_chunks.keys()):
            chunk = download.received_chunks[chunk_num]
            if chunk_num in download.chunk_hashes:
                expected_hash = download.chunk_hashes[chunk_num]
                actual_hash = hashlib.md5(chunk).hexdigest()
                if actual_hash != expected_hash:
                    logger.warning(f"Hash mismatch for chunk {chunk_num}")
                    # Request missing chunk
                    self.request_missing_chunks(download.session_id, [chunk_num], download.device_id)
                    return
            file_data += chunk

        decompressed = zlib.decompress(file_data)

        temp_path = os.path.join(FIMESH_IN_TEMP_DIR, download.file_name)
        with open(temp_path, 'wb') as f:
            f.write(decompressed)

        final_path = os.path.join(FIMESH_IN_DIR, download.file_name)
        os.rename(temp_path, final_path)

        from webui.db_handler import update_fimesh_transfer_status
        try:
            update_fimesh_transfer_status(download.session_id, 'completed')
        except Exception as e:
            logger.error(f"Error updating transfer status to completed: {e}")

    def fail_upload(self, upload):
        if os.path.exists(upload.file_path):
            file_name = os.path.basename(upload.file_path)
            failed_name = file_name + '___failed'
            failed_path = os.path.join(FIMESH_OUT_DIR, failed_name)
            os.rename(upload.file_path, failed_path)
        else:
            logger.warning(f"Warning: File {upload.file_path} not found during fail_upload")
        upload.failed = True

        from webui.db_handler import update_fimesh_transfer_status
        try:
            update_fimesh_transfer_status(upload.session_id, 'failed')
        except Exception as e:
            logger.error(f"Error updating transfer status to failed: {e}")

    def generate_session_id(self):
        return hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
