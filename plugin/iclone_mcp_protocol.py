import json


MAX_FRAME_SIZE = 1024 * 1024


class FrameTooLarge(ValueError):
    pass


class InvalidRequest(ValueError):
    pass


def decode_request(frame):
    if not frame:
        raise InvalidRequest("Request must not be empty.")
    try:
        request = json.loads(frame.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise InvalidRequest("Request must be valid UTF-8 JSON.")
    if not isinstance(request, dict):
        raise InvalidRequest("Request must be a JSON object.")

    unexpected = sorted(set(request) - {"type", "params"})
    if unexpected:
        raise InvalidRequest(
            "Unexpected request field(s): {0}.".format(", ".join(unexpected))
        )
    return request


class NdjsonBuffer(object):
    def __init__(self, max_frame_size=MAX_FRAME_SIZE):
        self._buffer = bytearray()
        self._max_frame_size = max_frame_size

    def feed(self, data):
        self._buffer.extend(data)
        frames = []

        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                if len(self._buffer) > self._max_frame_size:
                    self._buffer.clear()
                    raise FrameTooLarge("Request exceeds the 1 MiB limit.")
                return frames

            if newline > self._max_frame_size:
                self._buffer.clear()
                raise FrameTooLarge("Request exceeds the 1 MiB limit.")

            frame = bytes(self._buffer[:newline])
            del self._buffer[:newline + 1]
            if frame.endswith(b"\r"):
                frame = frame[:-1]
            frames.append(frame)
