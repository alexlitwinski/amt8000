"""Module for amt-8000 communication."""

import socket
import time
import threading

timeout = 5  # Aumentado para 5 segundos

dst_id = [0x00, 0x00]
our_id = [0x8F, 0xFF]
commands = {
    "auth": [0xF0, 0xF0],
    "status": [0x0B, 0x4A],
    "arm_disarm": [0x40, 0x1e],
    "panic": [0x40, 0x1a]
}

# Global connection pool to prevent multiple connections
_connection_pool = {}
_connection_lock = threading.Lock()

def split_into_octets(n):
    if 0 <= n <= 0xFFFF:
        high_byte = (n >> 8) & 0xFF
        low_byte = n & 0xFF
        return [high_byte, low_byte]
    else:
        raise ValueError("Número fora do intervalo (0 a 65535)")

def calculate_checksum(buffer):
    """Calculate a checksum for a given array of bytes."""
    checksum = 0
    for value in buffer:
        checksum ^= value
    checksum ^= 0xFF
    checksum &= 0xFF
    return checksum


def build_status(data):
    """Build the amt-8000 status from a given array of bytes."""
    length = merge_octets(data[4:6]) - 2
    payload = data[8 : 8 + length]

    if len(payload) != 143:
        raise ValueError(f"Invalid payload length: {len(payload)}, expected 143")

    model = "AMT-8000" if payload[0] == 1 else "Unknown"

    status = {
        "model": model,
        "version": f"{payload[1]}.{payload[2]}.{payload[3]}",
        "status": get_status(payload),
        "zonesFiring": (payload[20] & 0x8) > 0,
        "zonesClosed": (payload[20] & 0x4) > 0,
        "siren": (payload[20] & 0x2) > 0,
        "zones": {},
        "partitions": {}
    }

    # Extract zone information (first 61 zones as requested)
    for i in range(61):
        zone_number = i + 1
        status["zones"][zone_number] = {
            "number": zone_number,
            "enabled": False,
            "open": False,
            "violated": False,
            "anulated": False,  # bypassed
            "tamper": False,
            "lowBattery": False
        }

    # Zones enabled (bytes 12-18, 7 bytes = 56 bits, covers zones 1-56)
    for i, octet in enumerate(payload[12:19]):
        for j in range(8):
            zone_idx = j + i * 8
            if zone_idx < 61:  # Only process first 61 zones
                status["zones"][zone_idx + 1]["enabled"] = (octet & (1 << j)) > 0

    # Zones open (bytes 38-44, 7 bytes = 56 bits)
    for i, octet in enumerate(payload[38:45]):
        for j in range(8):
            zone_idx = j + i * 8
            if zone_idx < 61:  # Only process first 61 zones
                status["zones"][zone_idx + 1]["open"] = (octet & (1 << j)) > 0

    # Zones violated (bytes 46-52, 7 bytes = 56 bits)
    for i, octet in enumerate(payload[46:53]):
        for j in range(8):
            zone_idx = j + i * 8
            if zone_idx < 61:  # Only process first 61 zones
                status["zones"][zone_idx + 1]["violated"] = (octet & (1 << j)) > 0

    # Zones bypassed/anulated (bytes 54-61, 8 bytes = 64 bits)
    for i, octet in enumerate(payload[54:62]):
        for j in range(8):
            zone_idx = j + i * 8
            if zone_idx < 61:  # Only process first 61 zones
                status["zones"][zone_idx + 1]["anulated"] = (octet & (1 << j)) > 0

    # Zone tamper (bytes 89-95, 7 bytes = 56 bits)
    for i, octet in enumerate(payload[89:96]):
        for j in range(8):
            zone_idx = j + i * 8
            if zone_idx < 61:  # Only process first 61 zones
                status["zones"][zone_idx + 1]["tamper"] = (octet & (1 << j)) > 0

    # Zone low battery (bytes 105-111, 7 bytes = 56 bits)
    for i, octet in enumerate(payload[105:112]):
        for j in range(8):
            zone_idx = j + i * 8
            if zone_idx < 61:  # Only process first 61 zones
                status["zones"][zone_idx + 1]["lowBattery"] = (octet & (1 << j)) > 0

    # Extract partition information - CORRECTED: Use byte 22 as starting point
    for i in range(5):  # Process partitions 1-5
        octet = payload[22 + i]  # Start from byte 22 for partition 1
        partition_number = i + 1
        status["partitions"][partition_number] = {
            "number": partition_number,
            "enabled": (octet & 0x80) > 0,
            "armed": (octet & 0x01) > 0,
            "firing": (octet & 0x04) > 0,
            "fired": (octet & 0x08) > 0,
            "stay": (octet & 0x40) > 0
        }

    status["batteryStatus"] = battery_status_for(payload)
    status["tamper"] = (payload[71] & (1 << 0x01)) > 0

    return status


def battery_status_for(resp):
    """Retrieve the battery status."""
    batt = resp[134]
    if batt == 0x01:
        return "dead"
    if batt == 0x02:
        return "low"
    if batt == 0x03:
        return "middle"
    if batt == 0x04:
        return "full"

    return "unknown"


def merge_octets(buf):
    """Merge octets."""
    return buf[0] * 256 + buf[1]


def get_status(payload):
    """Retrieve the current status from a given array of bytes."""
    status = (payload[20] >> 5) & 0x03
    if status == 0x00:
        return "disarmed"
    if status == 0x01:
        return "partial_armed"
    if status == 0x03:
        return "armed_away"
    return "unknown"


class CommunicationError(Exception):
    """Exception raised for communication error."""

    def __init__(self, message="Communication error"):
        """Initialize the error."""
        self.message = message
        super().__init__(self.message)


class AuthError(Exception):
    """Exception raised for authentication error."""

    def __init__(self, message="Authentication Error"):
        """Initialize the error."""
        self.message = message
        super().__init__(self.message)


class Client:
    """Client to communicate with amt-8000."""

    def __init__(self, host, port, device_type=1, software_version=0x10):
        """Initialize the client."""
        self.host = host
        self.port = port
        self.device_type = device_type
        self.software_version = software_version
        self.client = None
        self._authenticated = False
        self._last_activity = 0

    def close(self):
        """Close a connection."""
        if self.client is None:
            return  # Already closed or never connected

        try:
            # Send a small delay before closing to ensure clean shutdown
            time.sleep(0.1)
            self.client.shutdown(socket.SHUT_RDWR)
        except:
            pass  # Ignore errors during shutdown
            
        try:
            self.client.close()
        except:
            pass  # Ignore errors during close
        finally:
            self.client = None
            self._authenticated = False

    def connect(self):
        """Create a new connection."""
        if self.client is not None:
            # Check if we need to reconnect (after 30 seconds of inactivity)
            if time.time() - self._last_activity > 30:
                self.close()
            else:
                # Connection still valid, just return
                return
            
        try:
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.settimeout(timeout)
            
            # Enable TCP keepalive
            self.client.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # Set TCP_NODELAY to disable Nagle's algorithm
            self.client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            self.client.connect((self.host, self.port))
            self._last_activity = time.time()
            
        except Exception as e:
            if self.client:
                try:
                    self.client.close()
                except:
                    pass
                self.client = None
            raise CommunicationError(f"Failed to connect to {self.host}:{self.port} - {e}")

    def auth(self, password):
        """Create a authentication for the current connection."""
        if self.client is None:
            raise CommunicationError("Client not connected. Call Client.connect")

        # If already authenticated and connection is fresh, skip
        if self._authenticated and (time.time() - self._last_activity < 30):
            return True

        pass_array = []
        for char in password:
            if len(password) != 6 or not char.isdigit():
                raise CommunicationError(
                    "Cannot parse password, only 6 integers long are accepted"
                )

            pass_array.append(int(char))

        length = [0x00, 0x0a]
        data = (
            dst_id
            + our_id
            + length
            + commands["auth"]
            + [self.device_type]
            + pass_array
            + [self.software_version]
        )

        cs = calculate_checksum(data)
        payload = bytes(data + [cs])

        try:
            self.client.send(payload)
            self._last_activity = time.time()

            return_data = bytearray()

            # Add small delay to ensure the panel processes the request
            time.sleep(0.05)
            
            data = self.client.recv(1024)
            self._last_activity = time.time()

            return_data.extend(data)

            if len(return_data) < 9:
                raise CommunicationError("Invalid authentication response")

            result = return_data[8:9][0]

            if result == 0:
                self._authenticated = True
                return True
            if result == 1:
                raise AuthError("Invalid password")
            if result == 2:
                raise AuthError("Incorrect software version")
            if result == 3:
                raise AuthError("Alarm panel will call back")
            if result == 4:
                raise AuthError("Waiting for user permission")
            raise CommunicationError("Unknown payload response for authentication")
            
        except socket.error as e:
            self.close()
            raise CommunicationError(f"Socket error during authentication: {e}")

    def status(self):
        """Return the current status."""
        if self.client is None:
            raise CommunicationError("Client not connected. Call Client.connect")

        length = [0x00, 0x02]
        status_data = dst_id + our_id + length + commands["status"]
        cs = calculate_checksum(status_data)
        payload = bytes(status_data + [cs])

        try:
            return_data = bytearray()
            self.client.send(payload)
            self._last_activity = time.time()

            # Add small delay to ensure the panel processes the request
            time.sleep(0.05)

            data = self.client.recv(1024)
            self._last_activity = time.time()
            return_data.extend(data)

            status = build_status(return_data)
            return status
            
        except socket.error as e:
            self.close()
            raise CommunicationError(f"Socket error during status request: {e}")

    def arm_system(self, partition):
        """Arm the system partition (no code required)."""
        if self.client is None:
              raise CommunicationError("Client not connected. Call Client.connect")

        if partition == 0:
          partition = 0xFF

        length = [0x00, 0x04]
        arm_data = dst_id + our_id + length + commands["arm_disarm"] + [ partition, 0x01 ]
        cs = calculate_checksum(arm_data)
        payload = bytes(arm_data + [cs])

        try:
            return_data = bytearray()
            self.client.send(payload)
            self._last_activity = time.time()

            # Add small delay to ensure the panel processes the request
            time.sleep(0.05)

            data = self.client.recv(1024)
            self._last_activity = time.time()
            return_data.extend(data)

            if len(return_data) > 8 and return_data[8] == 0x91:
                return 'armed'

            return 'not_armed'
            
        except socket.error as e:
            self.close()
            raise CommunicationError(f"Socket error during arm command: {e}")

    def disarm_system(self, partition):
        """Disarm the system partition (no code required)."""
        if self.client is None:
              raise CommunicationError("Client not connected. Call Client.connect")

        if partition == 0:
          partition = 0xFF

        length = [0x00, 0x04]
        arm_data = dst_id + our_id + length + commands["arm_disarm"] + [ partition, 0x00 ]
        cs = calculate_checksum(arm_data)
        payload = bytes(arm_data + [cs])

        try:
            return_data = bytearray()
            self.client.send(payload)
            self._last_activity = time.time()

            # Add small delay to ensure the panel processes the request
            time.sleep(0.05)

            data = self.client.recv(1024)
            self._last_activity = time.time()
            return_data.extend(data)

            if len(return_data) > 8 and return_data[8] == 0x91:
                return 'disarmed'

            return 'not_disarmed'
            
        except socket.error as e:
            self.close()
            raise CommunicationError(f"Socket error during disarm command: {e}")

    def panic(self, type):
        """Trigger panic alarm."""
        if self.client is None:
              raise CommunicationError("Client not connected. Call Client.connect")

        length = [0x00, 0x03]
        arm_data = dst_id + our_id + length + commands["panic"] +[ type ]
        cs = calculate_checksum(arm_data)
        payload = bytes(arm_data + [cs])

        try:
            return_data = bytearray()
            self.client.send(payload)
            self._last_activity = time.time()

            # Add small delay to ensure the panel processes the request
            time.sleep(0.05)

            data = self.client.recv(1024)
            self._last_activity = time.time()
            return_data.extend(data)

            if len(return_data) > 7 and return_data[7] == 0xfe:
                return 'triggered'

            return 'not_triggered'
            
        except socket.error as e:
            self.close()
            raise CommunicationError(f"Socket error during panic command: {e}")
