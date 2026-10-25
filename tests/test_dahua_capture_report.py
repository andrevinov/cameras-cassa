from __future__ import annotations

import importlib.machinery
import importlib.util
import ipaddress
import struct
import tempfile
import unittest
from pathlib import Path


REPORT = Path(__file__).resolve().parents[1] / "tools/dahua-capture-report"
loader = importlib.machinery.SourceFileLoader("dahua_capture_report", str(REPORT))
spec = importlib.util.spec_from_loader(loader.name, loader)
report = importlib.util.module_from_spec(spec)
loader.exec_module(report)


def frame(source: str, destination: str, source_port: int, dest_port: int, payload: bytes, flags=0x18):
    tcp = struct.pack("!HHIIHHHH", source_port, dest_port, 0, 0, 0x5000 | flags, 0, 0, 0)
    ip = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        20 + len(tcp) + len(payload),
        0,
        0,
        64,
        6,
        0,
        ipaddress.IPv4Address(source).packed,
        ipaddress.IPv4Address(destination).packed,
    )
    return b"\x00" * 12 + b"\x08\x00" + ip + tcp + payload


def udp_frame(source: str, destination: str, source_port: int, dest_port: int, payload: bytes):
    udp = struct.pack("!HHHH", source_port, dest_port, 8 + len(payload), 0)
    ip = struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0, 20 + len(udp) + len(payload), 0, 0, 64, 17, 0,
        ipaddress.IPv4Address(source).packed,
        ipaddress.IPv4Address(destination).packed,
    )
    return b"\x00" * 12 + b"\x08\x00" + ip + udp + payload


def audio_frame():
    extension = bytes((0x83, 1, 0x0E, 2)) + bytes(44)
    return (
        b"DHAV" + bytes((0xF0, 0, 0, 0)) + bytes(4)
        + struct.pack("<I", 400) + bytes(4) + bytes(2)
        + bytes((48, 0)) + extension + bytes(320) + b"dhav" + bytes(4)
    )


def write_pcap(path: Path, frames: list[bytes]):
    with path.open("wb") as output:
        output.write(b"\xd4\xc3\xb2\xa1" + struct.pack("<HHiIII", 2, 4, 0, 0, 65535, 1))
        for packet in frames:
            output.write(struct.pack("<IIII", 0, 0, len(packet), len(packet)))
            output.write(packet)


class CaptureReportTests(unittest.TestCase):
    def test_counts_only_camera_port_and_directions(self):
        camera = ipaddress.IPv4Address("192.0.2.9")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.pcap"
            write_pcap(
                path,
                [
                    frame("192.0.2.5", "192.0.2.9", 40000, 37777, b"", flags=0x02),
                    frame("192.0.2.5", "192.0.2.9", 40000, 37777, b"DHAVaudio"),
                    frame("198.51.100.7", "192.0.2.5", 12345, 40000, b"reply"),
                    frame("192.0.2.5", "192.0.2.9", 40001, 554, b"ignored"),
                ],
            )
            counts = report.summarize(path, camera)
        self.assertEqual(counts["packets_in_file"], 4)
        self.assertEqual(counts["connection_attempts"], 1)
        self.assertEqual(counts["distinct_client_connections"], 1)
        self.assertEqual(counts["payload_bytes_to_camera"], 9)
        self.assertEqual(counts["payload_bytes_from_camera"], 5)
        self.assertEqual(counts["dhav_markers_to_camera"], 1)

    def test_rejects_truncated_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.pcap"
            write_pcap(path, [frame("192.0.2.5", "192.0.2.9", 40000, 37777, b"x")])
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaises(report.CaptureError):
                report.summarize(path, ipaddress.IPv4Address("192.0.2.9"))

    def test_detects_udp_ptcp_and_dhav_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "talk.pcap"
            write_pcap(path, [
                udp_frame("192.0.2.5", "192.0.2.9", 40000, 17595, b"PTCP" + bytes(38) + audio_frame()),
                udp_frame("192.0.2.5", "192.0.2.9", 40000, 17595, b"PTCP" + bytes(20)),
            ])
            counts = report.summarize(path, ipaddress.IPv4Address("192.0.2.9"))
        self.assertEqual(counts["udp_packets_to_camera"], 2)
        self.assertEqual(counts["udp_ptcp_packets_to_camera"], 2)
        self.assertEqual(counts["udp_destination_ports"], {17595: 2})
        self.assertEqual(counts["dhav_audio_formats_to_camera"], {"PCMA/8000/1": 1})


if __name__ == "__main__":
    unittest.main()
