"""Download the parts of the WCA results export that the rating needs.

The export is one ~380 MB zip regenerated daily. Its members are compressed independently and
the zip's central directory sits at the end of the file, so with HTTP Range requests we can read
the directory (a few KB) and then only the byte ranges of the members we use: ~130 MB instead of
~380 MB, because scrambles and result_attempts are never touched. See docs/architecture.md.
"""
from __future__ import annotations

import io
import json
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .config import EXPORT_MEMBERS, RAW_DIR, USER_AGENT, WCA_EXPORT_API


def _request(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def export_metadata() -> dict:
    """Small JSON (~1 KB) that says when the latest export was generated and where it lives."""
    with _request(WCA_EXPORT_API) as r:
        return json.load(r)


class HttpRangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP Range requests, with a read-ahead buffer.

    zipfile only needs seek/tell/read, so wrapping this in ZipFile lets us stream single
    members out of a remote archive.
    """

    def __init__(self, url, block=8 << 20):
        super().__init__()
        # resolve redirects once (the WCA URL 301s to a versioned file on S3)
        with _request(url, {"Range": "bytes=0-0"}) as r:
            self.url = r.geturl()
            self.size = int(r.headers["Content-Range"].split("/")[1])
        self.pos = 0
        self.block = block
        self.buf_start, self.buf = 0, b""
        self.bytes_fetched = 0
        self.limit = None  # optional end offset that read-ahead must not cross (end of current member)

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        else:
            self.pos = self.size + offset
        return self.pos

    def _fill(self, start, length):
        stop = self.size if self.limit is None or start >= self.limit else self.limit
        end = min(stop, start + max(length, self.block), self.size) - 1
        end = max(end, start + length - 1)
        for attempt in range(5):
            try:
                with _request(self.url, {"Range": f"bytes={start}-{end}"}, timeout=120) as r:
                    data = r.read()
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 or attempt == 4:  # rate limited: never hammer, let the next cron run retry
                    raise
                time.sleep(2 ** attempt)
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        self.bytes_fetched += len(data)
        self.buf_start, self.buf = start, data

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        off = self.pos - self.buf_start
        if not (0 <= off and off + n <= len(self.buf)):
            self._fill(self.pos, n)
            off = 0
        out = self.buf[off:off + n]
        self.pos += len(out)
        return out

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def fetch_export(dest: Path = RAW_DIR, members=EXPORT_MEMBERS, url=None, local_zip: Path | None = None) -> dict:
    """Extract the needed members of the export into dest. Returns the export metadata.

    local_zip: use an already downloaded archive instead of the network (development, tests).
    """
    dest.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if local_zip is not None:
        src = open(local_zip, "rb")
    else:
        url = url or export_metadata()["tsv_url"]
        src = HttpRangeFile(url)
    with src, zipfile.ZipFile(src) as zf:
        infos = sorted((zf.getinfo(m) for m in members), key=lambda i: i.header_offset)
        for info in infos:
            m = info.filename
            if hasattr(src, "limit"):  # local header (30 bytes + name + extra) + data
                src.limit = info.header_offset + 30 + len(m.encode()) + 1024 + info.compress_size
            tmp = dest / (m + ".part")
            with zf.open(m) as fin, open(tmp, "wb") as fout:
                shutil.copyfileobj(fin, fout, 4 << 20)
            tmp.replace(dest / m)
        fetched = getattr(src, "bytes_fetched", None)
        total = getattr(src, "size", None)
    meta = json.loads((dest / "metadata.json").read_text())
    meta["_fetch"] = {"seconds": round(time.time() - t0, 1), "bytes_fetched": fetched, "archive_bytes": total}
    (dest / "fetch.json").write_text(json.dumps(meta, indent=1))
    return meta
