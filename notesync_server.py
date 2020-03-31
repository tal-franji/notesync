#!/usr/bin/python
# File sync server/client
#  Used to allow editing files on your laptop in local repo and reflecting changes on cloud machine

# Note - there is a tool https://www.tecmint.com/file-synchronization-in-linux-using-unison/
__author__ = "tal.franji@gmail.com"

import argparse
import base64
import collections
import json
import os
import re
import http.server
import random
import sys
import time
import urllib.parse
import zlib

# HTML returned to be run inside the notebook as an iframe communicationg with http://localhost
iframe_html = """
<html>
<body style="background-color:#b5b5b5;">
<small>laptop found</small>
<script>
function key_vat_to_url(kv) {
  var parts = [];
  for(var key in kv)
     parts.push(key + "=" + encodeURIComponent(kv[key]));
  return parts.join("&");
}

function callServer(event) {
    const callAsync = async () => {
      //console.log("CHILD>>> callin url: " + '/note.json?' + key_vat_to_url(event.data))
      event.source.postMessage(j, event.origin);
      const response = fetch('/note.json?' + key_vat_to_url(event.data));
      var j = await response.then(function (res) {
		                return res.json(); //extract JSON from the http response
	                 }).catch(function (err) {
		                return {status: "error", message: "ERROR:NO CONNECTION"};
	                 });
      //console.log("CHILD>>> json from server:", j)
      event.source.postMessage(j, event.origin);
    };
    callAsync();
}

window.addEventListener("message", callServer, false);
</script>
</body>
</html>
"""
g_target_dir = "."

def get_this_file_mtime():
    return int(os.path.getmtime(__file__))

# file created locally to check if seen by notebook.
NOTESYNC_DUMMY_FILE = "_notesync.dummy"
# script uploaded to notebook machine and run there.
SERVER_SCRIPT = "notesync_target.py"

# State machine - when server starts talking to a notebook JavaScript code
# This server manages a state
# INI: Notebook/JavaScript reload
#  |--> LCL: (error) detected notebook is running on laptop
#  |--> UPS: Uploading the Notebook machine target_server python code
#        |--> WPY: waiting for python code that creates file to end
#              |--> SYN: (running) synchronize files from laptop to target
#
# For each state there is a dict of parameter retured to the JavaScript
# the "command" parameter is the python code to run. The output of
# this code is used by JavaScript as parameter to the next request to this server
# So the Python code written here "returns" the next state and other parameters
notebook_bootstrap_code ={
    "DBG": {"command": """
    print('{"foo": "boooo"}')
    """, "message": "DEBUG"},

    "INI": {"command": """
import base64
import json
import os
import sys
import zlib

def _zP(filename):
    return os.path.join("{tdir}", filename)
def _zE(filename):
    return os.path.exists(_zP(filename))
def _zJ(**kwargs):
    print(json.dumps(kwargs))
def _zMT(filename):
    return int(os.path.getmtime(_zP(filename))) if _zE(filename) else 0
def _zTimes(filenames):
    return {{f: _zMT(f) for f in filenames}}
def _zDC(datastr, compression):
    if compression == "repr":
        return datastr
    if compression == "zb64":
        return str(zlib.decompress(base64.decodebytes(bytes(datastr, "utf-8"))), "utf-8")
if _zE("{dummy}"):
    _zJ(state="LCL")
elif _zMT("{target}") < {mtime}:
    _zJ(state="UPS", action="forget")
else:
    _zJ(state="SYN")
""".format(dummy=NOTESYNC_DUMMY_FILE,
           target=SERVER_SCRIPT,
           mtime=get_this_file_mtime(),
           tdir=g_target_dir),
            },

    "LCL": {"message": "ERROR - notebook and laptop-server running on same machine/folder "},

    "SYN": {"message": "Sync"},
    "WPY": {"message": "Waiting for python"},
    "ERR": {"message": "Notesync error"},
}


def preprocess_source(src):
    # TODO(franji): remove lines not relevant to target machine
    # change default according to target notebook/cloud
    return src

def repr_for_upload(data):
    """Find python-code representation of data which is the shortest.
    return tuple(repr, size, compression_method)"""
    data_and_len = []
    def calc_data_len(r, algo):
        return (r, len(r), algo)
    data_and_len.append(calc_data_len(repr(data), "repr"))
    # TODO(franji): python 2 issues?
    bd = bytes(data, "utf-8")
    #data_and_len.append(calc_data_len(repr(base64.encodebytes(bd)), "b64"))
    #data_and_len.append(calc_data_len(repr(zlib.compress(bd)), "zlib"))
    data_and_len.append(calc_data_len(repr(str(base64.encodebytes(zlib.compress(bd)), "utf-8")), "zb64"))
    data_and_len.sort(key=lambda t: t[1])  # sort by len
    return data_and_len[0]


g_response_count = 0

class FileSyncHandler(http.server.BaseHTTPRequestHandler):
    """FileSyncHandler is created for each request. Uses FileLooper to track files state."""
    def __init__(self, *args, **kwargs):
        self.update_ts = 0
        self.looper = args[0]
        super().__init__(*args[1:], **kwargs)
        # TODO(franji): Read timestamp from file

    def parse_params(self):
        url_parts = urllib.parse.urlparse(self.path)
        qs = url_parts[4]
        params0 = urllib.parse.parse_qs(qs)
        params = {}
        for k,v in params0.items():
            params[k] = v[-1]
        return params

    def send_iframe(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(iframe_html.encode('utf-8'))


    def upload_file(self, filename, preprocess_func=None, dst_filename=None, files_check_mtime=[]):
        command = ""
        message = ""
        if files_check_mtime:
            message = "Checking " + files_check_mtime[0]
        if filename:
            message = "Updating " + filename
            # file may be None if only checking mtimes
            with open(filename) as src:
                source_data = src.read()
            if not source_data:
                self.send_json(status="error", message="ERROR reading source code", state="ERR")
            if preprocess_func:
                source_data = preprocess_func(source_data)
            if not dst_filename:
                dst_filename = filename
            r, n, comp = repr_for_upload(source_data)
            print("DEBUG>>> uploading '{}' using compression method {} to get {} bytes".format(filename, comp, n) )
            command = "SRC_CODE = "
            command += r
            command +=  "\nCOMP = {}\n".format(repr(comp))
            command += """with open("%s", "w+t") as f:
    f.write(_zDC(SRC_CODE, COMP))
""" % dst_filename
        # even if no file to upload - return file times
        command += """_zJ(state="SYN", mtimes=_zTimes(%s))\n""" % repr(files_check_mtime)

        return self.send_json(status="ok",
                              message=message,
                              state="WPY", # waiting for python to execute
                              command=command)

    def upload_server(self):
        # TODO(franji): do we need server at target or just us code from send as 'command'
        # currently sending server as the existance of the server file
        # on the target machine is the indication this a new/old machine
        self.upload_file(__file__, preprocess_source, SERVER_SCRIPT)


    def sync_files(self, py_response):
        # take response mtimes and update our state
        mtimes = py_response.get("mtimes", {})
        for f, mt in mtimes.items():
            self.looper.set_file_target_mtime(f, mt)
        files_to_check_target_mtime = []
        file_to_upload = None
        while len(files_to_check_target_mtime) < 10:
            filename, local_mtime, target_mtime = self.looper.next()
            if not filename:  # may be None because of frequency
                break
            files_to_check_target_mtime.append(filename)
            if not target_mtime or target_mtime < local_mtime:
                file_to_upload = filename
                break  # found a file to upload
        # We now have 0 or more files to check file-time
        # and 0 or 1 files to upload
        # we want to construct the Python code to do that
        self.upload_file(file_to_upload, files_check_mtime=files_to_check_target_mtime)


    def handle_note_javascript_call(self):
        params = self.parse_params()
        state = params.get("state", "")
        py_response = json.loads(params.get("py_response", "{}"))
        state = py_response.get("state", state)
        action = py_response.get("action")
        if action:
            self.action_from_target(action)
        if state == "UPS":
            return self.upload_server()
        if state == "SYN":
            return self.sync_files(py_response)
        if state in notebook_bootstrap_code:
            res = dict()
            res.update(notebook_bootstrap_code[state])
            res.update(status="ok", state=state)
            return self.send_json(**res)

        self.send_json(status="error", message="ERROR NOTESYNC state error", state="ERR")

    def send_json(self, **kwargs):
        global g_response_count
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        g_response_count += 1  # DEBUG
        kwargs["n_debug"] = g_response_count
        response = json.dumps(kwargs).encode('utf-8')
        print("DEBUG >>> response: ", response)
        self.wfile.write(response)

    def do_GET(self):
        params = self.parse_params()
        print("DEBUG >>> do_GET ", self.path, params)
        if self.path.startswith("/iframe.html"):
            return self.send_iframe()
        if self.path.startswith("/note.json"):
            return self.handle_note_javascript_call()
        self.send_json(status="error")

    def action_from_target(self, action):
        if action == "forget":
            self.looper.clear_files()



def start_sync_server(args):
    addr, port, root_dir = "", args.port, args.dir
    looper = FileLooper(root_dir, args.rex_include, args.rex_exclude)
    def ServerConstructorHelper(*args, **kwargs):
        return FileSyncHandler(*([looper] + list(args)), **kwargs)

    Handler = ServerConstructorHelper
    httpd = http.server.HTTPServer((addr, port), Handler)

    print("File Sync Server at port", port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def relative_path(root_dir, dirpath, f):
    full = os.path.join(dirpath, f)
    if not root_dir:
        return full
    if not full.startswith(root_dir):
        print("ERROR - bad path for root", full)
        return None
    full = full[len(root_dir):]
    if full.startswith("/"):
        return full[1:]
    return full


def IterRelativePath(root_dir):
    # generate all files in the directories under root_dir
    # generate names relative to root_dir
    for dirpath, _, filenames in os.walk(root_dir):
        for f in filenames:
            filename = relative_path(root_dir, dirpath, f)
            yield filename


def iter_merge_infinite_loop(iter_builder1, iter_builder2, filter=lambda f: True):
    it1 = iter_builder1()
    it2 = iter_builder2()
    while True:
        try:
            x = it1.__next__()
            if filter(x):
                yield x
        except (StopIteration, RuntimeError):
            it1 = iter_builder1()
        try:
            x = it2.__next__()
            if filter(x):
                yield x
        except (StopIteration, RuntimeError):
            it2 = iter_builder2()


FileAttr = collections.namedtuple('FileAttr', ['local_mtime', 'target_mtime'])


class FileLooper(object):
    def __init__(self, root_dir, include_regex=[r".*\.(py|java|xml)$"], exclude_regex=["^\.git/"]):
        self.pat_include = [re.compile(r) for r in include_regex] if include_regex else None
        self.pat_exclude = [re.compile(r) for r in exclude_regex] if exclude_regex else None
        self.files_attr = {}  # map filename -> FileAttr
        self.log_count = 0
        self.frequency = 1.0  # every 1 calls(second) give a new file
        self._root_dir = root_dir
        self.recently_changed = set()
        self.loop_iter = iter_merge_infinite_loop(lambda: IterRelativePath(self._root_dir),
                                                  lambda: iter(self.recently_changed),
                                                  lambda f: not self._skip_file(f))

    def _skip_file(self, filename):
        skip = True
        if self.pat_include:
            for r in self.pat_include:
                if r.match(filename):
                    skip = False
        if self.pat_exclude:
            for r in self.pat_exclude:
                if r.match(filename):
                    skip = True
        return skip

    def __next__(self):
        self.next()

    def next(self):
        r = random.randint(0,1000)
        if r > int(500 /self.frequency):
            return (None, 0, 0)  # no files to send
        filename = self.loop_iter.__next__()
        attr = self.files_attr.get(filename, FileAttr(0, 0))
        full = os.path.join(self._root_dir, filename)
        local_mtime = int(os.path.getmtime(full))
        updated = attr.local_mtime and attr.local_mtime < local_mtime
        if updated:
            self.recently_changed.add(filename)
            # if updated - accelerate
            self.frequency = max(self.frequency / 2.0, 0.1);
        else:
            self.frequency = min(self.frequency * 1.01, 50);
            # check if need to remove from recently changed
            if filename in self.recently_changed and time.time() - attr.local_mtime > 5 * 60:
                self.recently_changed.remove(filename)
        self.files_attr[filename] = attr._replace(local_mtime=local_mtime)
        return (filename, local_mtime, attr.target_mtime)


    def clear_files(self):
        self.files_attr = {}  # new target machine - forget target_mfile

    def set_file_target_mtime(self, filename, target_mtime):
        attr = self.files_attr.get(filename, FileAttr(0, 0))
        self.files_attr[filename] = attr._replace(target_mtime=target_mtime)


def main():
    parser = argparse.ArgumentParser(description='File Sync server')
    parser.add_argument('--port', type=int,
                    help='Port server listens to')
    parser.add_argument('--dir',
                    help='root directory from which to read (laptop)', default=".")
    parser.add_argument('--target-dir',
                    help='target root dir to which to write (notebook machine)', default=".")
    parser.add_argument('--rex_include',
                    help='regex of files to include in sync (can give several)',
                    default=[r".*\.(py|java|xml|scala)$"],
                    action='append')
    parser.add_argument('--rex_exclude',
                    help='regex of files to exclude from sync (can give several)',
                    default=[r"^\."],
                    action='append')

    args = parser.parse_args()
    with open(NOTESYNC_DUMMY_FILE, "w+t") as dummy:
        dummy.write("#Dummy file to check if Notesync running on same machine as Jupyter")
    start_sync_server(args)
    return 0


if __name__ == '__main__':
    sys.exit(main())