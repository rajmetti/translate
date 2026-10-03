import urllib.request
import pathlib
import time
import json

backend = 'http://127.0.0.1:8000'
p = max(pathlib.Path('book-translator/backend/data/uploads').glob('*.epub'), key=lambda x: x.stat().st_size)
print('uploading', p)
boundary = '----FormBoundary'
body = (
    b'------FormBoundary\r\n'
    b'Content-Disposition: form-data; name="file"; filename="' + p.name.encode() + b'"\r\n'
    b'Content-Type: application/epub+zip\r\n\r\n'
    + open(p, 'rb').read()
    + b'\r\n------FormBoundary--\r\n'
)
req = urllib.request.Request(
    backend + '/api/upload',
    data=body,
    headers={'Content-Type': 'multipart/form-data; boundary=----FormBoundary'},
)
job_id = json.loads(urllib.request.urlopen(req).read())['job_id']
print('job_id', job_id)

s = urllib.request.urlopen(backend + f'/api/structure/{job_id}')
print('structure', len(json.loads(s.read())['spine']))

body = urllib.parse.urlencode({
    'target_language': 'Telugu',
    'scope': 'range',
    'model': 'gpt',
    'output_format': 'epub',
    'page_start': 144,
    'page_end': 144,
    'mode': 'standard',
}).encode()
req = urllib.request.Request(
    backend + f'/api/translate/{job_id}',
    data=body,
    headers={'Content-Type': 'application/x-www-form-urlencoded'},
)
print('translate', json.loads(urllib.request.urlopen(req).read()))

for i in range(60):
    st = json.loads(urllib.request.urlopen(backend + f'/api/status/{job_id}').read())
    print(st['status'], st.get('progress'), st.get('message'))
    if st['status'] in ('done', 'error'):
        break
    time.sleep(2)

pv = urllib.request.urlopen(backend + f'/api/preview/{job_id}')
print('preview', pv.status, pv.read().decode()[:800])
