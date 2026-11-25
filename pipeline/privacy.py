"""Local redaction for text that may be sent to a labeler or exported."""
import re

from credential_rules import spans as credential_spans

PATTERNS = {
    'EMAIL': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
    'URL': r"""https?://[^\s<>\[\])"']+""",
    'PATH': r"""(?:/(?:Users|home)/|[A-Za-z]:\\Users\\)[^\s"'<>]+""",
    'IP': r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    'PHONE': r'(?<!\w)(?:\+\d{1,3}[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}(?!\w)',
}
LABELS = ['person','full_name','email','phone_number','address','date_of_birth',
          'government_id','passport_number','bank_account','payment_card','username',
          'account_id','password','secret','api_key','access_token','recovery_code']


def load_model(name):
    if not name or name.casefold() == 'none':
        raise ValueError('A local PII model is required for prompt labeling')
    from gliner2 import GLiNER2
    return GLiNER2.from_pretrained(name)


def redact(text, model=None):
    spans = [(s['start'],s['end'],'CREDENTIAL') for s in credential_spans(text)]
    for label, pattern in PATTERNS.items():
        spans.extend((m.start(),m.end(),label) for m in re.finditer(pattern,text))
    if model:
        for start in range(0,len(text),1100):
            chunk = text[start:start+1400]
            output = model.extract_entities(chunk,LABELS,threshold=.5,include_spans=True)
            for label, values in output.get('entities',{}).items():
                if label not in LABELS:
                    raise ValueError('Unknown PII label')
                for value in values:
                    a,b = value['start'],value['end']
                    if not 0 <= a < b <= len(chunk):
                        raise ValueError('PII model reported an invalid span')
                    spans.append((start+a,start+b,label.upper()))
    merged = []
    for a,b,label in sorted(spans,key=lambda item:(item[0],-item[1])):
        if merged and a < merged[-1][1]:
            begin,end,_ = merged[-1]
            merged[-1] = (begin,max(b,end),'REDACTED')
        else:
            merged.append((a,b,label))
    for a,b,label in reversed(merged):
        text = text[:a]+f'[{label}]'+text[b:]
    if credential_spans(text):
        return None
    return text
