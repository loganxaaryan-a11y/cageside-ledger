import re
import unicodedata

def fighter_key(name):
    ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    key = re.sub('[^a-z0-9]', '', ascii_name.lower())
    # UFC's jose-henrique athlete URL identifies José Souza. The odds and bio
    # feeds retain Henrique while the Macau fight sheet uses Souza.
    return 'josehenrique' if key == 'josesouza' else key
