from pathlib import Path
import base64,json,mimetypes
root=Path(__file__).resolve().parents[1]
assets={}
for path in sorted((root/'dist').rglob('*')):
    parts=path.relative_to(root/'dist').parts
    if not path.is_file() or parts[0]=='server' or any(p.startswith('.') for p in parts):continue
    typ=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    assets['/'+'/'.join(parts)]=[typ,base64.b64encode(path.read_bytes()).decode()]
target=root/'dist/server/index.js'
target.parent.mkdir(exist_ok=True)
target.write_text('const ASSETS='+json.dumps(assets,separators=(',',':'))+';\n'+(root/'service/worker.mjs').read_text())
