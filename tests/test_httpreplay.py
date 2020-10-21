# Copyright (C) 2015-2019 Jurriaan Bremer <jbr@cuckoo.sh>
# This file is part of HTTPReplay - http://jbremer.org/httpreplay/
# See the file 'LICENSE' for copying permission.

import dpkt
import hashlib
import io
import logging
import mock
import os
import pytest
import tempfile

from httpreplay.cobweb import parse_body
from httpreplay.cut import (
    dummy_handler, http_handler, forward_handler, https_handler
)
from httpreplay.main import do_pcap2mitm
from httpreplay.reader import PcapReader
from httpreplay.smegma import TCPPacketStreamer
from httpreplay.utils import pcap2mitm

log = logging.getLogger(__name__)


class PcapTest(object):
    handlers = {
        80: http_handler,
    }
    pcapfile = ""
    expected_output = None

    use_exceptions = True
    tlsinfo = False

    @staticmethod
    def format(self, s, ts, p, sent, recv):
        raise NotImplementedError

    def test_pcap(self):
        with open(os.path.join("tests", "pcaps", self.pcapfile), "rb") as f:
            reader = PcapReader(f)
            reader.tcp = TCPPacketStreamer(reader, self.handlers)
            reader.tlsinfo = self.tlsinfo

            reader.raise_exceptions = self.use_exceptions

            output = [
                self.format(*stream) for stream in reader.process()
            ]

        assert self.expected_output == output


class TestSimple(PcapTest):
    """"Tests TCP reassembly and basic HTTP extraction"""
    pcapfile = "test.pcap"

    def format(self, s, ts, p, sent, recv):
        return ts, sent.uri, len(recv.body or "")

    expected_output = [
        (1278472581.261381, "/sd/facebook_icon.png", 3462),
        (1278472581.261490, "/sd/twitter_icon.png", 0),
        (1278472581.071695, "/sd/print.css?T_2_5_0_300", 0),
        (1278472581.584223, "/sd/cs_sic_controls_new.png?T_2_5_0_299", 0),
        (1278472580.653563, "/", 113331),
        (1278472581.577512, "/sd/cs_i2_gradients.png?T_2_5_0_299", 0),
        (1278472581.071626, "/sd/idlecore-tidied.css?T_2_5_0_300", 0),
        (1278472581.580736, "/sd/logo2.png", 0),
    ]


class TestNoResponse(PcapTest):
    """Extracts HTTP requests which have no response"""
    pcapfile = "2014-08-13-element1208_spm2.exe-sandbox-analysis.pcap"

    def format(self, s, ts, p, sent, recv):
        return sent.method, sent.uri, recv.raw

    expected_output = [
        ("POST", "/cmd.php", ""),
        ("GET", "/cmd.php", ""),
    ]


class TestEmptyRequest(PcapTest):
    """Handle client disconnect and empty request"""
    pcapfile = "2014-08-13-element1208_spm2.exe-sandbox-analysis.pcap"

    handlers = {
        25: forward_handler,
        80: dummy_handler,
    }

    def format(self, s, ts, p, sent, recv):
        return s[0], sent, recv

    expected_output = [
        ("172.16.165.133", "", "220 mx.google.com ESMTP v9si4604526wah.36\r\n"),
        ("172.16.165.133", "", "220 mx.google.com ESMTP v9si4604526wah.36\r\n"),
    ]


class TestCutoff(PcapTest):
    """Extracts HTTP response cut off during transmission"""
    pcapfile = "2014-12-13-download.pcap"

    def format(self, s, ts, p, sent, recv):
        return sent.uri, int(recv.headers["content-length"]), len(recv.body)

    expected_output = [
        ("/zp/zp-core/zp-extensions/tiny_mce/plugins/ajaxfilemanager/inc/main.php", 451729, 35040),
    ]


# FIXME: This fails for some reason?
class TestRetransmission(PcapTest):
    """Handles TCP Retransmission logic"""

    pcapfile = "2015-01-02-post-infection.pcap"

    handlers = {
        80: http_handler,
        48754: dummy_handler,
    }

    @pytest.mark.xfail()
    def test_pcap(self):
        TestRetransmission.test_pcap(self)

    def format(self, s, ts, p, sent, recv):
        return s, sent.__class__.__name__

    expected_output = [
        (("192.168.138.163", 49199, "219.70.113.58", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49202, "74.78.180.226", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49204, "68.80.249.239", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49205, "190.244.193.78", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49207, "173.28.84.203", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49208, "73.199.51.213", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49209, "66.81.47.199", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49211, "186.9.145.31", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49213, "68.193.144.105", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49214, "99.235.167.54", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49215, "126.119.135.45", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49218, "219.70.113.58", 48754), "TCPRetransmission"),
        (("192.168.138.163", 49220, "24.253.145.21", 48754), "TCPRetransmission"),
    ]


class TestSpuriousRetransmission(PcapTest):
    """Handles TCP Spurious Retransmission logic"""
    pcapfile = "2015-10-08-Nuclear-EK-example-2-traffic.pcap"

    def format(self, s, ts, p, sent, recv):
        return sent.uri

    expected_output = [
        "/",
        "/wp-content/themes/mostashfa/hover/css/style_common.css",
        "/wp-content/themes/mostashfa/js/animatescroll.js",
        "/url?sa=l&rct=k&q=&esrc=y&source=web&cd=6&ved=aXFtVVktOQV0AQlBUSQ0JT1F&url=https%3A%2F%2F5584e38742.com&MhKWJ=399940b556&JMCQIUt=95578e0&ZhmZl=bVU1&1Q5U=eTG1ZX&5z9YSX0=dW1R&Fuj1T2=cFQ",
        "/viewtopic?0cFYRYP=2b1af084f&Fg5Ot=aUE1BT0daBERSVU8KDUkFA&A3uQ=cSVU8HGwM&ZysTUyT=0a0f23070&CnhL8C=dDHQACGwcDAE8DAQEFAAIKAgABT1VeBg..&HK2yA=bk9QUlNVUltVVBt",
        "/certainly?XcahV=eB&WOmmu=82d5a31898&TRH=cEBSQQFBwcBBA0G&5htVN5B=aU1xdVk9GXQRAUFVODQ1NAQEKSVdWVVdTXV&Wcy=bJQHVBUSQAfBQEcBgUfAQ&B3zj=dBgNOAklUfX&ZkxS=9e82ca&L6p=fjQ0kD",
        "/wp-content/plugins/ultimate-gallery/ultimate.swf",
        "/main.htm",
        "/favicon.ico",
        "/including?5EMZF=bU1FQW1RTG1ZXTwYcAwcfAAMcBwcCTwI&CH7Vl=57dfb5e&GffCcya=42b973&Vjrh8k=cGAQECAgsF&CPBXbg=aUV1uVV9TRl1NR1sDRFZXT1FV&PhfPwgY=dAAVNCws.",
        "/harsh02.exe",
        "/amount?5funIuS=bV1JaUlQfUFVOABsHAR0BBRsD&MvLsp=884f265e&Nxjv3F=aU1xdVk9GXQRAUFVODQ1NBwJOV1JX&ENLUF=dFBwADDQIE&L22=cAQBOBAE&KU3=21c1d81d&WST12=eA08FSU9gVnFhZkkA",
        "/harsh02.exe",
        "/viewtopic?8U9Z=0d31950a&DS7a2p=bXVJQHVBUSQAfBQEcB&2R7v=74b6fb&M5d4SvQ=aUV1uWUBOQV0AQlBUSVdWVVdT&KSsYgDJ=cgUfAQEBSQQFBwcBBA0GBgNODQ0.",
        "/file.htm",
    ]


class TestIgmpAndHttp(PcapTest):
    """Handle IGMP packets and HTTP on port 80"""
    pcapfile = "2015-10-13-Neutrino-EK-traffic-second-run.pcap"

    def format(self, s, ts, p, sent, recv):
        return sent.method, sent.uri

    expected_output = (
            [("POST", "/forum/db.php")] * 3 +
            [("GET", "/domain/195.22.28.194")] * 2 +
            [("GET", "/")] +
            [("GET", "/domain/195.22.28.194")] +
            [("POST", "/forum/db.php")] +
            [("GET", "/view.js")] +
            [("POST", "/forum/db.php")] * 2
    )


class TestHttpNoDefaultPort(PcapTest):
    """Handle HTTP on non-default ports"""
    pcapfile = "2015-10-13-Neutrino-EK-traffic-second-run.pcap"

    handlers = {
        80: dummy_handler,
        "generic": http_handler,
    }

    def format(self, s, ts, p, sent, recv):
        return sent.method, sent.uri

    expected_output = [
        ("GET", "/bound/shout-32517633"),
        ("GET", "/snap/dHdmYmVpdXZs"),
        ("GET", "/full/a2hjY3hs"),
        ("GET", "/august/Z250anJ5dGRq"),
    ]


class TestCaptureNotAcked(PcapTest):
    """Extracts HTTP requests which are not acknowledged"""
    pcapfile = "2015-10-12-Angler-EK-sends-Bedep-traffic.pcap"

    handlers = {
        80: http_handler,
        443: dummy_handler,
    }

    def format(self, s, ts, p, sent, recv):
        if isinstance(recv, dpkt.http.Response):
            return hashlib.md5(recv.body).hexdigest()

    expected_output = [
        "f9a8489b5110b8b06a8e97453257075d", "5f473a890d750f1147dc0c7cc4668481",
        "3bd5799f7aa98f8a752a383cdf53f461", "65a65267a9d45cfd797bb4ade7534ca7",
        "0067b30547ff79e4417356eb02e46032", "72fd1899fdcd91e44c6c046775795d4d",
        "e4407e614445327e4edb836494cc4ef0", "cd9a2f577b63f7d9fd8d2bedcdd54bcd",
        "2c9e9b8a0e386e8db34827697160ec04", "1d67074ab1e6d3589da716a32fff6002",
        "0f3427e4788f146600121d1e64b7b00d", "a95fa6ffd78ab2a44ace57fa183b9d1f",
        None,
        "d41d8cd98f00b204e9800998ecf8427e", "eed8ec65a6dd9b05eed6d4a02e1439e4",
        "1d260bbdbdf8ae67145134958e5fd864", "d41d8cd98f00b204e9800998ecf8427e",
        "89205cebf4c75c8e70d896e3803c3fb8", "cbb2bbdd3458221e9b51a20763f751c0",
        "a7b807ebdb3843e2a3db757b5785792e", "28f06d78a5568dc4c2c9149682b67fa8",
        "d41d8cd98f00b204e9800998ecf8427e", "9220f37dceb71a516e01c5a9d2e8366d",
        "2098dedf3165609e56de26b8b0dc9661", "a6298fa74bc8e61f94859dc90757c839",
        "27eeac51fc7eb06a22372c0bb3e85950", "d41d8cd98f00b204e9800998ecf8427e",
        "d41d8cd98f00b204e9800998ecf8427e", "4971de24dd429af31e0359fbc5ca1460",
        "9bce0089598c20112cba73f37983da3e", "1520227cc1354cb144d30a50779ab95b",
        "d41d8cd98f00b204e9800998ecf8427e", "6593f3e7d45aca357b22be501d50ff01",
        "d41d8cd98f00b204e9800998ecf8427e", "2615820e5e0921ef0539f8651bf310a0",
        "d41d8cd98f00b204e9800998ecf8427e", "2eb071fbf1b8252932302e0946fad386",
        "95ce680d2cb92ee3380432ad361d5273", "0d621a81d3edbf9d58c76b01c37ed48b",
        "7008e1e1572f66b0fd30742e6ec4bb0f", "c3bef09a66c24455685e794e9b08b459",
        "719acc7111036d05908a2bbc2edb59cb", "63afa4cf1601f01c4751039f8bbfdab4",
        "d41d8cd98f00b204e9800998ecf8427e", "e59d25e237e5a3f3a6a06bd3faba7165",
        "f3856d13d9d3d951d2e1856661345cf5"
    ]


class TestCaptureNotAcked2(PcapTest):
    """Extracts HTTP requests which are not acknowledged"""
    pcapfile = "EK_MALWARE_2014-09-29-Nuclear-EK-traffic_mailware-traffic-analysis.net.pcap"

    def format(self, s, ts, p, sent, recv):
        # Only handle one particular stream.
        if s[1] != 49837 and s[3] != 49837:
            return
        if isinstance(recv, dpkt.http.Response):
            return hashlib.md5(recv.body).hexdigest()

    expected_output = (
            [None] * 114 +
            ["d41d8cd98f00b204e9800998ecf8427e"] +
            [None] * 33 +
            ["56398e76be6355ad5999b262208a17c9"] +
            [None] * 12 +
            ["07a37ca8f8898d5e1d8041ca37e8b399"] +
            ["56398e76be6355ad5999b262208a17c9"] +
            [None] * 2 +
            ["56398e76be6355ad5999b262208a17c9"] +
            [None] * 11 +
            ["d41d8cd98f00b204e9800998ecf8427e"] +
            [None] * 161 +
            ["56398e76be6355ad5999b262208a17c9"] +
            [None] * 40
    )


class TestWeirdRetransmission(PcapTest):
    """Packet 15 retransmits the tail of packet 11"""
    pcapfile = "2016-04-20-docker.pcap"

    handlers = {
        8080: http_handler
    }

    def format(self, s, ts, p, sent, recv):
        return getattr(sent, "uri", sent)

    expected_output = [
        "/jmx-console/",
        "/jmx-console/filterView.jsp",
        "/jmx-console/images/newlogo.gif",
        "/favicon.ico",
        "\x00\x00\x00\x00\x00"
    ]


class TestClientSideInvalidTcpPacketOrder(PcapTest):
    """Client side InvalidTcpPacketOrder exception."""
    pcapfile = "invalidtcppacketorder.pcap"

    handlers = {
        80: http_handler,
    }

    def format(self, s, ts, p, sent, recv):
        return len(sent.raw), len(recv.raw)

    expected_output = [
        (97, 179),
    ]


class TestTLSWithRC4(PcapTest):
    pcapfile = "stream11.pcap"

    def _https_handler(self):
        session_id = "5ab7c9537928268ba71cd5fc790b6accb29707cfa7b3f85347e432a439eb1b4b"
        master_key = "50321cf5552ba2f3ed34cd6eee005cf6490f5d915c7db8e2cfbf54940140308aa09c0a4e94107df6b25d2509f5bf0f13"
        return https_handler({
            session_id.decode("hex"): master_key.decode("hex"),
        })

    handlers = {
        443: _https_handler,
    }

    def format(self, s, ts, p, sent, recv):
        return getattr(sent, "uri", sent)

    expected_output = [
        "/iam.js",
    ]


class TestNoGzipBody(PcapTest):
    pcapfile = "nogzipbody.pcap"

    def _https_handler(self):
        session_id = "479ef8a88198b5b3f7e5b8bf79dea2d0635300ad744de08deb4e83610c5227e9"
        master_key = "25fba9ac38b8750ead7b9ba50aba06e12aa566ffa0c3fa24cbdaf638711b8458da84cd79e9b32f4025a858a5c106c7a5"
        return https_handler({
            session_id.decode("hex"): master_key.decode("hex"),
        })

    def format(self, s, ts, p, sent, recv):
        return getattr(sent, "uri", sent)

    handlers = {
        443: _https_handler,
    }

    expected_output = [
        "/js/ho/link_inline_images.min.js",
        "/fonts/source-sans-pro-subset/sourcesanspro-regular-webfont.eot?",
        "/fonts/gidole/gidole-regular-webfont.eot?",
    ]


class TestOddSMB(PcapTest):
    pcapfile = "invldord.pcap"
    expected_output = []


class TestNoTLSKeys(object):
    class DummyProtocol(object):
        def __init__(self):
            self.values = []

        def handle(self, s, ts, protocol, sent, recv, tlsinfo=None):
            self.values.append((s, ts, protocol, sent, recv))

    @mock.patch("httpreplay.cobweb.HttpProtocol.parse_request")
    def test_no_tls_keys(self, p):
        h = https_handler()
        h.parent.parent = dummy = self.DummyProtocol()
        h.handle((0, 0, 0, 0), 0, "tcp", "foo\r\n", "bar")

        p.assert_not_called()
        assert dummy.values == [
            ((0, 0, 0, 0), 0, "tcp", "foo\r\n", "bar"),
        ]


def test_read_chunked():
    def parse(content):
        try:
            headers = {"transfer-encoding": "chunked"}
            return parse_body(io.BytesIO(content), headers)
        except:
            return False

    assert parse(b"1\r\na\r\n0\r\n\r\n") == b"a"
    assert parse(b"\r\n\r\n1\r\na\r\n1\r\nb\r\n0\r\n\r\n") == b"ab"

    assert not parse(b"1\r\na\r\n0\r\n")
    assert not parse(b"\r\n")
    assert not parse(b"1\r\nfoo")
    assert not parse(b"foo\r\nfoo")


def test_init_reader():
    a = PcapReader("tests/pcaps/test.pcap")
    b = PcapReader(open("tests/pcaps/test.pcap", "rb"))
    assert list(a.pcap) == list(b.pcap)


try:
    import mitmproxy

    mitmproxy  # Fake usage.
except ImportError:
    pass
else:
    def test_do_pcap2mitm():
        filepath = tempfile.mktemp()
        do_pcap2mitm.callback(
            "tests/pcaps/2015-10-13-Neutrino-EK-traffic-second-run.pcap",
            open(filepath, "wb"), None, False
        )
        assert hashlib.md5(open(filepath, "rb").read()).hexdigest() == (
            "667ce4057bb6cfa0082df6ca1ba40a87"
        )


    def test_pcap2mitm():
        filepath = tempfile.mktemp()
        pcap2mitm(
            open("tests/pcaps/2015-10-13-Neutrino-EK-traffic-second-run.pcap", "rb"),
            open(filepath, "wb")
        )
        assert hashlib.md5(open(filepath, "rb").read()).hexdigest() == (
            "667ce4057bb6cfa0082df6ca1ba40a87"
        )


class TestTLSInfoJA3(PcapTest):
    """Handle HTTP on non-default ports"""
    pcapfile = "stream11.pcap"
    tlsinfo = True

    def _https_handler(self):
        session_id = "5ab7c9537928268ba71cd5fc790b6accb29707cfa7b3f85347e432a439eb1b4b"
        master_key = "50321cf5552ba2f3ed34cd6eee005cf6490f5d915c7db8e2cfbf54940140308aa09c0a4e94107df6b25d2509f5bf0f13"
        return https_handler({
            session_id.decode("hex"): master_key.decode("hex"),
        })

    handlers = {
        443: _https_handler
    }

    def format(self, s, ts, p, sent, recv, tlsinfo):
        print(tlsinfo.JA3, tlsinfo.JA3_params, tlsinfo.JA3S, tlsinfo.JA3S_params)
        return tlsinfo.JA3, tlsinfo.JA3_params, tlsinfo.JA3S, tlsinfo.JA3S_params

    expected_output = [
        ("2201d8e006f8f005a6b415f61e677532",
         "769,47-53-5-10-49171-49172-49161-49162-50-56-19-4,65281-0-5-10-11,23-24,0",
         "d2e6f7ef558ea8036c7e21b163b2d1af", "769,5,0-65281")
    ]


def test_patch_dpkt_ssl_tlshello():
    from httpreplay.misc import patch_dpkt_ssl_tlshello_unpacks
    patch_dpkt_ssl_tlshello_unpacks()
    assert getattr(dpkt.ssl, "parse_extensions")
    assert dpkt.ssl.TLSClientHello.__name__ == "_TLSClientHelloPatched"
    assert dpkt.ssl.TLSServerHello.__name__ == "_TLSServerHelloPatched"
