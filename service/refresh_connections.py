"""Refresh validated provider connections using a Sites service token on stdin."""
import hashlib, json, sys, urllib.request
ORIGIN='https://cageside-ledger-logan.mad1mad2mad3.chatgpt.site'
token=sys.stdin.readline().strip()
if not token:raise SystemExit('Missing private Site service access')
proof=hashlib.sha256(('ledger-refresh-v1:'+token).encode()).hexdigest()
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None
req=urllib.request.Request(ORIGIN+'/api/refresh',data=b'',headers={'OAI-Sites-Authorization':'Bearer '+token,'X-Ledger-Proof':proof})
with urllib.request.build_opener(NoRedirect()).open(req,timeout=90) as r:
    result=json.load(r)
    if not isinstance(result,dict) or 'ufcalendar' not in result:raise SystemExit('Invalid provider refresh response')
    print(json.dumps(result))
